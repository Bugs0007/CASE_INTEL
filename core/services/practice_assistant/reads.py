"""The practice read model: owner-scoped reads over cases, hearings, tasks
and case events, in the shapes of contracts.py.

Rules every read here follows:

  - `owner` is a required keyword argument and every query filters by it,
    on the row itself AND on the case it hangs off;
  - `scope` must be "personal" (the only scope today);
  - counting, filtering, ordering and the one piece of date arithmetic
    (overdue) happen in SQL or in this module, never in a model's answer;
  - "none recorded" is a statement about stored rows only. Nothing here
    infers a date, an outcome or a cause-list result from a missing row;
  - a read costs a fixed number of queries however many cases there are;
  - each read takes an optional `now` (an aware datetime) so a caller or a
    test can pin the clock; it defaults to the real time.

Days are India days. A hearing is an instant, so its window is the aware IST
start of `date_from` up to (exclusive) the IST start of the day after
`date_to` -- never `__date` on the UTC column. Task.due_date and
CaseEvent.date are plain dates and are compared as such.

What a calendar shows (mirrors frontend-next/lib/calendar.ts, which the
/calendar page and the case-page card are built on):

  - order within a day is hearing, then event (all-day before timed, timed by
    start), then task -- `sortWithinDay`; ties break on id;
  - a task with no due date has no day, and a dismissed task (status
    "cancelled") is gone; a completed task stays, with its status;
  - cancelled events and hearings of ANY status stay as entries with their
    own status (`buildCalendarItems` filters neither);
  - day markers (`dayMarkerCounts`) count every hearing, only open tasks, and
    events that are not cancelled. So an entry can exist on a day whose
    marker for its kind is 0.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
from typing import Iterable, Optional

from django.db.models import Count, Exists, F, OuterRef, Q, Subquery
from django.db.models.functions import TruncDate
from django.utils import timezone

from core.models import Case, CaseEvent, Hearing, Task
from core.services.india_time import INDIA_TZ, india_now
from core.services.parties import court_names_for_cases

from .contracts import (
    HARD_ROW_CAP,
    MAX_RANGE_DAYS,
    PAGE_SIZE,
    SCOPE_PERSONAL,
    TIMEZONE,
    CalendarEntry,
    CalendarWindow,
    CaseCandidate,
    CaseRow,
    DeadlineRow,
    OpenDeadlines,
    PortfolioSnapshot,
    Reference,
)

# The same predicate the hearing reminders use
# (core/services/notifications/hearing_reminders.py, INACTIVE_CASE_STATUSES):
# a case is active unless it is closed or archived.
INACTIVE_CASE_STATUSES = ("closed", "archived")

# A hearing that can be "the next hearing".
NEXT_HEARING_STATUS = "scheduled"

CALENDAR_KINDS = ("hearing", "event", "task")  # display order within a day
_KIND_ORDER = {kind: index for index, kind in enumerate(CALENDAR_KINDS)}

# How many tasks / events case_facts carries.
CASE_FACTS_ROWS = 10


def active_cases_q(prefix: str = "") -> Q:
    """Q for "this case is active" (status not closed/archived). `prefix` is
    the path to the case from the model being filtered, e.g. "case__"."""
    return ~Q(**{f"{prefix}status__in": INACTIVE_CASE_STATUSES})


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _check_scope(scope: str) -> None:
    if scope != SCOPE_PERSONAL:
        raise ValueError(f"Unsupported scope {scope!r}; only {SCOPE_PERSONAL!r} is available.")


def _clock(now: Optional[datetime]) -> datetime:
    """`now` as an aware India-time datetime."""
    if now is None:
        return india_now()
    if timezone.is_naive(now):
        raise ValueError("now must be an aware datetime.")
    return timezone.localtime(now, INDIA_TZ)


def _india_day_start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=INDIA_TZ)


def _hhmm(value: Optional[time]) -> Optional[str]:
    return value.strftime("%H:%M") if value else None


def _next_hearings(owner, now: datetime):
    """The outer case's upcoming scheduled hearings, earliest first. Same rule
    as the case cards (core/views/case.py::_annotate_next_hearing_date):
    status scheduled, at or after now."""
    return Hearing.objects.filter(
        owner=owner,
        case=OuterRef("pk"),
        status=NEXT_HEARING_STATUS,
        hearing_date__gte=now,
    ).order_by("hearing_date", "id")


def _hearing_is_untimed(hearing: Hearing) -> bool:
    """eCourts gives a date, stored as 00:00 UTC (see india_time.py). That is
    a day, not an appointment at 05:30 IST."""
    return hearing.hearing_date.astimezone(dt_timezone.utc).time() == time.min


def _hearing_label(hearing: Hearing) -> str:
    return (hearing.purpose or "").strip() or hearing.get_hearing_type_display()


def _hearing_ref(hearing: Hearing) -> Reference:
    local = timezone.localtime(hearing.hearing_date, INDIA_TZ)
    return {
        "kind": "hearing",
        "id": hearing.id,
        "case_id": hearing.case_id,
        "label": _hearing_label(hearing),
        "recorded_at": local.date().isoformat() if _hearing_is_untimed(hearing) else local.isoformat(),
    }


def _hearing_entry(hearing: Hearing) -> CalendarEntry:
    local = timezone.localtime(hearing.hearing_date, INDIA_TZ)
    return {
        "kind": "hearing",
        "id": hearing.id,
        "case_id": hearing.case_id,
        "case_title": hearing.case.title,
        "day": local.date().isoformat(),
        "start_time": None if _hearing_is_untimed(hearing) else local.strftime("%H:%M"),
        "end_time": None,
        "status": hearing.status,
        "label": _hearing_label(hearing),
        "provenance": hearing.source,
        "needs_review": False,
        "ref": _hearing_ref(hearing),
    }


def _task_ref(task: Task) -> Reference:
    return {
        "kind": "task",
        "id": task.id,
        "case_id": task.case_id,
        "label": task.title or "Task",
        "recorded_at": task.due_date.isoformat() if task.due_date else None,
    }


def _task_entry(task: Task) -> CalendarEntry:
    return {
        "kind": "task",
        "id": task.id,
        "case_id": task.case_id,
        "case_title": task.case.title if task.case_id else None,
        "day": task.due_date.isoformat(),
        "start_time": None,
        "end_time": None,
        "status": task.status,
        "label": task.title or "Task",
        "provenance": task.kind,
        "needs_review": task.needs_review,
        "ref": _task_ref(task),
    }


def _deadline_row(task: Task, today: date) -> DeadlineRow:
    return {
        "id": task.id,
        "case_id": task.case_id,
        "case_title": task.case.title if task.case_id else None,
        "title": task.title or "Task",
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "status": task.status,
        "kind": task.kind,
        "needs_review": task.needs_review,
        "due_date_basis": task.due_date_basis or None,
        "overdue": bool(task.due_date and task.due_date < today),
        "ref": _task_ref(task),
    }


def _event_entry(event: CaseEvent) -> CalendarEntry:
    return {
        "kind": "event",
        "id": event.id,
        "case_id": event.case_id,
        "case_title": event.case.title,
        "day": event.date.isoformat(),
        "start_time": _hhmm(event.start_time),
        "end_time": _hhmm(event.end_time),
        "status": event.status,
        "label": event.title,
        "provenance": "manual",
        "needs_review": False,
        "ref": {
            "kind": "event",
            "id": event.id,
            "case_id": event.case_id,
            "label": event.title,
            "recorded_at": event.date.isoformat(),
        },
    }


def _owned_tasks(owner):
    """The owner's tasks. A task may have no case; one that has a case must
    have the owner's."""
    return Task.objects.filter(Q(case__isnull=True) | Q(case__owner=owner), owner=owner)


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------


