from typing import Annotated

from django.utils import timezone
from pydantic import Field

from core.models import CaseBriefing, CauseListMatch, CourtOrder, Document, Hearing, Task
from core.services.india_time import INDIA_TZ

from ..access import scoped
from ..registry import KIND_READ, READ_HINTS, NotFound, ToolOutput, tool
from ..safety import MAX_ROWS, TextBudget, short_text
from .common import TIMEZONE, as_ist, latest_snapshot, now_ist, parties
from .orders import order_row, render_order_summary

# Same as core.services.hearing_digest.assemble.RESOLVED_SUMMARY_STATUSES
# (a parity test pins the composition to assemble_hearing_digest).
RESOLVED_SUMMARY_STATUSES = (
    CourtOrder.SUMMARY_SUMMARIZED,
    CourtOrder.SUMMARY_NO_DIRECTIONS,
    CourtOrder.SUMMARY_UNREADABLE,
)


def compose_prep(ctx, hearing: Hearing) -> dict:
    """The rows behind the hearing prep sheet, read the way
    hearing_digest.assemble_hearing_digest reads them, but owner-scoped."""
    case = hearing.case
    hearing_day = hearing.hearing_date.date()
    last_order = (
        scoped(CourtOrder, ctx)
        .filter(case=case, order_date__lt=hearing_day, summary_status__in=RESOLVED_SUMMARY_STATUSES)
        .select_related("case", "document")
        .order_by("-order_date", "-created_at")
        .first()
    )
    open_tasks = list(
        scoped(Task, ctx)
        .filter(case=case, status__in=Task.OPEN_STATUSES)
        .select_related("case")
        .order_by("due_date", "created_at")
    )
    documents = list(
        scoped(Document, ctx).filter(case=case).exclude(document_type="court_order").order_by("-created_at")
    )
    purposes = []
    if last_order and last_order.summary_next_date == hearing_day:
        purposes.append(last_order.summary_next_date_purpose)
    purposes.append(hearing.purpose or "")
    purposes = list(dict.fromkeys(p.strip() for p in purposes if p and p.strip()))
    return {
        "last_order": last_order,
        "open_tasks": open_tasks,
        "documents": documents,
        "purposes": purposes,
        "snapshot": latest_snapshot(ctx, case),
    }


@tool("get_hearing_prep", kind=KIND_READ, title="Get hearing prep", annotations=READ_HINTS)
def get_hearing_prep(
    ctx,
    hearing_id: Annotated[int, Field(description="A hearing id from get_schedule or get_case.")],
):
    """The prep sheet for one hearing: the cause-list slot, what the hearing is for, the last order
    before it and its summary, open tasks, the case's documents, the latest eCourts status, and the
    cached "state of the matter" paragraph if one exists. Stored data only; nothing is generated."""
    hearing = (
        scoped(Hearing, ctx)
        .filter(pk=hearing_id, case__owner_id__in=ctx.owner_ids)
        .select_related("case")
        .first()
    )
    if hearing is None:
        raise NotFound("No hearing with that id.")
    case = hearing.case
    prep = compose_prep(ctx, hearing)
    budget = TextBudget()

    matches = list(
        scoped(CauseListMatch, ctx).filter(hearing=hearing).order_by("-is_primary", "id")[:5]
    )
    briefing = scoped(CaseBriefing, ctx).filter(case=case).first()
    if briefing is None:
        briefing_state = {"state": "none", "untrusted_text": None, "generated_at": None}
    elif briefing.status == CaseBriefing.STATUS_READY and briefing.text:
        briefing_state = {
            "state": "cached",
            "note": "Made earlier from the facts at that time; it may be out of date. "
                    "Open the prep sheet in Case Intel to refresh it.",
            **budget.take(briefing.text, per_field=2500),
            "generated_at": as_ist(briefing.generated_at),
        }
    else:
        briefing_state = {"state": "failed", "untrusted_text": None, "generated_at": as_ist(briefing.generated_at)}

    snapshot = prep["snapshot"] or {}
    local = timezone.localtime(hearing.hearing_date, INDIA_TZ)
    data = {
        "hearing": {
            "hearing_id": hearing.id,
            "at": as_ist(hearing.hearing_date),
            "status": hearing.status,
            "type": hearing.hearing_type,
            "purposes": budget.take_list(prep["purposes"], per_field=300),
            "location": short_text(hearing.location) or None,
            "judge": short_text(hearing.judge) or None,
        },
        "case": {
            "case_id": case.id,
            "title": short_text(case.title),
            "case_number": short_text(case.case_number) or None,
            "parties": parties(case),
            "user_party_role": case.user_party_role,
        },
        "cause_list": {
            "status": hearing.cause_list_status,
            "item_number": hearing.cause_list_item_number or None,
            "court_hall": hearing.cause_list_court_hall or None,
            "bench": short_text(hearing.cause_list_bench) or None,
            "list_type": short_text(hearing.cause_list_list_type) or None,
            "stage": short_text(hearing.cause_list_stage) or None,
            "note": short_text(hearing.cause_list_note) or None,
            "checked_at": as_ist(hearing.cause_list_checked_at),
            "matches": [
                {
                    "item_number": m.item_number or None,
                    "court_hall": m.court_hall or None,
                    "court_name": short_text(m.court_name) or None,
                    "bench": short_text(m.bench) or None,
                    "list_type": short_text(m.list_type) or None,
                    "stage": short_text(m.stage) or None,
                    "is_primary": m.is_primary,
                }
                for m in matches
            ],
        },
        "last_order": (
            {**order_row(prep["last_order"]), "summary": render_order_summary(prep["last_order"], budget)}
            if prep["last_order"]
            else None
        ),
        "open_tasks": [
            {
                "task_id": t.id,
                "title": short_text(t.title) or "Task",
                "due_date": t.due_date.isoformat() if t.due_date else None,
                "kind": t.kind,
                "needs_review": t.needs_review,
            }
            for t in prep["open_tasks"][:MAX_ROWS]
        ],
        "documents": [
            {
                "document_id": d.id,
                "filename": short_text(d.filename),
                "document_type": d.document_type,
                "document_date": d.document_date.isoformat() if d.document_date else None,
            }
            for d in prep["documents"][:MAX_ROWS]
        ],
        "ecourts_status": {
            "case_status": short_text(snapshot.get("case_status")) or None,
            "stage": short_text(snapshot.get("stage") or snapshot.get("case_stage")) or None,
            "court": short_text(snapshot.get("court_name") or snapshot.get("court")) or None,
            "last_checked_at": as_ist(case.last_fetched_at),
        },
        "briefing": briefing_state,
        "as_of": now_ist().isoformat(),
        "timezone": TIMEZONE,
        "hearing_day": local.date().isoformat(),
    }
    data["truncated"] = (
        budget.truncated or len(prep["open_tasks"]) > MAX_ROWS or len(prep["documents"]) > MAX_ROWS
    )
    return ToolOutput(data=data, case_id=case.id, rows=1, untrusted=True)
