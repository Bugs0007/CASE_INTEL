"""
Court-order sync (Phase B): fetch order/judgment PDFs the portal has
uploaded for a tracked case and feed them into the EXISTING document
pipeline.

Runs ONLY inside the process_jobs worker (job_type="order_sync") -- never
inline in a request. Enqueued by court_tracking.enqueue_order_sync() after
a successful confirm/refresh, so it inherits the per-case refresh cooldown:
no new portal-facing endpoint or schedule exists for it.

Deliberately conservative toward the portal's download endpoints (more
abuse-sensitive than the status pages we already hit):
  - strictly sequential downloads, DOWNLOAD_DELAY_SECONDS apart, never
    parallel;
  - at most MAX_DOWNLOADS_PER_SYNC new orders per sync -- a backlog
    catches up across future refreshes instead of burst-downloading;
  - every listed order is saved as a PENDING CourtOrder row BEFORE its PDF
    is fetched (dedup on dedup_key), so a failed download is visible as
    "pending" and a later sync finishes the same row -- never a duplicate;
  - transient download errors (CAPTCHA, portal, dropped connection) are
    retried twice, 5 s then 15 s apart; a definite answer ("no longer
    listed") is not; two orders in a row failing stops the sync;
  - the portal's order NUMBER is a position, not an identity: HC Services
    numbers the Orders table 1..n by date at render time, so an order
    uploaded late (the 13 Aug order appearing after the 14 Aug one) shifts
    every later order up by one. A listed order whose key is new but whose
    date matches an order we hold that is no longer listed under its old
    key is the same order renumbered: the row is relabelled, nothing is
    downloaded. Without this the 14 Aug order was stored twice (as "2" and
    then "3") and "Order 2" showed on two hearings -- see
    reconcile_renumbered() and migration 0037 for the clean-up;
  - per-order failure isolation: one bad download skips that order and
    continues, it doesn't fail the sync.

Each downloaded PDF becomes a normal Document (document_type=
"court_order") saved through default_storage, then a document
ProcessingJob -- OCR-if-scanned, chunking, and embeddings all happen in
the existing pipeline, not here.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from datetime import date

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction

from core.models import ActivityLog, Case, CourtOrder, Document, ProcessingJob
from core.services.court_data import (
    CaptchaSolveError,
    CourtDataError,
    CourtOrderRecord,
    CourtPortalError,
    get_provider,
)

try:  # bharat-courts' transport; a dropped connection mid-download is transient
    import httpx

    _NETWORK_ERRORS: tuple = (httpx.HTTPError, OSError, TimeoutError)
except ImportError:  # pragma: no cover
    _NETWORK_ERRORS = (OSError, TimeoutError)
_TRANSIENT_ERRORS = (CaptchaSolveError, CourtPortalError, *_NETWORK_ERRORS)

logger = logging.getLogger(__name__)

DOWNLOAD_DELAY_SECONDS = 5
MAX_DOWNLOADS_PER_SYNC = 5
# Waits before the 1st and 2nd retry of one order's download (so at most
# three tries); only for transient errors.
RETRY_BACKOFF_SECONDS = (5, 15)
# Two orders in a row failing after all their retries means the portal is
# unwell: stop and leave the rest pending rather than keep hammering it.
MAX_CONSECUTIVE_PORTAL_FAILURES = 2
# A pending order that has failed this many whole syncs is marked failed and
# left alone (requeue_order_sync --retry-failed puts it back).
MAX_TOTAL_DOWNLOAD_ATTEMPTS = 6

ORDER_STORAGE_DIR = "documents/court_orders"

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")
# Written by _order_filename() when the portal listed no date for an order.
_UNDATED_TOKEN = "undated"
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _order_filename(case: Case, record: CourtOrderRecord) -> str:
    date_part = record.order_date.isoformat() if record.order_date else _UNDATED_TOKEN
    stem = f"{record.cnr}_order_{record.order_number}_{date_part}"
    return _FILENAME_SAFE_RE.sub("-", stem) + ".pdf"


def parse_order_filename(filename: str) -> CourtOrderRecord | None:
    """Inverse of _order_filename(): recover a CourtOrderRecord from a
    stored order PDF's name. Lives next to the writer above so the two
    can't drift apart.

    Returns None (and logs why) for anything unparseable -- callers scan
    whole storage directories, where one odd name must skip that file, not
    abort the scan. Never raises.

    The date segment is located by scanning "_"-separated segments RIGHT
    TO LEFT rather than just taking the last one, because
    default_storage.save() appends a random suffix on name collision
    (Django's Storage.get_available_name -> "<stem>_XXXXXXX.pdf"), which
    would otherwise sit where the date is expected. Anything after the
    date segment is that suffix and is ignored.
    """
    stem, dot, extension = filename.rpartition(".")
    if not dot or extension.lower() != "pdf":
        logger.warning("Skipping non-PDF order file %r.", filename)
        return None

    cnr, marker, rest = stem.partition("_order_")
    if not marker:
        logger.warning("Skipping order file %r: no '_order_' marker in the name.", filename)
        return None
    if not cnr:
        logger.warning("Skipping order file %r: empty CNR.", filename)
        return None

    segments = rest.split("_")
    for i in range(len(segments) - 1, -1, -1):
        segment = segments[i]
        if segment == _UNDATED_TOKEN:
            order_date = None
            break
        if _ISO_DATE_RE.match(segment):
            try:
                order_date = date.fromisoformat(segment)
            except ValueError:
                # Right shape, impossible value (e.g. "2026-13-45") --
                # keep scanning left; a real date may still be there.
                continue
            break
    else:
        logger.warning(
            "Skipping order file %r: no parseable order date in the name.", filename
        )
        return None

    order_number = "_".join(segments[:i])
    if not order_number:
        logger.warning("Skipping order file %r: no order number in the name.", filename)
        return None

    return CourtOrderRecord(cnr=cnr, order_number=order_number, order_date=order_date)


def order_sequence_sort_key(order_number: str) -> tuple:
    """Sort key putting orders in portal sequence.

    order_number is free text off the portal, so a plain string sort files
    "10" before "2". All-digit values sort numerically and first;
    anything else falls in after them, alphabetically.
    """
    value = (order_number or "").strip()
    if value.isdigit():
        return (0, int(value), "")
    return (1, 0, value.lower())


def _relabel(row: CourtOrder, record: CourtOrderRecord) -> None:
    """Point a held order at the portal's current number/date for it."""
    row.order_number = record.order_number
    row.dedup_key = record.dedup_key
    row.description = record.description or row.description
    row.judge = record.judge or row.judge
    fields = ["order_number", "dedup_key", "description", "judge"]
    if record.order_date != row.order_date:
        row.order_date = record.order_date
        fields.append("order_date")
        if row.document_id:
            Document.objects.filter(id=row.document_id).update(document_date=record.order_date)
    row.save(update_fields=fields)


def reconcile_renumbered(case: Case, records: list[CourtOrderRecord]) -> tuple[list[CourtOrderRecord], int]:
    """Match listed orders with new keys to held orders the portal now
    lists under a different number (see the module docstring).

    Pairs only by DATE and only unambiguously: for each date, the listed
    orders with new keys and the held orders no longer listed must be the
    same count; they are then paired in sequence order. Returns (the
    records still genuinely new, how many rows were relabelled).
    """
    listed_keys = {r.dedup_key for r in records}
    held = list(CourtOrder.objects.filter(case=case))
    held_keys = {o.dedup_key for o in held}
    unmatched = [r for r in records if r.dedup_key not in held_keys]
    stale = [o for o in held if o.dedup_key not in listed_keys]

    relabelled = 0
    remaining = list(unmatched)
    for day in sorted({r.order_date for r in unmatched if r.order_date}):
        recs = sorted(
            (r for r in unmatched if r.order_date == day),
            key=lambda r: order_sequence_sort_key(r.order_number),
        )
        rows = sorted(
            (o for o in stale if o.order_date == day),
            key=lambda o: order_sequence_sort_key(o.order_number),
        )
        if not rows or len(recs) != len(rows):
            continue
        for record, row in zip(recs, rows):
            logger.info(
                "Order sync for case %s: order dated %s renumbered on the portal "
                "(%s -> %s); relabelling instead of downloading it again.",
                case.id, day, row.order_number, record.order_number,
            )
            _relabel(row, record)
            remaining.remove(record)
            stale.remove(row)
            relabelled += 1
    return remaining, relabelled


def _normalised_text(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (text or "").lower())


def _pdf_text(pdf_bytes: bytes) -> str:
    try:
        from io import BytesIO

        from PyPDF2 import PdfReader

        return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf_bytes)).pages)
    except Exception:  # noqa: BLE001 -- unreadable PDF: not provably the same
        return ""