def portfolio_snapshot(
    *,
    owner,
    scope: str = SCOPE_PERSONAL,
    status: Optional[str] = None,
    page: int = 1,
    page_size: int = PAGE_SIZE,
    now: Optional[datetime] = None,
) -> PortfolioSnapshot:
    """Counts across the owner's cases plus one page of case rows.

    The counts always cover every case; `status` narrows only the rows and
    `total`. A case with several future hearings is one case. `page_size` is
    held to HARD_ROW_CAP. 4 queries (counts, rows, 2 for court names).
    """
    _check_scope(scope)
    if page < 1 or page_size < 1:
        raise ValueError("page and page_size must be at least 1.")
    page_size = min(page_size, HARD_ROW_CAP)
    current = _clock(now)
    upcoming = _next_hearings(owner, current)

    status_counts: dict[str, int] = {}
    active = active_with_next = 0
    grouped = (
        Case.objects.filter(owner=owner)
        .annotate(has_next=Exists(upcoming))
        .order_by()
        .values("status")
        .annotate(n=Count("id"), with_next=Count("id", filter=Q(has_next=True)))
    )
    for row in grouped:
        status_counts[row["status"]] = row["n"]
        if row["status"] not in INACTIVE_CASE_STATUSES:
            active += row["n"]
            active_with_next += row["with_next"]
    total_cases = sum(status_counts.values())

    cases_qs = Case.objects.filter(owner=owner)
    if status:
        cases_qs = cases_qs.filter(status=status)
    offset = (page - 1) * page_size
    cases = list(
        cases_qs.annotate(next_hearing_at=Subquery(upcoming.values("hearing_date")[:1]))
        .order_by("-created_at", "-id")
        .only("id", "title", "case_number", "status", "cnr_number")[offset : offset + page_size]
    )
    courts = court_names_for_cases(cases)
    rows: list[CaseRow] = [
        {
            "id": case.id,
            "title": case.title,
            "case_number": case.case_number or None,
            "court": courts.get(case.id) or None,
            "status": case.status,
            "next_hearing_at": (
                timezone.localtime(case.next_hearing_at, INDIA_TZ).isoformat()
                if case.next_hearing_at
                else None
            ),
        }
        for case in cases
    ]
    return {
        "status_counts": status_counts,
        "total_cases": total_cases,
        "active_cases": active,
        "active_with_next_hearing": active_with_next,
        "active_without_next_date": active - active_with_next,
        "cases": rows,
        "page": page,
        "page_size": page_size,
        "total": status_counts.get(status, 0) if status else total_cases,
        "as_of": current.isoformat(),
        "timezone": TIMEZONE,
    }


