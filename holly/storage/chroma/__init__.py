"""ChromaDB storage package — ICD-034, ICD-043."""

from __future__ import annotations

from holly.storage.chroma.client import (
    COLLECTION_PREFIX,
    EMBEDDING_DIM,
    MAX_PENDING_REQUESTS,
    QUERY_N_RESULTS_DEFAULT,
    QUERY_TIMEOUT_S,
    UPSERT_TIMEOUT_S,
    AsyncChromaClientProto,
    AsyncChromaCollectionProto,
    ChromaBackend,
    CollectionClient,
    DocumentRecord,
    QueryResult,
    collection_name,
)

__all__ = [
    "COLLECTION_PREFIX",
    "EMBEDDING_DIM",
    "MAX_PENDING_REQUESTS",
    "QUERY_N_RESULTS_DEFAULT",
    "QUERY_TIMEOUT_S",
    "UPSERT_TIMEOUT_S",
    "AsyncChromaClientProto",
    "AsyncChromaCollectionProto",
    "ChromaBackend",
    "CollectionClient",
    "DocumentRecord",
    "QueryResult",
    "collection_name",
]