def _same_order_redated(
    case: Case, record: CourtOrderRecord, pdf_bytes: bytes, listed_keys: set[str]
) -> CourtOrder | None:
    """The held order `record` really is, when the portal changed its DATE
    (same number, old key no longer listed) -- proven by identical text,
    since the PDFs themselves are stamped per download and never hash
    alike. None when there's no such row or the text can't prove it."""
    candidates = [
        o
        for o in CourtOrder.objects.filter(case=case, order_number=record.order_number)
        .exclude(order_date=record.order_date)
        .exclude(dedup_key__in=listed_keys)
        .select_related("document")
        if o.document is not None and o.document.extracted_text
    ]
    if len(candidates) != 1:
        return None
    new_text = _normalised_text(_pdf_text(pdf_bytes))
    if len(new_text) < 200 or new_text != _normalised_text(candidates[0].document.extracted_text):
        return None
    return candidates[0]


class _DownloadFailed(Exception):
    """One order's PDF could not be fetched after the allowed retries."""

    def __init__(self, cause: Exception, *, transient: bool):
        super().__init__(str(cause))
        self.cause = cause
        self.transient = transient


def error_kind(exc_or_text) -> str:
    """"captcha" | "portal" | "other" -- the only thing about a sync failure
    that ever reaches the case page (never the raw message, which can quote
    the portal's own text)."""
    if isinstance(exc_or_text, CaptchaSolveError):
        return "captcha"
    if isinstance(exc_or_text, (CourtPortalError, *_NETWORK_ERRORS)):
        return "portal"
    text = str(exc_or_text or "").lower()
    if "captcha" in text:
        return "captcha"
    if any(
        marker in text
        for marker in ("disconnect", "timed out", "timeout", "unrecognized", "portal", "connection", "server")
    ):
        return "portal"
    return "other"


