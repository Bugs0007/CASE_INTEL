"""
Court tracking service layer: rate limiting, guardrails, and DB sync for
eCourts case data. This is the ONLY place refresh_case_tracking() should
be called from -- views must not call CourtDataProvider directly, so
rate limiting/tracking_enabled checks can't be bypassed.
"""

from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timedelta

from django.core.cache import cache
from django.utils import timezone

from core.models import ActivityLog, Case, CourtFetchLog, Hearing
from core.services.court_data import CourtCaseData, CourtDataError, get_provider

logger = logging.getLogger(__name__)

MIN_REFETCH_INTERVAL = timedelta(hours=1)

PREVIEW_CACHE_TTL = timedelta(minutes=10)
PREVIEW_CACHE_PREFIX = "court_tracking:preview"
PREVIEW_THROTTLE_PREFIX = "court_tracking:preview_throttle"
PREVIEW_THROTTLE_MAX = 10
PREVIEW_THROTTLE_WINDOW = timedelta(minutes=10)


class TrackingNotEnabledError(Exception):
    """Raised when refresh_case_tracking() is called for a case with
    tracking_enabled=False."""


class MissingTrackingConfigError(Exception):
    """Raised when tracking_enabled=True but tracking_config is empty."""


class PreviewThrottledError(Exception):
    """Raised when a user exceeds the preview rate limit."""


class PreviewExpiredError(Exception):
    """Raised when a preview_token is unknown, expired, or doesn't belong
    to the requesting user/case."""


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


def _preview_cache_key(token: str) -> str:
    return f"{PREVIEW_CACHE_PREFIX}:{token}"


def _check_preview_throttle(user_id: int) -> None:
    """Max PREVIEW_THROTTLE_MAX previews per user per PREVIEW_THROTTLE_WINDOW.

    Preview is exempt from the per-case 1h rate limit (nothing is
    persisted), so without this a preview loop would be an unlimited free
    live-fetch endpoint. This is intentionally simple (get-then-set, not
    atomic) -- matching this module's existing MIN_REFETCH_INTERVAL check,
    which doesn't lock either. A little raciness on the count boundary is
    an acceptable trade for not adding new infrastructure.
    """
    key = f"{PREVIEW_THROTTLE_PREFIX}:{user_id}"
    count = cache.get(key)
    if count is None:
        cache.set(key, 1, int(PREVIEW_THROTTLE_WINDOW.total_seconds()))
        return
    if count >= PREVIEW_THROTTLE_MAX:
        raise PreviewThrottledError(
            f"Too many preview attempts ({PREVIEW_THROTTLE_MAX} per "
            f"{int(PREVIEW_THROTTLE_WINDOW.total_seconds() // 60)} minutes). Please wait and try again."
        )
    cache.incr(key)


def preview_case_tracking(case: Case, tracking_config: dict, *, user_id: int) -> dict:
    """Fetch live court data WITHOUT persisting anything to the case.

    This is the fix for tracking silently saving a mismatched case: setup
    used to fetch-and-persist in one step, so a wrong case_type/case_number
    combination that happened to resolve to a DIFFERENT real case saved
    that wrong case's data with no human check. Preview separates "fetch"
    from "save" -- the caller must show the result to a human and call
    confirm_case_tracking() with the returned preview_token to persist it.

    tracking_config accepts either shape CourtDataProvider.fetch_case()
    understands: the cascade shape (state/dist/complex/case_type/
    case_number/year, or the HC equivalent), or the CNR-first shape
    ({"court_type": ..., "cnr": "..."}) -- EcourtsProvider.fetch_case()
    dispatches between them, so this function doesn't need to know which.

    Raises PreviewThrottledError if the per-user throttle is exceeded.
    Raises CourtDataError (or a subclass) if the fetch itself fails --
    nothing is cached or persisted in that case.
    """
    _check_preview_throttle(user_id)

    provider = get_provider()
    data = provider.fetch_case(tracking_config)

    token = secrets.token_urlsafe(24)
    cache.set(
        _preview_cache_key(token),
        {
            "case_id": case.id,
            "user_id": user_id,
            "tracking_config": dict(tracking_config),
            "data": data,
        },
        int(PREVIEW_CACHE_TTL.total_seconds()),
    )

    case_title = " vs ".join(p for p in (data.petitioner, data.respondent) if p) or None

    return {
        "preview_token": token,
        "case_title": case_title,
        "cnr": data.cnr,
        "petitioner": data.petitioner,
        "respondent": data.respondent,
        "court_name": data.court_name,
        "case_status": data.case_status,
        "case_stage": data.case_stage,
        "case_type": tracking_config.get("case_type"),
        "case_number": tracking_config.get("case_number"),
        "year": tracking_config.get("year"),
        "next_hearing_date": data.next_hearing_date.isoformat() if data.next_hearing_date else None,
        "first_hearing_date": data.first_hearing_date.isoformat() if data.first_hearing_date else None,
        "hearing_count": len(data.hearing_history),
    }


