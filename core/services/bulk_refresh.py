"""Refresh every tracked case one advocate has -- the dashboard's "Refresh
all tracked cases" button.

Stand-in for a nightly refresh cron until the box is big enough to run one
(see docs in the Phase 1 report). It reuses refresh_case_tracking()
unchanged, so every guardrail of a single refresh still holds: the
one-real-fetch-per-case-per-hour limit (a case fetched in the last hour is
skipped and counted, not re-fetched), CourtFetchLog, the order-sync
enqueue, and the client-update draft for a new hearing date.

Shape of the work:
  - one ProcessingJob handles BATCH_SIZE cases, then queues a follow-on job
    carrying the remaining ids. The worker is a single FIFO loop, so this
    is what lets documents, order syncs and other advocates' jobs run in
    between instead of waiting behind a 200-case refresh.
  - only one tracking_refresh may be in flight system-wide
    (ProcessingJob.enqueue_tracking_refresh), same stance as the
    advocate_* fan-outs.
  - failures are isolated per case; MAX_CONSECUTIVE_PORTAL_ERRORS portal
    failures in a row stop the run, so an outage is never hammered.
  - cancel raises cancel_requested, checked between cases.
  - results accumulate in payload and are carried into each follow-on, so
    the last job in the chain holds the totals for the whole run.
"""

from __future__ import annotations

import logging

from django.db.models import F

from core.models import Case, JobAlreadyRunningError, ProcessingJob
from core.services.court_data import CourtDataError
from core.services.court_data.exceptions import CaptchaSolveError, CourtPortalError

logger = logging.getLogger(__name__)

BATCH_SIZE = 10
MAX_CONSECUTIVE_PORTAL_ERRORS = 5
MAX_FAILURES_KEPT = 50  # cap on the per-case failure list kept in payload

_ACTIVE = ("queued", "running")
_EMPTY_RESULTS = {
    "refreshed": 0,
    "rate_limited": 0,
    "failed": 0,
    "skipped": 0,
    "new_hearing_dates": 0,
    # Cases where the fetch found something new -- "5 updated" under the
    # dashboard button, as opposed to the count of dates above.
    "updated": 0,
    "drafts_created": 0,
}


class BulkRefreshCancelled(Exception):
    """Raised inside the worker when the advocate cancelled the run."""


class NothingToRefreshError(Exception):
    """The advocate has no open case with tracking enabled."""


def eligible_case_ids(owner) -> list[int]:
    """Open/pending cases with tracking on, least recently fetched first."""
    return list(
        Case.objects.filter(owner=owner, tracking_enabled=True, status__in=("open", "pending"))
        .order_by(F("last_fetched_at").asc(nulls_first=True), "id")
        .values_list("id", flat=True)
    )


def start_bulk_refresh(owner) -> ProcessingJob:
    """Raises NothingToRefreshError, or JobAlreadyRunningError when any
    tracking refresh (anyone's) is already queued or running."""
    case_ids = eligible_case_ids(owner)
    if not case_ids:
        raise NothingToRefreshError("None of your open cases has court tracking turned on.")
    return ProcessingJob.enqueue_tracking_refresh(owner, case_ids)


def chain_head(job: ProcessingJob) -> ProcessingJob:
    """Follow next_job_id to the job currently carrying the run."""
    seen = {job.id}
    while (job.payload or {}).get("next_job_id"):
        nxt = ProcessingJob.objects.filter(
            id=job.payload["next_job_id"], owner_id=job.owner_id, job_type="tracking_refresh"
        ).first()
        if nxt is None or nxt.id in seen:
            break
        seen.add(nxt.id)
        job = nxt
    return job


def run_status(root: ProcessingJob) -> dict:
    """The whole run's state, read from the head of the chain."""
    head = chain_head(root)
    payload = head.payload or {}
    total = payload.get("total", 0)
    results = {**_EMPTY_RESULTS, **payload.get("results", {})}
    return {
        "job_id": root.id,
        "current_job_id": head.id,
        "status": head.status,
        "total": total,
        "done": payload.get("done", 0),
        "results": results,
        "failures": payload.get("failures", []),
        "aborted_reason": payload.get("aborted_reason", ""),
        "error": head.error,
        "created_at": root.created_at,
        "finished_at": head.finished_at if head.status not in _ACTIVE else None,
    }


def cancel_run(root: ProcessingJob) -> ProcessingJob:
    return chain_head(root).request_cancel()


