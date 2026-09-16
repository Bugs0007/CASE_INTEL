"""Tasks from the directions in a court order's summary.

One Task per direction the order gives to the advocate's own side, due on
the date `direction_deadlines` works out. Runs at ingest (after the order
is summarised, in the process_jobs worker), when the advocate corrects
their party role, and from `manage.py generate_order_tasks`. Never on a
page view.

Gates, and why:
  - Party role unknown -> no tasks. Which side's directions are "yours" is
    exactly what is unknown; creating tasks from the other side's
    directions is the harm to avoid (same stance as build_order_summary).
  - Only the case's most recent order date, and only if recent
    (RECENT_ORDER_WINDOW_DAYS). The first sync of a newly tracked case
    ingests its entire order history; without this, every old direction
    would land as an overdue task.

A task the advocate has edited, completed or dismissed is never touched
(see upsert_system_task). An untouched task whose direction no longer
applies -- the role was corrected, or a forced re-summary reworded the
directions -- is deleted, since its source would simply recreate it.
Earlier orders' open tasks are left alone when a newer order arrives:
whether they were complied with can't be told from the order text.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from django.utils import timezone

from core.models import CourtOrder, Hearing, Task
from core.serializers.order_summary import build_order_summary
from core.services.order_summary.routing import normalize

from .direction_deadlines import parse_direction_due_date
from .service import (
    OUTCOME_CREATED,
    OUTCOME_SKIPPED,
    OUTCOME_UNCHANGED,
    OUTCOME_UPDATED,
    upsert_system_task,
)

logger = logging.getLogger(__name__)

RECENT_ORDER_WINDOW_DAYS = 60

REASON_ROLE_UNKNOWN = "party_role_unknown"
REASON_NOT_SUMMARIZED = "not_summarized"
REASON_UNDATED = "undated_order"
REASON_SUPERSEDED = "later_order_exists"
REASON_OUTSIDE_WINDOW = "order_too_old"

LATER_START_NOTE = (
    "The order counts this period from a later event (receipt of a copy, "
    "service, or an earlier step); the date here is counted from the order "
    "date, so the real deadline may be later."
)

_KNOWN_ROLES = ("petitioner", "respondent")


@dataclass
class OrderTaskResult:
    created: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped: int = 0
    pruned: int = 0
    reason: str = ""  # why no tasks were generated, if none were
    task_ids: list[int] = field(default_factory=list)


def dedup_key_for(order_id: int, side: str, direction: str) -> str:
    digest = hashlib.sha1(normalize(direction).lower().encode("utf-8")).hexdigest()[:12]
    return f"order:{order_id}:{side}:{digest}"


def generate_tasks_for_order(
    order: CourtOrder,
    *,
    today: date | None = None,
    latest_order_date: date | None = None,
) -> OrderTaskResult:
    """Create/refresh this order's direction tasks. Idempotent.

    `latest_order_date` lets a caller looping over a case's orders skip
    re-querying it per order.
    """
    result = OrderTaskResult()
    if order.summary_status != CourtOrder.SUMMARY_SUMMARIZED:
        result.reason = REASON_NOT_SUMMARIZED
        return result

    case = order.case
    role = case.user_party_role
    directions = build_order_summary(order)["your_side_directions"] or []
    wanted_keys = (
        {dedup_key_for(order.id, role, text) for text in directions}
        if role in _KNOWN_ROLES
        else set()
    )

    # Prune first, whatever the gates below decide: a task from the side
    # that is no longer the advocate's must go even for an older order.
    result.pruned = _prune_stale_tasks(order, keep=wanted_keys)

    if role not in _KNOWN_ROLES:
        result.reason = REASON_ROLE_UNKNOWN
        return result
    if order.order_date is None:
        result.reason = REASON_UNDATED
        return result

    if latest_order_date is None:
        latest_order_date = _latest_order_date(case)
    if latest_order_date and order.order_date < latest_order_date:
        result.reason = REASON_SUPERSEDED
        return result

    today = today or timezone.localdate()
    if order.order_date < today - timedelta(days=RECENT_ORDER_WINDOW_DAYS):
        result.reason = REASON_OUTSIDE_WINDOW
        return result

    next_hearing_date = order.summary_next_date or _next_hearing_after(case, order.order_date)

    for text in directions:
        due = parse_direction_due_date(
            text, order_date=order.order_date, next_hearing_date=next_hearing_date
        )
        task, outcome = upsert_system_task(
            owner=case.owner,
            case=case,
            kind=Task.KIND_ORDER_DIRECTION,
            dedup_key=dedup_key_for(order.id, role, text),
            title=text,
            description=LATER_START_NOTE if due.approximate else "",
            due_date=due.due_date,
            due_date_basis=due.basis,
            source_order=order,
            source_text=text,
        )
        result.task_ids.append(task.id)
        if outcome == OUTCOME_CREATED:
            result.created += 1
        elif outcome == OUTCOME_UPDATED:
            result.updated += 1
        elif outcome == OUTCOME_UNCHANGED:
            result.unchanged += 1
        elif outcome == OUTCOME_SKIPPED:
            result.skipped += 1

    if result.created or result.updated or result.pruned:
        logger.info(
            "Order %s direction tasks: %d created, %d updated, %d pruned.",
            order.id,
            result.created,
            result.updated,
            result.pruned,
        )
    return result


def sync_order_tasks_for_case(case, *, today: date | None = None) -> list[OrderTaskResult]:
    """Re-run generation for every summarised order on `case`.

    Used when the advocate corrects their party role: tasks from the old
    side are pruned wherever they exist, and the latest order gets tasks for
    the new side.
    """
    orders = list(
        CourtOrder.objects.filter(case=case, summary_status=CourtOrder.SUMMARY_SUMMARIZED)
        .select_related("case")
        .order_by("order_date")
    )
    latest = _latest_order_date(case)
    return [
        generate_tasks_for_order(order, today=today, latest_order_date=latest)
        for order in orders
    ]


def _prune_stale_tasks(order: CourtOrder, *, keep: set[str]) -> int:
    stale = (
        Task.objects.filter(
            owner_id=order.owner_id,
            kind=Task.KIND_ORDER_DIRECTION,
            dedup_key__startswith=f"order:{order.id}:",
            user_modified=False,
            status__in=Task.OPEN_STATUSES,
        )
        .exclude(dedup_key__in=keep)
    )
    deleted, _ = stale.delete()
    return deleted


def _latest_order_date(case) -> date | None:
    return (
        CourtOrder.objects.filter(case=case, order_date__isnull=False)
        .order_by("-order_date")
        .values_list("order_date", flat=True)
        .first()
    )


def _next_hearing_after(case, order_date: date) -> date | None:
    hearing = (
        Hearing.objects.filter(case=case, hearing_date__date__gt=order_date)
        .exclude(status="cancelled")
        .order_by("hearing_date")
        .first()
    )
    return hearing.hearing_date.date() if hearing else None
