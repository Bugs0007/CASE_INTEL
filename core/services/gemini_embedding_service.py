"""
Gemini embedding service for the Case Intel AI workflow.

Uses Google's Gemini embedding API as an optional embedding provider,
selected independently via USE_GEMINI_EMBEDDINGS (see ai_service_factory.py).

output_dimensionality is EXPLICITLY set to settings.EMBEDDING_DIMENSIONS on
every call -- Gemini's embedding models default to a higher native
dimension (e.g. 3072 for gemini-embedding-001), and relying on that default
would silently produce vectors that don't fit DocumentChunk.embedding's
fixed VectorField(dimensions=768) column.

On any API error (rate limit, network, auth) this raises rather than
falling back to another embedding provider. Embeddings from different
models live in different vector spaces and are not comparable, so mixing
them within a single document would corrupt retrieval -- DocumentProcessor
relies on that exception propagating to mark the whole document as failed.
"""

import logging
import time
from typing import Optional

from django.conf import settings
from google import genai
from google.genai import errors, types

logger = logging.getLogger(__name__)

# Gemini's embed_content endpoint caps input at 100 strings per request.
GEMINI_BATCH_LIMIT = 100


class GeminiEmbeddingService:
    """Generates text embeddings using the Gemini embedding API.

    Supported model:
        - gemini-embedding-001 (native 3072-dim, truncated to
          settings.EMBEDDING_DIMENSIONS via output_dimensionality)
    """

    DEFAULT_RETRY_ATTEMPTS = 5
    DEFAULT_RETRY_DELAY = 0.5  # seconds
    # Gemini's free tier meters embed_content per *content string* per
    # minute (100/min), so a single 100-text batch can exhaust the whole
    # window -- a sub-second exponential backoff never survives that. For
    # 429 RESOURCE_EXHAUSTED specifically, wait long enough for the
    # per-minute window to roll over instead.
    RATE_LIMIT_RETRY_DELAY = 30.0  # seconds
    # embed_text() is the interactive path (one chat query inside a web
    # request); ingestion uses embed_texts(). A web worker must not sit in
    # a 30 s rate-limit sleep or an unbounded HTTP wait, so queries get a
    # short per-call timeout, one retry, and no rate-limit sleep. A failed
    # query embedding is already handled upstream (VectorSearchService falls
    # back to keyword-only results), unlike a failed ingestion embedding.
    QUERY_TIMEOUT_SECONDS = 8
    QUERY_RETRY_ATTEMPTS = 2

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        resolved_key = api_key or settings.GEMINI_API_KEY
        if not resolved_key:
            raise ValueError(
                "GEMINI_API_KEY must be set in environment or passed explicitly."
            )
        self._client = genai.Client(api_key=resolved_key)
        self.model = model or settings.GEMINI_EMBEDDING_MODEL

    def _call_with_retry(self, func, *args, attempts=None, rate_limit_wait=True, **kwargs):
        """Execute function with exponential backoff retry.

        Only retries transient API errors; the final failure is re-raised
        so the caller fails the processing job instead of continuing with
        a partially-embedded document.

        `attempts` overrides DEFAULT_RETRY_ATTEMPTS and `rate_limit_wait=False`
        skips the long 429 sleep -- both for the interactive query path.
        """
        last_error = None
        delay = self.DEFAULT_RETRY_DELAY
        max_attempts = attempts or self.DEFAULT_RETRY_ATTEMPTS

        for attempt in range(max_attempts):
            try:
                return func(*args, **kwargs)
            except errors.APIError as e:
                last_error = e
                logger.warning(
                    "Gemini embedding request failed (attempt %d/%d): %s",
                    attempt + 1,
                    max_attempts,
                    str(e),
                )
                if attempt < max_attempts - 1:
                    wait = delay
                    if rate_limit_wait and getattr(e, "code", None) == 429:
                        wait = max(wait, self.RATE_LIMIT_RETRY_DELAY)
                    time.sleep(wait)
                    delay *= 2  # Exponential backoff

        raise last_error

    def _embed_batch(self, texts: list[str], *, interactive: bool = False) -> list[list[float]]:
        """Embed a single request (must already respect GEMINI_BATCH_LIMIT).

        `interactive=True` is for a query inside a web request: bounded by
        QUERY_TIMEOUT_SECONDS and QUERY_RETRY_ATTEMPTS with no rate-limit
        sleep. Ingestion keeps the patient defaults.
        """
        config_kwargs = {"output_dimensionality": settings.EMBEDDING_DIMENSIONS}
        retry_kwargs = {}
        if interactive:
            # http_options.timeout is in milliseconds.
            config_kwargs["http_options"] = types.HttpOptions(
                timeout=int(self.QUERY_TIMEOUT_SECONDS * 1000)
            )
            retry_kwargs = {"attempts": self.QUERY_RETRY_ATTEMPTS, "rate_limit_wait": False}
        response = self._call_with_retry(
            self._client.models.embed_content,
            model=self.model,
            contents=texts,
            config=types.EmbedContentConfig(**config_kwargs),
            **retry_kwargs,
        )

        embeddings = [list(e.values) for e in response.embeddings]
        for vec in embeddings:
            if len(vec) != settings.EMBEDDING_DIMENSIONS:
                raise ValueError(
                    f"Gemini returned a {len(vec)}-dim embedding; expected "
                    f"{settings.EMBEDDING_DIMENSIONS} (output_dimensionality "
                    "was not honored)."
                )
        return embeddings

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
        embeddings = self._embed_batch([text], interactive=True)
        elapsed = time.perf_counter() - start_time

        logger.debug(
            "Embedding generated: model=%s, dimensions=%d, elapsed=%.3fs",
            self.model,
            len(embeddings[0]),
            elapsed,
        )

        return embeddings[0]

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a batch of texts.

        Splits into GEMINI_BATCH_LIMIT-sized requests to respect the
        Gemini API's per-request cap on input strings, rather than issuing
        one call per chunk.

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

        batch_embeddings: list[list[float]] = []
        for i in range(0, len(non_empty_texts), GEMINI_BATCH_LIMIT):
            batch = non_empty_texts[i : i + GEMINI_BATCH_LIMIT]
            batch_embeddings.extend(self._embed_batch(batch))

        elapsed = time.perf_counter() - start_time

        # Map results back to original indices
        results: list[list[float]] = [
            [0.0] * settings.EMBEDDING_DIMENSIONS for _ in range(len(texts))
        ]
        for i, idx in enumerate(non_empty_indices):
            results[idx] = batch_embeddings[i]

        n_batches = (len(non_empty_texts) + GEMINI_BATCH_LIMIT - 1) // GEMINI_BATCH_LIMIT
        logger.debug(
            "Batch embeddings generated: count=%d, model=%s, requests=%d, elapsed=%.3fs",
            len(non_empty_texts),
            self.model,
            n_batches,
            elapsed,
        )

        return results
