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
  - case_number is scoped per owner, not global (see the
    (owner, case_number) UniqueConstraint on Case, core/models/case.py):
    two different advocates importing the same real court case (co-counsel,
    opposing counsel) each get their own independent row -- no conflict.
    A CNR this user already tracks is "skipped_duplicate", checked before
    the fetch even runs. The DB constraint still catches the rare residual
    case of two DIFFERENT CNRs resolving to the same case_number string
    for THIS SAME owner; that's recorded as "skipped_conflict" instead of
    raising a 500 for the whole batch.
"""

from __future__ import annotations

import logging
import time

from django.db import IntegrityError, transaction

from core.models import ActivityLog, Case, ProcessingJob
from core.services.court_data import CourtDataError
from core.services.court_tracking import refresh_case_tracking
from core.services.party_role import detect_party_role

logger = logging.getLogger(__name__)

IMPORT_DELAY_SECONDS = 1


def run_advocate_import(job: ProcessingJob, progress_callback=None) -> None:
    """Worker entry point for job_type="advocate_import".

    job.payload["selected"] is a list of dicts as returned by the
    advocate-search endpoint (core.services.court_data.CaseInfo.to_dict()
    shape) plus "court_type" injected by the view: {"cnr_number",
    "court_type", "case_number", "petitioner", "respondent",
    "court_name", ...}. job.payload["advocate_name"]/["bar_code"] (both
    default "") are the identity originally searched with -- see
    ProcessingJob.enqueue_advocate_import -- used below to auto-detect each
    new Case's user_party_role. Writes the outcome back into job.payload
    (never raises -- per-item failures are isolated, and the worker's own
    except/finally only sees this function return normally or raise on a
    genuine bug).
    """
    payload = job.payload or {}
    selected = payload.get("selected", [])
    advocate_name = payload.get("advocate_name", "") or ""
    bar_code = payload.get("bar_code", "") or ""
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

        try:
            with transaction.atomic():
                case = Case.objects.create(
                    owner=job.owner,
                    case_number=case_number,
                    # A free-text label the advocate assigns via the
                    # case-details form -- starts as the case number itself
                    # rather than an auto-generated "Petitioner vs
                    # Respondent" string, since that's no longer this
                    # field's purpose.
                    title=case_number,
                    client_name="",
                    court_type=court_type,
                    tracking_config={"court_type": court_type, "cnr": cnr},
                    tracking_enabled=True,
                )
        except IntegrityError:
            # Only reachable now for a same-owner collision -- a different
            # CNR whose case_number happens to match one this owner already
            # has (see the module docstring). A different owner sharing this
            # case_number is expected and no longer raises at all.
            logger.info(
                "Advocate import: owner %s already has a case numbered %r under a different CNR -- skipping.",
                job.owner_id,
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
        except Exception as exc:  # noqa: BLE001
            # Per-item isolation has to cover EVERY exception, not just
            # CourtDataError. This module documents "one bad fetch is recorded
            # under 'failed' and the batch continues", but anything unmapped
            # (a ValueError out of the provider's court_type dispatch, a
            # transport error, a parser bug) used to escape and kill the whole
            # job -- losing every case after the bad one and leaving already-
            # created rows behind with fetch_status="never_fetched".
            logger.exception("Advocate import: unexpected error for CNR %s", cnr)
            failed.append({"cnr": cnr, "error": f"{type(exc).__name__}: {exc}"})
            if progress_callback:
                progress_callback(i + 1, total)
            continue

        # Best-effort, one-shot: only runs right here at import time, never
        # on later periodic refreshes, so it can never silently overwrite a
        # role the advocate has since set manually.
        role = detect_party_role(advocate_name, bar_code, case.party_advocate_data)
        if role != "unknown":
            case.user_party_role = role
            case.save(update_fields=["user_party_role"])

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
