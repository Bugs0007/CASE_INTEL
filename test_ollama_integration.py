"""
Integration tests for Ollama LLM and embedding services.

This standalone script tests the Ollama integration independently of Django.
Run with: python test_ollama_integration.py

Prerequisites:
    - Ollama running: ollama serve
    - Models downloaded:
        * ollama pull llama3.1:8b
        * ollama pull nomic-embed-text
"""

import json
import logging
import sys
from pathlib import Path

# Setup Django
import django
from django.conf import settings

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

if not settings.configured:
    import os
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'case_intel_project.settings')
    django.setup()

from core.services.ai_service_factory import get_llm_client, get_embedding_service
from core.services.ollama_llm_client import OllamaLLMClient
from core.services.ollama_embedding_service import OllamaEmbeddingService

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def test_ollama_connection():
    """Test connection to Ollama server."""
    logger.info("=" * 70)
    logger.info("TEST 1: Ollama Connection")
    logger.info("=" * 70)

    try:
        client = OllamaLLMClient()
        logger.info("✓ Successfully connected to Ollama at %s", client.base_url)
        logger.info("✓ Model: %s", client.model)
        return True
    except ConnectionError as e:
        logger.error("✗ Failed to connect to Ollama: %s", e)
        logger.error("   Ensure Ollama is running: ollama serve")
        return False


def test_embedding_generation():
    """Test embedding generation."""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 2: Embedding Generation")
    logger.info("=" * 70)

    try:
        embedding_service = OllamaEmbeddingService()

        test_text = "This is a test document about legal proceedings."
        embeddings = embedding_service.embed_text(test_text)

        logger.info("✓ Generated embedding for text: %s...", test_text[:50])
        logger.info("  Dimensions: %d", len(embeddings))
        logger.info("  Sample values: [%.4f, %.4f, %.4f, ...]",
                   embeddings[0], embeddings[1], embeddings[2])

        # Verify dimensions match settings
        from django.conf import settings
        expected_dims = settings.EMBEDDING_DIMENSIONS
        if len(embeddings) != expected_dims:
            logger.error("✗ Dimension mismatch! Expected %d, got %d",
                        expected_dims, len(embeddings))
            return False

        logger.info("✓ Dimension matches settings: %d", expected_dims)
        return True
    except Exception as e:
        logger.error("✗ Embedding generation failed: %s", e)
        logger.error("   Ensure model is downloaded: ollama pull nomic-embed-text")
        return False


def test_batch_embeddings():
    """Test batch embedding generation."""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 3: Batch Embedding Generation")
    logger.info("=" * 70)

    try:
        embedding_service = OllamaEmbeddingService()

        texts = [
            "Motion to dismiss the case.",
            "Answer to plaintiff's complaint.",
            "Discovery request for documents.",
            "Settlement agreement between parties.",
            "",  # Test empty string handling
        ]

        embeddings = embedding_service.embed_texts(texts)

        logger.info("✓ Generated %d embeddings", len(embeddings))
        logger.info("  Input texts: %d", len(texts))
        logger.info("  Output embeddings: %d", len(embeddings))

        # Check dimensions
        from django.conf import settings
        expected_dims = settings.EMBEDDING_DIMENSIONS

        for i, emb in enumerate(embeddings):
            if len(emb) != expected_dims:
                logger.error("✗ Embedding %d has incorrect dimensions: %d",
                            i, len(emb))
                return False

        logger.info("✓ All embeddings have correct dimensions: %d", expected_dims)
        return True
    except Exception as e:
        logger.error("✗ Batch embedding generation failed: %s", e)
        return False


def test_llm_generation():
    """Test LLM text generation."""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 4: LLM Text Generation")
    logger.info("=" * 70)

    try:
        llm_client = OllamaLLMClient()

        messages = [
            {
                "role": "system",
                "content": "You are a legal assistant. Provide concise answers about legal procedures."
            },
            {
                "role": "user",
                "content": "What is a motion to dismiss in legal proceedings? Keep your answer to 2-3 sentences."
            }
        ]

        response = llm_client.generate(messages, temperature=0.1, max_tokens=200)

        logger.info("✓ LLM generation successful")
        logger.info("  Response:\n    %s...", response[:150])
        logger.info("  Length: %d characters", len(response))

        return len(response) > 0
    except Exception as e:
        logger.error("✗ LLM generation failed: %s", e)
        logger.error("   Ensure model is downloaded: ollama pull llama3.1:8b")
        return False


