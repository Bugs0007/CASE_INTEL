"""
Factory module for AI service instantiation.

Provides a centralized way to create LLM and embedding service
instances based on configuration. Supports both OpenAI and Ollama
backends with a single configuration switch.

Usage:
    from core.services.ai_service_factory import get_llm_client, get_embedding_service

    llm = get_llm_client()
    embedding_service = get_embedding_service()
"""

import logging
from typing import TYPE_CHECKING, Union

from django.conf import settings

if TYPE_CHECKING:
    from core.services.llm_client import LLMClient
    from core.services.ollama_llm_client import OllamaLLMClient
    from core.services.embedding_service import EmbeddingService
    from core.services.ollama_embedding_service import OllamaEmbeddingService

logger = logging.getLogger(__name__)

# Type aliases for cleaner type hints
LLMClientType = Union["LLMClient", "OllamaLLMClient"]
EmbeddingServiceType = Union["EmbeddingService", "OllamaEmbeddingService"]


def get_llm_client() -> LLMClientType:
    """Factory function to create an LLM client.

    Returns:
        LLMClient or OllamaLLMClient based on settings.USE_OLLAMA.

    Raises:
        ImportError: If required dependencies are missing.
        ConnectionError: If Ollama server is unreachable (when USE_OLLAMA=True).
        ValueError: If OpenAI API key is missing (when USE_OLLAMA=False).
    """
    use_ollama = getattr(settings, "USE_OLLAMA", False)

    if use_ollama:
        from core.services.ollama_llm_client import OllamaLLMClient

        logger.info("Creating Ollama LLM client (model=%s)", settings.OLLAMA_MODEL)
        return OllamaLLMClient()
    else:
        from core.services.llm_client import LLMClient

        logger.info("Creating OpenAI LLM client (model=%s)", settings.OPENAI_MODEL)
        return LLMClient()


def get_embedding_service() -> EmbeddingServiceType:
    """Factory function to create an embedding service.

    Returns:
        EmbeddingService or OllamaEmbeddingService based on settings.USE_OLLAMA.

    Raises:
        ImportError: If required dependencies are missing.
        ConnectionError: If Ollama server is unreachable (when USE_OLLAMA=True).
        ValueError: If OpenAI API key is missing (when USE_OLLAMA=False).
    """
    use_ollama = getattr(settings, "USE_OLLAMA", False)

    if use_ollama:
        from core.services.ollama_embedding_service import OllamaEmbeddingService

        logger.info(
            "Creating Ollama embedding service (model=%s)",
            settings.OLLAMA_EMBEDDING_MODEL,
        )
        return OllamaEmbeddingService()
    else:
        from core.services.embedding_service import EmbeddingService

        logger.info(
            "Creating OpenAI embedding service (model=%s)",
            settings.OPENAI_EMBEDDING_MODEL,
        )
        return EmbeddingService()
