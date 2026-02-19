"""ChromaDB client layer for Holly Grace storage.

Implements tenant-scoped ChromaDB operations per ICDs:
  ICD-034: Core ↔ ChromaDB (long-term memory, semantic search)
  ICD-043: Memory System ↔ ChromaDB (long-term vectors for semantic search)

Collection naming: memory_{tenant_id} — one collection per tenant, no cross-tenant
document visibility. Tenant isolation is architecturally enforced: CollectionClient
instances are bound to a single tenant_id and can only reach that tenant's collection.

All components use Protocol-based interfaces for mock-testability without a live
ChromaDB instance. Production use requires a chromadb AsyncHttpClient.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from typing import Any
    from uuid import UUID

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants (per ICD-034 / ICD-043)
# ---------------------------------------------------------------------------

COLLECTION_PREFIX: str = "memory"
"""Collection name prefix for tenant-scoped ChromaDB collections (ICD-034/043)."""

EMBEDDING_DIM: int = 1_536
"""Expected embedding vector dimension: text-embedding-3-small (ICD-034: vec[1536])."""

MAX_PENDING_REQUESTS: int = 1_000
"""Backpressure limit: max pending requests per tenant (ICD-034)."""

QUERY_N_RESULTS_DEFAULT: int = 10
"""Default top-k for semantic search queries (ICD-034)."""

UPSERT_TIMEOUT_S: float = 0.5
"""Target p99 upsert latency (ICD-034: p99 < 500ms)."""

QUERY_TIMEOUT_S: float = 1.0
"""Target p99 query latency (ICD-034: p99 < 1s)."""


# ---------------------------------------------------------------------------
# Key helper
# ---------------------------------------------------------------------------


def collection_name(tenant_id: UUID) -> str:
    """Return the tenant-scoped ChromaDB collection name: memory_{tenant_id}.

    ICD-034: collection name includes tenant_id for isolation.
    Two different tenant_ids always produce different collection names.

    >>> from uuid import UUID
    >>> t = UUID("00000000-0000-0000-0000-000000000001")
    >>> collection_name(t)
    'memory_00000000-0000-0000-0000-000000000001'
    """
    return f"{COLLECTION_PREFIX}_{tenant_id}"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class DocumentRecord:
    """Single document to upsert into a ChromaDB collection (ICD-034/043).

    id:
        Stable document identifier (msg_id for ICD-034, memory_id for ICD-043).
        Upsert by id is idempotent — same id upserted twice replaces the entry.

    embedding:
        Float vector of exactly EMBEDDING_DIM dimensions (1536 for
        text-embedding-3-small). Caller is responsible for generating embeddings.

    metadata:
        Key-value dict stored alongside the document. ICD-034 schema:
          {user_id, timestamp (epoch int), source}
        ICD-043 schema:
          {conversation_id, agent_id, memory_type, timestamp (epoch int)}

    document:
        Raw text content. Caller must pre-redact per ICD-034 redaction clause
        (documents assumed redacted before upsert).
    """

    id: str
    embedding: list[float]
    metadata: dict[str, Any]
    document: str


@dataclass(slots=True)
class QueryResult:
    """Result of a ChromaDB semantic search query (ICD-034/043).

    Fields mirror the raw chromadb query response keys.  Each inner list
    corresponds to one query_embedding (we always send exactly one).

    On QueryError (malformed query or collection error), all fields contain
    [[]] — empty inner list — per ICD-034 fail-safe error contract.
    """

    ids: list[list[str]]
    distances: list[list[float]]
    metadatas: list[list[dict[str, Any]]]
    documents: list[list[str]]

    @property
    def top_ids(self) -> list[str]:
        """Convenience: flat list of IDs from the first (and only) query result."""
        return self.ids[0] if self.ids else []

    @property
    def top_documents(self) -> list[str]:
        """Convenience: flat list of document texts from the first query result."""
        return self.documents[0] if self.documents else []

    @property
    def top_metadatas(self) -> list[dict[str, Any]]:
        """Convenience: flat list of metadata dicts from the first query result."""
        return self.metadatas[0] if self.metadatas else []


# ---------------------------------------------------------------------------
# Protocol interfaces
# ---------------------------------------------------------------------------


@runtime_checkable
class AsyncChromaCollectionProto(Protocol):
    """Protocol for an async ChromaDB collection (HTTP REST or gRPC, ICD-034)."""

    async def upsert(
        self,
        ids: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]],
        documents: list[str],
    ) -> None:
        """Upsert documents — idempotent by id (ICD-034: DuplicateDocument → replace)."""
        ...

    async def query(
        self,
        query_embeddings: list[list[float]],
        n_results: int,
        where: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Semantic search — return top-n_results by cosine distance."""
        ...

    async def delete(
        self,
        ids: list[str] | None = None,
        where: dict[str, Any] | None = None,
    ) -> None:
        """Delete documents by id list or metadata filter (ICD-034: delete old >30d)."""
        ...

    async def get(
        self,
        where: dict[str, Any] | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Retrieve documents optionally filtered by metadata predicate."""
        ...


@runtime_checkable
class AsyncChromaClientProto(Protocol):
    """Protocol for an async ChromaDB client (ICD-034: HTTP REST or gRPC)."""

    async def get_or_create_collection(
        self, name: str
    ) -> AsyncChromaCollectionProto:
        """Return existing collection or create it (auto-create on first use, ICD-034)."""
        ...


# ---------------------------------------------------------------------------
# Tenant-scoped collection client
# ---------------------------------------------------------------------------


@dataclass
class CollectionClient:
    """Tenant-scoped ChromaDB client (ICD-034/043).

    All operations are scoped to a single tenant's collection
    (memory_{tenant_id}).  Cross-tenant document visibility is architecturally
    impossible: a CollectionClient is bound to exactly one tenant_id and always
    calls get_or_create_collection with that tenant's collection name.

    ICD-034/043 acceptance criterion: queries return only same-tenant results.
    """

    _client: AsyncChromaClientProto
    _tenant_id: UUID

    @property
    def tenant_id(self) -> UUID:
        """The tenant this client is scoped to."""
        return self._tenant_id

    @property
    def target_collection_name(self) -> str:
        """The ChromaDB collection name for this tenant (memory_{tenant_id})."""
        return collection_name(self._tenant_id)

    async def _get_collection(self) -> AsyncChromaCollectionProto:
        """Auto-create-or-get this tenant's ChromaDB collection.

        ICD-034 error contract: CollectionNotFound → auto-create on first use.
        """
        return await self._client.get_or_create_collection(
            self.target_collection_name
        )

    async def upsert(self, docs: list[DocumentRecord]) -> None:
        """Upsert documents into this tenant's collection.

        Idempotent by doc.id — same id upserted twice replaces the prior entry
        (ICD-034: DuplicateDocumentError → update instead of insert).  Caller
        must pre-redact document text per ICD-034 redaction clause.
        """
        if not docs:
            return
        coll = await self._get_collection()
        await coll.upsert(
            ids=[d.id for d in docs],
            embeddings=[d.embedding for d in docs],
            metadatas=[d.metadata for d in docs],
            documents=[d.document for d in docs],
        )

    async def query(
        self,
        query_embedding: list[float],
        n_results: int = QUERY_N_RESULTS_DEFAULT,
        where: dict[str, Any] | None = None,
    ) -> QueryResult:
        """Semantic search across this tenant's collection only.

        Returns top-n_results documents ordered by cosine distance.
        On QueryError (malformed query), returns empty QueryResult (fail-safe,
        ICD-034). Cross-tenant leakage is impossible: only this tenant's
        collection is queried.
        """
        coll = await self._get_collection()
        try:
            kwargs: dict[str, Any] = {
                "query_embeddings": [query_embedding],
                "n_results": n_results,
            }
            if where is not None:
                kwargs["where"] = where
            raw: dict[str, Any] = await coll.query(**kwargs)
            return QueryResult(
                ids=raw.get("ids", [[]]),
                distances=raw.get("distances", [[]]),
                metadatas=raw.get("metadatas", [[]]),
                documents=raw.get("documents", [[]]),
            )
        except Exception:  # ICD-034: QueryError → fail-safe → return empty
            log.warning(
                "chroma.query failed for tenant=%s; returning empty result (fail-safe)",
                self._tenant_id,
            )
            return QueryResult(ids=[[]], distances=[[]], metadatas=[[]], documents=[[]])

    async def delete_by_ids(self, ids: list[str]) -> None:
        """Delete documents by explicit ID list from this tenant's collection."""
        if not ids:
            return
        coll = await self._get_collection()
        await coll.delete(ids=ids)

    async def delete_older_than(self, cutoff_timestamp: int) -> int:
        """Delete documents whose metadata.timestamp < cutoff_timestamp.

        ICD-034: delete old messages >30d. Uses a metadata filter to find
        expired documents, then deletes them by ID.

        Returns:
            Number of documents deleted.
        """
        coll = await self._get_collection()
        result: dict[str, Any] = await coll.get(
            where={"timestamp": {"$lt": cutoff_timestamp}}
        )
        expired_ids: list[str] = result.get("ids", [])
        if expired_ids:
            await coll.delete(ids=expired_ids)
        return len(expired_ids)


# ---------------------------------------------------------------------------
# Backend facade
# ---------------------------------------------------------------------------


@dataclass
class ChromaBackend:
    """Tenant-aware ChromaDB backend facade (ICD-034/043).

    Factory: ChromaBackend.from_client(client) wraps an async ChromaDB client.
    Use collection_for(tenant_id) to obtain a tenant-scoped CollectionClient.

    Each CollectionClient returned is a new instance bound to the given tenant_id.
    The underlying _client is shared across all tenants (connection pooling).
    """

    _client: AsyncChromaClientProto

    def collection_for(self, tenant_id: UUID) -> CollectionClient:
        """Return a tenant-scoped CollectionClient.

        Tenant isolation guaranteed by collection_name(tenant_id): two different
        tenant_ids produce different ChromaDB collection names.
        """
        return CollectionClient(_client=self._client, _tenant_id=tenant_id)

    @classmethod
    def from_client(cls, client: AsyncChromaClientProto) -> ChromaBackend:
        """Construct ChromaBackend from an async ChromaDB client."""
        return cls(_client=client)
