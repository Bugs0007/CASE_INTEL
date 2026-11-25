"""Write tools: propose, then confirm (docs/MCP_PLAN.md section 5, Phase 2).

  - propose_* validates its input, writes NOTHING to case data, and stores
    one McpProposal: the normalised args, their hash, a plain-text preview
    built here from those args, any blockers, and a 15-minute expiry.
  - confirm_proposal runs the change once through the same rules the web
    app uses, inside one transaction with its audit row. A second confirm
    returns the first result.
  - cancel_proposal closes an open proposal.

What can never be proposed: sending anything, invoices, fees, deletes,
eCourts refreshes or imports, tracking, party role or account settings.
A client-update proposal only ever creates a ClientMessage in `draft`
status; the advocate sends it from the web app.

Text the model supplies (a title, a note) is stored and shown quoted, never
as if the server wrote it.
"""

import hashlib
import json
from datetime import date, time, timedelta
from typing import Annotated, Literal, Optional

from django.db import transaction
from django.utils import timezone
from pydantic import Field

from core.models import ActivityLog, CaseEvent, CaseNote, CourtOrder, McpProposal, Task
from core.services.client_updates.service import draft_case_update, update_recipients
from core.services.india_time import INDIA_TZ

from .. import audit
from ..access import TenantContext, scoped
from ..registry import (
    KIND_PROPOSAL_ACTION,
    KIND_PROPOSE,
    SCOPE_WRITE,
    WRITE_HINTS,
    InvalidInput,
    NotFound,
    ToolOutput,
    tool,
)
from ..safety import clean_text, short_text
from .common import get_case, owned_case_q, parse_day

PROPOSAL_TTL = timedelta(minutes=15)
NEXT_STEP = (
    "Show this preview to the user. Call confirm_proposal with this proposal_id only after the user "
    "has agreed. Nothing has changed yet."
)
EVENT_TYPES = Literal[
    "arbitration", "mediation", "client_meeting", "client_call", "internal_meeting", "site_visit", "filing", "other"
]


