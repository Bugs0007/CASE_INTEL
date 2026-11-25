"""Helpers shared by the tool modules. Every row comes through scoped().

Tool modules must NOT use `from __future__ import annotations`: the SDK
builds each tool's input schema from real type objects.
"""

from datetime import date, datetime, timedelta

from django.db.models import Q
from django.utils import timezone

from core.models import Case, CourtFetchLog, CourtOrder, ProcessingJob
from core.services.india_time import INDIA_TZ, india_now
from core.services.parties import court_names_for_cases

from ..access import TenantContext, scoped
from ..registry import InvalidInput, NotFound
from ..safety import short_text

TIMEZONE = "Asia/Kolkata"

# Same rule as core.services.court_tracking.MIN_REFETCH_INTERVAL (a test
# pins the two together; this process may not import court_tracking).
MIN_REFETCH_INTERVAL = timedelta(hours=1)

# Same states as core.services.order_sync_status (a parity test pins them).
ORDER_SYNC_STATE_BY_JOB_STATUS = {
    "queued": "queued",
    "running": "running",
    "succeeded": "ok",
    "partial": "partial",
    "failed": "failed",
}
_ORDER_SYNC_FINISHED = ("succeeded", "partial", "failed")
_ORDER_SYNC_LISTED_OK = ("succeeded", "partial")


def now_ist() -> datetime:
    return india_now()


def as_ist(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        return timezone.localtime(value, INDIA_TZ).isoformat()
    return value.isoformat()


def parse_day(value, field: str):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise InvalidInput(f"{field} must be a date in the form YYYY-MM-DD.") from None


def get_case(ctx: TenantContext, case_id) -> Case:
    case = scoped(Case, ctx).filter(pk=case_id).first() if case_id is not None else None
    if case is None:
        raise NotFound("No case with that id.")
    return case


def owned_case_q(ctx: TenantContext, prefix: str = "case__") -> Q:
    """Rows whose case (if any) is also the caller's."""
    return Q(**{f"{prefix[:-2]}__isnull": True}) | Q(**{f"{prefix}owner_id__in": ctx.owner_ids})


def court_names(cases) -> dict:
    return court_names_for_cases(list(cases))


def case_ref(case: Case) -> dict:
    return {"case_id": case.id, "case_title": short_text(case.title)}


def parties(case: Case) -> dict:
    return {
        "petitioner": short_text(case.petitioner_name) or None,
        "respondent": short_text(case.respondent_name) or None,
        "client_name": short_text(case.client_name) or None,
    }


def order_sync_state(ctx: TenantContext, case: Case) -> dict:
    """{state, last_checked_at, last_success_at, found, downloaded}: the
    latest non-cancelled order_sync job decides (core/services/order_sync_status.py).
    The failure `reason` label is left out here."""
    jobs = scoped(ProcessingJob, ctx).filter(case=case, job_type="order_sync").order_by("-created_at", "-id")
    latest = jobs.exclude(status="cancelled").values_list("status", flat=True).first()
    finished = jobs.filter(status__in=_ORDER_SYNC_FINISHED).values_list("finished_at", flat=True).first()
    listed_ok = jobs.filter(status__in=_ORDER_SYNC_LISTED_OK).values_list("finished_at", flat=True).first()
    orders = scoped(CourtOrder, ctx).filter(case=case)
    return {
        "state": ORDER_SYNC_STATE_BY_JOB_STATUS.get(latest, "never"),
        "last_checked_at": as_ist(finished),
        "last_success_at": as_ist(listed_ok),
        "found": orders.count(),
        "downloaded": orders.filter(document__isnull=False).count(),
    }


def latest_snapshot(ctx: TenantContext, case: Case):
    """The eCourts snapshot from the last successful fetch (stored data,
    same rule as court_tracking.latest_snapshot), or None."""
    log = scoped(CourtFetchLog, ctx).filter(case=case, success=True).order_by("-timestamp").first()
    if log is None or not log.fields_changed:
        return None
    return log.fields_changed.get("snapshot")


def tracking_freshness(case: Case) -> dict:
    now = timezone.now()
    next_refresh = None
    if case.last_fetched_at is not None and now - case.last_fetched_at < MIN_REFETCH_INTERVAL:
        next_refresh = case.last_fetched_at + MIN_REFETCH_INTERVAL
    return {
        "tracking_enabled": case.tracking_enabled,
        "fetch_status": case.fetch_status,
        "last_checked_at": as_ist(case.last_fetched_at),
        "next_refresh_allowed_at": as_ist(next_refresh) if next_refresh else as_ist(now),
    }