# ---------------------------------------------------------------------------
# Calendar
# ---------------------------------------------------------------------------


def calendar_window(
    *,
    owner,
    scope: str = SCOPE_PERSONAL,
    date_from: date,
    date_to: date,
    kinds: Optional[Iterable[str]] = None,
    case_id: Optional[int] = None,
    now: Optional[datetime] = None,
) -> CalendarWindow:
    """Hearings, tasks and case events on the India days date_from..date_to
    (inclusive, at most MAX_RANGE_DAYS days).

    Which rows appear and which count towards the day markers is in the module
    docstring. `total` and `day_markers` are exact for the whole window;
    `entries` stops at HARD_ROW_CAP (earliest first) and `truncated` says so.
    Items of closed cases are included, as on the existing calendar.
    2 queries per requested kind (6 for all three).
    """
    _check_scope(scope)
    if isinstance(date_from, datetime) or isinstance(date_to, datetime):
        raise ValueError("date_from and date_to must be plain dates.")
    if date_to < date_from:
        raise ValueError("date_to is before date_from.")
    if (date_to - date_from).days + 1 > MAX_RANGE_DAYS:
        raise ValueError(f"A calendar window covers at most {MAX_RANGE_DAYS} days.")
    wanted = set(CALENDAR_KINDS if kinds is None else kinds)
    unknown = wanted - set(CALENDAR_KINDS)
    if unknown:
        raise ValueError(f"Unknown calendar kinds: {sorted(unknown)}")
    current = _clock(now)

    markers: dict[str, dict[str, int]] = {}
    total = 0
    keyed: list[tuple[tuple, CalendarEntry]] = []

    def mark(day: date, kind: str, shown: int, counted: int) -> None:
        nonlocal total
        total += shown
        slot = markers.setdefault(day.isoformat(), {"hearing": 0, "task": 0, "event": 0})
        slot[kind] += counted

    if "hearing" in wanted:
        hearings = Hearing.objects.filter(
            owner=owner,
            case__owner=owner,
            hearing_date__gte=_india_day_start(date_from),
            hearing_date__lt=_india_day_start(date_to + timedelta(days=1)),
        )
        if case_id is not None:
            hearings = hearings.filter(case_id=case_id)
        per_day = (
            hearings.order_by()
            .values(day=TruncDate("hearing_date", tzinfo=INDIA_TZ))
            .annotate(n=Count("id"))
        )
        for row in per_day:
            mark(row["day"], "hearing", row["n"], row["n"])
        for hearing in hearings.select_related("case").order_by("hearing_date", "id")[:HARD_ROW_CAP]:
            entry = _hearing_entry(hearing)
            keyed.append(((entry["day"], _KIND_ORDER["hearing"], hearing.hearing_date.isoformat(), hearing.id), entry))

    if "event" in wanted:
        events = CaseEvent.objects.filter(
            owner=owner, case__owner=owner, date__gte=date_from, date__lte=date_to
        )
        if case_id is not None:
            events = events.filter(case_id=case_id)
        per_day = (
            events.order_by()
            .values("date")
            .annotate(n=Count("id"), live=Count("id", filter=~Q(status=CaseEvent.STATUS_CANCELLED)))
        )
        for row in per_day:
            mark(row["date"], "event", row["n"], row["live"])
        ordered = events.select_related("case").order_by(
            "date", F("start_time").asc(nulls_first=True), "id"
        )
        for event in ordered[:HARD_ROW_CAP]:
            entry = _event_entry(event)
            keyed.append(((entry["day"], _KIND_ORDER["event"], entry["start_time"] or "", event.id), entry))

    if "task" in wanted:
        tasks = _owned_tasks(owner).filter(due_date__gte=date_from, due_date__lte=date_to).exclude(
            status=Task.STATUS_CANCELLED
        )
        if case_id is not None:
            tasks = tasks.filter(case_id=case_id)
        per_day = (
            tasks.order_by()
            .values("due_date")
            .annotate(n=Count("id"), open=Count("id", filter=Q(status__in=Task.OPEN_STATUSES)))
        )
        for row in per_day:
            mark(row["due_date"], "task", row["n"], row["open"])
        for task in tasks.select_related("case").order_by("due_date", "id")[:HARD_ROW_CAP]:
            entry = _task_entry(task)
            keyed.append(((entry["day"], _KIND_ORDER["task"], "", task.id), entry))

    # Each kind was read earliest-first up to the cap, so the first
    # HARD_ROW_CAP of the merged order are all among the rows fetched.
    keyed.sort(key=lambda pair: pair[0])
    entries = [entry for _, entry in keyed[:HARD_ROW_CAP]]
    return {
        "date_from": date_from.isoformat(),
        "date_to": date_to.isoformat(),
        "entries": entries,
        "day_markers": dict(sorted(markers.items())),
        "total": total,
        "truncated": total > len(entries),
        "as_of": current.isoformat(),
        "timezone": TIMEZONE,
    }


