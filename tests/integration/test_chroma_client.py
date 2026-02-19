"""Integration tests for holly.storage.chroma.client.

Covers Task 25.3 acceptance criteria (ICD-034/ICD-043):

  AC1:  collection_name produces "memory_{tenant_id}" pattern
  AC2:  Two different tenant_ids produce different collection names
  AC3:  CollectionClient.target_collection_name matches collection_name()
  AC4:  upsert calls collection.upsert with correct ids/embeddings/metadatas/documents
  AC5:  upsert is idempotent — same id can be upserted twice (both calls succeed)
  AC6:  upsert with empty list does not call collection.upsert
  AC7:  query calls collection.query with [query_embedding] and n_results
  AC8:  query returns only same-tenant results (CollectionClient scoped to one collection)
  AC9:  query returns empty QueryResult on exception (fail-safe, ICD-034)
  AC10: query where filter is forwarded when provided
  AC11: delete_by_ids calls collection.delete with correct ids
  AC12: delete_by_ids is a no-op for empty list
  AC13: delete_older_than calls collection.get with timestamp filter, then deletes returned ids
  AC14: delete_older_than returns count of deleted documents
  AC15: ChromaBackend.from_client wires all components
  AC16: collection_for(tenant_id_a) and collection_for(tenant_id_b) are different CollectionClients
  Hypothesis: collection_name always contains tenant_id string representation
  Hypothesis: different UUIDs always produce different collection names
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from holly.storage.chroma import (
    COLLECTION_PREFIX,
    EMBEDDING_DIM,
    AsyncChromaClientProto,
    ChromaBackend,
    CollectionClient,
    DocumentRecord,
    QueryResult,
    collection_name,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TENANT_A = UUID("aaaaaaaa-0000-0000-0000-000000000001")
_TENANT_B = UUID("bbbbbbbb-0000-0000-0000-000000000002")
_EMB = [0.1] * EMBEDDING_DIM


def _run(coro: Any) -> Any:
    return asyncio.get_event_loop().run_until_complete(coro)


def _make_collection(
    *,
    upsert_result: Any = None,
    query_result: dict[str, Any] | None = None,
    delete_result: Any = None,
    get_result: dict[str, Any] | None = None,
) -> AsyncMock:
    """Return an AsyncMock that satisfies AsyncChromaCollectionProto."""
    coll = AsyncMock()
    coll.upsert.return_value = upsert_result
    coll.query.return_value = query_result or {
        "ids": [["id1"]],
        "distances": [[0.1]],
        "metadatas": [[{"timestamp": 9999}]],
        "documents": [["hello"]],
    }
    coll.delete.return_value = delete_result
    coll.get.return_value = get_result or {"ids": [], "documents": [], "metadatas": []}
    return coll


def _make_client(coll: AsyncMock | None = None) -> AsyncMock:
    """Return an AsyncMock satisfying AsyncChromaClientProto."""
    client: AsyncMock = AsyncMock(spec=AsyncChromaClientProto)
    if coll is None:
        coll = _make_collection()
    client.get_or_create_collection.return_value = coll
    return client


def _make_doc(doc_id: str = "doc-1", text: str = "hello world") -> DocumentRecord:
    return DocumentRecord(
        id=doc_id,
        embedding=_EMB,
        metadata={"timestamp": 1_000_000, "source": "test"},
        document=text,
    )


# ---------------------------------------------------------------------------
# AC1-AC3: collection_name and scoping
# ---------------------------------------------------------------------------


class TestCollectionNaming:
    def test_collection_name_prefix(self) -> None:
        """AC1: collection_name starts with COLLECTION_PREFIX."""
        name = collection_name(_TENANT_A)
        assert name.startswith(COLLECTION_PREFIX + "_")

    def test_collection_name_contains_tenant_id(self) -> None:
        """AC1: collection_name contains string form of tenant_id."""
        name = collection_name(_TENANT_A)
        assert str(_TENANT_A) in name

    def test_collection_name_pattern(self) -> None:
        """AC1: exact pattern memory_{tenant_id}."""
        name = collection_name(_TENANT_A)
        assert name == f"memory_{_TENANT_A}"

    def test_different_tenants_different_names(self) -> None:
        """AC2: two different tenant_ids → different collection names."""
        assert collection_name(_TENANT_A) != collection_name(_TENANT_B)

    def test_same_tenant_deterministic(self) -> None:
        """AC2: same tenant_id always produces same collection name."""
        assert collection_name(_TENANT_A) == collection_name(_TENANT_A)

    def test_collection_client_target_name_matches_helper(self) -> None:
        """AC3: CollectionClient.target_collection_name matches collection_name()."""
        client = _make_client()
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        assert cc.target_collection_name == collection_name(_TENANT_A)

    def test_collection_client_tenant_id_property(self) -> None:
        """AC3: CollectionClient.tenant_id returns the bound tenant_id."""
        client = _make_client()
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        assert cc.tenant_id == _TENANT_A


# ---------------------------------------------------------------------------
# AC4-AC6: upsert
# ---------------------------------------------------------------------------


class TestUpsert:
    def test_upsert_calls_collection_upsert(self) -> None:
        """AC4: upsert calls collection.upsert with correct lists."""
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        doc = _make_doc("id-42", "some text")
        _run(cc.upsert([doc]))
        coll.upsert.assert_called_once_with(
            ids=["id-42"],
            embeddings=[_EMB],
            metadatas=[{"timestamp": 1_000_000, "source": "test"}],
            documents=["some text"],
        )

    def test_upsert_multiple_docs(self) -> None:
        """AC4: upsert passes all docs in one call."""
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        docs = [_make_doc(f"id-{i}", f"text {i}") for i in range(3)]
        _run(cc.upsert(docs))
        _args, _kwargs = coll.upsert.call_args
        assert _kwargs["ids"] == ["id-0", "id-1", "id-2"]
        assert len(_kwargs["embeddings"]) == 3

    def test_upsert_idempotent_same_id(self) -> None:
        """AC5: upsert with same id twice — both calls succeed without error."""
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        doc = _make_doc("stable-id")
        _run(cc.upsert([doc]))
        _run(cc.upsert([doc]))
        assert coll.upsert.call_count == 2

    def test_upsert_empty_list_no_call(self) -> None:
        """AC6: upsert([]) does not call collection.upsert."""
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        _run(cc.upsert([]))
        coll.upsert.assert_not_called()

    def test_upsert_uses_get_or_create_collection(self) -> None:
        """AC4: upsert retrieves collection via get_or_create_collection."""
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        _run(cc.upsert([_make_doc()]))
        client.get_or_create_collection.assert_called_once_with(
            collection_name(_TENANT_A)
        )


# ---------------------------------------------------------------------------
# AC7-AC10: query
# ---------------------------------------------------------------------------


class TestQuery:
    def test_query_passes_embedding_and_n_results(self) -> None:
        """AC7: query wraps embedding in a list and passes n_results."""
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        _run(cc.query(_EMB, n_results=5))
        coll.query.assert_called_once()
        _, kwargs = coll.query.call_args
        assert kwargs["query_embeddings"] == [_EMB]
        assert kwargs["n_results"] == 5

    def test_query_returns_query_result(self) -> None:
        """AC7: query returns a QueryResult with ids/distances/metadatas/documents."""
        coll = _make_collection(
            query_result={
                "ids": [["doc-1", "doc-2"]],
                "distances": [[0.05, 0.12]],
                "metadatas": [[{"source": "a"}, {"source": "b"}]],
                "documents": [["text a", "text b"]],
            }
        )
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        result = _run(cc.query(_EMB))
        assert isinstance(result, QueryResult)
        assert result.ids == [["doc-1", "doc-2"]]
        assert result.top_ids == ["doc-1", "doc-2"]

    def test_query_uses_same_tenant_collection(self) -> None:
        """AC8: query only calls get_or_create_collection with THIS tenant's name."""
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        _run(cc.query(_EMB))
        client.get_or_create_collection.assert_called_once_with(
            collection_name(_TENANT_A)
        )

    def test_query_fail_safe_on_exception(self) -> None:
        """AC9: query returns empty QueryResult when collection.query raises."""
        coll = _make_collection()
        coll.query.side_effect = RuntimeError("chroma unavailable")
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        result = _run(cc.query(_EMB))
        assert isinstance(result, QueryResult)
        assert result.ids == [[]]
        assert result.distances == [[]]
        assert result.top_ids == []
        assert result.top_documents == []

    def test_query_fail_safe_on_value_error(self) -> None:
        """AC9: fail-safe also catches ValueError (malformed query)."""
        coll = _make_collection()
        coll.query.side_effect = ValueError("malformed")
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        result = _run(cc.query(_EMB))
        assert result.top_ids == []

    def test_query_where_filter_forwarded(self) -> None:
        """AC10: where filter is passed to collection.query when provided."""
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        where = {"memory_type": {"$eq": "fact"}}
        _run(cc.query(_EMB, where=where))
        _, kwargs = coll.query.call_args
        assert kwargs.get("where") == where

    def test_query_no_where_when_none(self) -> None:
        """AC10: where is NOT passed when not provided."""
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        _run(cc.query(_EMB))
        _, kwargs = coll.query.call_args
        assert "where" not in kwargs

    def test_query_default_n_results(self) -> None:
        """AC7: default n_results is QUERY_N_RESULTS_DEFAULT (10)."""
        from holly.storage.chroma import QUERY_N_RESULTS_DEFAULT
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        _run(cc.query(_EMB))
        _, kwargs = coll.query.call_args
        assert kwargs["n_results"] == QUERY_N_RESULTS_DEFAULT


