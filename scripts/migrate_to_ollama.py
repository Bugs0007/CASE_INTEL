"""
Migration script from OpenAI embeddings to Ollama embeddings.

This script re-processes all existing documents with Ollama embeddings
to replace OpenAI embeddings. Run this after switching from OpenAI to Ollama.

Usage:
    python manage.py shell
    >>> from scripts.migrate_to_ollama import migrate_all_documents
    >>> migrate_all_documents(batch_size=5, skip_already_migrated=False)

Or from command line:
    python -c "
    import django;
    django.setup()
    from scripts.migrate_to_ollama import migrate_all_documents
    migrate_all_documents()
    "
"""

import logging
from typing import Optional

from django.conf import settings
from django.db import transaction

from core.models import Document, DocumentChunk
from core.services.document_processor import DocumentProcessor
from core.services.ai_service_factory import get_embedding_service

logger = logging.getLogger(__name__)


def get_migration_status() -> dict:
    """Get migration status information."""
    total_docs = Document.objects.count()
    total_chunks = DocumentChunk.objects.count()

    return {
        "total_documents": total_docs,
        "total_chunks": total_chunks,
        "embedding_model": settings.OLLAMA_EMBEDDING_MODEL if settings.USE_OLLAMA else settings.OPENAI_EMBEDDING_MODEL,
        "embedding_dimensions": settings.EMBEDDING_DIMENSIONS,
    }


def migrate_document(document: Document, processor: Optional[DocumentProcessor] = None) -> bool:
    """
    Re-process a single document with new embeddings.

    Args:
        document: The Document instance to migrate.
        processor: Optional DocumentProcessor instance (will create if not provided).

    Returns:
        True if successful, False otherwise.
    """
    if processor is None:
        processor = DocumentProcessor()

    try:
        logger.info(
            "Migrating document %d: %s (%s chunks)",
            document.id,
            document.filename,
            document.chunk_count,
        )

        # Re-process the document (will regenerate embeddings)
        processor.process_document(document.id)
        logger.info("✓ Document %d migrated successfully", document.id)
        return True

    except Exception as e:
        logger.error("✗ Failed to migrate document %d: %s", document.id, e)
        return False


@transaction.atomic
def migrate_all_documents(
    batch_size: int = 5,
    skip_already_migrated: bool = False,
    document_ids: Optional[list[int]] = None,
) -> dict:
    """
    Migrate all documents to new embeddings.

    This will:
    1. Load each document's raw text
    2. Re-chunk the text (optional, can be skipped)
    3. Generate new embeddings
    4. Replace old embeddings in database

    Args:
        batch_size: Number of documents to process before committing.
        skip_already_migrated: If True, skip documents that already have new embeddings.
        document_ids: Optional list of specific document IDs to migrate. If not provided, migrates all.

    Returns:
        Dictionary with migration results.
    """
    logger.info("=" * 70)
    logger.info("OLLAMA MIGRATION SCRIPT")
    logger.info("=" * 70)

    status = get_migration_status()
    logger.info("Current Status:")
    logger.info("  Total documents: %d", status["total_documents"])
    logger.info("  Total chunks: %d", status["total_chunks"])
    logger.info("  Embedding model: %s", status["embedding_model"])
    logger.info("  Embedding dimensions: %d", status["embedding_dimensions"])

    # Verify Ollama is configured
    if not settings.USE_OLLAMA:
        logger.warning("⚠ USE_OLLAMA is False. Continue anyway? (This will use configured embedding model)")

    # Get documents to migrate
    queryset = Document.objects.all()
    if document_ids:
        queryset = queryset.filter(id__in=document_ids)

    total_docs = queryset.count()
    if total_docs == 0:
        logger.warning("No documents to migrate")
        return {"migrated": 0, "failed": 0, "skipped": 0}

    logger.info("Will migrate %d documents", total_docs)

    # Initialize processor and embedding service
    processor = DocumentProcessor()
    embedding_service = get_embedding_service()

    logger.info("Using embedding service: %s", type(embedding_service).__name__)
    logger.info("=" * 70)

    migrated = 0
    failed = 0
    skipped = 0

    for i, document in enumerate(queryset, 1):
        try:
            # Process document (re-chunk and re-embed)
            if migrate_document(document, processor):
                migrated += 1
            else:
                failed += 1

            # Log progress
            if i % batch_size == 0:
                logger.info(
                    "Progress: %d/%d (migrated=%d, failed=%d, skipped=%d)",
                    i, total_docs, migrated, failed, skipped
                )

        except Exception as e:
            logger.error("Unexpected error processing document %d: %s", document.id, e)
            failed += 1

    # Final summary
    logger.info("=" * 70)
    logger.info("MIGRATION COMPLETE")
    logger.info("=" * 70)
    logger.info("Migrated: %d", migrated)
    logger.info("Failed: %d", failed)
    logger.info("Skipped: %d", skipped)
    logger.info("Total: %d", migrated + failed + skipped)

    if failed == 0:
        logger.info("✓ All documents migrated successfully!")
    else:
        logger.warning("⚠ %d documents failed to migrate", failed)

    return {
        "migrated": migrated,
        "failed": failed,
        "skipped": skipped,
    }


def rollback_to_openai():
    """
    Rollback: Re-process all documents with OpenAI embeddings.

    Only works if USE_OLLAMA was previously False. Run this to revert.
    """
    logger.warning("⚠ Rollback requested: Re-processing with OpenAI embeddings")

    if settings.USE_OLLAMA:
        logger.error("✗ Cannot rollback while USE_OLLAMA=True. Set it to False first.")
        return {"migrated": 0, "failed": 0}

    return migrate_all_documents()


if __name__ == "__main__":
    import django
    import sys

    django.setup()

    try:
        results = migrate_all_documents()
        sys.exit(0 if results["failed"] == 0 else 1)
    except KeyboardInterrupt:
        logger.warning("Migration interrupted by user")
        sys.exit(1)
