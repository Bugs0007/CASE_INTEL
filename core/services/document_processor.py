"""
Document processing pipeline for the Case Intel application.

Handles the full lifecycle of document ingestion:
    1. Text extraction from uploaded files (PDF, DOCX, TXT)
    2. Chunking extracted text into manageable segments
    3. Generating embeddings for each chunk via OpenAI
    4. Persisting chunks and embeddings to the database

Designed to be called from views or management commands after a
document file has been saved to storage.
"""

import logging
import re
from typing import Optional

from django.db import transaction

from core.models import Document, DocumentChunk
from core.services.ai_service_factory import get_embedding_service

logger = logging.getLogger(__name__)

# Chunking parameters
DEFAULT_CHUNK_SIZE = 1000  # characters
DEFAULT_CHUNK_OVERLAP = 200  # characters
MAX_CHUNKS_PER_DOCUMENT = 500


class DocumentProcessor:
    """Processes raw documents into searchable, embedded chunks.

    Usage::

        processor = DocumentProcessor()
        processor.process_document(document_id=42)
    """

    def __init__(
        self,
        embedding_service=None,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
    ) -> None:
        self._embedding_service = embedding_service
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap

    def _get_embedding_service(self):
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_text_from_file(file_path: str, file_type: str) -> str:
        """Extract plain text from a document file.

        Args:
            file_path: Absolute path to the file on disk.
            file_type: File extension (pdf, docx, txt, etc.).

        Returns:
            Extracted text content.

        Raises:
            ValueError: If file type is unsupported.
            FileNotFoundError: If the file does not exist.
        """
        file_type = (file_type or "").lower().lstrip(".")

        if file_type == "txt":
            return DocumentProcessor._extract_txt(file_path)
        elif file_type == "pdf":
            return DocumentProcessor._extract_pdf(file_path)
        elif file_type in ("docx", "doc"):
            return DocumentProcessor._extract_docx(file_path)
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

    @staticmethod
    def _extract_txt(file_path: str) -> str:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()

    @staticmethod
    def _extract_pdf(file_path: str) -> str:
        try:
            import PyPDF2
        except ImportError:
            raise ImportError(
                "PyPDF2 is required for PDF extraction. "
                "Install it with: pip install PyPDF2"
            )

        text_parts = []
        with open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)

        return "\n".join(text_parts)

    @staticmethod
    def _extract_docx(file_path: str) -> str:
        try:
            import docx
        except ImportError:
            raise ImportError(
                "python-docx is required for DOCX extraction. "
                "Install it with: pip install python-docx"
            )

        doc = docx.Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())

    # ------------------------------------------------------------------
    # Text chunking
    # ------------------------------------------------------------------

    def chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks at sentence boundaries.

        Args:
            text: The full document text.

        Returns:
            List of text chunks.
        """
        if not text.strip():
            return []

        # Normalize whitespace
        text = re.sub(r"\s+", " ", text).strip()

        chunks = []
        start = 0
        text_len = len(text)

        while start < text_len and len(chunks) < MAX_CHUNKS_PER_DOCUMENT:
            end = min(start + self._chunk_size, text_len)

            # Try to break at a sentence boundary
            if end < text_len:
                # Look for sentence-ending punctuation near the chunk boundary
                boundary = self._find_sentence_boundary(text, start, end)
                if boundary > start:
                    end = boundary

            chunk = text[start:end].strip()
            if chunk:
                chunks.append(chunk)

            # Move forward by chunk_size - overlap
            start = end - self._chunk_overlap if end < text_len else text_len

        logger.debug("Text chunked: %d chars -> %d chunks", text_len, len(chunks))
        return chunks

    @staticmethod
    def _find_sentence_boundary(text: str, start: int, end: int) -> int:
        """Find the nearest sentence boundary before `end`.

        Looks backwards from `end` for sentence-ending punctuation
        followed by whitespace. Returns `end` if no boundary is found
        within a reasonable search window.
        """
        # Search the last 20% of the chunk for a sentence boundary
        search_start = max(start, end - (end - start) // 5)
        search_region = text[search_start:end]

        # Look for '. ', '? ', '! ', '.\n' patterns
        for pattern in (". ", "? ", "! ", ".\n", "?\n", "!\n"):
            last_idx = search_region.rfind(pattern)
            if last_idx != -1:
                # Return position after the punctuation
                return search_start + last_idx + 1

        return end

    # ------------------------------------------------------------------
    # Main processing pipeline
    # ------------------------------------------------------------------

    @transaction.atomic
    def process_document(self, document_id: int) -> Document:
        """Run the full processing pipeline for a document.

        1. Mark document as processing
        2. Extract text from file
        3. Split into chunks
        4. Generate embeddings
        5. Persist chunks
        6. Mark document as completed

        Args:
            document_id: Primary key of the Document to process.

        Returns:
            The updated Document instance.

        Raises:
            Document.DoesNotExist: If document_id is invalid.
        """
        document = Document.objects.select_for_update().get(id=document_id)
        document.processing_status = "processing"
        document.save(update_fields=["processing_status"])

        logger.info(
            "Processing document %d: %s (%s)",
            document_id,
            document.filename,
            document.file_type,
        )

        try:
            # Step 1: Extract text
            extracted_text = self.extract_text_from_file(
                document.file_path, document.file_type or ""
            )
            document.extracted_text = extracted_text

            if not extracted_text.strip():
                logger.warning("No text extracted from document %d", document_id)
                document.processing_status = "completed"
                document.chunk_count = 0
                document.save(update_fields=[
                    "extracted_text", "processing_status", "chunk_count"
                ])
                return document

            # Step 2: Chunk text
            chunks = self.chunk_text(extracted_text)

            # Step 3: Generate embeddings in batch
            embedding_service = self._get_embedding_service()
            embeddings = embedding_service.embed_texts(chunks)

            # Step 4: Delete existing chunks (idempotent re-processing)
            DocumentChunk.objects.filter(document=document).delete()

            # Step 5: Create chunk records
            chunk_objects = [
                DocumentChunk(
                    document=document,
                    chunk_index=i,
                    chunk_text=chunk_text,
                    embedding=embedding,
                )
                for i, (chunk_text, embedding) in enumerate(zip(chunks, embeddings))
            ]
            DocumentChunk.objects.bulk_create(chunk_objects)

            # Step 6: Update document status
            document.processing_status = "completed"
            document.chunk_count = len(chunk_objects)
            document.save(update_fields=[
                "extracted_text", "processing_status", "chunk_count"
            ])

            logger.info(
                "Document %d processed: %d chunks created",
                document_id,
                len(chunk_objects),
            )

        except Exception:
            logger.exception("Failed to process document %d", document_id)
            document.processing_status = "failed"
            document.save(update_fields=["processing_status"])
            raise

        return document