def _download_with_retries(provider, config: dict, record: CourtOrderRecord) -> bytes:
    """download_order(), retried only for transient trouble: 1 try + up to
    len(RETRY_BACKOFF_SECONDS) retries, waiting 5 s then 15 s. "No longer
    listed" and other definite answers are not retried -- asking again
    cannot change them, and every attempt costs the portal a CAPTCHA'd
    search."""
    for attempt in range(len(RETRY_BACKOFF_SECONDS) + 1):
        try:
            return provider.download_order(config, record)
        except _TRANSIENT_ERRORS as exc:
            if attempt >= len(RETRY_BACKOFF_SECONDS):
                raise _DownloadFailed(exc, transient=True) from exc
            logger.info(
                "Order download for %s hit a transient error (%s); retrying in %ds.",
                record.dedup_key, type(exc).__name__, RETRY_BACKOFF_SECONDS[attempt],
            )
            time.sleep(RETRY_BACKOFF_SECONDS[attempt])
        except CourtDataError as exc:
            raise _DownloadFailed(exc, transient=False) from exc
    raise AssertionError("unreachable")  # pragma: no cover


def _ensure_row(case: Case, record: CourtOrderRecord) -> tuple[CourtOrder, bool]:
    """The CourtOrder for a listed order, created PENDING if new. Idempotent
    on (case, dedup_key), so a re-listing never makes a second row."""
    return CourtOrder.objects.get_or_create(
        case=case,
        dedup_key=record.dedup_key,
        defaults={
            "owner": case.owner,
            "order_number": record.order_number,
            "order_date": record.order_date,
            "description": record.description,
            "judge": record.judge,
            "source": "ecourts",
            "download_status": CourtOrder.DOWNLOAD_PENDING,
        },
    )


def _empty_result() -> dict:
    return {
        "listed": 0, "new": 0, "downloaded": 0, "failed": 0,
        "pending": 0, "relabelled": 0, "stopped_early": False, "reason": "",
    }


