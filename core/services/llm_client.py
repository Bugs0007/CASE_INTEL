"""
LLM client abstraction for the Case Intel AI workflow.

Provides a unified interface for LLM interactions, isolating the
application from vendor-specific API details. Supports dependency
injection for testing.
"""

import logging
from typing import Optional

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
    ) -> None:
        resolved_key = api_key or settings.OPENAI_API_KEY
        if not resolved_key:
            raise ValueError(
                "OPENAI_API_KEY must be set in environment or passed explicitly."
            )
        self._client = OpenAI(api_key=resolved_key)
        self.model = model or settings.OPENAI_MODEL

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
            openai.OpenAIError: On API failures.
        """
        logger.debug(
            "LLM request: model=%s, messages=%d, temperature=%.2f",
            self.model,
            len(messages),
            temperature,
        )

        response = self._client.chat.completions.create(
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

        response = self._client.chat.completions.create(
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
