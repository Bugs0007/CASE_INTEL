"""Cards for the assistant's newer proposals: add a task, mark an invoice
paid, add fees for several hearings at once, and send several invoices.

Like every card (see actions.py), these only propose: every field comes from
the owner's rows or the advocate's own words, and the advocate's Confirm
calls an existing owner-scoped endpoint (POST /api/tasks/,
POST /api/appearance-fees/<id>/mark-paid/, POST /api/appearance-fees/,
POST /api/appearance-fees/<id>/send/). Nothing here writes.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Exists, OuterRef

from core.models import AdvocateProfile, AppearanceFee, Case, Hearing
from core.services.india_time import INDIA_TZ, india_date, india_fmt

from . import billing, parsing

BULK_ROW_CAP = 40
TASK_TITLE_MAX = 255

BLOCKER_NOT_INVOICED = "This fee has no invoice yet. Generate the invoice before marking it paid."
BLOCKER_ALREADY_PAID = "This invoice is already marked paid."

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_WEEKDAY_RE = re.compile(r"\b(next\s+)?(" + "|".join(_WEEKDAYS) + r")\b", re.IGNORECASE)


def parse_weekday(text: str, today: date) -> Optional[date]:
    """"by Monday" -> the next Monday after today ("next Monday" too); today's
    own weekday means a week from today."""
    match = _WEEKDAY_RE.search(text or "")
    if not match:
        return None
    ahead = (_WEEKDAYS.index(match.group(2).lower()) - today.weekday()) % 7 or 7
    return today + timedelta(days=ahead)


def parse_due(text: str, today: date) -> Optional[date]:
    lowered = (text or "").lower()
    if re.search(r"\btomorrow\b", lowered):
        return today + timedelta(days=1)
    if re.search(r"\btoday\b|\btonight\b", lowered):
        return today
    days = parsing.parse_dates(text, today=today)
    if days:
        return days[0]
    weekday = parse_weekday(text, today)
    if weekday:
        return weekday
    if re.search(r"\bnext week\b", lowered):
        return today + timedelta(days=7)
    if re.search(r"\b(end of (?:the )?month|month end)\b", lowered):
        return (today.replace(day=1) + timedelta(days=32)).replace(day=1) - timedelta(days=1)
    return None


# ---------------------------------------------------------------------------
# Add a task
# ---------------------------------------------------------------------------

_TASK_BODY_RE = re.compile(
    r"\b(?:task|reminder|to-?do|note)\s+(?:to\s+|for\s+me\s+to\s+|that\s+)?(?P<body>.+)$|\bremind\s+me\s+(?:to\s+)?(?P<body2>.+)$",
    re.IGNORECASE,
)
_DUE_TAIL_RE = re.compile(
    r"\s+(?:by|on|before|due|until|latest by)\s+(?:the\s+)?(?:next\s+)?"
    r"(?:\d|today|tomorrow|tonight|next week|end of|month end|" + "|".join(_WEEKDAYS) + r"|jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec).*$",
    re.IGNORECASE,
)
_CASE_TAIL_RE = re.compile(r"\s+(?:in|for|on)\s+(?:the\s+)?(?P<case>.+?)(?:\s+(?:case|matter))?$", re.IGNORECASE)


def parse_task(query: str, today: date) -> dict:
    """{"title", "due_date", "case_text"} read from the advocate's words.
    "add a task to file the counter in Rao by Monday" ->
    title "File the counter", due next Monday, case text "Rao"."""
    text = " ".join((query or "").split()).rstrip("?.! ")
    match = _TASK_BODY_RE.search(text)
    body = (match.group("body") or match.group("body2")) if match else text
    due = parse_due(body, today)
    body = _DUE_TAIL_RE.sub("", body).strip()
    case_text = None
    tail = _CASE_TAIL_RE.search(body)
    if tail and len(tail.group("case")) >= 3:
        case_text = tail.group("case").strip()
        body = body[: tail.start()].strip()
    title = body[:1].upper() + body[1:] if body else "Task"
    return {"title": title[:TASK_TITLE_MAX], "due_date": due, "case_text": case_text}


def build_task_card(*, case: Optional[Case], title: str, due_date: Optional[date]) -> dict:
    return {
        "kind": "create_task",
        "case_id": case.id if case else None,
        "case_title": case.title if case else "",
        "title": title,
        "due_date": due_date.isoformat() if due_date else None,
        "blockers": [],
    }


# ---------------------------------------------------------------------------
# Mark an invoice paid
# ---------------------------------------------------------------------------


def build_mark_paid_card(*, fee: AppearanceFee) -> dict:
    blockers = []
    if fee.status == AppearanceFee.STATUS_PAID:
        blockers.append(BLOCKER_ALREADY_PAID)
    elif fee.status != AppearanceFee.STATUS_INVOICED:
        blockers.append(BLOCKER_NOT_INVOICED)
    return {
        "kind": "mark_invoice_paid",
        "case_id": fee.hearing.case_id,
        "case_title": fee.hearing.case.title,
        "fee_id": fee.id,
        "invoice_number": fee.invoice_number or None,
        "amount": billing._money(fee.amount),
        "category": fee.category,
        "fee_status": fee.status,
        "blockers": blockers,
    }


def payable_fees(*, owner, case_id: Optional[int] = None) -> list[AppearanceFee]:
    qs = AppearanceFee.objects.filter(
        owner=owner, hearing__case__owner=owner, status=AppearanceFee.STATUS_INVOICED
    ).select_related("hearing__case")
    if case_id is not None:
        qs = qs.filter(hearing__case_id=case_id)
    return list(qs.order_by("invoiced_at", "id"))


# ---------------------------------------------------------------------------
# Fees for several hearings at once
# ---------------------------------------------------------------------------


def unbilled_hearings(*, owner, date_from: date, date_to: date, now: datetime) -> list[Hearing]:
    """Past (or today's) hearings of the owner in the period, not cancelled,
    that have no appearance fee yet."""
    start = datetime.combine(date_from, datetime.min.time(), tzinfo=INDIA_TZ)
    end = min(datetime.combine(date_to + timedelta(days=1), datetime.min.time(), tzinfo=INDIA_TZ), now)
    return list(
        Hearing.objects.filter(owner=owner, case__owner=owner, hearing_date__gte=start, hearing_date__lt=end)
        .exclude(status="cancelled")
        .annotate(
            _billed=Exists(
                AppearanceFee.objects.filter(
                    hearing=OuterRef("pk"), category=AppearanceFee.CATEGORY_APPEARANCE
                ).exclude(status="cancelled")
            )
        )
        .filter(_billed=False)
        .select_related("case")
        .order_by("hearing_date", "id")[:BULK_ROW_CAP]
    )


def build_bulk_fees_card(*, owner, hearings: list[Hearing], amount: Optional[Decimal], period_text: str) -> dict:
    profile = AdvocateProfile.objects.filter(owner=owner).first()
    default = amount if amount is not None else (profile.default_fee_amount if profile else None)
    rows = [
        {
            "hearing_id": hearing.id,
            "case_id": hearing.case_id,
            "case_title": hearing.case.title,
            "date": india_date(hearing.hearing_date).isoformat(),
            "label": f"{india_fmt(hearing.hearing_date)}, {(hearing.purpose or '').strip() or hearing.get_hearing_type_display()}",
        }
        for hearing in hearings
    ]
    return {
        "kind": "bulk_create_fees",
        "case_id": None,
        "case_title": "",
        "category": AppearanceFee.CATEGORY_APPEARANCE,
        "amount": billing._money(default) if default else None,
        "period_text": period_text,
        "rows": rows,
        "blockers": [],
    }


# ---------------------------------------------------------------------------
# Send several invoices
# ---------------------------------------------------------------------------


def unsent_invoices(*, owner) -> list[AppearanceFee]:
    return list(
        AppearanceFee.objects.filter(owner=owner, hearing__case__owner=owner, status=AppearanceFee.STATUS_INVOICED)
        .exclude(send_status="sent")
        .select_related("hearing__case")
        .order_by("hearing__case__title", "id")[:BULK_ROW_CAP]
    )


def build_bulk_send_card(*, owner, fees: list[AppearanceFee]) -> dict:
    rows = []
    for fee in fees:
        single = billing.build_send_card(owner=owner, fee=fee)
        rows.append(
            {
                "fee_id": fee.id,
                "case_id": single["case_id"],
                "case_title": single["case_title"],
                "invoice_number": single["invoice_number"],
                "amount": single["amount"],
                "recipient_email": single["recipient_email"],
                "blockers": single["blockers"],
            }
        )
    return {"kind": "bulk_send_invoices", "case_id": None, "case_title": "", "rows": rows, "blockers": []}


# ---------------------------------------------------------------------------
# The chat text for each card
# ---------------------------------------------------------------------------


def _case_source(card: dict) -> list:
    if not card.get("case_id"):
        return []
    return [{"kind": "case", "id": card["case_id"], "case_id": card["case_id"], "label": card["case_title"], "recorded_at": None}]


def card_answer(card: dict) -> tuple[str, list]:
    kind = card["kind"]
    if kind == "create_task":
        where = f" on {card['case_title']}" if card.get("case_id") else ""
        due = f", due {india_fmt(date.fromisoformat(card['due_date']))}" if card.get("due_date") else ", with no due date"
        return (
            f"Ready to add the task \"{card['title']}\"{where}{due}. Check it below and confirm; "
            "it then shows in your deadlines and calendar.",
            _case_source(card),
        )
    if kind == "mark_invoice_paid":
        name = card["invoice_number"] or "this fee"
        if card["blockers"]:
            return f"{name} can't be marked paid: {card['blockers'][0]}", _case_source(card)
        return (
            f"Ready to mark {name} ({billing.amount_text(card['amount'])}, {card['case_title']}) as paid. Confirm below.",
            _case_source(card),
        )
    if kind == "bulk_create_fees":
        count = len(card["rows"])
        amount = f" of {billing.amount_text(card['amount'])} each" if card.get("amount") else ""
        return (
            f"{count} past hearing{'s' if count != 1 else ''} from {card['period_text']} "
            f"{'have' if count != 1 else 'has'} no appearance fee yet. Below is one row each{amount}: untick any you "
            "don't bill, adjust amounts, then confirm. Each fee is added as pending; invoices are not generated or sent.",
            [],
        )
    if kind == "bulk_send_invoices":
        ready = [row for row in card["rows"] if not row["blockers"]]
        blocked = len(card["rows"]) - len(ready)
        text = (
            f"{len(card['rows'])} invoice{'s are' if len(card['rows']) != 1 else ' is'} generated and not sent yet. "
            f"{len(ready)} can be sent now"
        )
        text += f"; {blocked} can't yet (the reason is on each row)." if blocked else "."
        return text + " Untick any you want to hold back, then confirm: each goes to its client's billing email.", []
    raise ValueError(f"No answer for card {kind!r}.")