# ---------------------------------------------------------------------------
# AC11-AC14: delete
# ---------------------------------------------------------------------------


class TestDeleteByIds:
    def test_delete_by_ids_calls_collection_delete(self) -> None:
        """AC11: delete_by_ids calls collection.delete with correct ids."""
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        _run(cc.delete_by_ids(["id-1", "id-2"]))
        coll.delete.assert_called_once_with(ids=["id-1", "id-2"])

    def test_delete_by_ids_empty_list_no_call(self) -> None:
        """AC12: delete_by_ids([]) does not call collection.delete."""
        coll = _make_collection()
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        _run(cc.delete_by_ids([]))
        coll.delete.assert_not_called()


class TestDeleteOlderThan:
    def test_delete_older_than_calls_get_with_timestamp_filter(self) -> None:
        """AC13: delete_older_than calls get with $lt timestamp filter."""
        coll = _make_collection(get_result={"ids": ["old-1", "old-2"]})
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        _run(cc.delete_older_than(1_000_000))
        coll.get.assert_called_once_with(
            where={"timestamp": {"$lt": 1_000_000}}
        )

    def test_delete_older_than_deletes_returned_ids(self) -> None:
        """AC13: delete_older_than deletes the ids returned by get."""
        coll = _make_collection(get_result={"ids": ["old-1", "old-2"]})
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        _run(cc.delete_older_than(1_000_000))
        coll.delete.assert_called_once_with(ids=["old-1", "old-2"])

    def test_delete_older_than_returns_count(self) -> None:
        """AC14: delete_older_than returns count of deleted documents."""
        coll = _make_collection(get_result={"ids": ["x", "y", "z"]})
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        count = _run(cc.delete_older_than(1_000_000))
        assert count == 3

    def test_delete_older_than_zero_when_none_found(self) -> None:
        """AC14: delete_older_than returns 0 when no expired documents found."""
        coll = _make_collection(get_result={"ids": []})
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        count = _run(cc.delete_older_than(1_000_000))
        assert count == 0
        coll.delete.assert_not_called()

    def test_delete_older_than_no_delete_when_empty(self) -> None:
        """AC13: collection.delete is NOT called when get returns empty ids."""
        coll = _make_collection(get_result={"ids": []})
        client = _make_client(coll)
        cc = CollectionClient(_client=client, _tenant_id=_TENANT_A)
        _run(cc.delete_older_than(999))
        coll.delete.assert_not_called()


