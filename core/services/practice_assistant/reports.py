"""Practice reports: the data behind the Case Bot's downloadable reports.

Five kinds (billing, hearings, cases, deadlines, brief), each built from the owner's
own rows with no model call, in India dates. `build_report` returns one plain
structure that report_render.py turns into a PDF or a DOCX, and whose
`row_count` the chat turn shows on its report card.

Every query filters by `owner` on the row AND on the case it hangs off, so a
report can only ever carry the caller's own data.

What the periods mean:
  billing   fees for hearings dated inside the period (a fee is a charge for
            a hearing, and a pending fee has no invoice date yet)
  hearings  hearings dated inside the period
  deadlines open tasks due inside the period when one is given, else all
  cases     every active case; a period does not apply
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Count, Exists, F, OuterRef, Subquery

from core.models import AppearanceFee, Case, CourtOrder, Hearing, Task
from core.services.india_time import INDIA_TZ, india_fmt, india_now
from core.services.money import pdf_inr
from core.services.parties import court_names_for_cases

from . import parsing, reads
from .contracts import REPORT_KINDS

MAX_PERIOD_DAYS = 1100
HEARING_ROW_CAP = 500
UNINVOICED_ROW_CAP = 200

TITLES = {
    "billing": "Billing report",
    "hearings": "Hearings report",
    "cases": "Cases report",
    "deadlines": "Deadlines report",
    "brief": "Hearing brief",
}


class ReportError(ValueError):
    """A bad kind or period. The message is plain text for the caller."""


def default_period(kind: str, today: date) -> Optional[tuple[date, date]]:
    if kind == "billing":
        start = parsing.financial_year_start(today)
        return start, date(start.year + 1, 3, 31)
    if kind == "hearings":
        return today, today + timedelta(days=30)
    if kind == "brief":
        return today, today + timedelta(days=6)
    return None


def check_period(date_from: Optional[date], date_to: Optional[date]) -> None:
    if (date_from is None) != (date_to is None):
        raise ReportError("Give both dates of the period, or neither.")
    if date_from and date_to:
        if date_to < date_from:
            raise ReportError("The end date cannot be before the start date.")
        if (date_to - date_from).days + 1 > MAX_PERIOD_DAYS:
            raise ReportError("A report can cover at most three years.")


def _start(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=INDIA_TZ)


def _day_bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """Aware India-time [start of date_from, start of the day after date_to)."""
    return _start(date_from), _start(date_to + timedelta(days=1))


def _inr(value) -> str:
    return pdf_inr(Decimal(value))


def period_text(date_from: Optional[date], date_to: Optional[date]) -> str:
    if date_from and date_to:
        if date_from == date_to:
            return india_fmt(date_from)
        return f"{india_fmt(date_from)} to {india_fmt(date_to)}"
    return "All dates"


def _client_name(case: Case) -> str:
    """The case's client, else its billing contact (the person invoices go to).
    Callers prefetch client_contacts, so this adds no query per row."""
    name = (case.client_name or (case.client.name if case.client_id else "") or "").strip()
    if name:
        return name
    contact = next((c for c in case.client_contacts.all() if c.is_billing_contact), None)
    return (contact.name if contact else "").strip()


# ---------------------------------------------------------------------------
# One builder per kind
# ---------------------------------------------------------------------------


def _billing(owner, date_from: date, date_to: date, now: datetime) -> dict:
    start, end = _day_bounds(date_from, date_to)
    fees = list(
        AppearanceFee.objects.filter(
            owner=owner,
            hearing__case__owner=owner,
            hearing__hearing_date__gte=start,
            hearing__hearing_date__lt=end,
        )
        .select_related("hearing__case__client")
        .prefetch_related("hearing__case__client_contacts")
        .order_by("hearing__case__client_name", "hearing__case__title", "hearing__hearing_date", "id")
    )
    invoiced = paid = pending = Decimal(0)
    for fee in fees:
        if fee.status == AppearanceFee.STATUS_PAID:
            invoiced += fee.amount
            paid += fee.amount
        elif fee.status == AppearanceFee.STATUS_INVOICED:
            invoiced += fee.amount
        else:
            pending += fee.amount
    rows = [
        [
            _client_name(fee.hearing.case) or "-",
            fee.hearing.case.title,
            india_fmt(fee.hearing.hearing_date),
            fee.get_category_display(),
            _inr(fee.amount),
            fee.get_status_display() + (", sent" if fee.send_status == AppearanceFee.SEND_SENT else ""),
            fee.invoice_number or "-",
            india_fmt(fee.invoiced_at) or "-",
            india_fmt(fee.paid_at) or "-",
        ]
        for fee in fees
    ]

    billed = AppearanceFee.objects.filter(
        owner=owner,
        hearing=OuterRef("pk"),
        status__in=[AppearanceFee.STATUS_INVOICED, AppearanceFee.STATUS_PAID],
    )
    anything = AppearanceFee.objects.filter(owner=owner, hearing=OuterRef("pk"))
    hearing_qs = (
        Hearing.objects.filter(
            owner=owner,
            case__owner=owner,
            hearing_date__gte=start,
            hearing_date__lt=min(end, now),
        )
        .exclude(status="cancelled")
        .annotate(has_billed=Exists(billed), has_fee=Exists(anything))
        .filter(has_billed=False)
        .select_related("case__client")
        .prefetch_related("case__client_contacts")
        .order_by("case__client_name", "case__title", "hearing_date", "id")
    )
    uninvoiced = list(hearing_qs[:UNINVOICED_ROW_CAP])
    uninvoiced_rows = [
        [
            _client_name(h.case) or "-",
            h.case.title,
            india_fmt(h.hearing_date),
            "Fee recorded, not invoiced" if h.has_fee else "No fee recorded",
        ]
        for h in uninvoiced
    ]

    blocks = [
        {
            "type": "summary",
            "heading": "Totals",
            "items": [
                ["Invoiced (including paid)", _inr(invoiced)],
                ["Paid", _inr(paid)],
                ["Outstanding (invoiced, not paid)", _inr(invoiced - paid)],
                ["Not yet invoiced", _inr(pending)],
                ["Fees in this report", str(len(fees))],
            ],
        },
        {
            "type": "table",
            "heading": "Fees by client and case",
            "columns": ["Client", "Case", "Hearing", "Category", "Amount", "Status", "Invoice", "Invoiced", "Paid"],
            "weights": [2, 3, 1.4, 1.5, 1.5, 1.6, 1.4, 1.4, 1.4],
            "rows": rows,
            "empty": "No fees are recorded for hearings in this period.",
        },
        {
            "type": "table",
            "heading": "Past hearings with no invoice",
            "columns": ["Client", "Case", "Hearing", "Fee"],
            "weights": [3, 4, 1.6, 3],
            "rows": uninvoiced_rows,
            "empty": "Every past hearing in this period has an invoice.",
            "note": (
                f"Only the first {UNINVOICED_ROW_CAP} are listed."
                if hearing_qs.count() > UNINVOICED_ROW_CAP
                else None
            ),
        },
    ]
    return {"row_count": len(fees), "blocks": blocks}


def _slot(hearing: Hearing) -> str:
    status = hearing.cause_list_status
    if status == Hearing.CAUSE_LIST_LISTED:
        bits = [
            f"Item {hearing.cause_list_item_number}" if hearing.cause_list_item_number else "",
            f"Court {hearing.cause_list_court_hall}" if hearing.cause_list_court_hall else "",
            hearing.cause_list_bench or "",
            hearing.cause_list_list_type or "",
        ]
        return ", ".join(bit for bit in bits if bit) or "Listed"
    if status == Hearing.CAUSE_LIST_NOT_CHECKED:
        return "-"
    return hearing.get_cause_list_status_display()


def _hearings(owner, date_from: date, date_to: date, now: datetime) -> dict:
    start, end = _day_bounds(date_from, date_to)
    qs = (
        Hearing.objects.filter(
            owner=owner, case__owner=owner, hearing_date__gte=start, hearing_date__lt=end
        )
        .select_related("case")
        .order_by("hearing_date", "id")
    )
    total = qs.count()
    hearings = list(qs[:HEARING_ROW_CAP])
    courts = court_names_for_cases([h.case for h in hearings])
    rows = [
        [
            india_fmt(h.hearing_date),
            h.case.title,
            h.case.case_number or "-",
            courts.get(h.case_id) or h.location or "-",
            ((h.purpose or "").strip() or h.get_hearing_type_display()),
            h.get_status_display(),
            _slot(h),
        ]
        for h in hearings
    ]
    return {
        "row_count": total,
        "blocks": [
            {
                "type": "table",
                "heading": "Hearings",
                "columns": ["Date", "Case", "Case no.", "Court", "Purpose", "Status", "Cause list"],
                "weights": [1.5, 3, 2, 3, 2.4, 1.5, 3],
                "rows": rows,
                "empty": "No hearings are recorded in Case Intel for this period.",
                "note": f"Only the first {HEARING_ROW_CAP} of {total} are listed." if total > len(rows) else None,
            }
        ],
    }


def _cases(owner, now: datetime) -> dict:
    upcoming = reads._next_hearings(owner, now)
    open_tasks = Task.objects.filter(
        owner=owner, case=OuterRef("pk"), status__in=Task.OPEN_STATUSES
    ).values("case").annotate(n=Count("id")).values("n")
    cases = list(
        Case.objects.filter(owner=owner)
        .exclude(status__in=reads.INACTIVE_CASE_STATUSES)
        .annotate(
            next_at=Subquery(upcoming.values("hearing_date")[:1]),
            last_order=Subquery(
                CourtOrder.objects.filter(owner=owner, case=OuterRef("pk"), order_date__isnull=False)
                .order_by(F("order_date").desc(nulls_last=True))
                .values("order_date")[:1]
            ),
            open_task_count=Subquery(open_tasks),
        )
        .order_by(F("next_at").asc(nulls_first=True), "title", "id")
    )
    courts = court_names_for_cases(cases)
    missing = sum(1 for case in cases if case.next_at is None)
    rows = [
        [
            case.title,
            case.case_number or "-",
            courts.get(case.id) or "-",
            india_fmt(case.next_at) if case.next_at else "No next date recorded",
            india_fmt(case.last_order) if case.last_order else "-",
            str(case.open_task_count or 0),
        ]
        for case in cases
    ]
    return {
        "row_count": len(cases),
        "blocks": [
            {
                "type": "summary",
                "heading": "Summary",
                "items": [
                    ["Active cases", str(len(cases))],
                    ["With no next date recorded", str(missing)],
                ],
            },
            {
                "type": "table",
                "heading": "Active cases (those with no next date first)",
                "columns": ["Case", "Case no.", "Court", "Next date", "Last order", "Open tasks"],
                "weights": [4, 2.4, 3, 2.2, 1.6, 1.2],
                "rows": rows,
                "empty": "No active cases are recorded in Case Intel.",
            },
        ],
    }


def _deadlines(owner, date_from: Optional[date], date_to: Optional[date], now: datetime) -> dict:
    today = now.date()
    qs = reads._owned_tasks(owner).filter(status__in=Task.OPEN_STATUSES)
    if date_from and date_to:
        qs = qs.filter(due_date__gte=date_from, due_date__lte=date_to)
    tasks = list(qs.select_related("case").order_by(F("due_date").asc(nulls_last=True), "id"))
    overdue = sum(1 for task in tasks if task.due_date and task.due_date < today)
    rows = [
        [
            india_fmt(task.due_date) if task.due_date else "No due date",
            "Overdue" if task.due_date and task.due_date < today else "",
            task.title or "Task",
            task.case.title if task.case_id else "-",
            task.get_kind_display() if hasattr(task, "get_kind_display") else task.kind,
            task.get_status_display(),
        ]
        for task in tasks
    ]
    return {
        "row_count": len(tasks),
        "blocks": [
            {
                "type": "summary",
                "heading": "Summary",
                "items": [["Open tasks", str(len(tasks))], ["Overdue", str(overdue)]],
            },
            {
                "type": "table",
                "heading": "Open tasks (overdue first)",
                "columns": ["Due", "", "Task", "Case", "Kind", "Status"],
                "weights": [1.8, 1.2, 5, 4, 1.8, 1.8],
                "rows": rows,
                "empty": "No open tasks are recorded in Case Intel.",
            },
        ],
    }


def build_report(
    *,
    owner,
    kind: str,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    now: Optional[datetime] = None,
) -> dict:
    """The report of `kind` for `owner`, as plain data:

      {kind, title, date_from, date_to, period_text, generated_on, row_count,
       blocks: [{type: summary|table, heading, ...}]}

    With no period, billing is this financial year and hearings today..+30;
    cases and deadlines have none. `date_from`/`date_to` are India dates.
    """
    if kind not in REPORT_KINDS:
        raise ReportError("Unknown report.")
    current = now.astimezone(INDIA_TZ) if now else india_now()
    check_period(date_from, date_to)
    if date_from is None:
        period = default_period(kind, current.date())
        date_from, date_to = period if period else (None, None)
    if kind == "cases":
        date_from = date_to = None
    if kind == "billing":
        body = _billing(owner, date_from, date_to, current)
    elif kind == "hearings":
        body = _hearings(owner, date_from, date_to, current)
    elif kind == "cases":
        body = _cases(owner, current)
    elif kind == "brief":
        from .brief import build_brief

        if (date_to - date_from).days > 30:
            raise ReportError("A hearing brief can cover at most 31 days.")
        body = build_brief(owner, date_from, date_to, current)
    else:
        body = _deadlines(owner, date_from, date_to, current)
    return {
        "kind": kind,
        "title": TITLES[kind],
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "period_text": period_text(date_from, date_to),
        "generated_on": india_fmt(current),
        **body,
    }


def report_card(report: dict) -> dict:
    """The ReportCard (contracts.py) for a built report."""
    return {
        "kind": report["kind"],
        "title": report["title"],
        "date_from": report["date_from"],
        "date_to": report["date_to"],
        "row_count": report["row_count"],
        "formats": ["pdf", "docx"],
        # Hearings whose "state of the matter" paragraph is not written yet:
        # the card offers to ask for them (never done by building the report).
        "briefings_missing": report.get("briefings_missing", []),
    }


def totals_for_answer(report: dict) -> list[tuple[str, str]]:
    """The summary lines of a report, for the chat answer."""
    for block in report["blocks"]:
        if block["type"] == "summary":
            return [(label, value) for label, value in block["items"]]
    return []