def _cancel_requested(job: ProcessingJob) -> bool:
    return ProcessingJob.objects.filter(id=job.id, cancel_requested=True).exists()


def run_tracking_refresh(job: ProcessingJob, progress_callback=None) -> dict:
    """Worker entry point (job_type="tracking_refresh")."""
    from core.services.court_tracking import (
        InvalidTrackingConfigError,
        MissingTrackingConfigError,
        TrackingNotEnabledError,
        refresh_case_tracking,
    )

    payload = dict(job.payload or {})
    # `pending` is saved after every case, so a worker that dies mid-batch
    # is reclaimed with exactly the cases it hadn't reached yet.
    pending = list(payload.get("case_ids", []))
    total = payload.get("total", len(pending))
    done = payload.get("done", 0)
    results = {**_EMPTY_RESULTS, **payload.get("results", {})}
    failures = list(payload.get("failures", []))
    consecutive = payload.get("consecutive_portal_errors", 0)

    def save(extra: dict | None = None) -> None:
        job.payload = {
            **payload,
            "case_ids": pending,
            "total": total,
            "done": done,
            "results": results,
            "failures": failures[-MAX_FAILURES_KEPT:],
            "consecutive_portal_errors": consecutive,
            **(extra or {}),
        }
        job.save(update_fields=["payload", "updated_at"])

    def record_failure(case, exc) -> None:
        results["failed"] += 1
        failures.append(
            {"case_id": case.id, "case_number": case.case_number, "error": str(exc)[:300]}
        )

    processed = 0
    while pending and processed < BATCH_SIZE:
        if _cancel_requested(job):
            save({"aborted_reason": "Cancelled."})
            raise BulkRefreshCancelled()

        case_id = pending.pop(0)
        processed += 1
        done += 1
        case = Case.objects.filter(id=case_id, owner_id=job.owner_id).first()
        if case is None or not case.tracking_enabled:
            results["skipped"] += 1
        else:
            try:
                outcome = refresh_case_tracking(case)
            except (CaptchaSolveError, CourtPortalError) as exc:
                consecutive += 1
                record_failure(case, exc)
            except (
                CourtDataError,
                TrackingNotEnabledError,
                MissingTrackingConfigError,
                InvalidTrackingConfigError,
            ) as exc:
                # The portal answered (or the case can't be looked up at
                # all) -- a per-case problem, not an outage.
                consecutive = 0
                record_failure(case, exc)
            except Exception as exc:  # noqa: BLE001 -- one bad case must not end the run
                logger.exception("Bulk refresh: case %s failed unexpectedly.", case.id)
                record_failure(case, exc)
            else:
                consecutive = 0
                if outcome.get("rate_limited"):
                    results["rate_limited"] += 1
                else:
                    results["refreshed"] += 1
                    new_dates = outcome.get("new_hearing_dates") or []
                    results["new_hearing_dates"] += len(new_dates)
                    results["updated"] += 1 if new_dates else 0
                    results["drafts_created"] += outcome.get("client_update_drafts", 0)

        save()
        if progress_callback:
            progress_callback(done, total)

        if consecutive >= MAX_CONSECUTIVE_PORTAL_ERRORS:
            aborted_reason = (
                f"Stopped after {consecutive} portal errors in a row -- eCourts looks "
                "unavailable. Try again later; cases already refreshed are kept."
            )
            logger.warning("Bulk refresh job %s aborted: %s", job.id, aborted_reason)
            save({"aborted_reason": aborted_reason})
            return job.payload

    if pending:
        # Hand the remainder to a fresh job at the back of the queue.
        follow_on = ProcessingJob.objects.create(
            owner_id=job.owner_id,
            job_type="tracking_refresh",
            payload={
                "case_ids": pending,
                "total": total,
                "done": done,
                "results": results,
                "failures": failures[-MAX_FAILURES_KEPT:],
                "consecutive_portal_errors": consecutive,
                "root_job_id": payload.get("root_job_id", job.id),
            },
            progress_current=done,
            progress_total=total,
        )
        save({"next_job_id": follow_on.id})
    return job.payload


__all__ = [
    "BATCH_SIZE",
    "BulkRefreshCancelled",
    "JobAlreadyRunningError",
    "MAX_CONSECUTIVE_PORTAL_ERRORS",
    "NothingToRefreshError",
    "cancel_run",
    "chain_head",
    "eligible_case_ids",
    "run_status",
    "run_tracking_refresh",
    "start_bulk_refresh",
]