# ---------------------------------------------------------------------------
# AC15-AC16: ChromaBackend
# ---------------------------------------------------------------------------


class TestChromaBackendFactory:
    def test_from_client_returns_chroma_backend(self) -> None:
        """AC15: from_client() returns a ChromaBackend."""
        client = _make_client()
        backend = ChromaBackend.from_client(client)
        assert isinstance(backend, ChromaBackend)

    def test_collection_for_returns_collection_client(self) -> None:
        """AC15: collection_for() returns a CollectionClient."""
        client = _make_client()
        backend = ChromaBackend.from_client(client)
        cc = backend.collection_for(_TENANT_A)
        assert isinstance(cc, CollectionClient)

    def test_collection_for_binds_correct_tenant(self) -> None:
        """AC15: CollectionClient from collection_for has the correct tenant_id."""
        client = _make_client()
        backend = ChromaBackend.from_client(client)
        cc = backend.collection_for(_TENANT_A)
        assert cc.tenant_id == _TENANT_A

    def test_different_tenants_get_different_clients(self) -> None:
        """AC16: collection_for(A) and collection_for(B) are different instances."""
        client = _make_client()
        backend = ChromaBackend.from_client(client)
        cc_a = backend.collection_for(_TENANT_A)
        cc_b = backend.collection_for(_TENANT_B)
        assert cc_a is not cc_b
        assert cc_a.target_collection_name != cc_b.target_collection_name

    def test_tenant_isolation_collection_names_differ(self) -> None:
        """AC16: two tenants get different ChromaDB collection names (isolation)."""
        client = _make_client()
        backend = ChromaBackend.from_client(client)
        cc_a = backend.collection_for(_TENANT_A)
        cc_b = backend.collection_for(_TENANT_B)
        assert cc_a.target_collection_name == f"memory_{_TENANT_A}"
        assert cc_b.target_collection_name == f"memory_{_TENANT_B}"

    def test_backend_shares_underlying_client(self) -> None:
        """AC15: all CollectionClient instances share the same underlying client."""
        client = _make_client()
        backend = ChromaBackend.from_client(client)
        cc_a = backend.collection_for(_TENANT_A)
        cc_b = backend.collection_for(_TENANT_B)
        # Both clients hold a reference to the same chromadb async client
        assert cc_a._client is cc_b._client


