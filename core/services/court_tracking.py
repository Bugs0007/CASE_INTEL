"""
Court tracking service layer: rate limiting, guardrails, and DB sync for
eCourts case data. This is the ONLY place refresh_case_tracking() should
be called from -- views must not call CourtDataProvider directly, so
rate limiting/tracking_enabled checks can't be bypassed.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta

from django.utils import timezone

from core.models import ActivityLog, Case, CourtFetchLog, Hearing
from core.services.court_data import CourtCaseData, CourtDataError, get_provider

logger = logging.getLogger(__name__)

MIN_REFETCH_INTERVAL = timedelta(hours=1)


class TrackingNotEnabledError(Exception):
    """Raised when refresh_case_tracking() is called for a case with
    tracking_enabled=False."""


class MissingTrackingConfigError(Exception):
    """Raised when tracking_enabled=True but tracking_config is empty."""


def refresh_case_tracking(case: Case, *, force: bool = False) -> dict:
    """Fetch live court data for `case` and sync it into the DB.

    Guardrails (enforced here, not in views, so nothing can bypass them):
      - Raises TrackingNotEnabledError if case.tracking_enabled is False.
      - Rate-limited to one real fetch per case per hour. Inside that
        window, returns the cached DB state with rate_limited=True
        instead of hitting the portal, UNLESS force=True.

    `force=True` is a raw capability of this function, not an
    authorization check -- callers (views, management commands) are
    responsible for only passing it when the caller is actually allowed
    to bypass the rate limit (staff users / management commands). See
    core/views/case_tracking.py.

    Returns a dict:
        {
            "rate_limited": bool,
            "retry_after": datetime | None,
            "case": Case,
            "data": CourtCaseData | None,   # None when rate_limited
            "new_hearing_dates": list[date],
        }

    Raises CourtDataError (or a subclass) if the fetch itself fails --
    the failure is still logged to CourtFetchLog before re-raising.
    """
    if not case.tracking_enabled:
        raise TrackingNotEnabledError(f"Tracking is not enabled for case {case.id}")

    if not force and case.last_fetched_at is not None:
        elapsed = timezone.now() - case.last_fetched_at
        if elapsed < MIN_REFETCH_INTERVAL:
            return {
                "rate_limited": True,
                "retry_after": case.last_fetched_at + MIN_REFETCH_INTERVAL,
                "case": case,
                "data": None,
                "new_hearing_dates": [],
            }

    if not case.tracking_config:
        raise MissingTrackingConfigError(f"Case {case.id} has no tracking_config set")

    provider = get_provider()
    start = time.monotonic()
    success = False
    error_message = None
    log_payload = None
    new_hearing_dates: list = []

    try:
        data = provider.fetch_case(case.tracking_config)
        success = True
        _apply_case_data(case, data)
        new_hearing_dates = _upsert_hearings(case, data)
        log_payload = _build_snapshot(data, new_hearing_dates)
    except CourtDataError as exc:
        error_message = str(exc)
        case.fetch_status = "failed"
        case.save(update_fields=["fetch_status"])
        raise
    finally:
        duration_ms = int((time.monotonic() - start) * 1000)
        CourtFetchLog.objects.create(
            case=case,
            success=success,
            error_message=error_message,
            fields_changed=log_payload,
            duration_ms=duration_ms,
        )

    case.last_fetched_at = timezone.now()
    case.fetch_status = "success"
    case.save(update_fields=["last_fetched_at", "fetch_status"])

    if new_hearing_dates:
        dates_str = ", ".join(d.isoformat() for d in new_hearing_dates)
        ActivityLog.objects.create(
            case=case,
            activity_type="court_hearing_update",
            description=f"eCourts: new hearing date(s) found for {case.case_number}: {dates_str}",
        )

    return {
        "rate_limited": False,
        "retry_after": None,
        "case": case,
        "data": data,
        "new_hearing_dates": new_hearing_dates,
    }


def _apply_case_data(case: Case, data: CourtCaseData) -> None:
    """Persist the CNR on first successful fetch. Everything else
    (status/stage/judge/next hearing) is derived from Hearing rows and
    the latest CourtFetchLog snapshot -- see _build_snapshot -- rather
    than new Case columns, since Phase A1 deliberately didn't add them."""
    if not case.cnr_number and data.cnr:
        case.cnr_number = data.cnr
        case.save(update_fields=["cnr_number"])


def _upsert_hearings(case: Case, data: CourtCaseData) -> list:
    """Upsert Hearing rows for source='ecourts', deduped on
    (case, hearing_date, source) per the unique constraint. Returns the
    list of hearing dates that are genuinely new (didn't exist before
    this call) -- the signal an ActivityLog entry gets written for."""
    new_dates = []
    today = timezone.localdate()

    for record in data.hearing_history:
        if record.hearing_date is None:
            continue

        hearing_datetime = timezone.make_aware(
            datetime.combine(record.hearing_date, datetime.min.time())
        )
        existed = Hearing.objects.filter(
            case=case, hearing_date=hearing_datetime, source="ecourts"
        ).exists()

        Hearing.objects.update_or_create(
            case=case,
            hearing_date=hearing_datetime,
            source="ecourts",
            defaults={
                "hearing_type": "other",
                "judge": record.judge or "",
                "business_date": record.business_date,
                "purpose": record.purpose or "",
                "status": "completed" if record.hearing_date < today else "scheduled",
            },
        )

        if not existed:
            new_dates.append(record.hearing_date)

    return new_dates


def _build_snapshot(data: CourtCaseData, new_hearing_dates: list) -> dict:
    """CourtFetchLog.fields_changed payload: a full snapshot of what the
    fetch returned (so the API layer has a persistent place to read
    current status/stage/judge from without new Case columns) plus an
    explicit list of which fields were new this run, for at-a-glance
    debugging."""
    return {
        "snapshot": {
            "cnr": data.cnr,
            "case_status": data.case_status,
            "case_stage": data.case_stage,
            "court_and_judge": data.court_and_judge,
            "court_name": data.court_name,
            "next_hearing_date": data.next_hearing_date.isoformat() if data.next_hearing_date else None,
            "first_hearing_date": data.first_hearing_date.isoformat() if data.first_hearing_date else None,
            "nature_of_disposal": data.nature_of_disposal,
            "hearing_count": len(data.hearing_history),
        },
        "new_hearing_dates": [d.isoformat() for d in new_hearing_dates],
    }


def latest_snapshot(case: Case) -> dict | None:
    """The snapshot from the most recent successful fetch, for display
    without triggering a new one. None if the case has never been
    fetched successfully."""
    log = (
        CourtFetchLog.objects.filter(case=case, success=True)
        .order_by("-timestamp")
        .first()
    )
    if log is None or not log.fields_changed:
        return None
    return log.fields_changed.get("snapshot")