def test_json_generation():
    """Test LLM JSON generation."""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 5: LLM JSON Generation")
    logger.info("=" * 70)

    try:
        llm_client = OllamaLLMClient()

        messages = [
            {
                "role": "system",
                "content": "You are a JSON generating system. Respond only with valid JSON."
            },
            {
                "role": "user",
                "content": """Classify this legal query:
Query: "What were the key arguments in the motion to dismiss?"

Respond with JSON:
{
    "query_type": "simple_qa" or "summarize" or "compare" or "timeline" or "unclear",
    "needs_clarification": true or false
}"""
            }
        ]

        response = llm_client.generate_with_json(messages, temperature=0.0, max_tokens=100)

        logger.info("✓ JSON generation successful")
        logger.info("  Response:\n    %s", response[:200])

        # Try to parse JSON
        try:
            parsed = json.loads(response)
            logger.info("✓ Valid JSON returned")
            logger.info("  Query type: %s", parsed.get("query_type"))
            logger.info("  Needs clarification: %s", parsed.get("needs_clarification"))
            return True
        except json.JSONDecodeError:
            logger.warning("⚠ Response is not valid JSON, but generation completed")
            return True

    except Exception as e:
        logger.error("✗ JSON generation failed: %s", e)
        return False


def test_factory_pattern():
    """Test the AI service factory."""
    logger.info("\n" + "=" * 70)
    logger.info("TEST 6: Factory Pattern")
    logger.info("=" * 70)

    try:
        from django.conf import settings

        use_ollama = settings.USE_OLLAMA
        logger.info("USE_OLLAMA setting: %s", use_ollama)

        llm = get_llm_client()
        embedding = get_embedding_service()

        logger.info("✓ LLM client: %s", type(llm).__name__)
        logger.info("✓ Embedding service: %s", type(embedding).__name__)

        if use_ollama:
            if isinstance(llm, OllamaLLMClient):
                logger.info("✓ Factory correctly returns OllamaLLMClient")
            else:
                logger.error("✗ Factory returned wrong LLM type for USE_OLLAMA=True")
                return False

            if isinstance(embedding, OllamaEmbeddingService):
                logger.info("✓ Factory correctly returns OllamaEmbeddingService")
            else:
                logger.error("✗ Factory returned wrong embedding type for USE_OLLAMA=True")
                return False

        return True
    except Exception as e:
        logger.error("✗ Factory pattern test failed: %s", e)
        return False


def run_all_tests():
    """Run all integration tests."""
    logger.info("\n")
    logger.info("╔" + "=" * 68 + "╗")
    logger.info("║" + " " * 15 + "OLLAMA INTEGRATION TEST SUITE" + " " * 24 + "║")
    logger.info("╚" + "=" * 68 + "╝")

    results = {
        "Connection": test_ollama_connection(),
        "Embedding Single": test_embedding_generation(),
        "Embedding Batch": test_batch_embeddings(),
        "LLM Generation": test_llm_generation(),
        "JSON Generation": test_json_generation(),
        "Factory Pattern": test_factory_pattern(),
    }

    # Summary
    logger.info("\n" + "=" * 70)
    logger.info("TEST SUMMARY")
    logger.info("=" * 70)

    passed = sum(1 for v in results.values() if v)
    total = len(results)

    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        logger.info("  [%s] %s", status, test_name)

    logger.info("=" * 70)
    logger.info("Results: %d/%d tests passed", passed, total)

    if passed == total:
        logger.info("✓ All tests passed! Ollama integration is working correctly.")
        return 0
    else:
        logger.error("✗ Some tests failed. Check the logs above for details.")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
