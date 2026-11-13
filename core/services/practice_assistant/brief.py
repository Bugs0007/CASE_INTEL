"""The hearing brief: one section per scheduled hearing in a period, with the
case's status, the last order, your side's directions, open tasks, the
written "state of the matter" briefing and points to cover.

Built from the same pieces as the per-hearing prep sheet
(core/services/hearing_digest): assemble_hearing_digest for the facts and the
cached CaseBriefing paragraph for the prose. Building it never calls a model
and never enqueues anything; hearings whose paragraph is not written yet are
listed so the advocate can ask for them (the report card's button calls the
existing POST /api/hearings/<id>/digest/briefing/ for each).
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone

from django.utils import timezone

from core.models import Hearing
from core.serializers.order_summary import build_order_summary
from core.services.hearing_digest.assemble import assemble_hearing_digest
from core.services.hearing_digest.briefing import STATE_READY, STATE_STALE, get_briefing_state
from core.services.india_time import INDIA_TZ, india_fmt
from core.services.parties import court_names_for_cases

BRIEF_HEARING_CAP = 25
# Read-only: the cause-list outcome to warn about. Only the cause-list
# service ever assigns it (see test_causelist_framework).
NOT_ON_CAUSE_LIST = "not_listed"


def _direction_text(item) -> str:
    if isinstance(item, dict):
        return str(item.get("text") or item.get("direction") or item.get("summary") or "").strip()
    return str(item or "").strip()


def _when(hearing: Hearing) -> str:
    local = timezone.localtime(hearing.hearing_date, INDIA_TZ)
    untimed = hearing.hearing_date.astimezone(dt_timezone.utc).time() == time.min
    return local.strftime("%a %d %b %Y") + ("" if untimed else local.strftime(", %H:%M"))


def _slot(hearing: Hearing) -> str:
    from .reports import _slot as report_slot  # one wording for the cause-list column

    slot = report_slot(hearing)
    return "Not checked yet" if slot == "-" else slot


def hearing_section(hearing: Hearing, court: str, today: date) -> tuple[dict, bool]:
    """(section block, briefing missing) for one hearing."""
    digest = assemble_hearing_digest(hearing)
    case = hearing.case
    snapshot = digest.snapshot or {}
    briefing = get_briefing_state(case)

    status = " / ".join(p for p in (snapshot.get("case_status"), snapshot.get("case_stage")) if p)
    items = [
        ("When", _when(hearing)),
        ("Court", court or hearing.location or "Not recorded"),
        ("Case status", status or case.get_status_display()),
        ("Hearing for", "; ".join(digest.purposes) or hearing.get_hearing_type_display()),
        ("Cause list", _slot(hearing)),
    ]

    points: list[str] = []
    your_side: list[str] = []
    order = digest.last_order
    if order is not None:
        summary = build_order_summary(order)
        happened = (summary.get("what_happened") or "").strip()
        items.append(("Last order", f"{india_fmt(order.order_date)}: {happened or 'No summary text.'}"))
        your_side = [t for t in (_direction_text(d) for d in summary.get("your_side_directions") or []) if t]
        if summary.get("your_side_directions") is None:
            # Party role unknown: both sides' directions, labelled.
            for label, key in (("Petitioner", "petitioner_directions"), ("Respondent", "respondent_directions")):
                your_side += [f"{label}: {t}" for t in (_direction_text(d) for d in summary.get(key) or []) if t]
        if your_side:
            items.append(("Directions", "; ".join(your_side)))
    else:
        items.append(("Last order", "No summarised order before this hearing."))

    for direction in your_side:
        points.append(f"Report compliance with the direction: {direction}")
    for task in digest.open_tasks[:6]:
        if task.due_date and task.due_date < today:
            points.append(f"Overdue since {india_fmt(task.due_date)}: {task.title or 'Task'}")
        elif task.due_date and task.due_date <= hearing.hearing_date.date():
            points.append(f"Due before the hearing ({india_fmt(task.due_date)}): {task.title or 'Task'}")
    if digest.purposes:
        points.append(f"Be ready for: {digest.purposes[0]}")
    if hearing.cause_list_status == NOT_ON_CAUSE_LIST:
        points.append("The case is not on the court's cause list for this date: confirm with the registry.")
    if digest.open_tasks:
        items.append(
            (
                "Open tasks",
                "; ".join(
                    (task.title or "Task") + (f" (due {india_fmt(task.due_date)})" if task.due_date else "")
                    for task in digest.open_tasks[:6]
                ),
            )
        )

    ready = briefing["status"] == STATE_READY
    if ready or (briefing["status"] == STATE_STALE and briefing["text"]):
        note = "" if ready else " (written before the latest changes)"
        items.append((f"State of the matter{note}", briefing["text"]))
    else:
        items.append(("State of the matter", "Not written yet."))

    heading = f"{case.title}" + (f" ({case.case_number})" if case.case_number else "")
    section = {
        "type": "section",
        "heading": heading,
        "items": items,
        "bullets_heading": "Points to cover",
        "bullets": points or ["Nothing pending is recorded for this case; review the file before the hearing."],
        "ref_hearing_id": hearing.id,
    }
    missing = not ready and briefing["status"] != "unavailable" and briefing["status"] != "generating"
    return section, missing


def build_brief(owner, date_from: date, date_to: date, now: datetime) -> dict:
    start = datetime.combine(date_from, time.min, tzinfo=INDIA_TZ)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=INDIA_TZ)
    qs = (
        Hearing.objects.filter(
            owner=owner, case__owner=owner, status="scheduled", hearing_date__gte=start, hearing_date__lt=end
        )
        .select_related("case")
        .order_by("hearing_date", "id")
    )
    total = qs.count()
    hearings = list(qs[:BRIEF_HEARING_CAP])
    courts = court_names_for_cases([h.case for h in hearings])
    today = now.astimezone(INDIA_TZ).date()
    blocks, missing = [], []
    for hearing in hearings:
        section, needs = hearing_section(hearing, courts.get(hearing.case_id) or "", today)
        blocks.append(section)
        if needs:
            missing.append(hearing.id)
    if not blocks:
        blocks.append(
            {
                "type": "table",
                "heading": "Hearings",
                "columns": ["Date", "Case"],
                "rows": [],
                "empty": "No scheduled hearings are recorded in Case Intel for this period.",
            }
        )
    elif total > len(hearings):
        blocks.append(
            {
                "type": "summary",
                "heading": "Not included",
                "items": [("Hearings left out", f"{total - len(hearings)} (the brief covers the first {BRIEF_HEARING_CAP})")],
            }
        )
    return {"row_count": total, "blocks": blocks, "briefings_missing": missing}