def confirm_case_tracking(case: Case, preview_token: str, *, user_id: int) -> dict:
    """Persist a previously-previewed fetch.

    Never trusts client-supplied case data -- loads ONLY the server-cached
    payload keyed by preview_token (and checks it actually belongs to this
    case and this user) rather than anything in the request body, so a
    confirm call can't be used to smuggle in different data than what was
    actually previewed and shown to the user.

    Raises PreviewExpiredError if the token is unknown, expired, or
    doesn't match this case/user -- the caller should tell the user to
    preview again rather than silently retrying.
    """
    cached = cache.get(_preview_cache_key(preview_token))
    if cached is None:
        raise PreviewExpiredError("This preview has expired. Please search again.")
    if cached["case_id"] != case.id or cached["user_id"] != user_id:
        raise PreviewExpiredError("This preview does not match the requested case. Please search again.")

    data: CourtCaseData = cached["data"]
    tracking_config: dict = cached["tracking_config"]

    case.court_type = tracking_config.get("court_type")
    case.tracking_config = tracking_config
    case.tracking_enabled = True
    case.save(update_fields=["court_type", "tracking_config", "tracking_enabled"])

    _apply_case_data(case, data)
    new_hearing_dates = _upsert_hearings(case, data)
    log_payload = _build_snapshot(data, new_hearing_dates)

    CourtFetchLog.objects.create(
        case=case,
        success=True,
        error_message=None,
        fields_changed=log_payload,
        duration_ms=None,
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

    # One-time use -- a stale token can't be replayed to re-persist the
    # same (or since-changed) cached payload after this.
    cache.delete(_preview_cache_key(preview_token))

    return {"case": case, "data": data, "new_hearing_dates": new_hearing_dates}


def untrack_case(case: Case) -> None:
    """Clear all court-tracking state for a case: the setup-mismatch
    recovery path (Part 3).

    Clears last_fetched_at along with everything else -- leaving it set
    would let the wrong case's fetch continue rate-limiting a correct
    re-track attempt for up to an hour, which is exactly the recovery
    flow this function exists for. Only Hearing rows with source='ecourts'
    are deleted; manually-entered hearings are untouched.
    """
    Hearing.objects.filter(case=case, source="ecourts").delete()

    case.cnr_number = None
    case.court_type = None
    case.tracking_config = None
    case.tracking_enabled = False
    case.fetch_status = "never_fetched"
    case.last_fetched_at = None
    case.save(
        update_fields=[
            "cnr_number",
            "court_type",
            "tracking_config",
            "tracking_enabled",
            "fetch_status",
            "last_fetched_at",
        ]
    )

    ActivityLog.objects.create(
        case=case,
        activity_type="court_tracking_removed",
        description=f"Court tracking removed for {case.case_number}",
    )


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
