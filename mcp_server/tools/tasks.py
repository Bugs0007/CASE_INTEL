from typing import Annotated, Literal, Optional

from django.db.models import F
from pydantic import Field

from core.models import Task

from ..access import scoped
from ..registry import KIND_READ, READ_HINTS, ToolOutput, tool
from ..safety import clamp_limit, short_text
from .common import TIMEZONE, get_case, now_ist, owned_case_q, parse_day

_STATUS_FILTER = {
    "open": Task.OPEN_STATUSES,
    "pending": (Task.STATUS_PENDING,),
    "in_progress": (Task.STATUS_IN_PROGRESS,),
    "completed": (Task.STATUS_COMPLETED,),
    "cancelled": (Task.STATUS_CANCELLED,),
}


def task_row(task: Task, today) -> dict:
    return {
        "task_id": task.id,
        "case_id": task.case_id,
        "case_title": short_text(task.case.title) if task.case_id else None,
        "title": short_text(task.title) or "Task",
        "kind": task.kind,
        "status": task.status,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "basis": task.due_date_basis or None,
        "needs_review": task.needs_review,
        "overdue": bool(task.due_date and task.due_date < today and task.status in Task.OPEN_STATUSES),
    }


@tool("list_tasks", kind=KIND_READ, title="List tasks", annotations=READ_HINTS)
def list_tasks(
    ctx,
    case_id: Annotated[Optional[int], Field(description="Only this case's tasks. Optional.")] = None,
    status: Annotated[
        Optional[Literal["open", "pending", "in_progress", "completed", "cancelled", "all"]],
        Field(description="Default: open (pending or in progress)."),
    ] = None,
    due_before: Annotated[Optional[str], Field(description="Only tasks due on or before this date, YYYY-MM-DD.")] = None,
    limit: Annotated[Optional[int], Field(description="At most 50. Default 25.")] = None,
):
    """Tasks and deadlines, earliest due first (undated last): manual tasks, directions from court
    orders, and limitation deadlines. `basis` says how a due date was worked out; `needs_review`
    marks a date the system was not sure of."""
    limit = clamp_limit(limit, 25)
    qs = scoped(Task, ctx).filter(owned_case_q(ctx))
    if case_id is not None:
        qs = qs.filter(case=get_case(ctx, case_id))
    wanted = status or "open"
    if wanted != "all":
        qs = qs.filter(status__in=_STATUS_FILTER[wanted])
    due = parse_day(due_before, "due_before")
    if due:
        qs = qs.filter(due_date__lte=due)
    total = qs.count()
    today = now_ist().date()
    tasks = list(qs.select_related("case").order_by(F("due_date").asc(nulls_last=True), "id")[:limit])
    return ToolOutput(
        data={
            "tasks": [task_row(t, today) for t in tasks],
            "total": total,
            "truncated": total > len(tasks),
            "as_of": now_ist().isoformat(),
            "timezone": TIMEZONE,
        },
        case_id=case_id,
        rows=len(tasks),
        untrusted=True,
    )
