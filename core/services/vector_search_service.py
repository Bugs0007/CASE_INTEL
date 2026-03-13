"""
Vector search service using pgvector for semantic similarity search.

Uses PostgreSQL's pgvector extension through Django ORM to perform
cosine similarity searches on document chunk embeddings.
"""

import logging
from typing import Optional

from django.conf import settings
from pgvector.django import CosineDistance

from core.models import DocumentChunk
from core.services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


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
    """Performs semantic similarity search over document chunks using pgvector.

    Uses cosine distance for similarity scoring. Supports filtering by
    case_id and document_type.
    """

    def __init__(self, embedding_service: Optional[EmbeddingService] = None) -> None:
        self._embedding_service = embedding_service or EmbeddingService()

    def search(
        self,
        query: str,
        case_id: Optional[int] = None,
        document_types: Optional[list[str]] = None,
        top_k: Optional[int] = None,
    ) -> list[VectorSearchResult]:
        """Search for document chunks semantically similar to the query.

        Args:
            query: The search query text.
            case_id: Optional case ID to filter results.
            document_types: Optional list of document types to filter.
            top_k: Number of results to return (defaults to AI_SEARCH_TOP_K).

        Returns:
            List of VectorSearchResult sorted by descending similarity.
        """
        top_k = top_k or settings.AI_SEARCH_TOP_K

        # Generate query embedding
        query_embedding = self._embedding_service.embed_text(query)

        # Build queryset with filters
        queryset = DocumentChunk.objects.select_related("document").filter(
            embedding__isnull=False,
        )

        if case_id is not None:
            queryset = queryset.filter(document__case_id=case_id)

        if document_types:
            queryset = queryset.filter(document__document_type__in=document_types)

        # Annotate with cosine distance and order by similarity
        queryset = (
            queryset.annotate(
                distance=CosineDistance("embedding", query_embedding),
            )
            .order_by("distance")[:top_k]
        )

        results = []
        for chunk in queryset:
            # Convert cosine distance to similarity score (1 - distance)
            similarity = 1.0 - (chunk.distance or 1.0)
            results.append(VectorSearchResult(chunk=chunk, score=similarity))

        logger.info(
            "Vector search completed: query='%s...', case_id=%s, results=%d, "
            "top_score=%.3f",
            query[:50],
            case_id,
            len(results),
            results[0].score if results else 0.0,
        )

        return results
