"""Answers that weigh records against each other: comparisons and rankings,
what to focus on today, and which cases need attention and why.

Every figure is computed here from the owner's own rows (no model call), and
every row the answer names carries its `ref`, so validate_references keeps
the sources honest. Each read returns a summary dict; the matching
`*_answer` turns it into (text, sources).
"""
from __future__ import annotations

import re
import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Exists, OuterRef, Q
from django.utils import timezone

from core.models import AppearanceFee, Case, Hearing, Task
from core.services.india_time import INDIA_TZ

from . import reads
from .answers import _cap, _inr, _n, case_ref, fmt_day
from .billing import fee_ref
from .contracts import DEFAULT_RANGE_DAYS, Reference

COMPARE_KINDS = ("fee_ranking", "outstanding_by_client", "case_age", "compare_periods")
TOP_ROWS = 5
ATTENTION_ROWS = 10
LOW_SHARE = Decimal("0.7")  # a fee below 70% of its category's median is "low"
UNPAID_DAYS = 30
UNBILLED_DAYS = 30
SOON_DAYS = 2
# Read-only: the cause-list outcome to warn about. Only the cause-list
# service ever assigns it (see test_causelist_framework).
NOT_ON_CAUSE_LIST = "not_listed"

_CATEGORY_LABELS = dict(AppearanceFee.CATEGORY_CHOICES)


def _start(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=INDIA_TZ)


def _money(value) -> str:
    return str(Decimal(value).quantize(Decimal("0.01")))


def _fee_case(fee: AppearanceFee) -> str:
    return fee.hearing.case.title


def _fee_name(fee: AppearanceFee) -> str:
    return fee.invoice_number or f"{_CATEGORY_LABELS.get(fee.category, fee.category)} fee"


# ---------------------------------------------------------------------------
# Which comparison a question asks for
# ---------------------------------------------------------------------------

_OWED_RE = re.compile(r"\b(owes?|owing|outstanding|unpaid|dues?|pending payments?|yet to pay|not paid)\b")
_HIGH_RE = re.compile(r"\b(highest|biggest|largest|costliest|top|most expensive|too high|high)\b")
_CASE_AGE_RE = re.compile(r"\b(oldest|newest|latest|longest|old|new)\b.*\b(cases?|matters?)\b|\b(cases?|matters?)\b.*\b(oldest|newest|longest)\b")
_PERIOD_WORDS = r"(today|tomorrow|yesterday|this week|next week|last week|this month|next month|last month)"
_TWO_PERIODS_RE = re.compile(rf"\b{_PERIOD_WORDS}\b.*\b(or|vs\.?|versus|than|compared to|and)\b.*\b{_PERIOD_WORDS}\b")


def compare_kind(text: str) -> Optional[tuple[str, dict]]:
    """(kind, args) for a comparison these reads can answer, else None.
    `text` is normalised lower case."""
    two = _TWO_PERIODS_RE.search(text)
    if two:
        return "compare_periods", {"periods": [two.group(1), two.group(3)]}
    if re.search(r"\b(busier|busiest|quieter|more hearings|fewer hearings)\b", text):
        return "compare_periods", {"periods": ["this week", "next week"]}
    if _CASE_AGE_RE.search(text) and not re.search(r"\b(fees?|bills?|billings?|invoices?)\b", text):
        newest = bool(re.search(r"\b(newest|latest|new)\b", text))
        return "case_age", {"newest": newest}
    if _OWED_RE.search(text) or re.search(r"\bclients?\b.*\b(most|least)\b", text):
        return "outstanding_by_client", {}
    if re.search(r"\b(fees?|bills?|billings?|invoices?|charges?|amounts?|earn\w*)\b", text):
        return "fee_ranking", {"high": bool(_HIGH_RE.search(text))}
    return None


# ---------------------------------------------------------------------------
# Comparisons
# ---------------------------------------------------------------------------


def _owned_fees(owner):
    return (
        AppearanceFee.objects.filter(owner=owner, hearing__case__owner=owner)
        .exclude(status="cancelled")
        .select_related("hearing__case")
    )


def _fee_row(fee: AppearanceFee, **extra) -> dict:
    return {
        "fee_id": fee.id,
        "name": _fee_name(fee),
        "case_title": _fee_case(fee),
        "category": fee.category,
        "amount": _money(fee.amount),
        "status": fee.status,
        "ref": fee_ref(fee),
        **extra,
    }


