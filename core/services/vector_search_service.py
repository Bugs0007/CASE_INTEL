"""
Hybrid search service for Case Intel.

Replaces the original cosine-only search with a two-stage pipeline:

    Stage 1 — Retrieval (pure SQL, no LLM)
        a. Vector search  : pgvector cosine similarity         → top_k results
        b. Keyword search : PostgreSQL tsvector / tsquery      → top_k results

    Stage 2 — Fusion
        Reciprocal Rank Fusion (RRF) merges both ranked lists into a single
        score.  RRF is rank-based so it handles the different score scales of
        cosine distance and tf-idf naturally.

        RRF formula:  score(d) = Σ  1 / (k + rank_i(d))
        where k=60 is the standard constant that dampens the influence of
        very high ranks.

Why this beats cosine-only search for legal documents:
    - Legal queries often contain exact terms (case numbers, statute names,
      party names, clause numbers) where keyword matching outperforms
      semantic similarity.
    - Semantic search catches paraphrases and synonyms that BM25 misses.
    - RRF fusion keeps the best of both worlds without requiring any LLM call.

The optional cross-encoder reranker (sentence-transformers) further refines
the top results without any Ollama call, saving ~15 seconds per query.
"""

import logging
from typing import Optional

from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db import connection
from pgvector.django import CosineDistance

from core.models import DocumentChunk
from core.services.ai_service_factory import get_embedding_service

logger = logging.getLogger(__name__)

# RRF constant — 60 is the value used in the original paper
_RRF_K = 60


class VectorSearchResult:
    """Represents a single search result with its relevance score."""

    __slots__ = ("chunk", "score")

    def __init__(self, chunk: DocumentChunk, score: float) -> None:
        self.chunk = chunk
        self.score = score

    def to_dict(self) -> dict:
        return {
            "chunk_id": self.chunk.id,
            "document_id": self.chunk.document_id,
            "chunk_index": self.chunk.chunk_index,
            "text": self.chunk.chunk_text,
            "score": self.score,
            "metadata": {
                "filename": self.chunk.document.filename,
                "document_type": self.chunk.document.document_type or "",
                "case_id": self.chunk.document.case_id,
                "file_type": self.chunk.document.file_type or "",
            },
        }


