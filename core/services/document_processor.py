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

from django.core.files.storage import default_storage
from django.db import connection

from core.models import Document, DocumentChunk
from core.services.ai_service_factory import get_embedding_service

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Chunking parameters
# ---------------------------------------------------------------------------
DEFAULT_CHUNK_SIZE = 500          # characters — tighter for legal clauses
DEFAULT_CHUNK_OVERLAP = 100       # characters
# Raised from 500 now that processing runs in the background worker with
# batched embedding — at 500 the old synchronous path silently indexed only
# the first ~100 pages of large documents.
MAX_CHUNKS_PER_DOCUMENT = 5000

# Chunks embedded + inserted per batch by process_document. Keeps peak
# memory bounded on the 1GB production box and gives the worker a natural
# point to report progress. 100 matches Gemini's per-request input cap.
EMBED_BATCH_SIZE = 100

# Max characters fed to spaCy in one nlp() call. A spaCy Doc costs roughly
# 100x its text in RAM (a 400-page document peaked the worker at ~440MB
# before this cap), and spaCy hard-errors past nlp.max_length (1M chars)
# anyway. Sentence-splitting segment by segment bounds that memory to
# ~10-20MB regardless of document size; the only cost is that a sentence
# straddling a segment boundary may be split in two.
NLP_SEGMENT_CHARS = 100_000


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
                # exclude (not disable!) every component and keep only the
                # model's tokenizer + a rule-based sentencizer. With the
                # parser disabled (as it always was here), sentence
                # boundaries already came from the sentencizer -- but
                # `disable=` still LOADS all component weights (~215MB
                # resident) and tok2vec/lemmatizer kept running per call.
                # `exclude=` skips loading them entirely (~25MB), which
                # matters on the 1GB production box.
                self._nlp = spacy.load(
                    "en_core_web_sm",
                    exclude=[
                        "tok2vec", "tagger", "parser", "ner",
                        "lemmatizer", "attribute_ruler",
                    ],
                )
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
        with default_storage.open(file_path, "rb") as f:
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
        # Always read as bytes and decode manually -- text-mode "r" isn't
        # reliably honored across storage backends (S3Storage streams bytes
        # regardless of the mode string passed to .open()).
        with default_storage.open(file_path, "rb") as f:
            return f.read().decode("utf-8", errors="replace")

    @staticmethod
    def _extract_pdf(file_path: str) -> str:
        try:
            import PyPDF2
        except ImportError:
            raise ImportError("pip install PyPDF2")
        text_parts = []
        with default_storage.open(file_path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text_parts.append(page_text)
        return "\n".join(text_parts)

    @staticmethod
    def _pdf_page_count(file_path: str) -> int:
        try:
            import PyPDF2
        except ImportError:
            raise ImportError("pip install PyPDF2")
        with default_storage.open(file_path, "rb") as f:
            return len(PyPDF2.PdfReader(f).pages)

    @staticmethod
    def _extract_docx(file_path: str) -> str:
        try:
            import docx
        except ImportError:
            raise ImportError("pip install python-docx")
        with default_storage.open(file_path, "rb") as f:
            doc = docx.Document(f)
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
        if nlp is None:
            parts = re.split(r'(?<=[.?!])\s+(?=[A-Z])', text)
            return [p.strip() for p in parts if p.strip()]

        sentences: list[str] = []
        for segment in self._segment_for_nlp(text):
            doc = nlp(segment)
            sentences.extend(
                sent.text.strip() for sent in doc.sents if sent.text.strip()
            )
        return sentences

    @staticmethod
    def _segment_for_nlp(text: str) -> list[str]:
        """Split text into <=NLP_SEGMENT_CHARS pieces at whitespace, so
        each spaCy call stays small (see NLP_SEGMENT_CHARS)."""
        if len(text) <= NLP_SEGMENT_CHARS:
            return [text]
        segments = []
        start = 0
        while start < len(text):
            end = min(start + NLP_SEGMENT_CHARS, len(text))
            if end < len(text):
                # Back up to the last space so words stay intact.
                space = text.rfind(" ", start, end)
                if space > start:
                    end = space
            segments.append(text[start:end])
            start = end
        return segments

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
                owner=target_doc.owner,
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

    def process_document(self, document_id: int, progress_callback=None) -> Document:
        """Run the full processing pipeline for a document.

        Args:
            document_id: The Document row to process.
            progress_callback: Optional ``callback(current, total)`` invoked
                after each embedded chunk-batch is persisted. Used by the
                ``process_jobs`` worker to report incremental progress.

        NOT wrapped in one big transaction on purpose: the slow work
        (OCR, embedding API calls) must not hold a transaction open, and
        progress written by the callback must be visible to other
        connections while the job is still running. Chunks are embedded
        and inserted in EMBED_BATCH_SIZE batches so peak memory stays
        bounded regardless of document size.
        """
        document = Document.objects.get(id=document_id)
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
                .filter(
                    content_hash=file_hash,
                    processing_status="completed",
                    owner=document.owner,
                )
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
                # Identical bytes -- reuse the original's extraction (and
                # its OCR result, if the original was a scanned PDF)
                # instead of re-extracting.
                document.extracted_text = existing.extracted_text
                document.ocr_applied = existing.ocr_applied

                n_cloned = self._clone_chunks_from(existing, document)
                document.processing_status = "completed"
                document.chunk_count = n_cloned
                document.save(update_fields=[
                    "extracted_text", "ocr_applied", "processing_status", "chunk_count",
                ])
                if progress_callback:
                    progress_callback(n_cloned, n_cloned)
                return document

            extracted_text = self.extract_text_from_file(
                document.file_path, document.file_type or ""
            )

            # --- OCR fallback for scanned PDFs (worker context only:
            # views enqueue a ProcessingJob rather than calling this
            # inline, so this slow path never runs in a request cycle).
            ocr_applied = False
            if (document.file_type or "").lower().lstrip(".") == "pdf":
                from core.services.ocr_service import extract_text_with_ocr, needs_ocr

                page_count = self._pdf_page_count(document.file_path)
                if needs_ocr(extracted_text, page_count):
                    logger.info(
                        "Document %d yields negligible text (%d chars over %d "
                        "pages) -- running ocrmypdf.",
                        document_id, len(extracted_text.strip()), page_count,
                    )
                    extracted_text = extract_text_with_ocr(document.file_path)
                    ocr_applied = True

            document.extracted_text = extracted_text
            document.ocr_applied = ocr_applied

            if not extracted_text.strip():
                logger.warning("No text extracted from document %d", document_id)
                document.processing_status = "completed"
                document.chunk_count = 0
                document.save(update_fields=[
                    "extracted_text", "ocr_applied", "processing_status", "chunk_count",
                ])
                return document

            chunks = self.chunk_text(extracted_text)
            total = len(chunks)
            if progress_callback:
                progress_callback(0, total)

            embedding_service = self._get_embedding_service()

            DocumentChunk.objects.filter(document=document).delete()

            # Embed + insert in batches: bounded memory, and each batch is
            # a natural progress checkpoint for the worker.
            n_created = 0
            for start in range(0, total, EMBED_BATCH_SIZE):
                batch = chunks[start : start + EMBED_BATCH_SIZE]
                embeddings = embedding_service.embed_texts(batch)
                DocumentChunk.objects.bulk_create([
                    DocumentChunk(
                        owner=document.owner,
                        document=document,
                        chunk_index=start + i,
                        chunk_text=chunk_text,
                        embedding=embedding,
                    )
                    for i, (chunk_text, embedding) in enumerate(zip(batch, embeddings))
                ])
                n_created += len(batch)
                if progress_callback:
                    progress_callback(n_created, total)

            self._populate_search_vectors(document_id)

            document.processing_status = "completed"
            document.chunk_count = n_created
            document.save(update_fields=[
                "extracted_text", "ocr_applied", "processing_status", "chunk_count",
            ])

            logger.info(
                "Document %d processed: %d chunks created%s",
                document_id,
                n_created,
                " (OCR applied)" if ocr_applied else "",
            )

        except Exception:
            logger.exception("Failed to process document %d", document_id)
            document.processing_status = "failed"
            document.save(update_fields=["processing_status"])
            raise

        return document