def fee_ranking(*, owner, high: bool = False) -> dict:
    """Fees ranked by amount within their category, with each category's
    median, so "low" and "high" mean relative to the advocate's own fees."""
    fees = list(_owned_fees(owner))
    by_category: dict[str, list[AppearanceFee]] = defaultdict(list)
    for fee in fees:
        by_category[fee.category].append(fee)
    groups = []
    for category, items in sorted(by_category.items(), key=lambda kv: -len(kv[1])):
        median = Decimal(statistics.median([fee.amount for fee in items]))
        ordered = sorted(items, key=lambda fee: (fee.amount, fee.id), reverse=high)
        flagged = [
            fee
            for fee in ordered
            if len(items) >= 3
            and (fee.amount > median / LOW_SHARE if high else fee.amount < median * LOW_SHARE)
        ]
        groups.append(
            {
                "category": category,
                "count": len(items),
                "median": _money(median),
                "rows": [
                    _fee_row(fee, share=int(fee.amount * 100 / median) if median else None)
                    for fee in (flagged or ordered)[:TOP_ROWS]
                ],
                "flagged": len(flagged),
            }
        )
    return {"kind": "fee_ranking", "high": high, "total": len(fees), "groups": groups}


def _client_label(case: Case) -> str:
    if case.client_name:
        return case.client_name
    contact = next(iter(case.client_contacts.all()), None)
    return contact.name if contact else case.title


def outstanding_by_client(*, owner, now: datetime) -> dict:
    """Invoiced, unpaid amounts summed per client (the case's client name,
    else its first contact, else the case title), largest first."""
    fees = list(
        _owned_fees(owner)
        .filter(status=AppearanceFee.STATUS_INVOICED)
        .prefetch_related("hearing__case__client_contacts")
    )
    clients: dict[str, dict] = {}
    for fee in fees:
        label = _client_label(fee.hearing.case)
        entry = clients.setdefault(label, {"client": label, "amount": Decimal(0), "fees": [], "oldest": None})
        entry["amount"] += fee.amount
        entry["fees"].append(_fee_row(fee))
        if fee.invoiced_at and (entry["oldest"] is None or fee.invoiced_at < entry["oldest"]):
            entry["oldest"] = fee.invoiced_at
    rows = sorted(clients.values(), key=lambda row: (-row["amount"], row["client"]))
    for row in rows:
        row["amount"] = _money(row["amount"])
        row["days"] = (now - row.pop("oldest")).days if row.get("oldest") else None
    return {"kind": "outstanding_by_client", "total": len(fees), "clients": rows[:TOP_ROWS], "client_count": len(rows)}


def case_age(*, owner, newest: bool = False) -> dict:
    """Active cases by filing date (where recorded), else by when they were
    added to Case Intel. The basis is stated in the answer."""
    active = Case.objects.filter(owner=owner).filter(reads.active_cases_q())
    dated = active.filter(filing_date__isnull=False)
    if dated.exists():
        basis = "filing"
        order = ("-filing_date", "-id") if newest else ("filing_date", "id")
        cases = list(dated.order_by(*order)[:TOP_ROWS])
    else:
        basis = "added"
        order = ("-created_at", "-id") if newest else ("created_at", "id")
        cases = list(active.order_by(*order)[:TOP_ROWS])
    rows = [
        {
            "id": case.id,
            "title": case.title,
            "case_number": case.case_number or None,
            "since": (case.filing_date or timezone.localtime(case.created_at, INDIA_TZ).date()).isoformat(),
        }
        for case in cases
    ]
    return {"kind": "case_age", "newest": newest, "basis": basis, "cases": rows, "active": active.count()}