def args_hash(tool_name: str, args: dict) -> str:
    blob = json.dumps({"tool": tool_name, "args": args}, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _required_text(value, field: str, limit: int) -> str:
    text = clean_text(value)
    if not text:
        raise InvalidInput(f"{field} is empty.")
    if len(text) > limit:
        raise InvalidInput(f"{field} is longer than {limit} characters.")
    return text


def _optional_text(value, field: str, limit: int) -> str:
    text = clean_text(value)
    if len(text) > limit:
        raise InvalidInput(f"{field} is longer than {limit} characters.")
    return text


def _parse_time(value, field: str):
    if value in (None, ""):
        return None
    try:
        return time.fromisoformat(str(value)).replace(second=0, microsecond=0)
    except ValueError:
        raise InvalidInput(f"{field} must be a time in the form HH:MM.") from None


def _store(ctx: TenantContext, tool_name: str, args: dict, preview: str, *, case=None, blockers=None):
    blockers = list(blockers or [])
    expires_at = timezone.now() + PROPOSAL_TTL
    proposal = McpProposal(
        owner=ctx.user,
        case=case,
        tool=tool_name,
        args=args,
        args_hash=args_hash(tool_name, args),
        preview=preview,
        blockers=blockers,
        expires_at=expires_at,
        client_id=(ctx.client_id or "")[:255],
        token_id=ctx.token_id,
    )
    proposal.save()
    return ToolOutput(
        data={
            "proposal_id": proposal.id,
            "tool": tool_name,
            "preview": preview,
            "blockers": blockers,
            "can_confirm": not blockers,
            "expires_at": timezone.localtime(expires_at, INDIA_TZ).isoformat(),
            "next_step": NEXT_STEP if not blockers else "This cannot be confirmed. Tell the user why.",
            "truncated": False,
        },
        case_id=case.id if case else None,
        rows=0,
        proposal_id=proposal.id,
    )


def _quote(text: str, limit: int = 120) -> str:
    text = text.replace("\n", " ")
    return f'"{text[:limit]}{"…" if len(text) > limit else ""}"'


def _case_label(case) -> str:
    return f"{short_text(case.title, 120)} ({short_text(case.case_number, 60)})"


# ---------------------------------------------------------------------------
# propose_* (write nothing but the McpProposal row)
# ---------------------------------------------------------------------------


@tool("propose_task", kind=KIND_PROPOSE, title="Propose task", annotations=WRITE_HINTS, scope=SCOPE_WRITE)
def propose_task(
    ctx,
    title: Annotated[str, Field(description="What has to be done. At most 255 characters.")],
    case_id: Annotated[Optional[int], Field(description="The case it belongs to. Optional.")] = None,
    due_date: Annotated[Optional[str], Field(description="India date, YYYY-MM-DD. Optional.")] = None,
    description: Annotated[Optional[str], Field(description="More detail. At most 2000 characters.")] = None,
):
    """Propose a new task (a to-do with an optional due date). Changes nothing until the user confirms
    with confirm_proposal."""
    case = get_case(ctx, case_id) if case_id is not None else None
    due = parse_day(due_date, "due_date")
    args = {
        "case_id": case.id if case else None,
        "title": _required_text(title, "title", 255),
        "due_date": due.isoformat() if due else None,
        "description": _optional_text(description, "description", 2000),
    }
    preview = f"Create a task {_quote(args['title'])}"
    preview += f" on the case {_case_label(case)}" if case else " (not linked to a case)"
    preview += f", due {args['due_date']}." if args["due_date"] else ", with no due date."
    return _store(ctx, "propose_task", args, preview, case=case)


@tool("propose_case_note", kind=KIND_PROPOSE, title="Propose case note", annotations=WRITE_HINTS,
      scope=SCOPE_WRITE)
def propose_case_note(
    ctx,
    case_id: Annotated[int, Field(description="The case the note belongs to.")],
    text: Annotated[str, Field(description="The note, plain text. At most 5000 characters.")],
    title: Annotated[Optional[str], Field(description="A short title. Optional.")] = None,
):
    """Propose a note on a case. Changes nothing until the user confirms with confirm_proposal."""
    case = get_case(ctx, case_id)
    body = _required_text(text, "text", 5000)
    heading = _optional_text(title, "title", 200) or body.split("\n", 1)[0][:80]
    args = {"case_id": case.id, "title": heading, "text": body}
    preview = f"Add a note titled {_quote(heading)} to the case {_case_label(case)} ({len(body)} characters)."
    return _store(ctx, "propose_case_note", args, preview, case=case)


@tool("propose_case_event", kind=KIND_PROPOSE, title="Propose case event", annotations=WRITE_HINTS,
      scope=SCOPE_WRITE)
def propose_case_event(
    ctx,
    case_id: Annotated[int, Field(description="The case the appointment belongs to.")],
    date: Annotated[str, Field(description="India date, YYYY-MM-DD.")],
    title: Annotated[str, Field(description="What the appointment is. At most 200 characters.")],
    start_time: Annotated[Optional[str], Field(description="India time HH:MM. Leave out for all day.")] = None,
    end_time: Annotated[Optional[str], Field(description="India time HH:MM, after start_time.")] = None,
    event_type: Annotated[Optional[EVENT_TYPES], Field(description="Default: other.")] = None,
):
    """Propose one of the advocate's own appointments on a case (arbitration, mediation, client meeting,
    site visit...). It is never a court hearing. Changes nothing until the user confirms."""
    case = get_case(ctx, case_id)
    day = parse_day(date, "date")
    if day is None:
        raise InvalidInput("date is required.")
    start = _parse_time(start_time, "start_time")
    end = _parse_time(end_time, "end_time")
    if end is not None and (start is None or end <= start):
        raise InvalidInput("end_time needs a start_time and must be after it.")
    args = {
        "case_id": case.id,
        "date": day.isoformat(),
        "title": _required_text(title, "title", 200),
        "start_time": start.strftime("%H:%M") if start else None,
        "end_time": end.strftime("%H:%M") if end else None,
        "event_type": event_type or CaseEvent.TYPE_OTHER,
    }
    when = f"{args['date']} " + (
        f"{args['start_time']}" + (f"-{args['end_time']}" if args["end_time"] else "") if start else "(all day)"
    )
    preview = (
        f"Add the appointment {_quote(args['title'])} ({args['event_type'].replace('_', ' ')}) on {when} IST "
        f"to the case {_case_label(case)}. This is not a court hearing."
    )
    return _store(ctx, "propose_case_event", args, preview, case=case)


@tool("propose_task_update", kind=KIND_PROPOSE, title="Propose task update", annotations=WRITE_HINTS,
      scope=SCOPE_WRITE)
def propose_task_update(
    ctx,
    task_id: Annotated[int, Field(description="A task_id from list_tasks.")],
    status: Annotated[Optional[Literal["pending", "in_progress", "completed"]], Field()] = None,
    due_date: Annotated[Optional[str], Field(description="New India due date, YYYY-MM-DD.")] = None,
):
    """Propose a change to a task's status or due date. Changes nothing until the user confirms."""
    task = scoped(Task, ctx).filter(owned_case_q(ctx), pk=task_id).select_related("case").first()
    if task is None:
        raise NotFound("No task with that id.")
    new_due = parse_day(due_date, "due_date")
    if status is None and new_due is None:
        raise InvalidInput("Give a status or a due_date.")
    args = {"task_id": task.id, "status": status, "due_date": new_due.isoformat() if new_due else None}
    changes = []
    if status:
        changes.append(f"status {task.status} -> {status}")
    if new_due:
        old = task.due_date.isoformat() if task.due_date else "none"
        changes.append(f"due date {old} -> {args['due_date']}")
    preview = f"Change the task {_quote(short_text(task.title) or 'Task')}: " + "; ".join(changes) + "."
    blockers = []
    if task.status == Task.STATUS_CANCELLED:
        blockers.append("This task was dismissed. Reopen it in Case Intel first.")
    return _store(ctx, "propose_task_update", args, preview, case=task.case if task.case_id else None,
                  blockers=blockers)


def _client_update_basis(ctx, case):
    """(heard_on, order) for the update: the case's latest dated order."""
    order = (
        scoped(CourtOrder, ctx)
        .filter(case=case, order_date__isnull=False)
        .order_by("-order_date", "-created_at")
        .first()
    )
    return (order.order_date, order) if order else (None, None)


@tool("propose_client_update_draft", kind=KIND_PROPOSE, title="Propose client update draft",
      annotations=WRITE_HINTS, scope=SCOPE_WRITE)
def propose_client_update_draft(
    ctx,
    case_id: Annotated[int, Field(description="The case to write the client update for.")],
):
    """Propose a client-update DRAFT for a case, written by Case Intel from the latest order and next
    date. Confirming only saves a draft in Case Intel; it is never sent from here. The advocate reads,
    edits and sends it in the web app. Recipients are the case's client contacts; they cannot be chosen
    here."""
    case = get_case(ctx, case_id)
    heard_on, order = _client_update_basis(ctx, case)
    recipients = update_recipients(case)
    blockers = []
    if not recipients:
        blockers.append("No client contact on this case has an email and accepts case updates.")
    if order is None:
        blockers.append("No dated court order to report on.")
    args = {"case_id": case.id, "order_id": order.id if order else None}
    names = ", ".join(short_text(r.get("name"), 80) or "client" for r in recipients[:5])
    preview = (
        f"Save a client-update draft (not sent) for the case {_case_label(case)}"
        + (f" about the order of {heard_on.isoformat()}" if heard_on else "")
        + (f", addressed to {len(recipients)} contact(s): {names}" if recipients else "")
        + ". You send it yourself from Case Intel."
    )
    return _store(ctx, "propose_client_update_draft", args, preview, case=case, blockers=blockers)


# ---------------------------------------------------------------------------
# Executors: run only from confirm_proposal, inside its transaction
# ---------------------------------------------------------------------------


def _run_task(ctx, args):
    case = get_case(ctx, args["case_id"]) if args["case_id"] else None
    task = scoped(Task, ctx).create(
        owner=ctx.user,
        case=case,
        title=args["title"],
        description=args["description"] or None,
        due_date=date.fromisoformat(args["due_date"]) if args["due_date"] else None,
        kind=Task.KIND_MANUAL,
    )
    return {"task_id": task.id}


def _run_case_note(ctx, args):
    case = get_case(ctx, args["case_id"])
    note = scoped(CaseNote, ctx).create(owner=ctx.user, case=case, title=args["title"], body=args["text"])
    return {"note_id": note.id}


def _run_case_event(ctx, args):
    case = get_case(ctx, args["case_id"])
    event = scoped(CaseEvent, ctx).create(
        owner=ctx.user,
        case=case,
        title=args["title"],
        event_type=args["event_type"],
        date=date.fromisoformat(args["date"]),
        start_time=time.fromisoformat(args["start_time"]) if args["start_time"] else None,
        end_time=time.fromisoformat(args["end_time"]) if args["end_time"] else None,
    )
    return {"event_id": event.id}


def _run_task_update(ctx, args):
    task = scoped(Task, ctx).filter(owned_case_q(ctx), pk=args["task_id"]).select_for_update(of=("self",)).first()
    if task is None:
        raise NotFound("No task with that id.")
    fields = []
    if args["status"] and args["status"] != task.status:
        task.status = args["status"]
        task.completed_at = timezone.now() if task.status == Task.STATUS_COMPLETED else None
        fields += ["status", "completed_at"]
    if args["due_date"]:
        new_due = date.fromisoformat(args["due_date"])
        if new_due != task.due_date:
            task.due_date = new_due
            fields.append("due_date")
    if fields:
        task.user_modified = True  # the system never overwrites it again (tasks/service.py)
        task.save(update_fields=fields + ["user_modified", "updated_at"])
    return {"task_id": task.id, "changed": sorted(set(fields))}


def _run_client_update_draft(ctx, args):
    case = get_case(ctx, args["case_id"])
    order = scoped(CourtOrder, ctx).filter(pk=args["order_id"], case=case).first() if args["order_id"] else None
    if order is None:
        raise InvalidInput("The order this draft was based on is gone. Propose again.")
    message, outcome = draft_case_update(case, heard_on=order.order_date, order=order)
    return {
        "draft_id": message.id if message else None,
        "status": message.status if message else None,
        "outcome": outcome,
        "sent": False,
    }


EXECUTORS = {
    "propose_task": _run_task,
    "propose_case_note": _run_case_note,
    "propose_case_event": _run_case_event,
    "propose_task_update": _run_task_update,
    "propose_client_update_draft": _run_client_update_draft,
}


# ---------------------------------------------------------------------------
# confirm / cancel
# ---------------------------------------------------------------------------

ProposalId = Annotated[int, Field(description="The proposal_id a propose_* tool returned.")]


def _expire_if_due(ctx, proposal_id) -> None:
    scoped(McpProposal, ctx).filter(
        pk=proposal_id, status=McpProposal.STATUS_OPEN, expires_at__lte=timezone.now()
    ).update(status=McpProposal.STATUS_EXPIRED)


def _confirmed_output(proposal, *, case_id=None, audited=False):
    return ToolOutput(
        data={
            "proposal_id": proposal.id,
            "tool": proposal.tool,
            "status": proposal.status,
            "result": proposal.result,
            "confirmed_at": timezone.localtime(proposal.confirmed_at, INDIA_TZ).isoformat(),
            "truncated": False,
        },
        case_id=case_id,
        rows=1,
        proposal_id=proposal.id,
        audited=audited,
    )


@tool("confirm_proposal", kind=KIND_PROPOSAL_ACTION, title="Confirm proposal", annotations=WRITE_HINTS,
      scope=SCOPE_WRITE, rate_bucket="confirm")
def confirm_proposal(ctx, proposal_id: ProposalId):
    """Make the change a propose_* tool described, after the user has seen its preview and agreed. Runs
    once: confirming the same proposal again returns the first result. Fails if the proposal expired
    (15 minutes), was cancelled or has blockers."""
    _expire_if_due(ctx, proposal_id)
    with transaction.atomic():
        proposal = scoped(McpProposal, ctx).select_for_update().filter(pk=proposal_id).first()
        if proposal is None:
            raise NotFound("No proposal with that id.")
        if proposal.status == McpProposal.STATUS_CONFIRMED:
            return _confirmed_output(proposal, case_id=proposal.case_id)
        if proposal.status == McpProposal.STATUS_EXPIRED:
            raise InvalidInput("This proposal expired. Propose it again.")
        if proposal.status == McpProposal.STATUS_CANCELLED:
            raise InvalidInput("This proposal was cancelled.")
        if args_hash(proposal.tool, proposal.args) != proposal.args_hash or proposal.tool not in EXECUTORS:
            raise InvalidInput("This proposal changed after it was made. Propose it again.")
        if proposal.blockers:
            raise InvalidInput("This proposal has blockers and cannot be confirmed.")

        result = EXECUTORS[proposal.tool](ctx, proposal.args)
        proposal.status = McpProposal.STATUS_CONFIRMED
        proposal.result = result
        proposal.confirmed_at = timezone.now()
        proposal.save(update_fields=["status", "result", "confirmed_at", "updated_at"])
        # The audit row is part of the change: same transaction, and a
        # failure here rolls the change back.
        ActivityLog(
            owner=ctx.user,
            case_id=proposal.case_id,
            activity_type=audit.ACTIVITY_WRITE,
            description=audit.describe(
                tool="confirm_proposal",
                ctx_client_id=ctx.client_id,
                token_id=ctx.token_id,
                args={"proposal_id": proposal.id, "proposal_tool": proposal.tool},
                result="ok",
                rows=1,
                proposal_id=proposal.id,
            ),
        ).save()
    return _confirmed_output(proposal, case_id=proposal.case_id, audited=True)


@tool("cancel_proposal", kind=KIND_PROPOSAL_ACTION, title="Cancel proposal", annotations=WRITE_HINTS,
      scope=SCOPE_WRITE)
def cancel_proposal(ctx, proposal_id: ProposalId):
    """Close a proposal the user does not want. Nothing is changed. Cancelling twice is fine; a
    confirmed proposal cannot be cancelled."""
    _expire_if_due(ctx, proposal_id)
    proposal = scoped(McpProposal, ctx).filter(pk=proposal_id).first()
    if proposal is None:
        raise NotFound("No proposal with that id.")
    if proposal.status == McpProposal.STATUS_CONFIRMED:
        raise InvalidInput("This proposal was already confirmed and cannot be cancelled.")
    if proposal.status == McpProposal.STATUS_OPEN:
        scoped(McpProposal, ctx).filter(pk=proposal.pk, status=McpProposal.STATUS_OPEN).update(
            status=McpProposal.STATUS_CANCELLED
        )
        proposal.status = McpProposal.STATUS_CANCELLED
    return ToolOutput(
        data={"proposal_id": proposal.id, "status": proposal.status, "truncated": False},
        case_id=proposal.case_id,
        rows=0,
        proposal_id=proposal.id,
    )

