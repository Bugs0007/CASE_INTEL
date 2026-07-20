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
  - dedup via CourtOrder.dedup_key BEFORE downloading, so a re-fetch
    never re-downloads (or duplicates) an already-ingested order;
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

from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

from core.models import ActivityLog, Case, CourtOrder, Document, ProcessingJob
from core.services.court_data import CourtDataError, CourtOrderRecord, get_provider

logger = logging.getLogger(__name__)

DOWNLOAD_DELAY_SECONDS = 5
MAX_DOWNLOADS_PER_SYNC = 5

_FILENAME_SAFE_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _order_filename(case: Case, record: CourtOrderRecord) -> str:
    date_part = record.order_date.isoformat() if record.order_date else "undated"
    stem = f"{record.cnr}_order_{record.order_number}_{date_part}"
    return _FILENAME_SAFE_RE.sub("-", stem) + ".pdf"


def sync_case_orders(case: Case, progress_callback=None) -> dict:
    """Fetch newly-listed orders for a tracked case. Worker entry point.

    Returns {"listed": int, "new": int, "downloaded": int, "failed": int}.

    Raises CourtDataError only if the LISTING itself fails (nothing to
    work with); individual download failures are logged and skipped.
    """
    if not case.tracking_enabled or not case.tracking_config:
        logger.info("Order sync skipped for case %s: tracking not enabled/configured.", case.id)
        return {"listed": 0, "new": 0, "downloaded": 0, "failed": 0}

    config = dict(case.tracking_config)
    # Cascade-shaped configs carry no CNR; the portals' order listing is
    # CNR-keyed, so inject the CNR persisted on first successful fetch.
    if not config.get("cnr") and case.cnr_number:
        config["cnr"] = case.cnr_number
    if not config.get("cnr"):
        logger.info("Order sync skipped for case %s: no CNR known yet.", case.id)
        return {"listed": 0, "new": 0, "downloaded": 0, "failed": 0}

    provider = get_provider()
    records = provider.list_orders(config)

    known_keys = set(
        CourtOrder.objects.filter(case=case).values_list("dedup_key", flat=True)
    )
    new_records = [r for r in records if r.dedup_key not in known_keys]
    to_download = new_records[:MAX_DOWNLOADS_PER_SYNC]
    if len(new_records) > MAX_DOWNLOADS_PER_SYNC:
        logger.info(
            "Order sync for case %s: %d new orders, capping this sync at %d "
            "(the rest catch up on future refreshes).",
            case.id, len(new_records), MAX_DOWNLOADS_PER_SYNC,
        )

    downloaded = 0
    failed = 0
    total = len(to_download)
    if progress_callback:
        progress_callback(0, total)

    for i, record in enumerate(to_download):
        if i > 0:
            time.sleep(DOWNLOAD_DELAY_SECONDS)
        try:
            pdf_bytes = provider.download_order(config, record)
        except CourtDataError as exc:
            failed += 1
            logger.warning(
                "Order sync for case %s: download failed for %s: %s",
                case.id, record.dedup_key, exc,
            )
            continue

        filename = _order_filename(case, record)
        saved_name = default_storage.save(
            f"documents/court_orders/{filename}", ContentFile(pdf_bytes)
        )
        document = Document.objects.create(
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
        CourtOrder.objects.create(
            case=case,
            order_number=record.order_number,
            order_date=record.order_date,
            description=record.description,
            judge=record.judge,
            source="ecourts",
            dedup_key=record.dedup_key,
            document=document,
        )
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
    }