# ---------------------------------------------------------------------------
# DocumentRecord + QueryResult helpers
# ---------------------------------------------------------------------------


class TestDocumentRecord:
    def test_immutable_frozen(self) -> None:
        """DocumentRecord is frozen (immutable)."""
        doc = _make_doc()
        with pytest.raises((AttributeError, TypeError)):
            doc.id = "new-id"  # type: ignore[misc]

    def test_fields_accessible(self) -> None:
        """DocumentRecord fields match constructor args."""
        doc = _make_doc("test-id", "hello")
        assert doc.id == "test-id"
        assert doc.document == "hello"
        assert doc.embedding == _EMB


class TestQueryResultHelpers:
    def test_top_ids_extracts_first_list(self) -> None:
        qr = QueryResult(
            ids=[["a", "b"]],
            distances=[[0.1, 0.2]],
            metadatas=[[{}, {}]],
            documents=[["x", "y"]],
        )
        assert qr.top_ids == ["a", "b"]

    def test_top_documents_extracts_first_list(self) -> None:
        qr = QueryResult(
            ids=[["a"]],
            distances=[[0.1]],
            metadatas=[[{}]],
            documents=[["the doc"]],
        )
        assert qr.top_documents == ["the doc"]

    def test_top_metadatas_extracts_first_list(self) -> None:
        qr = QueryResult(
            ids=[["a"]],
            distances=[[0.1]],
            metadatas=[[{"k": "v"}]],
            documents=[["doc"]],
        )
        assert qr.top_metadatas == [{"k": "v"}]

    def test_top_ids_empty_on_empty_ids(self) -> None:
        qr = QueryResult(ids=[], distances=[], metadatas=[], documents=[])
        assert qr.top_ids == []


# ---------------------------------------------------------------------------
# Hypothesis properties
# ---------------------------------------------------------------------------


class TestHypothesisProperties:
    @given(st.uuids())
    @settings(max_examples=50)
    def test_collection_name_contains_tenant_id(self, tenant_id: UUID) -> None:
        """collection_name always contains the string form of tenant_id."""
        name = collection_name(tenant_id)
        assert str(tenant_id) in name

    @given(st.uuids(), st.uuids())
    @settings(max_examples=50)
    def test_different_uuids_produce_different_names(
        self, t1: UUID, t2: UUID
    ) -> None:
        """Different UUIDs always produce different collection names."""
        if t1 != t2:
            assert collection_name(t1) != collection_name(t2)

    @given(st.uuids())
    @settings(max_examples=50)
    def test_collection_name_starts_with_prefix(self, tenant_id: UUID) -> None:
        """collection_name always starts with COLLECTION_PREFIX + '_'."""
        name = collection_name(tenant_id)
        assert name.startswith(f"{COLLECTION_PREFIX}_")
