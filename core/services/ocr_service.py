"""
OCR support for scanned PDFs, built on ocrmypdf.

Runs ONLY inside the `process_jobs` background worker (DocumentProcessor
is never called from a request cycle anymore) -- OCR takes minutes, far
past gunicorn's 120s timeout.

Memory discipline (production is a 1GB t3.micro):
    - The source PDF is streamed from storage to a temp file in 64KB
      blocks, never held in memory.
    - The PDF is OCRed in OCR_PAGE_BATCH-page slices, each written to its
      own temp file. pikepdf (an ocrmypdf dependency) loads pages lazily,
      so slicing never materialises the whole document.
    - ocrmypdf runs as a subprocess per slice with --jobs 1: page
      rasterisation/tesseract memory is bounded to one page at a time and
      is fully returned to the OS when the subprocess exits.

System dependencies (NOT pip-installable -- see deploy/provision.sh and
PROVISIONING.md): tesseract-ocr and ghostscript must be on PATH.
"""

import logging
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

# Pages OCRed per ocrmypdf subprocess invocation.
OCR_PAGE_BATCH = 10

# A PDF whose direct extraction yields fewer characters than this (in
# total, or per page on average) is treated as scanned. Real text pages
# run thousands of chars/page; scanned pages yield 0 or stray artifacts.
MIN_TOTAL_CHARS = 100
MIN_CHARS_PER_PAGE = 25


def needs_ocr(extracted_text: str, page_count: int) -> bool:
    """True when direct text extraction yielded negligible real text."""
    n_chars = len(extracted_text.strip())
    if page_count <= 0:
        return n_chars < MIN_TOTAL_CHARS
    return n_chars < max(MIN_TOTAL_CHARS, MIN_CHARS_PER_PAGE * page_count)


def _run_ocrmypdf(input_path: Path, output_path: Path) -> None:
    """OCR one page-slice via an ocrmypdf subprocess.

    --skip-text leaves any page that already has real text untouched;
    --jobs 1 caps concurrency (memory, not speed, is the constraint);
    --optimize 0 skips the output-size optimisation passes we don't need
    for a throwaway intermediate file.
    """
    cmd = [
        sys.executable, "-m", "ocrmypdf",
        "--skip-text",
        "--jobs", "1",
        "--optimize", "0",
        "--quiet",
        str(input_path),
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ocrmypdf failed (exit {result.returncode}): "
            f"{result.stderr.strip()[-2000:]}"
        )


def extract_text_with_ocr(file_path: str) -> str:
    """OCR a stored PDF in page-batches and return its full text.

    The OCRed page-slices are used only for text extraction and then
    discarded -- the original file in storage is never modified.
    """
    import pikepdf
    import PyPDF2

    with tempfile.TemporaryDirectory(prefix="caseintel_ocr_") as tmp:
        tmp_dir = Path(tmp)
        source = tmp_dir / "source.pdf"

        # Stream the file out of storage (local disk or S3) in blocks.
        with default_storage.open(file_path, "rb") as src, open(source, "wb") as dst:
            shutil.copyfileobj(src, dst, length=65536)

        text_parts: list[str] = []
        with pikepdf.open(source) as pdf:
            n_pages = len(pdf.pages)
            for start in range(0, n_pages, OCR_PAGE_BATCH):
                end = min(start + OCR_PAGE_BATCH, n_pages)
                batch_in = tmp_dir / f"batch_{start}.pdf"
                batch_out = tmp_dir / f"batch_{start}_ocr.pdf"

                slice_pdf = pikepdf.new()
                for page in pdf.pages[start:end]:
                    slice_pdf.pages.append(page)
                slice_pdf.save(batch_in)
                slice_pdf.close()

                _run_ocrmypdf(batch_in, batch_out)

                with open(batch_out, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    for page in reader.pages:
                        page_text = page.extract_text()
                        if page_text:
                            text_parts.append(page_text)

                # Free the slice files immediately rather than waiting for
                # the TemporaryDirectory cleanup at the end.
                batch_in.unlink(missing_ok=True)
                batch_out.unlink(missing_ok=True)

                logger.info("OCR progress: pages %d-%d of %d done", start + 1, end, n_pages)

        return "\n".join(text_parts)
