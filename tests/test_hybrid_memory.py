"""Tests for hybrid memory (BM25 + Vector merge) — Phase 18b.

Tests:
- BM25Index building, searching, and staleness detection
- Query sanitization (SQL keywords, BM25 operators)
- Score normalization and merge formula
- Fallback to vector-only when BM25 unavailable
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from src.memory.hybrid import (
    BM25Index,
    HybridResult,
    _merge_results,
    _tokenize,
    _vector_only_results,
    get_index,
    hybrid_search,
    sanitize_query,
)


class TestTokenizer:
    """_tokenize should produce clean tokens for BM25."""

    def test_basic_tokenization(self):
        tokens = _tokenize("Hello World")
        assert tokens == ["hello", "world"]

    def test_removes_punctuation(self):
        tokens = _tokenize("order #12345, status: shipped!")
        assert "order" in tokens
        assert "12345" in tokens
        assert "status" in tokens
        assert "shipped" in tokens

    def test_filters_short_tokens(self):
        tokens = _tokenize("I am a big cat")
        assert "i" not in tokens  # 1 char filtered
        assert "am" in tokens  # 2 chars kept
        assert "big" in tokens
        assert "cat" in tokens

    def test_lowercasing(self):
        tokens = _tokenize("Liberty Forge Classic Tee")
        assert all(t == t.lower() for t in tokens)

    def test_empty_string(self):
        assert _tokenize("") == []


class TestQuerySanitization:
    """sanitize_query should strip unsafe patterns."""

    def test_removes_sql_keywords(self):
        result = sanitize_query("SELECT * FROM orders UNION DROP TABLE")
        assert "SELECT" not in result
        assert "UNION" not in result
        assert "DROP" not in result

    def test_removes_bm25_operators(self):
        result = sanitize_query('+"exact match" -exclude ~fuzzy')
        assert "+" not in result
        assert "-" not in result
        assert "~" not in result
        assert '"' not in result

    def test_preserves_normal_text(self):
        result = sanitize_query("order 12345 revenue Classic Tee")
        assert "order" in result
        assert "12345" in result
        assert "revenue" in result
        assert "Classic" in result

    def test_caps_length(self):
        long_query = "a " * 600
        result = sanitize_query(long_query)
        assert len(result) <= 1000

    def test_empty_after_sanitization(self):
        result = sanitize_query("SELECT DROP DELETE")
        assert result.strip() == ""

    def test_collapses_whitespace(self):
        result = sanitize_query("hello    world")
        assert result == "hello world"


class TestBM25Index:
    """BM25Index should build, search, and track staleness."""

    def test_build_empty(self):
        idx = BM25Index(collection_name="test")
        idx.build([], [], [])
        assert idx.document_count == 0
        assert idx.bm25 is None

    def test_build_and_search(self):
        idx = BM25Index(collection_name="test")
        docs = [
            "Liberty Forge Classic Tee is our best seller",
            "We The People Patriot Tee is new",
            "Revenue report for January 2026",
        ]
        idx.build(docs, ["d1", "d2", "d3"], [{}, {}, {}])
        assert idx.document_count == 3

        results = idx.search("Classic Tee", k=2)
        assert len(results) > 0
        # First result should be the Classic Tee document
        assert results[0][0] == 0  # doc index 0

    def test_search_empty_index(self):
        idx = BM25Index(collection_name="test")
        assert idx.search("anything") == []

    def test_search_no_matches(self):
        idx = BM25Index(collection_name="test")
        idx.build(["hello world"], ["d1"], [{}])
        results = idx.search("zzzzxyzzy")
        assert len(results) == 0

    def test_staleness_detection(self):
        idx = BM25Index(collection_name="test")
        assert idx.is_stale  # No index built yet

        idx.build(["doc"], ["d1"], [{}])
        assert not idx.is_stale  # Just built

        # Simulate old build
        idx.built_at = time.time() - 25 * 3600
        assert idx.is_stale

    def test_search_respects_k(self):
        idx = BM25Index(collection_name="test")
        docs = [f"document about topic {i}" for i in range(20)]
        ids = [f"d{i}" for i in range(20)]
        meta = [{}] * 20
        idx.build(docs, ids, meta)

        results = idx.search("document topic", k=3)
        assert len(results) <= 3


class TestGetIndex:
    """get_index should return cached indexes."""

    def test_creates_new_index(self):
        idx = get_index("test_unique_coll_12345")
        assert isinstance(idx, BM25Index)
        assert idx.collection_name == "test_unique_coll_12345"

    def test_returns_same_index(self):
        idx1 = get_index("test_same_coll")
        idx2 = get_index("test_same_coll")
        assert idx1 is idx2


class TestVectorOnlyResults:
    """_vector_only_results should convert ChromaDB results to HybridResult."""

    def test_basic_conversion(self):
        vector_results = [
            {"text": "doc1", "metadata": {"key": "val"}, "distance": 0.2},
            {"text": "doc2", "metadata": {}, "distance": 0.5},
        ]
        results = _vector_only_results(vector_results, k=5)
        assert len(results) == 2
        assert results[0].text == "doc1"
        assert results[0].vector_score == pytest.approx(0.8, abs=0.01)
        assert results[0].bm25_score == 0.0
        assert results[0].source == "vector"

    def test_respects_k(self):
        vector_results = [{"text": f"doc{i}", "distance": 0.1} for i in range(10)]
        results = _vector_only_results(vector_results, k=3)
        assert len(results) == 3


class TestMergeResults:
    """_merge_results should combine vector and BM25 results with weighted scoring."""

    def test_vector_only_merge(self):
        """When BM25 returns nothing, vector results only."""
        vector_results = [
            {"text": "doc1", "metadata": {}, "distance": 0.2},
        ]
        index = BM25Index(collection_name="test")
        index.build(["doc1"], ["d1"], [{}])

        results = _merge_results(vector_results, [], index, k=5, alpha=0.6)
        assert len(results) == 1
        assert results[0].source == "vector"
        assert results[0].bm25_score == 0.0

    def test_bm25_only_merge(self):
        """When vector returns nothing, BM25 results only."""
        index = BM25Index(collection_name="test")
        index.build(["doc from bm25"], ["d1"], [{"k": "v"}])

        bm25_hits = [(0, 5.0)]
        results = _merge_results([], bm25_hits, index, k=5, alpha=0.6)
        assert len(results) == 1
        assert results[0].source == "bm25"
        assert results[0].vector_score == 0.0

    def test_both_sources_merge(self):
        """When both find the same doc, it should have source='both' and highest score."""
        vector_results = [
            {"text": "shared document", "metadata": {}, "distance": 0.3},
        ]
        index = BM25Index(collection_name="test")
        index.build(["shared document"], ["d1"], [{}])

        bm25_hits = [(0, 5.0)]
        results = _merge_results(vector_results, bm25_hits, index, k=5, alpha=0.6)
        assert len(results) == 1
        assert results[0].source == "both"
        assert results[0].vector_score > 0
        assert results[0].bm25_score > 0

    def test_alpha_weighting(self):
        """Alpha controls the vector vs keyword weight."""
        vector_results = [
            {"text": "vector doc", "metadata": {}, "distance": 0.1},  # score 0.9
        ]
        index = BM25Index(collection_name="test")
        index.build(["bm25 doc"], ["d1"], [{}])
        bm25_hits = [(0, 5.0)]  # normalized to 1.0

        # High alpha = vector-weighted
        results_high = _merge_results(vector_results, bm25_hits, index, k=5, alpha=0.9)
        # Low alpha = keyword-weighted
        results_low = _merge_results(vector_results, bm25_hits, index, k=5, alpha=0.1)

        # With high alpha, vector doc should score higher
        vector_doc_high = next((r for r in results_high if r.text == "vector doc"), None)
        vector_doc_low = next((r for r in results_low if r.text == "vector doc"), None)
        assert vector_doc_high is not None
        assert vector_doc_low is not None
        assert vector_doc_high.combined_score > vector_doc_low.combined_score

    def test_sorted_by_combined_score(self):
        """Results should be sorted by combined_score descending."""
        vector_results = [
            {"text": "doc1", "metadata": {}, "distance": 0.5},
            {"text": "doc2", "metadata": {}, "distance": 0.1},
        ]
        index = BM25Index(collection_name="test")
        index.build(["doc1", "doc2"], ["d1", "d2"], [{}, {}])
        bm25_hits = [(0, 2.0), (1, 1.0)]

        results = _merge_results(vector_results, bm25_hits, index, k=5, alpha=0.6)
        scores = [r.combined_score for r in results]
        assert scores == sorted(scores, reverse=True)


class TestHybridSearchIntegration:
    """hybrid_search integration with mocked ChromaDB."""

    @patch("src.memory.long_term.retrieve")
    def test_returns_results_with_stale_index_fallback(self, mock_retrieve):
        """When BM25 index rebuild fails, falls back to vector-only."""
        mock_retrieve.return_value = [
            {"text": "fallback doc", "metadata": {}, "distance": 0.2},
        ]

        # Force a stale index and mock rebuild to fail
        with patch("src.memory.hybrid.rebuild_index", side_effect=Exception("ChromaDB down")):
            results = hybrid_search("test_stale_coll", "query text here", k=5)

        assert len(results) == 1
        assert results[0].source == "vector"

    def test_empty_query_returns_nothing(self):
        """Empty or unsafe-only query returns empty results."""
        results = hybrid_search("test_coll", "SELECT DROP DELETE", k=5)
        assert results == []

    @patch("src.memory.long_term.retrieve")
    def test_normal_search_calls_both(self, mock_retrieve):
        """Normal search queries both vector and BM25."""
        mock_retrieve.return_value = [
            {"text": "result doc", "metadata": {}, "distance": 0.3},
        ]

        # Pre-build a non-stale index
        idx = get_index("test_both_coll_2")
        idx.build(["result doc"], ["d1"], [{}])

        results = hybrid_search("test_both_coll_2", "result", k=5)
        mock_retrieve.assert_called_once()
        assert len(results) >= 1
