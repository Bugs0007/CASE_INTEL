"""The "order check" status of a case: has the portal's order list been
looked at, did it work, and what did it find.

Read from the case's order_sync jobs and CourtOrder rows -- nothing new is
stored. The latest non-cancelled job decides the state, so a later success
clears an earlier failure:

    never     no order sync has ever run for the case
    queued    one is waiting for the worker
    running   one is in progress
    ok        the latest one finished cleanly (zero orders found is "ok":
              the portal simply has none published)
    partial   it finished, but at least one order's PDF could not be
              downloaded yet (kept pending; the next sync retries it)
    failed    it could not list the orders at all (CAPTCHA, portal down)

`reason` is one of three fixed labels, never the raw error: the portal's own
messages can quote party names and mean nothing to an advocate.
"""

from django.db.models import Count, OuterRef, Subquery
from django.db.models.fields.json import KeyTextTransform, KeyTransform
from django.db.models.functions import Coalesce

from core.models import Case, CourtOrder, ProcessingJob
from core.services.court_order_sync import error_kind

REASON_LABELS = {
    "captcha": "CAPTCHA not read",
    "portal": "court portal didn't answer",
    "other": "other",
}
_STATE_BY_JOB_STATUS = {
    "queued": "queued",
    "running": "running",
    "succeeded": "ok",
    "partial": "partial",
    "failed": "failed",
}
_FINISHED = ("succeeded", "partial", "failed")
# The listing itself worked in both of these.
_LISTED_OK = ("succeeded", "partial")


def _jobs():
    return ProcessingJob.objects.filter(case=OuterRef("pk"), job_type="order_sync")


def _count_of(orders):
    return Coalesce(Subquery(orders.order_by().values("case").annotate(n=Count("id")).values("n")[:1]), 0)


def annotate_order_sync(qs):
    """Add the `_os_*` annotations the summary reads -- correlated
    subqueries, so a list of N cases is still one query."""
    newest_first = ("-created_at", "-id")
    latest = _jobs().exclude(status="cancelled").order_by(*newest_first)
    finished = _jobs().filter(status__in=_FINISHED).order_by(*newest_first)
    listed_ok = _jobs().filter(status__in=_LISTED_OK).order_by(*newest_first)
    orders = CourtOrder.objects.filter(case=OuterRef("pk"))
    return qs.annotate(
        _os_status=Subquery(latest.values("status")[:1]),
        _os_error=Subquery(latest.values("error")[:1]),
        _os_reason=Subquery(
            latest.annotate(r=KeyTextTransform("reason", KeyTransform("result", "payload"))).values("r")[:1]
        ),
        _os_checked_at=Subquery(finished.values("finished_at")[:1]),
        _os_success_at=Subquery(listed_ok.values("finished_at")[:1]),
        _os_found=_count_of(orders),
        _os_downloaded=_count_of(orders.filter(document__isnull=False)),
    )


def order_sync_summary(case: Case) -> dict:
    """{state, last_checked_at, last_success_at, found, downloaded, reason}.

    Uses the annotations when the queryset carried them (the case list and
    detail views); otherwise one query for this case."""
    source = case
    if not hasattr(case, "_os_status"):
        source = annotate_order_sync(Case.objects.filter(pk=case.pk)).first() or case
    state = _STATE_BY_JOB_STATUS.get(getattr(source, "_os_status", None), "never")

    reason = None
    if state in ("failed", "partial"):
        stored = getattr(source, "_os_reason", None)
        kind = stored if state == "partial" and stored in REASON_LABELS else error_kind(
            getattr(source, "_os_error", "")
        )
        reason = REASON_LABELS[kind]

    return {
        "state": state,
        "last_checked_at": getattr(source, "_os_checked_at", None),
        "last_success_at": getattr(source, "_os_success_at", None),
        "found": getattr(source, "_os_found", 0),
        "downloaded": getattr(source, "_os_downloaded", 0),
        "reason": reason,
    }
