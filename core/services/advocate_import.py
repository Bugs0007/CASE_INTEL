"""
Advocate case import: bulk-create Cases from selected eCourts
advocate-search results, fetching each one's full case data through the
EXISTING court-tracking machinery (refresh_case_tracking).

Runs ONLY inside the process_jobs worker (job_type="advocate_import") --
never inline in a request. N sequential CAPTCHA-gated fetches can run
well past a request timeout, unlike a single search call (see
core/views/advocate_search.py, which IS synchronous -- the advocate
search itself needs no per-case fetch, just one portal call).

Deliberately conservative toward the portal, same posture as
court_order_sync.py:
  - strictly sequential, IMPORT_DELAY_SECONDS apart, never parallel;
  - per-case failure isolation: one bad fetch is recorded under "failed"
    and the batch continues;
  - two distinct "already exists" outcomes, since Case.case_number is
    GLOBALLY unique (not scoped per owner, see core/models/case.py): a
    CNR this user already tracks is "skipped_duplicate"; a case_number
    some OTHER user already created collides at the DB level and is
    "skipped_conflict" instead of raising a 500 for the whole batch. This
    is a pre-existing schema property (case_number unique=True predates
    this feature) that becomes more likely to bite now that cases are
    being bulk-added from a shared external source rather than typed in
    by hand -- flagged, not changed, here.
"""

from __future__ import annotations

import logging
import time

from django.db import IntegrityError, transaction

from core.models import ActivityLog, Case, ProcessingJob
from core.services.court_data import CourtDataError
from core.services.court_tracking import refresh_case_tracking

logger = logging.getLogger(__name__)

IMPORT_DELAY_SECONDS = 1


def _case_title(petitioner: str, respondent: str, fallback: str) -> str:
    parts = [p for p in (petitioner, respondent) if p]
    return " vs ".join(parts) if parts else fallback


def run_advocate_import(job: ProcessingJob, progress_callback=None) -> None:
    """Worker entry point for job_type="advocate_import".

    job.payload["selected"] is a list of dicts as returned by the
    advocate-search endpoint (core.services.court_data.CaseInfo.to_dict()
    shape) plus "court_type" injected by the view: {"cnr_number",
    "court_type", "case_number", "petitioner", "respondent",
    "court_name", ...}. Writes the outcome back into job.payload (never
    raises -- per-item failures are isolated, and the worker's own
    except/finally only sees this function return normally or raise on a
    genuine bug).
    """
    selected = (job.payload or {}).get("selected", [])
    total = len(selected)

    created: list[int] = []
    skipped_duplicate: list[str] = []
    skipped_conflict: list[str] = []
    failed: list[dict] = []

    if progress_callback:
        progress_callback(0, total)

    for i, item in enumerate(selected):
        if i > 0:
            time.sleep(IMPORT_DELAY_SECONDS)

        cnr = (item.get("cnr_number") or "").strip()
        court_type = item.get("court_type") or "district"

        if not cnr:
            failed.append({"cnr": cnr, "error": "Missing CNR."})
            if progress_callback:
                progress_callback(i + 1, total)
            continue

        if Case.objects.filter(owner=job.owner, cnr_number=cnr).exists():
            skipped_duplicate.append(cnr)
            if progress_callback:
                progress_callback(i + 1, total)
            continue

        case_number = item.get("case_number") or cnr
        title = _case_title(item.get("petitioner", ""), item.get("respondent", ""), case_number)

        try:
            with transaction.atomic():
                case = Case.objects.create(
                    owner=job.owner,
                    case_number=case_number,
                    title=title,
                    client_name="",
                    court_type=court_type,
                    tracking_config={"court_type": court_type, "cnr": cnr},
                    tracking_enabled=True,
                )
        except IntegrityError:
            logger.info(
                "Advocate import: case_number %r already tracked by another owner -- skipping.",
                case_number,
            )
            skipped_conflict.append(cnr)
            if progress_callback:
                progress_callback(i + 1, total)
            continue

        try:
            refresh_case_tracking(case)
        except CourtDataError as exc:
            logger.warning("Advocate import: fetch failed for CNR %s: %s", cnr, exc)
            failed.append({"cnr": cnr, "error": str(exc)})
            if progress_callback:
                progress_callback(i + 1, total)
            continue

        created.append(case.id)
        if progress_callback:
            progress_callback(i + 1, total)

    ProcessingJob.objects.filter(id=job.id).update(
        payload={
            "selected": selected,
            "created": created,
            "skipped_duplicate": skipped_duplicate,
            "skipped_conflict": skipped_conflict,
            "failed": failed,
        }
    )

    if created:
        ActivityLog.objects.create(
            owner=job.owner,
            case=None,
            activity_type="advocate_search_import",
            description=f"Advocate search: {len(created)} case(s) added from eCourts search results.",
        )
