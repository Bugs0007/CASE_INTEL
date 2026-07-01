"""
Document processing pipeline for the Case Intel application.

Improvements over the original:
    1. SHA-256 deduplication — identical files skip embedding entirely.
       Chunks from the original document are cloned for the new document row.
    2. spaCy sentence-aware chunking — respects sentence boundaries so
       legal clauses are never split mid-thought. Falls back to regex if
       spaCy is not installed.
    3. tsvector population — after bulk_create, a single raw SQL UPDATE
       populates the full-text search vector on each chunk, enabling
       BM25 keyword search in VectorSearchService without a separate index.
"""

import hashlib
import logging
import re

from django.db import connection, transaction

from core.models import Document, DocumentChunk
from core.services.ai_service_factory import get_embedding_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunking parameters
# ---------------------------------------------------------------------------
DEFAULT_CHUNK_SIZE = 500          # characters — tighter for legal clauses
DEFAULT_CHUNK_OVERLAP = 100       # characters
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
        self._nlp = None  # lazy-loaded spaCy model

    # ------------------------------------------------------------------
    # Lazy service initialisation
    # ------------------------------------------------------------------

    def _get_embedding_service(self):
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    def _get_nlp(self):
        """Load spaCy model once, fall back gracefully if not installed."""
        if self._nlp is not None:
            return self._nlp
        try:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_sm", disable=["ner", "tagger", "parser"])
                if "sentencizer" not in self._nlp.pipe_names:
                    self._nlp.add_pipe("sentencizer")
            except OSError:
                logger.warning(
                    "spaCy model 'en_core_web_sm' not found. "
                    "Run: python -m spacy download en_core_web_sm  "
                    "Falling back to blank sentencizer."
                )
                self._nlp = spacy.blank("en")
                self._nlp.add_pipe("sentencizer")
        except ImportError:
            logger.warning(
                "spaCy not installed. Falling back to regex sentence splitting. "
                "Install with: pip install spacy"
            )
            self._nlp = None
        return self._nlp

    # ------------------------------------------------------------------
    # SHA-256 hashing
    # ------------------------------------------------------------------

    @staticmethod
    def compute_file_hash(file_path: str) -> str:
        """Return the SHA-256 hex digest of a file's raw bytes."""
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for block in iter(lambda: f.read(65536), b""):
                h.update(block)
        return h.hexdigest()

    # ------------------------------------------------------------------
    # Text extraction
    # ------------------------------------------------------------------

    @staticmethod
    def extract_text_from_file(file_path: str, file_type: str) -> str:
        """Extract plain text from a document file."""
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
            raise ImportError("pip install PyPDF2")
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
            raise ImportError("pip install python-docx")
        doc = docx.Document(file_path)
        return "\n".join(para.text for para in doc.paragraphs if para.text.strip())

    # ------------------------------------------------------------------
    # Text chunking — spaCy sentence-aware
    # ------------------------------------------------------------------

    def chunk_text(self, text: str) -> list[str]:
        """Split text into overlapping chunks that respect sentence boundaries."""
        if not text.strip():
            return []

        text = re.sub(r"\s+", " ", text).strip()

        sentences = self._split_into_sentences(text)
        if not sentences:
            return []

        chunks: list[str] = []
        current_sentences: list[str] = []
        current_len = 0

        for sentence in sentences:
            sent_len = len(sentence)

            if sent_len > self._chunk_size and not current_sentences:
                for hard_chunk in self._hard_split(sentence):
                    chunks.append(hard_chunk)
                    if len(chunks) >= MAX_CHUNKS_PER_DOCUMENT:
                        return chunks
                continue

            if current_len + sent_len > self._chunk_size and current_sentences:
                chunks.append(" ".join(current_sentences))
                if len(chunks) >= MAX_CHUNKS_PER_DOCUMENT:
                    return chunks

                while current_sentences and current_len > self._chunk_overlap:
                    removed = current_sentences.pop(0)
                    current_len -= len(removed) + 1

            current_sentences.append(sentence)
            current_len += sent_len + 1

        if current_sentences:
            chunks.append(" ".join(current_sentences))

        logger.debug("Chunked %d chars → %d chunks", len(text), len(chunks))
        return chunks

    def _split_into_sentences(self, text: str) -> list[str]:
        """Return a list of sentences using spaCy or regex fallback."""
        nlp = self._get_nlp()
        if nlp is not None:
            doc = nlp(text)
            return [sent.text.strip() for sent in doc.sents if sent.text.strip()]

        parts = re.split(r'(?<=[.?!])\s+(?=[A-Z])', text)
        return [p.strip() for p in parts if p.strip()]

    def _hard_split(self, text: str) -> list[str]:
        """Hard-split an oversized sentence at word boundaries."""
        words = text.split()
        chunk, chunks = [], []
        length = 0
        for word in words:
            if length + len(word) > self._chunk_size and chunk:
                chunks.append(" ".join(chunk))
                chunk, length = [], 0
            chunk.append(word)
            length += len(word) + 1
        if chunk:
            chunks.append(" ".join(chunk))
        return chunks

    # ------------------------------------------------------------------
    # tsvector population
    # ------------------------------------------------------------------

    @staticmethod
    def _populate_search_vectors(document_id: int) -> None:
        """Update search_vector for all chunks of a document in one SQL call."""
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE document_chunks
                SET    search_vector = to_tsvector('english', chunk_text)
                WHERE  document_id = %s
                """,
                [document_id],
            )
        logger.debug("tsvector populated for document %d", document_id)

    # ------------------------------------------------------------------
    # Deduplication helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _clone_chunks_from(source_doc: Document, target_doc: Document) -> int:
        """Copy chunk rows from source_doc to target_doc."""
        source_chunks = list(
            DocumentChunk.objects.filter(document=source_doc).order_by("chunk_index")
        )
        if not source_chunks:
            return 0

        cloned = [
            DocumentChunk(
                document=target_doc,
                chunk_index=chunk.chunk_index,
                chunk_text=chunk.chunk_text,
                embedding=chunk.embedding,
                search_vector=chunk.search_vector,
            )
            for chunk in source_chunks
        ]
        DocumentChunk.objects.bulk_create(cloned)
        return len(cloned)

    # ------------------------------------------------------------------
    # Main processing pipeline
    # ------------------------------------------------------------------

    @transaction.atomic
    def process_document(self, document_id: int) -> Document:
        """Run the full processing pipeline for a document."""
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
            file_hash = self.compute_file_hash(document.file_path)
            document.content_hash = file_hash
            document.save(update_fields=["content_hash"])

            existing = (
                Document.objects
                .filter(content_hash=file_hash, processing_status="completed")
                .exclude(id=document_id)
                .first()
            )

            if existing and existing.chunk_count:
                logger.info(
                    "Document %d is a duplicate of document %d (hash=%s). "
                    "Cloning %d chunks instead of re-embedding.",
                    document_id,
                    existing.id,
                    file_hash[:12],
                    existing.chunk_count,
                )
                extracted_text = self.extract_text_from_file(
                    document.file_path, document.file_type or ""
                )
                document.extracted_text = extracted_text

                n_cloned = self._clone_chunks_from(existing, document)
                document.processing_status = "completed"
                document.chunk_count = n_cloned
                document.save(update_fields=["extracted_text", "processing_status", "chunk_count"])
                return document

            extracted_text = self.extract_text_from_file(
                document.file_path, document.file_type or ""
            )
            document.extracted_text = extracted_text

            if not extracted_text.strip():
                logger.warning("No text extracted from document %d", document_id)
                document.processing_status = "completed"
                document.chunk_count = 0
                document.save(update_fields=["extracted_text", "processing_status", "chunk_count"])
                return document

            chunks = self.chunk_text(extracted_text)

            embedding_service = self._get_embedding_service()
            embeddings = embedding_service.embed_texts(chunks)

            DocumentChunk.objects.filter(document=document).delete()

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

            self._populate_search_vectors(document_id)

            document.processing_status = "completed"
            document.chunk_count = len(chunk_objects)
            document.save(update_fields=["extracted_text", "processing_status", "chunk_count"])

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