class VectorSearchService:
    """Hybrid semantic + keyword search over DocumentChunk using pgvector + tsvector.

    Usage::

        service = VectorSearchService()
        results = service.search("what was the settlement amount?", case_id=3)
    """

    def __init__(self, embedding_service=None, use_reranker: bool = True) -> None:
        self._embedding_service = embedding_service or get_embedding_service()
        self._reranker = None
        self._use_reranker = use_reranker

    # ------------------------------------------------------------------
    # Optional cross-encoder reranker (no Ollama required)
    # ------------------------------------------------------------------

    def _get_reranker(self):
        """Lazy-load the cross-encoder. Returns None if not installed."""
        if self._reranker is not None:
            return self._reranker
        if not self._use_reranker:
            return None
        try:
            from sentence_transformers import CrossEncoder
            # ms-marco-MiniLM-L-6-v2 is ~80 MB, runs fast on CPU
            self._reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
            logger.info("Cross-encoder reranker loaded.")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed — skipping reranker. "
                "Install with: pip install sentence-transformers"
            )
            self._reranker = None
        return self._reranker

    # ------------------------------------------------------------------
    # Vector search leg
    # ------------------------------------------------------------------

    def _vector_search(
        self,
        query_embedding: list[float],
        case_id: Optional[int],
        top_k: int,
    ) -> list[DocumentChunk]:
        """Return top_k chunks by cosine similarity."""
        qs = (
            DocumentChunk.objects
            .select_related("document")
            .filter(embedding__isnull=False)
        )
        if case_id is not None:
            qs = qs.filter(document__case_id=case_id)

        return list(
            qs.annotate(distance=CosineDistance("embedding", query_embedding))
            .order_by("distance")[:top_k]
        )

    # ------------------------------------------------------------------
    # Keyword search leg
    # ------------------------------------------------------------------

    @staticmethod
    def _build_or_fallback_query(query: str) -> Optional[SearchQuery]:
        """Build a ranked OR tsquery from PostgreSQL-normalized query lexemes."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT plainto_tsquery('english', %s)::text",
                [query],
            )
            tsquery_text = cursor.fetchone()[0]

        if not tsquery_text:
            return None

        raw_tsquery = tsquery_text.replace(" & ", " | ")
        return SearchQuery(raw_tsquery, search_type="raw", config="english")

    def _keyword_search(
        self,
        query: str,
        case_id: Optional[int],
        top_k: int,
    ) -> list[DocumentChunk]:
        """Return top_k chunks by full-text (tsvector) ranking."""
        qs = (
            DocumentChunk.objects
            .select_related("document")
            .filter(search_vector__isnull=False)
        )
        if case_id is not None:
            qs = qs.filter(document__case_id=case_id)

        search_query = SearchQuery(query, search_type="websearch", config="english")

        exact_hits = list(
            qs.filter(search_vector=search_query)
            .annotate(rank=SearchRank("search_vector", search_query))
            .order_by("-rank")[:top_k]
        )
        if exact_hits:
            return exact_hits

        fallback_query = self._build_or_fallback_query(query)
        if fallback_query is None:
            return []

        fallback_hits = list(
            qs.filter(search_vector=fallback_query)
            .annotate(rank=SearchRank("search_vector", fallback_query))
            .order_by("-rank")[:top_k]
        )
        if fallback_hits:
            logger.info(
                "Keyword search fallback used for query='%s...' with ranked OR tsquery.",
                query[:50],
            )
        return fallback_hits

    # ------------------------------------------------------------------
    # RRF fusion
    # ------------------------------------------------------------------

    @staticmethod
    def _rrf_fuse(
        vector_results: list[DocumentChunk],
        keyword_results: list[DocumentChunk],
        top_k: int,
    ) -> list[tuple[DocumentChunk, float]]:
        """Merge two ranked lists using Reciprocal Rank Fusion.

        Returns list of (chunk, rrf_score) sorted by descending score.
        """
        scores: dict[int, float] = {}   # chunk_id → rrf_score
        chunk_map: dict[int, DocumentChunk] = {}

        for rank, chunk in enumerate(vector_results, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (_RRF_K + rank)
            chunk_map[chunk.id] = chunk

        for rank, chunk in enumerate(keyword_results, start=1):
            scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (_RRF_K + rank)
            chunk_map[chunk.id] = chunk

        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return [(chunk_map[cid], score) for cid, score in ranked[:top_k]]

    # ------------------------------------------------------------------
    # Cross-encoder reranking
    # ------------------------------------------------------------------

    def _rerank(
        self,
        query: str,
        candidates: list[tuple[DocumentChunk, float]],
        top_k: int,
    ) -> list[tuple[DocumentChunk, float]]:
        """Re-score candidates with a local cross-encoder model.

        The cross-encoder looks at (query, chunk_text) together, giving
        much more accurate relevance scores than embedding cosine distance.
        This replaces the LLM-based chunk_ranker node entirely.
        """
        reranker = self._get_reranker()
        if reranker is None or not candidates:
            return candidates[:top_k]

        pairs = [(query, chunk.chunk_text) for chunk, _ in candidates]
        scores = reranker.predict(pairs)

        reranked = sorted(
            zip([c for c, _ in candidates], scores),
            key=lambda x: x[1],
            reverse=True,
        )
        return [(chunk, float(score)) for chunk, score in reranked[:top_k]]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        keyword_query: Optional[str] = None,
        case_id: Optional[int] = None,
        document_types: Optional[list[str]] = None,  # kept for API compatibility
        top_k: Optional[int] = None,
    ) -> list[VectorSearchResult]:
        """Hybrid search: pgvector + tsvector → RRF → cross-encoder rerank.

        Args:
            query: Natural-language question from the user.
            case_id: Scope the search to a specific case.
            document_types: Ignored (kept for backwards compatibility).
            top_k: How many results to return.

        Returns:
            List of VectorSearchResult sorted by descending relevance.
        """
        top_k = top_k or settings.AI_SEARCH_TOP_K
        keyword_query = keyword_query or query
        # Fetch more candidates than needed so RRF and reranker have room to work
        candidate_k = top_k * 3

        # --- Stage 1a: vector search ---
        query_embedding = self._embedding_service.embed_text(query)
        vector_hits = self._vector_search(query_embedding, case_id, candidate_k)

        # --- Stage 1b: keyword search ---
        keyword_hits = self._keyword_search(keyword_query, case_id, candidate_k)

        # --- Stage 2: RRF fusion ---
        fused = self._rrf_fuse(vector_hits, keyword_hits, candidate_k)

        # --- Stage 3: cross-encoder rerank (local, no Ollama) ---
        reranked = self._rerank(query, fused, top_k)

        results = [
            VectorSearchResult(chunk=chunk, score=score)
            for chunk, score in reranked
        ]

        logger.info(
            "Hybrid search: query='%s...', case_id=%s, "
            "vector_hits=%d, keyword_hits=%d, final=%d, top_score=%.4f",
            query[:50],
            case_id,
            len(vector_hits),
            len(keyword_hits),
            len(results),
            results[0].score if results else 0.0,
        )

        return results
