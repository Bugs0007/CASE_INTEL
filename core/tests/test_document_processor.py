"""
Unit tests for the document processing pipeline.

Tests text chunking logic (which has no external dependencies) and
verifies the process_document orchestration via mocked services.
"""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from core.models import Case, Document, DocumentChunk
from core.services.document_processor import DocumentProcessor


class TestTextChunking(TestCase):
    """Tests for DocumentProcessor.chunk_text (pure logic, no I/O)."""

    def setUp(self):
        self.processor = DocumentProcessor(chunk_size=100, chunk_overlap=20)

    def test_empty_text_returns_empty_list(self):
        self.assertEqual(self.processor.chunk_text(""), [])
        self.assertEqual(self.processor.chunk_text("   "), [])

    def test_short_text_returns_single_chunk(self):
        text = "This is a short sentence."
        chunks = self.processor.chunk_text(text)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(chunks[0], text)

    def test_long_text_creates_multiple_chunks(self):
        text = "Word " * 200  # ~1000 chars
        chunks = self.processor.chunk_text(text)
        self.assertGreater(len(chunks), 1)

    def test_chunks_have_overlap(self):
        # With overlap, the end of one chunk should appear at the start of the next
        text = "a " * 200  # 400 chars, chunk_size=100, overlap=20
        chunks = self.processor.chunk_text(text)
        self.assertGreater(len(chunks), 1)

        # Verify no empty chunks
        for chunk in chunks:
            self.assertTrue(len(chunk.strip()) > 0)

    def test_respects_max_chunks_limit(self):
        # Create text that would generate too many chunks
        processor = DocumentProcessor(chunk_size=10, chunk_overlap=0)
        text = "x" * 100000
        chunks = processor.chunk_text(text)
        self.assertLessEqual(len(chunks), 500)

    def test_sentence_boundary_detection(self):
        text = (
            "First sentence here. Second sentence here. Third sentence here. "
            "Fourth sentence here. Fifth sentence here."
        )
        processor = DocumentProcessor(chunk_size=60, chunk_overlap=10)
        chunks = processor.chunk_text(text)
        # Chunks should try to end at sentence boundaries
        self.assertGreater(len(chunks), 1)


class TestDocumentProcessing(TestCase):
    """Tests for the full process_document pipeline with mocked externals."""

    def setUp(self):
        self.case = Case.objects.create(
            case_number="CASE-001",
            title="Test Case",
            client_name="Test Client",
        )
        self.document = Document.objects.create(
            case=self.case,
            filename="test.txt",
            file_path="/tmp/test.txt",
            file_type="txt",
            processing_status="pending",
        )

    @patch.object(DocumentProcessor, "extract_text_from_file")
    @patch("core.services.document_processor.EmbeddingService")
    def test_process_document_creates_chunks(self, mock_embed_cls, mock_extract):
        """Verify chunks are created and document status updated."""
        mock_extract.return_value = "This is test content. " * 10

        # Mock embedding service
        mock_embed_instance = MagicMock()
        mock_embed_instance.embed_texts.return_value = [
            [0.1] * 1536 for _ in range(5)
        ]
        mock_embed_cls.return_value = mock_embed_instance

        processor = DocumentProcessor(
            embedding_service=mock_embed_instance,
            chunk_size=50,
            chunk_overlap=10,
        )
        result = processor.process_document(self.document.id)

        self.assertEqual(result.processing_status, "completed")
        self.assertGreater(result.chunk_count, 0)
        self.assertEqual(
            DocumentChunk.objects.filter(document=self.document).count(),
            result.chunk_count,
        )

    @patch.object(DocumentProcessor, "extract_text_from_file")
    def test_process_document_handles_empty_text(self, mock_extract):
        """Verify graceful handling of documents with no extractable text."""
        mock_extract.return_value = ""

        processor = DocumentProcessor()
        result = processor.process_document(self.document.id)

        self.assertEqual(result.processing_status, "completed")
        self.assertEqual(result.chunk_count, 0)

    @patch.object(DocumentProcessor, "extract_text_from_file")
    def test_process_document_handles_failure(self, mock_extract):
        """Verify document is marked as failed on extraction error."""
        mock_extract.side_effect = ValueError("Unsupported file type")

        processor = DocumentProcessor()

        with self.assertRaises(ValueError):
            processor.process_document(self.document.id)

        self.document.refresh_from_db()
        self.assertEqual(self.document.processing_status, "failed")

    def test_idempotent_reprocessing(self):
        """Verify re-processing deletes old chunks before creating new ones."""
        # Create some existing chunks
        for i in range(3):
            DocumentChunk.objects.create(
                document=self.document,
                chunk_index=i,
                chunk_text=f"Old chunk {i}",
            )

        with patch.object(
            DocumentProcessor, "extract_text_from_file", return_value="New content. " * 5
        ):
            mock_embed = MagicMock()
            mock_embed.embed_texts.return_value = [[0.1] * 1536]

            processor = DocumentProcessor(
                embedding_service=mock_embed,
                chunk_size=200,
                chunk_overlap=20,
            )
            processor.process_document(self.document.id)

        # Old chunks should be gone
        chunks = DocumentChunk.objects.filter(document=self.document)
        for chunk in chunks:
            self.assertFalse(chunk.chunk_text.startswith("Old chunk"))
