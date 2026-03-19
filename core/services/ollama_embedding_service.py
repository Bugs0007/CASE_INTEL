"""
Ollama embedding service for the Case Intel AI workflow.

Uses local Ollama models to generate embeddings instead of OpenAI API
for 100% local operation with zero API costs.

Default model: nomic-embed-text (768 dimensions)
"""

import logging
import time
from typing import Optional

from django.conf import settings
import ollama

logger = logging.getLogger(__name__)


class OllamaEmbeddingService:
    """Generates text embeddings using local Ollama models.

    The embedding dimensions must match the pgvector VectorField
    configured on DocumentChunk.

    Supported models:
        - nomic-embed-text: 768 dimensions (recommended, fast)
        - mxbai-embed-large: 1024 dimensions
        - all-minilm: 384 dimensions
    """

    DEFAULT_RETRY_ATTEMPTS = 3
    DEFAULT_RETRY_DELAY = 0.5  # seconds

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.model = model or settings.OLLAMA_EMBEDDING_MODEL
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self._client = ollama.Client(host=self.base_url)

    def _call_with_retry(self, func, *args, **kwargs):
        """Execute function with exponential backoff retry."""
        last_error = None
        delay = self.DEFAULT_RETRY_DELAY

        for attempt in range(self.DEFAULT_RETRY_ATTEMPTS):
            try:
                return func(*args, **kwargs)
            except (ollama.ResponseError, ConnectionError) as e:
                last_error = e
                logger.warning(
                    "Ollama embedding request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.DEFAULT_RETRY_ATTEMPTS,
                    str(e),
                )
                if attempt < self.DEFAULT_RETRY_ATTEMPTS - 1:
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff

        raise last_error

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

        start_time = time.perf_counter()

        response = self._call_with_retry(
            self._client.embed,
            model=self.model,
            input=text,
        )

        elapsed = time.perf_counter() - start_time
        embeddings = response.get("embeddings", [[]])[0]

        logger.debug(
            "Embedding generated: model=%s, dimensions=%d, elapsed=%.3fs",
            self.model,
            len(embeddings),
            elapsed,
        )

        return embeddings

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

        start_time = time.perf_counter()

        # Ollama embed API supports batch input
        response = self._call_with_retry(
            self._client.embed,
            model=self.model,
            input=non_empty_texts,
        )

        all_embeddings = response.get("embeddings", [])
        elapsed = time.perf_counter() - start_time

        # Map results back to original indices
        results: list[list[float]] = [
            [0.0] * settings.EMBEDDING_DIMENSIONS for _ in range(len(texts))
        ]
        for i, idx in enumerate(non_empty_indices):
            if i < len(all_embeddings):
                results[idx] = all_embeddings[i]

        logger.debug(
            "Batch embeddings generated: count=%d, model=%s, elapsed=%.3fs",
            len(non_empty_texts),
            self.model,
            elapsed,
        )

        return results
