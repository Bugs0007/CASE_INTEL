"""Portal-facing helpers shared by the adapters.

Everything here exists because of something observed on the live portals
(2026-10-10, see docs/causelists/COVERAGE.md):

- hcservices answers a CAPTCHA failure with the PLAIN text `Invalid Captcha`
  or `{"Error":"ERROR_VAL"}` (an empty CAPTCHA), and bharat-courts only
  retries on the quoted string `"Invalid Captcha"`, returning the rest as a
  success. `classify_hcservices_index` tells these apart from the one
  response that means "no list": `No cause List Available for this date`.
- an index row can point at a PDF the court has not uploaded; the link then
  returns the 21-byte body `Order not uploaded` (HTTP 200, text/html).
  `download_pdf` reports that as `not_uploaded`, not as an error and not as
  a document.
- PDFs are streamed to disk, never held whole in memory (t3.small box).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path

import httpx
from django.conf import settings

from .exceptions import CauseListFetchError

logger = logging.getLogger(__name__)

INDEX_TABLE = "table"
INDEX_NONE_AVAILABLE = "none_available"
INDEX_CAPTCHA_FAILED = "captcha_failed"
INDEX_OTHER = "other"

_PDF_MAGIC = b"%PDF"
_BOM = b"\xef\xbb\xbf"


def classify_hcservices_index(text: str) -> tuple[str, str]:
    """(kind, detail) for the body of an hcservices `showCauseList` POST.

    Order matters: a CAPTCHA failure must never be read as "nothing
    published", which is the mistake the previous Telangana code made for
    any short table-less body.
    """
    body = (text or "").strip().lstrip("﻿").strip()
    low = body.lower()
    if not body:
        return INDEX_OTHER, "empty response"
    if "invalid captcha" in low or "error_val" in low:
        return INDEX_CAPTCHA_FAILED, body[:80]
    if "no cause list available" in low:
        return INDEX_NONE_AVAILABLE, body[:80]
    if "<table" in low and "<a " in low and "href" in low:
        return INDEX_TABLE, ""
    return INDEX_OTHER, body[:120]


def classify_pdf_head(head: bytes) -> str:
    """'pdf' | 'not_uploaded' | 'other' from the first bytes of a body."""
    head = head or b""
    if head.startswith(_BOM):
        head = head[len(_BOM):]
    if head.lstrip().startswith(_PDF_MAGIC):
        return "pdf"
    if b"order not uploaded" in head.lower():
        return "not_uploaded"
    return "other"


@dataclass
class Download:
    kind: str  # pdf | not_uploaded | other
    size: int = 0
    sha256: str = ""
    preview: bytes = b""


class Pacer:
    """Minimum gap between requests to one host."""

    def __init__(self, min_gap: float | None = None):
        self.min_gap = (
            float(min_gap)
            if min_gap is not None
            else float(getattr(settings, "CAUSE_LIST_MIN_REQUEST_GAP_SECONDS", 1.5))
        )
        self._last = 0.0

    async def wait(self) -> None:
        gap = time.monotonic() - self._last
        if self._last and gap < self.min_gap:
            await asyncio.sleep(self.min_gap - gap)
        self._last = time.monotonic()


async def download_pdf(
    http,  # bharat_courts RateLimitedClient
    url: str,
    dest: Path,
    *,
    pacer: Pacer,
    headers: dict | None = None,
    attempts: int = 3,
) -> Download:
    """Stream `url` into `dest` if (and only if) it is a PDF.

    A leading UTF-8 BOM (the portal prepends one) is cut off while writing,
    so the file on disk starts at %PDF. Transport errors are retried
    (bharat-courts' own retry covers only ConnectError/ReadTimeout, and the
    portal does drop connections: RemoteProtocolError was seen live).
    """
    max_bytes = int(getattr(settings, "CAUSE_LIST_MAX_DOC_BYTES", 40 * 1024 * 1024))
    last_exc: Exception | None = None
    for attempt in range(1, attempts + 1):
        await pacer.wait()
        try:
            client = http._ensure_client()
            async with client.stream("GET", url, headers=headers or {}) as resp:
                resp.raise_for_status()
                digest = hashlib.sha256()
                size = 0
                head = b""
                kind = None
                out = None
                try:
                    async for chunk in resp.aiter_bytes():
                        if kind is None:
                            head += chunk
                            if len(head) < 16:
                                continue  # not enough bytes to classify yet
                            kind = classify_pdf_head(head)
                            if kind != "pdf":
                                return Download(kind=kind, size=len(head), preview=head[:200])
                            data = head[len(_BOM):] if head.startswith(_BOM) else head
                            data = data[data.find(_PDF_MAGIC):]
                            out = dest.open("wb")
                            out.write(data)
                            digest.update(data)
                            size = len(data)
                            continue
                        size += len(chunk)
                        if size > max_bytes:
                            raise CauseListFetchError(f"{url}: larger than {max_bytes} bytes")
                        out.write(chunk)
                        digest.update(chunk)
                    if kind is None:  # body ended before 16 bytes: never a PDF
                        guess = classify_pdf_head(head)
                        return Download(
                            kind="not_uploaded" if guess == "not_uploaded" else "other",
                            size=len(head),
                            preview=head[:200],
                        )
                finally:
                    if out is not None:
                        out.close()
                return Download(kind="pdf", size=size, sha256=digest.hexdigest())
        except CauseListFetchError:
            raise
        except (httpx.TransportError, httpx.HTTPStatusError) as exc:
            last_exc = exc
            if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code < 500:
                raise CauseListFetchError(f"{url}: HTTP {exc.response.status_code}") from exc
            logger.warning("Cause-list download attempt %d/%d failed: %s", attempt, attempts, exc)
            await asyncio.sleep(2 * attempt)
    raise CauseListFetchError(f"{url}: download failed after {attempts} attempts: {last_exc}")


def safe_name(text: str, limit: int = 60) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", text or "").strip("_")[:limit] or "doc"


def run_bounded(coro, seconds: float):
    """asyncio.run with a wall-clock budget. Raises CauseListFetchError on
    timeout so adapters can turn it into a `fetch_error` FetchResult."""
    try:
        return asyncio.run(asyncio.wait_for(coro, timeout=seconds))
    except asyncio.TimeoutError as exc:
        raise CauseListFetchError(f"timed out after {seconds:.0f}s") from exc


def setting(name: str, default):
    return getattr(settings, name, default)
