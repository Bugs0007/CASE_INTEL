"""
Embedding generation service for the Case Intel AI workflow.

Wraps the OpenAI embeddings API to generate vector representations
of text for semantic search via pgvector.
"""

import logging
from typing import Optional

from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Generates text embeddings using the OpenAI embeddings API.

    The embedding dimensions must match the pgvector VectorField
    configured on DocumentChunk (default: 1536).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        resolved_key = api_key or settings.OPENAI_API_KEY
        if not resolved_key:
            raise ValueError(
                "OPENAI_API_KEY must be set in environment or passed explicitly."
            )
        self._client = OpenAI(api_key=resolved_key)
        self.model = model or settings.OPENAI_EMBEDDING_MODEL

    def embed_text(self, text: str) -> list[float]:
        """Generate an embedding vector for a single text string.

        Args:
            text: The text to embed.

        Returns:
            A list of floats representing the embedding vector.
        """
        if not text.strip():
            logger.warning("Empty text passed to embed_text, returning zero vector.")
            return [0.0] * settings.EMBEDDING_DIMENSIONS

        response = self._client.embeddings.create(
            model=self.model,
            input=text,
        )
        embedding = response.data[0].embedding
        logger.debug(
            "Embedding generated: model=%s, dimensions=%d",
            self.model,
            len(embedding),
        )
        return embedding

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Args:
            texts: List of text strings to embed.

        Returns:
            List of embedding vectors, one per input text.
        """
        if not texts:
            return []

        # Filter empty strings but preserve index mapping
        non_empty_indices = [i for i, t in enumerate(texts) if t.strip()]
        non_empty_texts = [texts[i] for i in non_empty_indices]

        if not non_empty_texts:
            return [[0.0] * settings.EMBEDDING_DIMENSIONS] * len(texts)

        response = self._client.embeddings.create(
            model=self.model,
            input=non_empty_texts,
        )

        # Map results back to original indices
        results: list[list[float]] = [
            [0.0] * settings.EMBEDDING_DIMENSIONS
        ] * len(texts)
        for idx, embedding_obj in zip(non_empty_indices, response.data):
            results[idx] = embedding_obj.embedding

        logger.debug(
            "Batch embeddings generated: count=%d, model=%s",
            len(non_empty_texts),
            self.model,
        )
        return results