def sync_case_orders(case: Case, progress_callback=None) -> dict:
    """List the orders the portal shows for a tracked case and fetch their
    PDFs. Worker entry point.

    Every listed order becomes a CourtOrder row immediately (PENDING), and
    every PENDING row -- new, or left over from an earlier sync -- is worked
    on, MAX_DOWNLOADS_PER_SYNC at a time. A download that keeps failing
    leaves its row pending with the error noted, to be finished in place on
    a later sync; it never makes a second row.

    Returns {"listed", "new", "downloaded", "failed", "pending",
    "relabelled", "stopped_early", "reason"}: the job's recorded result.
    `failed` is downloads that failed THIS run; `pending` is rows still
    waiting for a PDF afterwards (some only because of the per-sync cap).

    Raises CourtDataError only if the LISTING itself fails (nothing to
    work with); individual download failures are recorded, not raised.
    """
    if not case.tracking_enabled or not case.tracking_config:
        logger.info("Order sync skipped for case %s: tracking not enabled/configured.", case.id)
        return _empty_result()

    config = dict(case.tracking_config)
    # Cascade-shaped configs carry no CNR; the portals' order listing is
    # CNR-keyed, so inject the CNR persisted on first successful fetch.
    if not config.get("cnr") and case.cnr_number:
        config["cnr"] = case.cnr_number
    if not config.get("cnr"):
        logger.info("Order sync skipped for case %s: no CNR known yet.", case.id)
        return _empty_result()

    provider = get_provider()
    records = provider.list_orders(config)
    by_key = {r.dedup_key: r for r in records}
    listed_keys = set(by_key)

    new_records, relabelled = reconcile_renumbered(case, records)
    for record in new_records:
        _ensure_row(case, record)

    # Orders we were still waiting for that the portal has stopped listing:
    # nothing to fetch any more.
    CourtOrder.objects.filter(case=case, download_status=CourtOrder.DOWNLOAD_PENDING).exclude(
        dedup_key__in=listed_keys
    ).update(
        download_status=CourtOrder.DOWNLOAD_FAILED,
        last_download_error="No longer listed on the court portal.",
    )

    work = list(
        CourtOrder.objects.filter(
            case=case, download_status=CourtOrder.DOWNLOAD_PENDING, dedup_key__in=listed_keys
        ).order_by("-order_date", "-id")
    )
    to_download = work[:MAX_DOWNLOADS_PER_SYNC]
    if len(work) > MAX_DOWNLOADS_PER_SYNC:
        logger.info(
            "Order sync for case %s: %d orders waiting, capping this sync at %d "
            "(the rest are picked up on later syncs).",
            case.id, len(work), MAX_DOWNLOADS_PER_SYNC,
        )

    downloaded = 0
    failed = 0
    consecutive_portal_failures = 0
    stopped_early = False
    reason = ""
    total = len(to_download)
    if progress_callback:
        progress_callback(0, total)

    for i, row in enumerate(to_download):
        if consecutive_portal_failures >= MAX_CONSECUTIVE_PORTAL_FAILURES:
            stopped_early = True
            logger.warning(
                "Order sync for case %s stopped after %d portal failures in a row; "
                "%d order(s) left pending for the next sync.",
                case.id, consecutive_portal_failures, total - i,
            )
            break
        if i > 0:
            time.sleep(DOWNLOAD_DELAY_SECONDS)
        record = by_key[row.dedup_key]
        try:
            pdf_bytes = _download_with_retries(provider, config, record)
        except _DownloadFailed as exc:
            failed += 1
            row.download_attempts += 1
            row.last_download_error = str(exc.cause)[:300]
            if row.download_attempts >= MAX_TOTAL_DOWNLOAD_ATTEMPTS:
                row.download_status = CourtOrder.DOWNLOAD_FAILED
            row.save(update_fields=["download_attempts", "last_download_error", "download_status"])
            consecutive_portal_failures = consecutive_portal_failures + 1 if exc.transient else 0
            reason = error_kind(exc.cause)
            logger.warning(
                "Order sync for case %s: download failed for %s (attempt %d): %s",
                case.id, record.dedup_key, row.download_attempts, exc.cause,
            )
            if progress_callback:
                progress_callback(downloaded + failed, total)
            continue
        consecutive_portal_failures = 0

        redated = _same_order_redated(case, record, pdf_bytes, listed_keys)
        if redated is not None:
            logger.info(
                "Order sync for case %s: order %s re-dated on the portal (%s -> %s); "
                "same text, relabelling instead of storing it twice.",
                case.id, record.order_number, redated.order_date, record.order_date,
            )
            row.delete()  # the pending row just made for the new date
            _relabel(redated, record)
            relabelled += 1
            if progress_callback:
                progress_callback(downloaded + failed + 1, total)
            continue

        filename = _order_filename(case, record)
        saved_name = default_storage.save(f"{ORDER_STORAGE_DIR}/{filename}", ContentFile(pdf_bytes))
        with transaction.atomic():
            document = Document.objects.create(
                owner=case.owner,
                case=case,
                filename=filename,
                file_path=saved_name,
                file_type="pdf",
                file_size=len(pdf_bytes),
                document_type="court_order",
                document_date=record.order_date,
                processing_status="pending",
                content_hash=hashlib.sha256(pdf_bytes).hexdigest(),
            )
            row.document = document
            row.download_status = CourtOrder.DOWNLOAD_DOWNLOADED
            row.download_attempts += 1
            row.last_download_error = ""
            row.save(update_fields=["document", "download_status", "download_attempts", "last_download_error"])
        ProcessingJob.enqueue(document)
        downloaded += 1
        if progress_callback:
            progress_callback(downloaded + failed, total)
        logger.info(
            "Order sync for case %s: downloaded %s (%d bytes) -> document %d",
            case.id, record.dedup_key, len(pdf_bytes), document.id,
        )

    if downloaded:
        ActivityLog.objects.create(
            owner=case.owner,
            case=case,
            activity_type="court_order_fetched",
            description=(
                f"eCourts: {downloaded} new order(s) downloaded for "
                f"{case.case_number} and queued for processing."
            ),
        )

    return {
        "listed": len(records),
        "new": len(new_records),
        "downloaded": downloaded,
        "failed": failed,
        "pending": CourtOrder.objects.filter(case=case, download_status=CourtOrder.DOWNLOAD_PENDING).count(),
        "relabelled": relabelled,
        "stopped_early": stopped_early,
        "reason": reason,
    }
