"""Deterministic answer text for the practice assistant.

Every sentence here is built from a read result of reads.py: exact counts,
the explicit date range, India dates. An empty result is worded as "none
recorded in Case Intel" -- it is a statement about stored rows, never about
what a court did or will do. Nothing here calls a model.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Iterable, Optional

from .contracts import HARD_ROW_CAP, Reference

# How many source chips one answer carries, and how many rows it spells out.
MAX_SOURCES = 12
MAX_LINES = 12

FALLBACK_CLARIFICATION = (
    "I couldn't match that to something I can look up. I can:\n"
    "- show your hearings, tasks and events for a day or up to 31 days (\"hearings tomorrow\", \"what's coming up\")\n"
    "- list your open deadlines, or the cases with no next date\n"
    "- look up one case by its number, CNR or title\n"
    "- say what to focus on today, or which cases need attention and why\n"
    "- compare fees, what clients owe, case ages, or two weeks\n"
    "- summarise billing; add, change, invoice, send, mark paid or delete fees after you confirm\n"
    "- add a task or reminder\n"
    "- make a hearing brief with talking points, or a billing, hearings, cases or deadlines report, as PDF or Word\n"
    "- start a status memo, client letter, personal note or list of dates for a case\n"
    "I don't answer general law questions."
)
BILLING_NOT_AVAILABLE = (
    "Billing questions are not available in the assistant yet. "
    "You can see fees and invoices on the Billing page."
)
NO_INVOICE_TO_SEND = "No invoice is waiting to be sent. Only invoiced, unpaid fees can be emailed."
RANGE_TOO_LONG = (
    "I can show at most 31 days at a time, and the end date cannot be before the "
    "start date. Please ask about a shorter range."
)
CASE_NOT_FOUND = (
    "I could not find one of your cases matching that. "
    "Try the case number, the CNR or part of the title."
)
CASE_TEXT_NEEDED = "Which case do you mean? Give me the case number, the CNR or part of the title."
CHOOSE_CASE = "Which case do you mean? Pick one below."
NOT_RECORDED_NOTE = (
    "This reflects only what is recorded in Case Intel; "
    "it says nothing about what the court has or has not fixed."
)


# ---------------------------------------------------------------------------
# Small formatters
# ---------------------------------------------------------------------------


def fmt_day(value: str | date) -> str:
    """'2026-11-12' (or a longer ISO string, or a date) -> '12 Nov 2026'."""
    day = value if isinstance(value, date) else date.fromisoformat(value[:10])
    return day.strftime("%d %b %Y")


def _fmt_as_of(as_of: str) -> str:
    return datetime.fromisoformat(as_of).strftime("%d %b %Y, %H:%M") + " IST"


def _n(count: int, singular: str, plural: Optional[str] = None) -> str:
    return f"{count} {singular if count == 1 else (plural or singular + 's')}"


def _more(total: int, shown: int) -> list[str]:
    return [f"...and {total - shown} more."] if total > shown else []


def case_ref(row: dict) -> Reference:
    """A Reference for a case row of the read model (CaseRow / case_facts' case)."""
    return {
        "kind": "case",
        "id": row["id"],
        "case_id": row["id"],
        "label": row["title"],
        "recorded_at": None,
    }


def _case_line(row: dict) -> str:
    parts = [row["title"]]
    if row.get("case_number"):
        parts.append(f"({row['case_number']})")
    return " ".join(parts)


def _entry_line(entry: dict, *, with_day: bool) -> str:
    kind = {"hearing": "Hearing", "task": "Task", "event": "Event"}[entry["kind"]]
    when = fmt_day(entry["day"]) if with_day else ""
    if entry.get("start_time"):
        when = f"{when} {entry['start_time']}".strip()
    head = f"{when}: {kind}" if when else kind
    bits = [head, entry["label"]]
    if entry.get("case_title"):
        bits.append(entry["case_title"])
    line = ", ".join(bits) + f" ({entry['status'].replace('_', ' ')})"
    if entry.get("needs_review"):
        line += " [needs review]"
    return "- " + line


def _deadline_line(row: dict) -> str:
    if row["due_date"]:
        due = f"Due {fmt_day(row['due_date'])}" + (" (overdue)" if row["overdue"] else "")
    else:
        due = "No due date recorded"
    bits = [f"{due}: {row['title']}"]
    if row.get("case_title"):
        bits.append(row["case_title"])
    line = ", ".join(bits)
    if row.get("needs_review"):
        line += " [needs review]"
    return "- " + line


def _cap(refs: Iterable[Reference]) -> list[Reference]:
    out: list[Reference] = []
    seen: set[tuple] = set()
    for ref in refs:
        key = (ref["kind"], ref["id"])
        if key in seen:
            continue
        seen.add(key)
        out.append(ref)
        if len(out) == MAX_SOURCES:
            break
    return out


# ---------------------------------------------------------------------------
# One builder per intent: (answer text, sources)
# ---------------------------------------------------------------------------


def overview_answer(snapshot: dict) -> tuple[str, list[Reference]]:
    total = snapshot["total_cases"]
    if total == 0:
        return f"As of {_fmt_as_of(snapshot['as_of'])}, no cases are recorded in Case Intel.", []
    statuses = ", ".join(
        f"{count} {name.replace('_', ' ')}"
        for name, count in sorted(snapshot["status_counts"].items(), key=lambda item: (-item[1], item[0]))
    )
    lines = [
        f"As of {_fmt_as_of(snapshot['as_of'])}, Case Intel has **{_n(total, 'case')}** recorded "
        f"({statuses}).",
        f"{_n(snapshot['active_cases'], 'case')} {'is' if snapshot['active_cases'] == 1 else 'are'} "
        "active (not closed or archived): "
        f"{snapshot['active_with_next_hearing']} with a scheduled next hearing recorded and "
        f"{snapshot['active_without_next_date']} with none recorded in Case Intel.",
    ]
    return "\n".join(lines), _cap(case_ref(row) for row in snapshot["cases"])


def calendar_answer(window: dict) -> tuple[str, list[Reference]]:
    single = window["date_from"] == window["date_to"]
    span = (
        f"{fmt_day(window['date_from'])}"
        if single
        else f"{fmt_day(window['date_from'])} to {fmt_day(window['date_to'])}"
    )
    entries = window["entries"]
    total = window["total"]
    if total == 0:
        return (
            f"No hearings, tasks or events are recorded in Case Intel for {span} (India dates). "
            + NOT_RECORDED_NOTE,
            [],
        )
    if window["truncated"]:
        counts = f"{_n(total, 'item')} recorded (the first {len(entries)} are available here)"
    else:
        by_kind = {kind: sum(1 for e in entries if e["kind"] == kind) for kind in ("hearing", "task", "event")}
        kinds = [_n(by_kind[kind], kind) for kind in ("hearing", "task", "event") if by_kind[kind]]
        counts = "**" + (kinds[0] if len(kinds) == 1 else ", ".join(kinds[:-1]) + " and " + kinds[-1]) + "**"
    head = f"{'On' if single else 'From'} {span} (India dates), Case Intel has {counts}."
    lines = [head] + [_entry_line(e, with_day=not single) for e in entries[:MAX_LINES]]
    lines += _more(total, min(len(entries), MAX_LINES))
    return "\n".join(lines), _cap(e["ref"] for e in entries)


def open_deadlines_answer(result: dict) -> tuple[str, list[Reference]]:
    entries = result["entries"]
    total = result["total"]
    if total == 0:
        return "No open tasks or deadlines are recorded in Case Intel.", []
    overdue = sum(1 for row in entries if row["overdue"])
    # Rows come earliest-due first, so when the list was cut short and even
    # its last row is overdue, there may be more overdue rows beyond it.
    at_least = result["truncated"] and bool(entries) and entries[-1]["overdue"]
    head = (
        f"As of {_fmt_as_of(result['as_of'])}, Case Intel has **{_n(total, 'open task')}** recorded"
        + (f", **{'at least ' if at_least else ''}{overdue} overdue**" if overdue or at_least else ", none overdue")
        + ". Due dates are the recorded ones."
    )
    lines = [head] + [_deadline_line(row) for row in entries[:MAX_LINES]]
    lines += _more(total, min(len(entries), MAX_LINES))
    return "\n".join(lines), _cap(row["ref"] for row in entries)


def missing_next_date_summary(snapshot: dict, inactive_statuses: Iterable[str]) -> dict:
    """The cases-without-a-next-date view of a portfolio snapshot read with
    the largest page. The count is exact; the rows are those among the page
    read (the most recently added cases)."""
    inactive = set(inactive_statuses)
    rows = [
        row
        for row in snapshot["cases"]
        if row["status"] not in inactive and row["next_hearing_at"] is None
    ]
    return {
        "active_cases": snapshot["active_cases"],
        "active_without_next_date": snapshot["active_without_next_date"],
        "cases": rows,
        "truncated": len(rows) < snapshot["active_without_next_date"],
        "as_of": snapshot["as_of"],
        "timezone": snapshot["timezone"],
    }


def missing_next_date_answer(summary: dict) -> tuple[str, list[Reference]]:
    missing = summary["active_without_next_date"]
    active = summary["active_cases"]
    if active == 0:
        return "No active cases are recorded in Case Intel.", []
    if missing == 0:
        return (
            f"Every active case ({active}) has a scheduled next hearing recorded in Case Intel.",
            [],
        )
    rows = summary["cases"]
    head = (
        f"{missing} of your {_n(active, 'active case')} "
        f"{'has' if missing == 1 else 'have'} no scheduled next hearing recorded in Case Intel. "
        + NOT_RECORDED_NOTE
    )
    lines = [head] + ["- " + _case_line(row) for row in rows[:MAX_LINES]]
    lines += _more(missing, min(len(rows), MAX_LINES))
    if summary["truncated"]:
        lines.append(f"Only your {HARD_ROW_CAP} most recently added cases were looked through for the list.")
    return "\n".join(lines), _cap(case_ref(row) for row in rows)


def case_facts_answer(facts: dict) -> tuple[str, list[Reference]]:
    case = facts["case"]
    head = _case_line(case)
    if case.get("court"):
        head += f", {case['court']}"
    lines = [f"**{head}**. Status: {case['status'].replace('_', ' ')}."]
    refs: list[Reference] = [case["ref"]]

    hearing = facts["next_hearing"]
    if hearing:
        when = fmt_day(hearing["day"]) + (f" {hearing['start_time']}" if hearing["start_time"] else "")
        lines.append(f"Next hearing recorded: {when} ({hearing['label']}).")
        refs.append(hearing["ref"])
    else:
        lines.append("No scheduled next hearing is recorded in Case Intel for this case.")

    tasks = facts["open_tasks"]
    if tasks["total"]:
        lines.append(f"Open tasks recorded: {tasks['total']}.")
        lines += [_deadline_line(row) for row in tasks["entries"]]
        lines += _more(tasks["total"], len(tasks["entries"]))
        refs += [row["ref"] for row in tasks["entries"]]
    else:
        lines.append("No open tasks are recorded in Case Intel for this case.")

    events = facts["upcoming_events"]
    if events["total"]:
        lines.append(f"Upcoming events recorded: {events['total']}.")
        lines += [_entry_line(e, with_day=True) for e in events["entries"]]
        lines += _more(events["total"], len(events["entries"]))
        refs += [e["ref"] for e in events["entries"]]
    else:
        lines.append("No upcoming events are recorded in Case Intel for this case.")
    return "\n".join(lines), _cap(refs)


# ---------------------------------------------------------------------------
# Billing (only reached with settings.PRACTICE_INVOICE_ACTIONS_ENABLED on)
# ---------------------------------------------------------------------------


def _inr(amount: str) -> str:
    from .billing import amount_text

    return amount_text(amount)


def _fee_line(row: dict) -> str:
    state = {"pending": "no invoice yet", "invoiced": "invoiced", "paid": "paid"}[row["status"]]
    if row["status"] == "invoiced":
        state += ", sent" if row["sent"] else ", not sent"
    return f"- {row['invoice_number'] or row['category'].title()}, {row['case_title']}, {_inr(row['amount'])} ({state})"


def _fee_sources(summary: dict, rows: list[dict]) -> list[Reference]:
    case_refs = [case_ref(case) for case in summary.get("cases", [])]
    return _cap([row["ref"] for row in rows] + case_refs)


def billing_summary_answer(summary: dict) -> tuple[str, list[Reference]]:
    counts, totals = summary["counts"], summary["totals"]
    if not any(counts.values()):
        return "No fees or invoices are recorded in Case Intel.", []

    labels = (
        ("pending", "fee", "fees", "with no invoice yet"),
        ("invoiced_unsent", "invoice", "invoices", "not yet sent"),
        ("sent_unpaid", "invoice", "invoices", "sent and unpaid"),
        ("paid_30d", "fee", "fees", "paid in the last 30 days"),
    )
    parts = [
        f"**{_n(counts[key], one, many)}** {label} ({_inr(totals[key])})"
        for key, one, many, label in labels
        if counts[key]
    ]
    joined = parts[0] if len(parts) == 1 else "; ".join(parts[:-1]) + "; and " + parts[-1]
    head = f"As of {_fmt_as_of(summary['as_of'])}, Case Intel has {joined}."
    rows = summary["rows"]
    lines = [head] + [_fee_line(row) for row in rows[:MAX_LINES]]
    lines += _more(summary["total"], min(len(rows), MAX_LINES))
    return "\n".join(lines), _fee_sources(summary, rows[:MAX_LINES])


def invoice_send_answer(summary: dict, card: Optional[dict]) -> tuple[str, list[Reference]]:
    """`summary["candidates"]` holds the rows considered; `card` is set only
    when exactly one remained."""
    rows = summary["candidates"]
    if not rows:
        return NO_INVOICE_TO_SEND, []
    if card is None:
        shown = rows[:5]
        lines = ["More than one invoice could be meant. Which one should I prepare to send?"]
        lines += [
            f"- {row['invoice_number'] or 'No number'}, {row['case_title']}, {_inr(row['amount'])}"
            for row in shown
        ]
        lines += _more(summary["total"], len(shown))
        return "\n".join(lines), _fee_sources(summary, shown)
    label = card["invoice_number"] or "This fee"
    if card["blockers"]:
        text = f"{label} cannot be sent yet. " + " ".join(card["blockers"])
    else:
        text = (
            f"Invoice {label} for {_inr(card['amount'])} is ready to send to "
            f"{card['recipient_name'] or card['recipient_email']}. Confirm below to send it."
        )
    return text, _fee_sources(summary, rows)


# ---------------------------------------------------------------------------
# Action cards, drafts and reports
# ---------------------------------------------------------------------------

FEE_ACTIONS_OFF = (
    "Adding, changing, invoicing and deleting fees from the assistant is turned off for your "
    "account. You can do all of it on the Billing page."
)
DRAFTING_OFF = "Starting drafts from the assistant is turned off for your account."
REPORTS_OFF = "Reports from the assistant are turned off for your account."
WHICH_FEE = "Which fee do you mean? Give me the invoice number, or name the case."
MANY_INVOICES = "More than one invoice number was named. Which one do you mean?"
NOTHING_TO_CHANGE = (
    "What should change? Tell me the new amount, the category (appearance, hotel, flight or "
    "other) or a new description, for example: change INV-0042 to Rs 20,000."
)
DRAFT_KIND_NEEDED = (
    "Which kind of draft do you want: a status memo, a personal note, a client letter or a list of dates?"
)
REPORT_KIND_NEEDED = (
    "Which report do you want: billing, hearings, cases or deadlines? "
    "You can add a period, for example: billing report for this month."
)

_CATEGORY_PHRASE = {
    "appearance": "an appearance fee",
    "hotel": "a hotel charge",
    "flight": "a flight charge",
    "other": "another charge",
}
_CATEGORY_NOUN = {
    "appearance": "appearance fee",
    "hotel": "hotel charge",
    "flight": "flight charge",
    "other": "other charge",
}


def no_fees_for_case(title: str) -> str:
    return f"No fee is recorded for {title} in Case Intel."


def _fee_label(card: dict) -> str:
    if card.get("invoice_number"):
        return f"Invoice {card['invoice_number']}"
    noun = _CATEGORY_NOUN.get(card.get("category") or (card.get("current") or {}).get("category") or "", "fee")
    return f"The {noun}"


def _hearing_text(card: dict) -> str:
    for option in card["hearing_options"]:
        if option["id"] == card["hearing_id"]:
            return f", for the hearing on {fmt_day(option['date'])}"
    return ""


def _blocked(prefix: str, card: dict) -> str:
    return f"{prefix} " + " ".join(card["blockers"])


def fee_action_answer(card: dict, summary: dict) -> tuple[str, list[Reference]]:
    """The sentence above a fee action card. Wording only: every figure is the
    card's own."""
    sources = _fee_sources(summary, [summary["fee"]] if summary.get("fee") else [])
    kind, title = card["kind"], card["case_title"]
    if kind == "create_fee":
        phrase = _CATEGORY_PHRASE.get(card["category"], "a charge")
        amount = _inr(card["amount"]) if card["amount"] else "your default appearance fee"
        if card["blockers"]:
            return _blocked(f"I cannot add {phrase} on {title} yet.", card), sources
        return (
            f"Ready to add {phrase} of {amount} on {title}{_hearing_text(card)}. "
            "Check the details and confirm below.",
            sources,
        )
    label = _fee_label(card)
    if kind == "update_fee":
        if card["blockers"]:
            return _blocked(f"{label} on {title} cannot be changed.", card), sources
        current, proposed = card["current"], card["proposed"]
        parts = []
        if "amount" in proposed:
            parts.append(f"the amount from {_inr(current['amount'])} to {_inr(proposed['amount'])}")
        if "category" in proposed:
            parts.append(
                f"the category from {_CATEGORY_NOUN.get(current['category'], current['category'])} "
                f"to {_CATEGORY_NOUN.get(proposed['category'], proposed['category'])}"
            )
        if "description" in proposed:
            parts.append("the description")
        text = f"Ready to change {' and '.join(parts)} on {label.lower() if label.startswith('The') else label} ({title})."
        if card["regenerates_invoice"]:
            text += f" The invoice PDF will be made again under the same number, {card['invoice_number']}."
        return text + " Confirm below.", sources
    if kind == "generate_invoice":
        if card["blockers"]:
            return _blocked(f"An invoice cannot be generated for the {title} fee yet.", card), sources
        noun = _CATEGORY_NOUN.get(card["category"], "fee")
        return (
            f"Ready to generate the invoice for the {noun} of {_inr(card['amount'])} on {title}. "
            "Generating it does not send it. Confirm below.",
            sources,
        )
    if card["blockers"]:
        return _blocked(f"The fee on {title} cannot be deleted.", card), sources
    noun = _CATEGORY_NOUN.get(card["category"], "fee")
    return (
        f"Ready to delete the {noun} of {_inr(card['amount'])} on {title}, which has no invoice yet. "
        "This cannot be undone. Confirm below.",
        sources,
    )


def draft_answer(card: dict) -> tuple[str, list[Reference]]:
    sources = [case_ref({"id": card["case_id"], "title": card["case_title"]})]
    return (
        f"Ready to start a {card['subtype_label'].lower()} draft for {card['case_title']}. "
        "Check the instructions below and confirm to start it. Nothing is sent, and you review the draft before using it.",
        sources,
    )


_REPORT_ROWS = {
    "billing": ("fee", "fees"),
    "hearings": ("hearing", "hearings"),
    "cases": ("active case", "active cases"),
    "deadlines": ("open task", "open tasks"),
    "brief": ("hearing", "hearings"),
}


def report_answer(summary: dict) -> tuple[str, list[Reference]]:
    singular, plural = _REPORT_ROWS[summary["kind"]]
    count = summary["row_count"]
    period = "" if summary["kind"] == "cases" else f" for {summary['period_text']}" if summary["period_text"] != "All dates" else ""
    if count == 0:
        text = f"Your {summary['title'].lower()}{period} is ready, but no {plural} are recorded in Case Intel for it."
    else:
        text = f"Your {summary['title'].lower()}{period} is ready with {_n(count, singular, plural)}."
    if summary["kind"] == "brief" and count:
        text += (
            " Each hearing has its own section: case status, the last order and your side's directions, "
            "open tasks, the written state of the matter, and points to cover."
        )
        missing = summary.get("briefings_missing") or 0
        if missing:
            text += (
                f" The state-of-the-matter paragraph is not written yet for {_n(missing, 'hearing')}: press "
                "**Write missing briefings** below, then download again in a minute or two."
            )
    if summary["kind"] == "billing" and count:
        figures = dict(summary["totals"])
        text += (
            f" Invoiced {figures.get('Invoiced (including paid)')}, paid {figures.get('Paid')}, "
            f"outstanding {figures.get('Outstanding (invoiced, not paid)')}."
        )
    return text + " Download it below as a PDF or a Word file.", []


# ---------------------------------------------------------------------------
# Which references a read result contains
# ---------------------------------------------------------------------------


def allowed_references(summary) -> dict[tuple, Reference]:
    """Every Reference a read result carries, keyed by (kind, id): each row's
    own `ref`, plus a case Reference for each case row under a `cases` key."""
    found: dict[tuple, Reference] = {}

    def walk(node, key=None):
        if isinstance(node, dict):
            ref = node.get("ref")
            if isinstance(ref, dict) and "kind" in ref and "id" in ref:
                found[(ref["kind"], ref["id"])] = ref
            for name, value in node.items():
                if name != "ref":
                    walk(value, name)
        elif isinstance(node, list):
            for item in node:
                if key == "cases" and isinstance(item, dict) and "id" in item and "title" in item:
                    ref = case_ref(item)
                    found[(ref["kind"], ref["id"])] = ref
                walk(item)

    walk(summary)
    return found
