"""
LLM client abstraction for the Case Intel AI workflow.

Provides a unified interface for LLM interactions, isolating the
application from vendor-specific API details. Supports dependency
injection for testing.
"""

import logging
from typing import Optional

import httpx
from django.conf import settings
from openai import OpenAI

logger = logging.getLogger(__name__)


class LLMClient:
    """Abstraction over the OpenAI chat completions API.

    Attributes:
        model: The model identifier to use for completions.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[float] = None,
        max_retries: Optional[int] = None,
    ) -> None:
        resolved_key = api_key or settings.OPENAI_API_KEY
        if not resolved_key:
            raise ValueError(
                "OPENAI_API_KEY must be set in environment or passed explicitly."
            )
        # Bounded on purpose -- see LLM_REQUEST_TIMEOUT_SECONDS in settings.
        # connect is capped separately so an unreachable provider fails in
        # seconds instead of consuming the whole read budget.
        resolved_timeout = (
            timeout if timeout is not None
            else getattr(settings, "LLM_REQUEST_TIMEOUT_SECONDS", 25)
        )
        self._client = OpenAI(
            api_key=resolved_key,
            base_url=base_url,
            timeout=httpx.Timeout(resolved_timeout, connect=min(5.0, resolved_timeout)),
            max_retries=(
                max_retries if max_retries is not None
                else getattr(settings, "LLM_MAX_RETRIES", 1)
            ),
        )
        self.model = model or settings.OPENAI_MODEL

    def _client_for(self, timeout: Optional[float]):
        """The SDK client for one call. With a per-call `timeout` the request
        gets exactly one attempt of that length (no retries): used for calls
        that are optional and have their own fallback."""
        if timeout is None:
            return self._client
        return self._client.with_options(
            timeout=httpx.Timeout(timeout, connect=min(5.0, timeout)), max_retries=0
        )

    def generate(
        self,
        messages: list[dict],
        temperature: float = 0.1,
        max_tokens: int = 4096,
        timeout: Optional[float] = None,
    ) -> str:
        """Generate a chat completion.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature (0 = deterministic).
            max_tokens: Maximum tokens in the response.
            timeout: Optional per-call limit in seconds. Given, the call is a
                single attempt that long; omitted, the client-wide timeout
                and retry settings apply.

        Returns:
            The assistant's response text.

        Raises:
            openai.OpenAIError: On API failures (including
                openai.APITimeoutError when the limit is hit).
        """
        logger.debug(
            "LLM request: model=%s, messages=%d, temperature=%.2f",
            self.model,
            len(messages),
            temperature,
        )

        response = self._client_for(timeout).chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.choices[0].message.content or ""
        logger.debug(
            "LLM response: tokens_used=%s",
            response.usage.total_tokens if response.usage else "unknown",
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

        response = self._client_for(None).chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content or "{}"
        logger.debug(
            "LLM JSON response: tokens_used=%s",
            response.usage.total_tokens if response.usage else "unknown",
        )
        return content
