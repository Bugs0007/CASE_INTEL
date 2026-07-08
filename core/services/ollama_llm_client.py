"""
Ollama LLM client for the Case Intel AI workflow.

Provides the same interface as LLMClient but uses local Ollama
models instead of OpenAI API for 100% local operation.
"""

import logging
import time
from typing import Optional

from django.conf import settings
import ollama

logger = logging.getLogger(__name__)


class OllamaLLMClient:
    """Abstraction over the Ollama chat API.

    Attributes:
        model: The Ollama model identifier (e.g., "llama3.1:8b").
        base_url: The Ollama server URL.
    """

    DEFAULT_RETRY_ATTEMPTS = 3
    DEFAULT_RETRY_DELAY = 1.0  # seconds

    def __init__(
        self,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
    ) -> None:
        self.model = model or settings.OLLAMA_MODEL
        self.base_url = base_url or settings.OLLAMA_BASE_URL
        self._client = ollama.Client(host=self.base_url)

        # Verify connection on initialization
        self._verify_connection()

    def _verify_connection(self) -> None:
        """Verify Ollama server is reachable."""
        try:
            self._client.list()
            logger.info("Ollama connection verified: %s", self.base_url)
        except Exception as e:
            logger.error("Failed to connect to Ollama at %s: %s", self.base_url, e)
            raise ConnectionError(
                f"Cannot connect to Ollama server at {self.base_url}. "
                "Ensure Ollama is running: 'ollama serve'"
            ) from e

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
                    "Ollama request failed (attempt %d/%d): %s",
                    attempt + 1,
                    self.DEFAULT_RETRY_ATTEMPTS,
                    str(e),
                )
                if attempt < self.DEFAULT_RETRY_ATTEMPTS - 1:
                    time.sleep(delay)
                    delay *= 2  # Exponential backoff

        raise last_error

    def generate(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature (0 = deterministic).
            max_tokens: Maximum tokens in the response.

        Returns:
            The assistant's response text.

        Raises:
            ollama.ResponseError: On API failures.
            ConnectionError: If Ollama server is unreachable.
        """
        logger.debug(
            "LLM request: model=%s, messages=%d, temperature=%.2f",
            self.model,
            len(messages),
            temperature,
        )

        start_time = time.perf_counter()

        response = self._call_with_retry(
            self._client.chat,
            model=self.model,
            messages=messages,
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        )

        elapsed = time.perf_counter() - start_time
        content = response.get("message", {}).get("content", "")
        eval_count = response.get("eval_count", 0)

        logger.debug(
            "LLM response: tokens=%d, elapsed=%.2fs, tokens/sec=%.1f",
            eval_count,
            elapsed,
            eval_count / elapsed if elapsed > 0 else 0,
        )

        return content

    def generate_with_json(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 4096,
    ) -> str:
        """Generate a chat completion with JSON response format.

        Same as generate() but instructs the model to return valid JSON.
        """
        logger.debug(
            "LLM JSON request: model=%s, messages=%d",
            self.model,
            len(messages),
        )

        start_time = time.perf_counter()

        response = self._call_with_retry(
            self._client.chat,
            model=self.model,
            messages=messages,
            format="json",  # Ollama's JSON mode
            options={
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        )

        elapsed = time.perf_counter() - start_time
        content = response.get("message", {}).get("content", "{}")
        eval_count = response.get("eval_count", 0)

        logger.debug(
            "LLM JSON response: tokens=%d, elapsed=%.2fs",
            eval_count,
            elapsed,
        )

        return content
