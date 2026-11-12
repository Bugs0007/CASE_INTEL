"""Owner-scoped, read-only billing reads for the practice assistant.

Nothing here (or anywhere under graph/ and practice_assistant/) sends mail,
generates an invoice or changes a fee's status: the assistant only reads and
proposes. The advocate's own confirmation calls the existing fee endpoints.

Every field of the send card comes from database rows. Model text never
reaches it.
"""
from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Count, Q, Sum
from django.db.models.functions import Lower

from core.models import AppearanceFee
from core.services.india_time import INDIA_TZ, india_now
from core.services.invoice_service import MissingBillingContactError, get_billing_contact
from core.services.money import pdf_inr

from .contracts import SCOPE_PERSONAL, TIMEZONE, ActionCard, Reference

UNPAID_ROW_LIMIT = 25
PAID_WINDOW_DAYS = 30
MAX_INVOICE_TOKENS = 20

BLOCKER_NOT_INVOICED = "This fee has no invoice yet. Generate the invoice first."
BLOCKER_PAID = "This invoice is already paid."
BLOCKER_NO_EMAIL = "No billing email is recorded for this client."

_TOKEN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-/_.]*")


def _check_scope(scope: str) -> None:
    if scope != SCOPE_PERSONAL:
        raise ValueError(f"Unsupported scope {scope!r}; only {SCOPE_PERSONAL!r} is available.")


def _clock(now: Optional[datetime]) -> datetime:
    if now is None:
        return india_now()
    if now.tzinfo is None:
        raise ValueError("now must be an aware datetime.")
    return now.astimezone(INDIA_TZ)


def _owned(owner, case_id: Optional[int]):
    qs = AppearanceFee.objects.filter(owner=owner, hearing__case__owner=owner)
    if case_id is not None:
        qs = qs.filter(hearing__case_id=case_id)
    return qs


def _money(value) -> str:
    return str(Decimal(value).quantize(Decimal("0.01")))


def fee_ref(fee: AppearanceFee) -> Reference:
    label = fee.invoice_number or f"{fee.get_category_display()} (no invoice yet)"
    return {
        "kind": "fee",
        "id": fee.id,
        "case_id": fee.hearing.case_id,
        "label": label,
        "recorded_at": fee.invoiced_at.isoformat() if fee.invoiced_at else None,
    }


def _row(fee: AppearanceFee) -> dict:
    return {
        "id": fee.id,
        "case_id": fee.hearing.case_id,
        "case_title": fee.hearing.case.title,
        "category": fee.category,
        "amount": _money(fee.amount),
        "status": fee.status,
        "invoice_number": fee.invoice_number or None,
        "sent": fee.send_status == AppearanceFee.SEND_SENT,
        "send_status": fee.send_status,
        "ref": fee_ref(fee),
    }


def case_list(rows: list[dict]) -> list[dict]:
    seen: dict[int, dict] = {}
    for row in rows:
        seen.setdefault(row["case_id"], {"id": row["case_id"], "title": row["case_title"]})
    return list(seen.values())


def billing_summary(
    *, owner, scope: str, case_id: Optional[int] = None, now: Optional[datetime] = None
) -> dict:
    """Counts and totals by stage, plus up to 25 unpaid rows ordered by case.
    A fixed number of queries however many fees there are."""
    _check_scope(scope)
    clock = _clock(now)
    paid_from = datetime.combine(
        clock.date() - timedelta(days=PAID_WINDOW_DAYS - 1), time.min, tzinfo=INDIA_TZ
    )
    base = _owned(owner, case_id)
    sent_q = Q(send_status=AppearanceFee.SEND_SENT)
    invoiced_q = Q(status=AppearanceFee.STATUS_INVOICED)
    stages = {
        "pending": Q(status=AppearanceFee.STATUS_PENDING),
        "invoiced_unsent": invoiced_q & ~sent_q,
        "sent_unpaid": invoiced_q & sent_q,
        "paid_30d": Q(status=AppearanceFee.STATUS_PAID, paid_at__gte=paid_from),
    }
    aggregates = {}
    for name, condition in stages.items():
        aggregates[f"{name}_count"] = Count("id", filter=condition)
        aggregates[f"{name}_total"] = Sum("amount", filter=condition)
    agg = base.aggregate(**aggregates)

    unpaid = base.exclude(status=AppearanceFee.STATUS_PAID)
    total = unpaid.count()
    fees = list(
        unpaid.select_related("hearing__case").order_by("hearing__case__title", "hearing__case_id", "id")[
            :UNPAID_ROW_LIMIT
        ]
    )
    rows = [_row(fee) for fee in fees]
    return {
        "counts": {name: agg[f"{name}_count"] for name in stages},
        "totals": {name: _money(agg[f"{name}_total"] or 0) for name in stages},
        "rows": rows,
        "cases": case_list(rows),
        "total": total,
        "truncated": total > len(rows),
        "as_of": clock.isoformat(),
        "timezone": TIMEZONE,
    }


def invoice_send_candidates(
    *, owner, scope: str, case_id: Optional[int] = None, text: str = ""
) -> list[AppearanceFee]:
    """The owner's fees that the advocate might mean. An invoice number found
    in `text` that is one of the owner's OWN numbers names exactly those fees
    (whatever their status, so a paid one answers with its blocker). Otherwise
    every invoiced fee, narrowed by `case_id`. Unsent first."""
    _check_scope(scope)
    base = _owned(owner, case_id).select_related("hearing__case")
    tokens = list(dict.fromkeys(t.lower().rstrip(".") for t in _TOKEN_RE.findall(text or "")))
    tokens = [t for t in tokens if t][:MAX_INVOICE_TOKENS]
    if tokens:
        named = list(
            base.exclude(invoice_number="")
            .annotate(_number=Lower("invoice_number"))
            .filter(_number__in=tokens)
            .order_by("id")
        )
        if named:
            return named
    return list(
        base.filter(status=AppearanceFee.STATUS_INVOICED).order_by("send_status", "hearing__case__title", "id")
    )


def build_send_card(*, owner, fee: AppearanceFee) -> ActionCard:
    """The confirmation card for one fee, every field read from rows. `fee`
    is re-fetched under `owner`; a fee that is not theirs raises DoesNotExist."""
    fee = AppearanceFee.objects.select_related("hearing__case").get(
        id=fee.id, owner=owner, hearing__case__owner=owner
    )
    case = fee.hearing.case
    blockers: list[str] = []
    if fee.status == AppearanceFee.STATUS_PAID:
        blockers.append(BLOCKER_PAID)
    elif fee.status != AppearanceFee.STATUS_INVOICED or not fee.invoice_number or not fee.invoice_pdf_path:
        blockers.append(BLOCKER_NOT_INVOICED)
    name = email = None
    try:
        contact = get_billing_contact(case)
        name, email = contact.name, contact.email
    except MissingBillingContactError:
        blockers.append(BLOCKER_NO_EMAIL)
    return {
        "kind": "send_invoice",
        "fee_id": fee.id,
        "case_id": case.id,
        "invoice_number": fee.invoice_number or None,
        "amount": _money(fee.amount),
        "recipient_name": name,
        "recipient_email": email,
        "blockers": blockers,
    }


def candidate_rows(fees: list[AppearanceFee]) -> list[dict]:
    return [_row(fee) for fee in fees]


def amount_text(amount: str) -> str:
    return pdf_inr(Decimal(amount))
