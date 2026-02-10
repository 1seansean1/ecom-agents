"""Hybrid memory: BM25 keyword search + ChromaDB vector search with weighted merge.

Phase 18b (openclaw-inspired): Combines exact keyword matching with semantic
similarity for better retrieval. Addresses the gap where pure vector search
misses exact matches like order IDs or product names.

Architecture:
- BM25 index maintained per collection (rebuilt on store)
- ChromaDB vector search (existing)
- Weighted merge: score = α * vector_score + (1-α) * bm25_score
- Configurable α per collection (default 0.6 = vector-weighted)

Security:
- Query sanitization: strip SQL keywords and special operators
- Per-collection scoping: no cross-collection leakage
- Index staleness detection: fallback to vector-only if index too old
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# Max age before BM25 index is considered stale (24 hours)
MAX_INDEX_AGE_SECONDS = 24 * 3600

# Default vector weight (higher = more semantic, lower = more keyword)
DEFAULT_ALPHA = 0.6

# SQL-like keywords to strip from search queries
_UNSAFE_QUERY_PATTERNS = re.compile(
    r"\b(UNION|SELECT|DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)

# BM25 operator characters to strip
_BM25_OPERATORS = re.compile(r"[+\-*\"~^]")


@dataclass
class HybridResult:
    """A single result from hybrid search."""

    text: str
    metadata: dict[str, Any]
    vector_score: float  # 0-1 normalized (1 = most similar)
    bm25_score: float    # 0-1 normalized (1 = best keyword match)
    combined_score: float
    source: str          # "vector", "bm25", or "both"


@dataclass
class BM25Index:
    """In-memory BM25 index for a single collection."""

    collection_name: str
    documents: list[str] = field(default_factory=list)
    doc_ids: list[str] = field(default_factory=list)
    doc_metadata: list[dict[str, Any]] = field(default_factory=list)
    bm25: BM25Okapi | None = None
    built_at: float = 0.0

    @property
    def is_stale(self) -> bool:
        """Whether this index needs rebuilding."""
        if self.bm25 is None:
            return True
        return (time.time() - self.built_at) > MAX_INDEX_AGE_SECONDS

    @property
    def document_count(self) -> int:
        """Number of documents in the index."""
        return len(self.documents)

    def build(self, documents: list[str], doc_ids: list[str], metadata: list[dict[str, Any]]) -> None:
        """Build/rebuild the BM25 index from documents."""
        self.documents = documents
        self.doc_ids = doc_ids
        self.doc_metadata = metadata

        if not documents:
            self.bm25 = None
            self.built_at = time.time()
            return

        # Tokenize documents for BM25
        tokenized = [_tokenize(doc) for doc in documents]
        self.bm25 = BM25Okapi(tokenized)
        self.built_at = time.time()
        logger.info(
            "BM25 index rebuilt for %s: %d documents",
            self.collection_name,
            len(documents),
        )

    def search(self, query: str, k: int = 5) -> list[tuple[int, float]]:
        """Search the BM25 index. Returns list of (doc_index, score)."""
        if self.bm25 is None or not self.documents:
            return []

        tokenized_query = _tokenize(query)
        if not tokenized_query:
            return []

        scores = self.bm25.get_scores(tokenized_query)

        # Get top-k indices sorted by score descending
        indexed_scores = [(i, float(s)) for i, s in enumerate(scores) if s > 0]
        indexed_scores.sort(key=lambda x: x[1], reverse=True)
        return indexed_scores[:k]


# Module-level index cache
_indexes: dict[str, BM25Index] = {}


def get_index(collection_name: str) -> BM25Index:
    """Get or create a BM25 index for a collection."""
    if collection_name not in _indexes:
        _indexes[collection_name] = BM25Index(collection_name=collection_name)
    return _indexes[collection_name]


def rebuild_index(collection_name: str) -> int:
    """Rebuild the BM25 index for a collection from ChromaDB.

    Returns the number of documents indexed.
    """
    from src.memory.long_term import _get_client

    client = _get_client()
    coll = client.get_or_create_collection(name=collection_name)

    # Get all documents from collection
    result = coll.get(include=["documents", "metadatas"])
    documents = result.get("documents", []) or []
    doc_ids = result.get("ids", []) or []
    metadata = result.get("metadatas", []) or []

    index = get_index(collection_name)
    index.build(documents, doc_ids, metadata)
    return len(documents)


def sanitize_query(query: str) -> str:
    """Sanitize a search query by removing unsafe patterns.

    Strips SQL keywords and BM25 operator characters to prevent
    index injection or unexpected query behavior.
    """
    # Strip SQL keywords
    cleaned = _UNSAFE_QUERY_PATTERNS.sub("", query)
    # Strip BM25 operators
    cleaned = _BM25_OPERATORS.sub(" ", cleaned)
    # Collapse whitespace
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    # Cap length
    return cleaned[:1000]


def hybrid_search(
    collection_name: str,
    query: str,
    k: int = 5,
    alpha: float = DEFAULT_ALPHA,
    force_rebuild: bool = False,
) -> list[HybridResult]:
    """Search using both BM25 keyword and ChromaDB vector similarity.

    Args:
        collection_name: ChromaDB collection to search
        query: Search query text
        k: Number of results to return
        alpha: Weight for vector score (0-1). Higher = more semantic.
        force_rebuild: Force BM25 index rebuild before searching

    Returns:
        List of HybridResult sorted by combined_score descending.
    """
    from src.memory.long_term import retrieve

    # Sanitize query
    safe_query = sanitize_query(query)
    if not safe_query:
        return []

    # Get vector search results from ChromaDB
    vector_results = retrieve(collection_name, safe_query, k=k * 2)  # Over-fetch for merge

    # Get or build BM25 index
    index = get_index(collection_name)
    if index.is_stale or force_rebuild:
        try:
            rebuild_index(collection_name)
        except Exception as e:
            logger.warning("BM25 index rebuild failed for %s: %s", collection_name, e)
            # Fallback to vector-only
            return _vector_only_results(vector_results, k)

    # BM25 search
    bm25_hits = index.search(safe_query, k=k * 2)

    # Merge results
    return _merge_results(vector_results, bm25_hits, index, k, alpha)


def _vector_only_results(vector_results: list[dict], k: int) -> list[HybridResult]:
    """Convert vector-only results when BM25 is unavailable."""
    results = []
    for r in vector_results[:k]:
        # ChromaDB returns distances (lower = closer). Normalize to 0-1 score.
        distance = r.get("distance", 1.0)
        vector_score = max(0.0, 1.0 - distance)

        results.append(HybridResult(
            text=r["text"],
            metadata=r.get("metadata", {}),
            vector_score=vector_score,
            bm25_score=0.0,
            combined_score=vector_score,
            source="vector",
        ))
    return results


def _merge_results(
    vector_results: list[dict],
    bm25_hits: list[tuple[int, float]],
    index: BM25Index,
    k: int,
    alpha: float,
) -> list[HybridResult]:
    """Merge vector and BM25 results with weighted scoring.

    Uses the formula: combined = α * vector_norm + (1-α) * bm25_norm
    where both scores are normalized to [0, 1].
    """
    # Build lookup by document text for deduplication
    merged: dict[str, HybridResult] = {}

    # Normalize BM25 scores to [0, 1]
    max_bm25 = max((s for _, s in bm25_hits), default=1.0)
    if max_bm25 == 0:
        max_bm25 = 1.0

    # Process vector results
    for r in vector_results:
        distance = r.get("distance", 1.0)
        vector_score = max(0.0, 1.0 - distance)
        text = r["text"]

        merged[text] = HybridResult(
            text=text,
            metadata=r.get("metadata", {}),
            vector_score=vector_score,
            bm25_score=0.0,
            combined_score=alpha * vector_score,
            source="vector",
        )

    # Process BM25 results
    for doc_idx, raw_score in bm25_hits:
        if doc_idx >= len(index.documents):
            continue

        text = index.documents[doc_idx]
        bm25_norm = raw_score / max_bm25

        if text in merged:
            # Both sources found this document
            existing = merged[text]
            existing.bm25_score = bm25_norm
            existing.combined_score = alpha * existing.vector_score + (1 - alpha) * bm25_norm
            existing.source = "both"
        else:
            # BM25-only result
            merged[text] = HybridResult(
                text=text,
                metadata=index.doc_metadata[doc_idx] if doc_idx < len(index.doc_metadata) else {},
                vector_score=0.0,
                bm25_score=bm25_norm,
                combined_score=(1 - alpha) * bm25_norm,
                source="bm25",
            )

    # Sort by combined score and return top-k
    results = sorted(merged.values(), key=lambda r: r.combined_score, reverse=True)
    return results[:k]


def _tokenize(text: str) -> list[str]:
    """Simple whitespace + lowercasing tokenizer for BM25."""
    # Remove non-alphanumeric except spaces and hyphens
    cleaned = re.sub(r"[^\w\s-]", " ", text.lower())
    tokens = cleaned.split()
    # Filter very short tokens (less than 2 chars)
    return [t for t in tokens if len(t) >= 2]