# ---------------------------------------------------------------------------
# Deadlines
# ---------------------------------------------------------------------------


def open_deadlines(
    *,
    owner,
    scope: str = SCOPE_PERSONAL,
    case_id: Optional[int] = None,
    limit: int = PAGE_SIZE,
    now: Optional[datetime] = None,
) -> OpenDeadlines:
    """The owner's open tasks (pending / in progress), earliest due first,
    undated ones last.

    Due dates are the stored ones; the only arithmetic is `overdue` (due
    before India today). An undated open task is listed with due_date None
    and is never overdue. `limit` is held to HARD_ROW_CAP; `total` is the
    exact count and `truncated` is set when rows were left out. 2 queries.
    """
    _check_scope(scope)
    if limit < 1:
        raise ValueError("limit must be at least 1.")
    limit = min(limit, HARD_ROW_CAP)
    current = _clock(now)
    tasks = _owned_tasks(owner).filter(status__in=Task.OPEN_STATUSES)
    if case_id is not None:
        tasks = tasks.filter(case_id=case_id)
    total = tasks.count()
    rows = tasks.select_related("case").order_by(F("due_date").asc(nulls_last=True), "id")[:limit]
    entries = [_deadline_row(task, current.date()) for task in rows]
    return {
        "entries": entries,
        "total": total,
        "truncated": total > len(entries),
        "as_of": current.isoformat(),
        "timezone": TIMEZONE,
    }


# ---------------------------------------------------------------------------
# One case
# ---------------------------------------------------------------------------


