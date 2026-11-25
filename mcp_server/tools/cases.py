from typing import Annotated, Literal, Optional

from django.db.models import Max
from django.utils import timezone
from pydantic import Field

from core.models import Case, Hearing, Task
from core.services.practice_assistant import reads

from ..access import scoped
from ..registry import KIND_READ, READ_HINTS, ToolOutput, tool
from ..safety import MAX_QUERY_CHARS, MAX_ROWS, clamp_limit, short_text
from .common import (
    TIMEZONE,
    as_ist,
    court_names,
    get_case,
    now_ist,
    order_sync_state,
    parties,
    tracking_freshness,
)

CaseId = Annotated[int, Field(description="A case_id from list_cases or get_schedule.")]


def _next_hearings(ctx, case_ids) -> dict:
    """{case_id: earliest scheduled hearing at or after now}."""
    found = {}
    rows = (
        scoped(Hearing, ctx)
        .filter(case_id__in=case_ids, case__owner_id__in=ctx.owner_ids, status="scheduled",
                hearing_date__gte=timezone.now())
        .order_by("hearing_date", "id")
        .values("case_id", "id", "hearing_date")
    )
    for row in rows:
        found.setdefault(row["case_id"], row)
    return found


@tool("list_cases", kind=KIND_READ, title="List cases", annotations=READ_HINTS)
def list_cases(
    ctx,
    query: Annotated[
        Optional[str],
        Field(description="Part of a party name, client name, case number, title or CNR. Optional."),
    ] = None,
    status: Annotated[Optional[Literal["open", "pending", "closed", "archived"]], Field()] = None,
    limit: Annotated[Optional[int], Field(description="At most 50. Default 20.")] = None,
):
    """The advocate's cases, newest first, or those matching `query`.

    Each row: case_id, title, parties, court, CNR, status, next scheduled hearing and when the case
    was last checked on eCourts. Stored data only.
    """
    limit = clamp_limit(limit, 20)
    needle = (query or "").strip()[:MAX_QUERY_CHARS]
    if needle:
        ids = [c["id"] for c in reads.resolve_case_candidates(owner=ctx.owner, text=needle, limit=MAX_ROWS)]
        qs = scoped(Case, ctx).filter(id__in=ids)
    else:
        qs = scoped(Case, ctx)
    if status:
        qs = qs.filter(status=status)
    total = qs.count()
    cases = list(qs.order_by("-created_at", "-id")[:limit])
    courts = court_names(cases)
    upcoming = _next_hearings(ctx, [c.id for c in cases])
    rows = []
    for case in cases:
        nxt = upcoming.get(case.id)
        rows.append(
            {
                "case_id": case.id,
                "title": short_text(case.title),
                "case_number": short_text(case.case_number) or None,
                "cnr": case.cnr_number or None,
                "parties": parties(case),
                "court": short_text(courts.get(case.id)) or None,
                "status": case.status,
                "next_hearing": {"hearing_id": nxt["id"], "at": as_ist(nxt["hearing_date"])} if nxt else None,
                "last_checked_at": as_ist(case.last_fetched_at),
            }
        )
    return ToolOutput(
        data={
            "cases": rows,
            "total": total,
            "truncated": total > len(rows),
            "as_of": now_ist().isoformat(),
            "timezone": TIMEZONE,
        },
        rows=len(rows),
        untrusted=True,
    )


@tool("get_case", kind=KIND_READ, title="Get case", annotations=READ_HINTS)
def get_case_tool(ctx, case_id: CaseId):
    """One case: parties, your side (user_party_role), court, next hearing, open tasks, upcoming
    appointments, the order-check state and when eCourts was last checked. Stored data only."""
    case = get_case(ctx, case_id)
    facts = reads.case_facts(owner=ctx.owner, case_id=case.id)
    nxt = facts["next_hearing"]
    return ToolOutput(
        data={
            "case_id": case.id,
            "title": short_text(case.title),
            "case_number": short_text(case.case_number) or None,
            "cnr": case.cnr_number or None,
            "court": short_text(facts["case"]["court"]) or None,
            "status": case.status,
            "case_type": case.case_type,
            "parties": parties(case),
            "user_party_role": case.user_party_role,
            "next_hearing": (
                {
                    "hearing_id": nxt["id"],
                    "date": nxt["day"],
                    "start_time": nxt["start_time"],
                    "label": short_text(nxt["label"]),
                }
                if nxt
                else None
            ),
            "open_task_count": facts["open_tasks"]["total"],
            "open_tasks": [
                {
                    "task_id": t["id"],
                    "title": short_text(t["title"]),
                    "due_date": t["due_date"],
                    "overdue": t["overdue"],
                    "kind": t["kind"],
                }
                for t in facts["open_tasks"]["entries"]
            ],
            "upcoming_events": [
                {"event_id": e["id"], "date": e["day"], "start_time": e["start_time"], "label": short_text(e["label"])}
                for e in facts["upcoming_events"]["entries"]
            ],
            "order_sync": order_sync_state(ctx, case),
            "tracking": tracking_freshness(case),
            "truncated": facts["open_tasks"]["truncated"] or facts["upcoming_events"]["truncated"],
            "as_of": facts["as_of"],
            "timezone": TIMEZONE,
        },
        case_id=case.id,
        rows=1,
        untrusted=True,
    )


@tool("get_data_freshness", kind=KIND_READ, title="Get data freshness", annotations=READ_HINTS)
def get_data_freshness(ctx, case_id: CaseId):
    """When this case's data was last checked: eCourts case status (and the earliest time a refresh
    is allowed, one per hour), the order check, and the cause list for its hearings. This tool only
    reports times. It never starts a check."""
    case = get_case(ctx, case_id)
    hearings = scoped(Hearing, ctx).filter(case=case, case__owner_id__in=ctx.owner_ids)
    last_cause_list = hearings.aggregate(at=Max("cause_list_checked_at"))["at"]
    nxt = (
        hearings.filter(status="scheduled", hearing_date__gte=timezone.now())
        .order_by("hearing_date", "id")
        .values("id", "hearing_date", "cause_list_status", "cause_list_checked_at")
        .first()
    )
    open_tasks = scoped(Task, ctx).filter(case=case, status__in=Task.OPEN_STATUSES).count()
    return ToolOutput(
        data={
            "case_id": case.id,
            "ecourts": tracking_freshness(case),
            "order_sync": order_sync_state(ctx, case),
            "cause_list": {
                "last_checked_at": as_ist(last_cause_list),
                "next_hearing": (
                    {
                        "hearing_id": nxt["id"],
                        "at": as_ist(nxt["hearing_date"]),
                        "cause_list_status": nxt["cause_list_status"],
                        "checked_at": as_ist(nxt["cause_list_checked_at"]),
                    }
                    if nxt
                    else None
                ),
            },
            "open_task_count": open_tasks,
            "truncated": False,
            "as_of": now_ist().isoformat(),
            "timezone": TIMEZONE,
        },
        case_id=case.id,
        rows=1,
    )
