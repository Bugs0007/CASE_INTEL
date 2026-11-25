from datetime import timedelta
from typing import Annotated, Literal, Optional

from pydantic import Field

from core.models import Case, Hearing
from core.services.practice_assistant import reads
from core.services.practice_assistant.contracts import MAX_RANGE_DAYS

from ..access import scoped
from ..registry import KIND_READ, READ_HINTS, InvalidInput, ToolOutput, tool
from ..safety import MAX_ROWS, short_text
from .common import TIMEZONE, as_ist, court_names, now_ist, parse_day

_KIND_BY_INCLUDE = {"hearings": "hearing", "tasks": "task", "events": "event"}


@tool("get_schedule", kind=KIND_READ, title="Get schedule", annotations=READ_HINTS)
def get_schedule(
    ctx,
    date_from: Annotated[Optional[str], Field(description="First India date, YYYY-MM-DD. Default: today.")] = None,
    date_to: Annotated[
        Optional[str], Field(description="Last India date, YYYY-MM-DD. Default: tomorrow. At most 31 days.")
    ] = None,
    include: Annotated[
        Optional[list[Literal["hearings", "tasks", "events"]]],
        Field(description="Which kinds to include. Default: all three."),
    ] = None,
):
    """Hearings, tasks and the advocate's own appointments on India days date_from..date_to.

    Each hearing carries its stored cause-list result (listed / not_listed / not_published /
    fetch_failed / unsupported / not_checked) with item number, court hall, bench, list type and
    when it was last checked. This reads stored data only; it does not check any court website.
    """
    today = now_ist().date()
    start = parse_day(date_from, "date_from") or today
    end = parse_day(date_to, "date_to") or (start + timedelta(days=1))
    if end < start:
        raise InvalidInput("date_to is before date_from.")
    if (end - start).days + 1 > MAX_RANGE_DAYS:
        raise InvalidInput(f"The window covers at most {MAX_RANGE_DAYS} days.")
    kinds = [_KIND_BY_INCLUDE[item] for item in (include or _KIND_BY_INCLUDE)]

    window = reads.calendar_window(owner=ctx.owner, date_from=start, date_to=end, kinds=kinds)
    entries = window["entries"][:MAX_ROWS]

    hearing_ids = [e["id"] for e in entries if e["kind"] == "hearing"]
    slots = {
        row["id"]: row
        for row in scoped(Hearing, ctx)
        .filter(id__in=hearing_ids, case__owner_id__in=ctx.owner_ids)
        .values(
            "id",
            "cause_list_status",
            "cause_list_item_number",
            "cause_list_court_hall",
            "cause_list_bench",
            "cause_list_list_type",
            "cause_list_stage",
            "cause_list_checked_at",
            "location",
        )
    }
    case_ids = {e["case_id"] for e in entries if e.get("case_id")}
    courts = court_names(scoped(Case, ctx).filter(id__in=case_ids))

    items = []
    for entry in entries:
        item = {
            "type": entry["kind"],
            "id": entry["id"],
            "date": entry["day"],
            "start_time": entry["start_time"],
            "end_time": entry["end_time"],
            "status": entry["status"],
            "label": short_text(entry["label"]),
            "case_id": entry.get("case_id"),
            "case_title": short_text(entry.get("case_title")),
            "court": short_text(courts.get(entry.get("case_id"))) or None,
        }
        if entry["kind"] == "hearing":
            slot = slots.get(entry["id"], {})
            item.update(
                {
                    "cause_list_status": slot.get("cause_list_status"),
                    "item_number": slot.get("cause_list_item_number") or None,
                    "court_hall": slot.get("cause_list_court_hall") or None,
                    "bench": short_text(slot.get("cause_list_bench")) or None,
                    "list_type": short_text(slot.get("cause_list_list_type")) or None,
                    "stage": short_text(slot.get("cause_list_stage")) or None,
                    "cause_list_checked_at": as_ist(slot.get("cause_list_checked_at")),
                }
            )
        elif entry["kind"] == "task":
            item["needs_review"] = entry["needs_review"]
        items.append(item)

    return ToolOutput(
        data={
            "date_from": window["date_from"],
            "date_to": window["date_to"],
            "items": items,
            "total": window["total"],
            "truncated": window["total"] > len(items),
            "as_of": window["as_of"],
            "timezone": TIMEZONE,
        },
        rows=len(items),
        untrusted=True,
    )