def period_bounds(phrase: str, today: date) -> tuple[date, date]:
    week = DEFAULT_RANGE_DAYS
    if phrase == "today":
        return today, today
    if phrase == "tomorrow":
        return today + timedelta(days=1), today + timedelta(days=1)
    if phrase == "yesterday":
        return today - timedelta(days=1), today - timedelta(days=1)
    if phrase == "this week":
        return today, today + timedelta(days=week - 1)
    if phrase == "next week":
        return today + timedelta(days=week), today + timedelta(days=2 * week - 1)
    if phrase == "last week":
        return today - timedelta(days=week), today - timedelta(days=1)
    first = today.replace(day=1)
    if phrase == "last month":
        end = first - timedelta(days=1)
        return end.replace(day=1), end
    if phrase == "next month":
        first = (first + timedelta(days=32)).replace(day=1)
    end = (first + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return first, end


def compare_periods(*, owner, periods: list[str], now: datetime) -> dict:
    today = now.date()
    rows = []
    for phrase in periods[:2]:
        date_from, date_to = period_bounds(phrase, today)
        window = reads.calendar_window(owner=owner, date_from=date_from, date_to=date_to, now=now)
        counts = {"hearing": 0, "task": 0, "event": 0}
        for markers in window["day_markers"].values():
            for kind in counts:
                counts[kind] += markers[kind]
        busiest = max(window["day_markers"].items(), key=lambda kv: sum(kv[1].values()), default=None)
        rows.append(
            {
                "phrase": phrase,
                "date_from": date_from.isoformat(),
                "date_to": date_to.isoformat(),
                **counts,
                "busiest_day": busiest[0] if busiest and sum(busiest[1].values()) else None,
                "entries": window["entries"][:3],
            }
        )
    return {"kind": "compare_periods", "periods": rows}


def compare(*, owner, kind: str, args: dict, now: datetime) -> dict:
    if kind == "fee_ranking":
        return fee_ranking(owner=owner, high=args.get("high", False))
    if kind == "outstanding_by_client":
        return outstanding_by_client(owner=owner, now=now)
    if kind == "case_age":
        return case_age(owner=owner, newest=args.get("newest", False))
    if kind == "compare_periods":
        return compare_periods(owner=owner, periods=args.get("periods") or ["this week", "next week"], now=now)
    raise ValueError(f"Unknown comparison {kind!r}.")


def _fee_ranking_answer(summary: dict) -> tuple[str, list[Reference]]:
    if not summary["total"]:
        return "No fees are recorded in Case Intel yet, so there is nothing to compare.", []
    word = "high" if summary["high"] else "low"
    lines, refs = [], []
    for group in summary["groups"]:
        label = _CATEGORY_LABELS.get(group["category"], group["category"]).lower()
        if group["count"] < 3:
            amounts = ", ".join(f"{row['name']} {_inr(row['amount'])}" for row in group["rows"])
            lines.append(
                f"**{label.capitalize()}**: only {_n(group['count'], 'fee')} ({amounts}), too few to say "
                f"any is unusually {word}."
            )
        elif group["flagged"]:
            lines.append(
                f"**{label.capitalize()}**: {_n(group['count'], 'fee')}, median {_inr(group['median'])}. "
                f"{_n(group['flagged'], 'fee is', 'fees are')} well {'above' if summary['high'] else 'below'} it:"
            )
            lines += [
                f"- {row['name']}, {row['case_title']}: {_inr(row['amount'])} ({row['share']}% of the median)"
                for row in group["rows"]
            ]
        else:
            lines.append(
                f"**{label.capitalize()}**: {_n(group['count'], 'fee')}, median {_inr(group['median'])}. "
                f"None is far {'above' if summary['high'] else 'below'} it; the {'highest' if summary['high'] else 'lowest'} are:"
            )
            lines += [f"- {row['name']}, {row['case_title']}: {_inr(row['amount'])}" for row in group["rows"][:3]]
        refs += [row["ref"] for row in group["rows"]]
    head = f"Compared within each fee type across your {_n(summary['total'], 'fee')} (cancelled ones left out):"
    return "\n".join([head, *lines]), _cap(refs)


def _outstanding_answer(summary: dict) -> tuple[str, list[Reference]]:
    if not summary["clients"]:
        return "No invoice is waiting for payment: every invoiced fee is marked paid.", []
    top = summary["clients"][0]
    lines = [
        f"**{top['client']}** owes the most: **{_inr(top['amount'])}** across {_n(len(top['fees']), 'unpaid invoice')}."
    ]
    if len(summary["clients"]) > 1:
        lines.append("Next:")
        lines += [
            f"- {row['client']}: {_inr(row['amount'])} ({_n(len(row['fees']), 'invoice')})"
            for row in summary["clients"][1:]
        ]
    lines.append(
        f"Counted from invoices generated and not yet marked paid ({_n(summary['total'], 'invoice')}, "
        f"{_n(summary['client_count'], 'client')})."
    )
    refs = [fee["ref"] for row in summary["clients"] for fee in row["fees"]]
    return "\n".join(lines), _cap(refs)


def _years_months(since: date, today: date) -> str:
    months = (today.year - since.year) * 12 + today.month - since.month - (today.day < since.day)
    years, months = divmod(max(months, 0), 12)
    if years and months:
        return f"{_n(years, 'year')} {_n(months, 'month')}"
    if years:
        return _n(years, "year")
    return _n(months, "month") if months else "under a month"


def _case_age_answer(summary: dict, today: date) -> tuple[str, list[Reference]]:
    if not summary["cases"]:
        return "You have no active cases in Case Intel.", []
    first = summary["cases"][0]
    word = "newest" if summary["newest"] else "oldest"
    if summary["basis"] == "filing":
        basis = "by filing date"
        when = f"filed {fmt_day(first['since'])}"
    else:
        basis = "by the date it was added to Case Intel, since no filing dates are recorded"
        when = f"added {fmt_day(first['since'])}"
    lines = [
        f"Your {word} active case ({basis}) is **{first['title']}**"
        + (f" ({first['case_number']})" if first["case_number"] else "")
        + f", {when}, {_years_months(date.fromisoformat(first['since']), today)} ago."
    ]
    if len(summary["cases"]) > 1:
        lines.append("Then:")
        lines += [f"- {row['title']}, {fmt_day(row['since'])}" for row in summary["cases"][1:]]
    return "\n".join(lines), _cap(case_ref(row) for row in summary["cases"])


def _counts_text(row: dict) -> str:
    kinds = [_n(row[kind], kind) for kind in ("hearing", "task", "event") if row[kind]]
    return ", ".join(kinds) if kinds else "nothing recorded"


def _periods_answer(summary: dict) -> tuple[str, list[Reference]]:
    a, b = summary["periods"]
    total = lambda row: row["hearing"] * 3 + row["task"] + row["event"]  # noqa: E731 - hearings weigh most
    if a["hearing"] == b["hearing"] and total(a) == total(b):
        verdict = f"{a['phrase'].capitalize()} and {b['phrase']} look about the same."
    else:
        busier, quieter = (a, b) if total(a) > total(b) else (b, a)
        verdict = f"**{busier['phrase'].capitalize()} is busier** than {quieter['phrase']}."
    lines = [verdict]
    for row in (a, b):
        span = fmt_day(row["date_from"]) if row["date_from"] == row["date_to"] else f"{fmt_day(row['date_from'])} to {fmt_day(row['date_to'])}"
        busiest = f"; busiest day {fmt_day(row['busiest_day'])}" if row["busiest_day"] and row["date_from"] != row["date_to"] else ""
        lines.append(f"- {row['phrase'].capitalize()} ({span}): {_counts_text(row)}{busiest}")
    lines.append("Hearings count most; ask for either period to see the full list.")
    refs = [entry["ref"] for row in (a, b) for entry in row["entries"]]
    return "\n".join(lines), _cap(refs)


def compare_answer(summary: dict, today: date) -> tuple[str, list[Reference]]:
    kind = summary["kind"]
    if kind == "fee_ranking":
        return _fee_ranking_answer(summary)
    if kind == "outstanding_by_client":
        return _outstanding_answer(summary)
    if kind == "case_age":
        return _case_age_answer(summary, today)
    return _periods_answer(summary)


# ---------------------------------------------------------------------------
# What to focus on today
# ---------------------------------------------------------------------------


def _unbilled_hearings(owner, now: datetime, days: int = UNBILLED_DAYS) -> list[Hearing]:
    """Past hearings of active cases in the last `days` days with no fee."""
    since = _start(now.date() - timedelta(days=days))
    return list(
        Hearing.objects.filter(owner=owner, case__owner=owner, hearing_date__gte=since, hearing_date__lt=now)
        .filter(reads.active_cases_q("case__"))
        .exclude(status="cancelled")
        .annotate(_billed=Exists(AppearanceFee.objects.filter(hearing=OuterRef("pk")).exclude(status="cancelled")))
        .filter(_billed=False)
        .select_related("case")
        .order_by("hearing_date", "id")
    )


def today_focus(*, owner, now: datetime) -> dict:
    today = now.date()
    window = reads.calendar_window(owner=owner, date_from=today, date_to=today, now=now)
    hearings = [entry for entry in window["entries"] if entry["kind"] == "hearing" and entry["status"] == "scheduled"]
    events = [entry for entry in window["entries"] if entry["kind"] == "event"]
    tasks = list(
        reads._owned_tasks(owner)
        .filter(status__in=Task.OPEN_STATUSES, due_date__lte=today)
        .select_related("case")
        .order_by("due_date", "id")[:TOP_ROWS * 2]
    )
    unbilled = _unbilled_hearings(owner, now)
    return {
        "kind": "today_focus",
        "day": today.isoformat(),
        "hearings": hearings,
        "events": events,
        "deadlines": [reads._deadline_row(task, today) for task in tasks],
        "unbilled": [
            {
                "id": hearing.id,
                "case_title": hearing.case.title,
                "day": timezone.localtime(hearing.hearing_date, INDIA_TZ).date().isoformat(),
                "ref": reads._hearing_ref(hearing),
            }
            for hearing in unbilled[:TOP_ROWS]
        ],
        "unbilled_total": len(unbilled),
    }


def today_focus_answer(summary: dict) -> tuple[str, list[Reference]]:
    lines: list[str] = []
    step = 0
    if summary["hearings"]:
        step += 1
        lines.append(f"{step}. **Court today: {_n(len(summary['hearings']), 'hearing')}**")
        lines += [
            f"- {(entry['start_time'] + ' ') if entry['start_time'] else ''}{entry['case_title']}, {entry['label']}"
            for entry in summary["hearings"]
        ]
    overdue = [row for row in summary["deadlines"] if row["overdue"]]
    due_today = [row for row in summary["deadlines"] if not row["overdue"]]
    if overdue:
        step += 1
        lines.append(f"{step}. **Overdue: {_n(len(overdue), 'task')}**")
        lines += [
            f"- {row['title']}" + (f", {row['case_title']}" if row["case_title"] else "") + f" (due {fmt_day(row['due_date'])})"
            for row in overdue
        ]
    if due_today:
        step += 1
        lines.append(f"{step}. **Due today: {_n(len(due_today), 'task')}**")
        lines += [f"- {row['title']}" + (f", {row['case_title']}" if row["case_title"] else "") for row in due_today]
    if summary["events"]:
        step += 1
        lines.append(f"{step}. **Appointments: {_n(len(summary['events']), 'event')}**")
        lines += [
            f"- {(entry['start_time'] + ' ') if entry['start_time'] else ''}{entry['label']}, {entry['case_title']}"
            for entry in summary["events"]
        ]
    if summary["unbilled_total"]:
        step += 1
        lines.append(
            f"{step}. **Billing: {_n(summary['unbilled_total'], 'past hearing')} in the last {UNBILLED_DAYS} days "
            f"{'has' if summary['unbilled_total'] == 1 else 'have'} no fee recorded**"
        )
        lines += [f"- {fmt_day(row['day'])}, {row['case_title']}" for row in summary["unbilled"]]
    head = f"For today, {fmt_day(summary['day'])}, in order:"
    if not lines:
        return f"Nothing needs you today ({fmt_day(summary['day'])}): no hearings, no tasks due or overdue, and every recent hearing has a fee.", []
    refs = (
        [entry["ref"] for entry in summary["hearings"]]
        + [row["ref"] for row in summary["deadlines"]]
        + [entry["ref"] for entry in summary["events"]]
        + [row["ref"] for row in summary["unbilled"]]
    )
    return "\n".join([head, *lines]), _cap(refs)


# ---------------------------------------------------------------------------
# Which cases need attention, and why
# ---------------------------------------------------------------------------

_WEIGHTS = {"overdue": 3, "cause_list": 3, "no_outcome": 2, "unpaid": 2, "no_next_date": 1}


def attention(*, owner, now: datetime) -> dict:
    today = now.date()
    cases = {case.id: case for case in Case.objects.filter(owner=owner).filter(reads.active_cases_q())}
    reasons: dict[int, list[tuple[str, str, Optional[Reference]]]] = defaultdict(list)

    for task in (
        reads._owned_tasks(owner)
        .filter(status__in=Task.OPEN_STATUSES, due_date__lt=today, case_id__in=cases)
        .order_by("due_date", "id")
    ):
        reasons[task.case_id].append(
            ("overdue", f"task overdue since {fmt_day(task.due_date)}: {task.title or 'Task'}", reads._task_ref(task))
        )

    soon = Hearing.objects.filter(
        owner=owner,
        case_id__in=cases,
        status="scheduled",
        hearing_date__gte=_start(today),
        hearing_date__lt=_start(today + timedelta(days=SOON_DAYS + 1)),
        cause_list_status__in=(NOT_ON_CAUSE_LIST, Hearing.CAUSE_LIST_FETCH_FAILED),
    )
    for hearing in soon:
        day = fmt_day(timezone.localtime(hearing.hearing_date, INDIA_TZ).date())
        text = (
            f"hearing on {day} is not on the court's cause list"
            if hearing.cause_list_status == NOT_ON_CAUSE_LIST
            else f"the cause list for the hearing on {day} could not be checked"
        )
        reasons[hearing.case_id].append(("cause_list", text, reads._hearing_ref(hearing)))

    stale = Hearing.objects.filter(
        owner=owner,
        case_id__in=cases,
        status="scheduled",
        hearing_date__gte=_start(today - timedelta(days=UNBILLED_DAYS)),
        hearing_date__lt=_start(today),
    ).order_by("hearing_date")
    for hearing in stale:
        day = fmt_day(timezone.localtime(hearing.hearing_date, INDIA_TZ).date())
        reasons[hearing.case_id].append(
            ("no_outcome", f"hearing on {day} has passed with no outcome or next date recorded", reads._hearing_ref(hearing))
        )

    for fee in AppearanceFee.objects.filter(
        owner=owner,
        hearing__case_id__in=cases,
        status=AppearanceFee.STATUS_INVOICED,
        invoiced_at__lt=now - timedelta(days=UNPAID_DAYS),
    ).select_related("hearing__case"):
        reasons[fee.hearing.case_id].append(
            ("unpaid", f"{_fee_name(fee)} ({_inr(_money(fee.amount))}) unpaid for {(now - fee.invoiced_at).days} days", fee_ref(fee))
        )

    upcoming = set(
        Hearing.objects.filter(owner=owner, case_id__in=cases, status="scheduled", hearing_date__gte=now).values_list(
            "case_id", flat=True
        )
    )
    for case_id in cases:
        if case_id not in upcoming and not any(kind == "no_outcome" for kind, _, _ in reasons[case_id]):
            reasons[case_id].append(("no_next_date", "no next hearing date recorded", None))

    rows = []
    for case_id, items in reasons.items():
        if not items:
            continue
        case = cases[case_id]
        rows.append(
            {
                "id": case.id,
                "title": case.title,
                "case_number": case.case_number or None,
                "score": sum(_WEIGHTS[kind] for kind, _, _ in items),
                "reasons": [text for _, text, _ in items],
                "refs": [{"ref": ref} for _, _, ref in items if ref],
                "only_no_date": all(kind == "no_next_date" for kind, _, _ in items),
            }
        )
    rows.sort(key=lambda row: (-row["score"], row["title"], row["id"]))
    urgent = [row for row in rows if not row["only_no_date"]]
    quiet = [row for row in rows if row["only_no_date"]]
    return {
        "kind": "attention",
        "cases": urgent[:ATTENTION_ROWS],
        "urgent_total": len(urgent),
        "no_date_total": len(quiet),
        "no_date_cases": quiet[:3],
        "active": len(cases),
    }


def attention_answer(summary: dict) -> tuple[str, list[Reference]]:
    urgent, quiet = summary["cases"], summary["no_date_total"]
    if not urgent and not quiet:
        return f"None of your {_n(summary['active'], 'active case')} needs attention right now.", []
    lines = []
    if urgent:
        lines.append(f"**{_n(summary['urgent_total'], 'case needs', 'cases need')} attention**, most pressing first:")
        for row in urgent:
            lines.append(f"- **{row['title']}**: " + "; ".join(row["reasons"]))
        if summary["urgent_total"] > len(urgent):
            lines.append(f"...and {summary['urgent_total'] - len(urgent)} more.")
    if quiet:
        names = ", ".join(row["title"] for row in summary["no_date_cases"])
        more = f" and {quiet - len(summary['no_date_cases'])} more" if quiet > len(summary["no_date_cases"]) else ""
        lines.append(
            f"{_n(quiet, 'other case has', 'other cases have')} no next hearing date recorded ({names}{more}); "
            "ask **which cases have no next date** for the full list."
        )
    lines.append("Reasons checked: overdue tasks, cause-list problems for the next two days, past hearings with no outcome, invoices unpaid over 30 days, and missing next dates.")
    refs = []
    for row in urgent:
        refs.append(case_ref(row))
        refs += [item["ref"] for item in row["refs"]]
    return "\n".join(lines), _cap(refs)