def case_facts(
    *,
    owner,
    scope: str = SCOPE_PERSONAL,
    case_id: int,
    now: Optional[datetime] = None,
) -> Optional[dict]:
    """Recorded facts about one of the owner's cases, or None when the case is
    not the owner's (or does not exist) -- the case is resolved under the
    owner before anything related is read.

    Keys: `case` (identity + `ref`), `next_hearing` (or None: no scheduled
    hearing at or after now is RECORDED, nothing more), `open_tasks` and
    `upcoming_events` (each `{entries, total, truncated}`, at most
    CASE_FACTS_ROWS entries; events are scheduled ones dated India today or
    later), `as_of`, `timezone`. 6 queries (case, 2 court name, hearing,
    tasks, events).
    """
    _check_scope(scope)
    current = _clock(now)
    today = current.date()
    open_task_count = Count(
        "tasks", filter=Q(tasks__owner=owner, tasks__status__in=Task.OPEN_STATUSES), distinct=True
    )
    event_count = Count(
        "events",
        filter=Q(events__owner=owner, events__status=CaseEvent.STATUS_SCHEDULED, events__date__gte=today),
        distinct=True,
    )
    case = (
        Case.objects.filter(owner=owner, pk=case_id)
        .annotate(open_task_count=open_task_count, upcoming_event_count=event_count)
        .first()
    )
    if case is None:
        return None
    court = court_names_for_cases([case]).get(case.id) or None

    hearing = (
        Hearing.objects.filter(
            owner=owner, case=case, status=NEXT_HEARING_STATUS, hearing_date__gte=current
        )
        .select_related("case")
        .order_by("hearing_date", "id")
        .first()
    )
    tasks = list(
        Task.objects.filter(owner=owner, case=case, status__in=Task.OPEN_STATUSES)
        .select_related("case")
        .order_by(F("due_date").asc(nulls_last=True), "id")[:CASE_FACTS_ROWS]
    )
    events = list(
        CaseEvent.objects.filter(
            owner=owner, case=case, status=CaseEvent.STATUS_SCHEDULED, date__gte=today
        )
        .select_related("case")
        .order_by("date", F("start_time").asc(nulls_first=True), "id")[:CASE_FACTS_ROWS]
    )
    return {
        "case": {
            "id": case.id,
            "title": case.title,
            "case_number": case.case_number or None,
            "cnr_number": case.cnr_number or None,
            "court": court,
            "status": case.status,
            "ref": {
                "kind": "case",
                "id": case.id,
                "case_id": case.id,
                "label": case.title,
                "recorded_at": None,
            },
        },
        "next_hearing": _hearing_entry(hearing) if hearing else None,
        "open_tasks": {
            "entries": [_deadline_row(task, today) for task in tasks],
            "total": case.open_task_count,
            "truncated": case.open_task_count > len(tasks),
        },
        "upcoming_events": {
            "entries": [_event_entry(event) for event in events],
            "total": case.upcoming_event_count,
            "truncated": case.upcoming_event_count > len(events),
        },
        "as_of": current.isoformat(),
        "timezone": TIMEZONE,
    }


def resolve_case_candidates(
    *,
    owner,
    scope: str = SCOPE_PERSONAL,
    text: str,
    limit: int = 5,
) -> list[CaseCandidate]:
    """The owner's cases whose title, case number or CNR contains `text`
    (case-insensitive), or whose client, party or client-contact name does,
    for the "which case did you mean" chooser. "K. Rao" also matches "K Rao".
    Blank text matches nothing. Ordered by title then id; `limit` is held to
    HARD_ROW_CAP. 3 queries (cases, 2 for court names), 0 for blank text.
    """
    _check_scope(scope)
    if limit < 1:
        raise ValueError("limit must be at least 1.")
    needle = (text or "").strip()
    if not needle:
        return []
    match = Q()
    for variant in dict.fromkeys([needle, " ".join(needle.replace(".", " ").split())]):
        match |= (
            Q(title__icontains=variant)
            | Q(case_number__icontains=variant)
            | Q(case_number_raw__icontains=variant)
            | Q(cnr_number__icontains=variant)
            | Q(client_name__icontains=variant)
            | Q(petitioner_name__icontains=variant)
            | Q(respondent_name__icontains=variant)
            | Q(client_contacts__name__icontains=variant)
        )
    ids = Case.objects.filter(owner=owner).filter(match).values("id")
    cases = list(
        Case.objects.filter(owner=owner, id__in=ids)
        .order_by("title", "id")
        .only("id", "title", "case_number", "cnr_number")[: min(limit, HARD_ROW_CAP)]
    )
    return _candidates(cases)


def case_candidates_by_ids(*, owner, ids: list[int]) -> list[CaseCandidate]:
    """Chooser rows for these of the owner's cases, in the given order."""
    found = {case.id: case for case in Case.objects.filter(owner=owner, id__in=ids[:HARD_ROW_CAP])}
    return _candidates([found[case_id] for case_id in ids if case_id in found])


def _candidates(cases: list[Case]) -> list[CaseCandidate]:
    courts = court_names_for_cases(cases)
    return [
        {
            "id": case.id,
            "title": case.title,
            "case_number": case.case_number or None,
            "court": courts.get(case.id) or None,
        }
        for case in cases
    ]
