from decimal import Decimal
from typing import Annotated, Optional

from pydantic import Field

from core.models import AppearanceFee, ClientMessage

from ..access import scoped
from ..registry import KIND_READ, READ_HINTS, ToolOutput, tool
from ..safety import MAX_ROWS, TextBudget, short_text
from .common import TIMEZONE, as_ist, get_case, now_ist, owned_case_q

OptionalCaseId = Annotated[Optional[int], Field(description="Only this case. Optional.")]


@tool("list_client_drafts", kind=KIND_READ, title="List client drafts", annotations=READ_HINTS)
def list_client_drafts(ctx, case_id: OptionalCaseId = None):
    """Client-update and payment-reminder drafts waiting in Case Intel (status draft). Read only:
    this server cannot send them; the advocate sends from the Case Intel web app."""
    qs = scoped(ClientMessage, ctx).filter(status=ClientMessage.STATUS_DRAFT).filter(owned_case_q(ctx))
    if case_id is not None:
        qs = qs.filter(case=get_case(ctx, case_id))
    total = qs.count()
    budget = TextBudget()
    rows = []
    for message in qs.select_related("case").order_by("-created_at", "-id")[:MAX_ROWS]:
        rows.append(
            {
                "draft_id": message.id,
                "case_id": message.case_id,
                "case_title": short_text(message.case.title) if message.case_id else None,
                "kind": message.kind,
                "status": message.status,
                "subject": budget.take(message.subject, per_field=255),
                "body": budget.take(message.body, per_field=1500),
                "recipients": [short_text(r, 254) for r in (message.recipients or [])][:10],
                "created_at": as_ist(message.created_at),
            }
        )
    return ToolOutput(
        data={
            "drafts": rows,
            "total": total,
            "truncated": total > len(rows) or budget.truncated,
            "as_of": now_ist().isoformat(),
            "timezone": TIMEZONE,
        },
        case_id=case_id,
        rows=len(rows),
        untrusted=True,
    )


@tool("list_unpaid_fees", kind=KIND_READ, title="List unpaid fees", annotations=READ_HINTS)
def list_unpaid_fees(ctx, case_id: OptionalCaseId = None):
    """Fees not yet paid: pending (no invoice yet) and invoiced. Amounts are in rupees, as strings.
    Read only: this server cannot create, send or mark invoices."""
    qs = (
        scoped(AppearanceFee, ctx)
        .filter(status__in=(AppearanceFee.STATUS_PENDING, AppearanceFee.STATUS_INVOICED))
        .filter(hearing__owner_id__in=ctx.owner_ids, hearing__case__owner_id__in=ctx.owner_ids)
    )
    if case_id is not None:
        qs = qs.filter(hearing__case=get_case(ctx, case_id))
    totals = {AppearanceFee.STATUS_PENDING: Decimal("0"), AppearanceFee.STATUS_INVOICED: Decimal("0")}
    for status, amount in qs.values_list("status", "amount"):
        totals[status] += amount or Decimal("0")
    total = qs.count()
    rows = []
    for fee in qs.select_related("hearing__case").order_by("hearing__hearing_date", "id")[:MAX_ROWS]:
        rows.append(
            {
                "fee_id": fee.id,
                "case_id": fee.hearing.case_id,
                "case_title": short_text(fee.hearing.case.title),
                "hearing_id": fee.hearing_id,
                "hearing_at": as_ist(fee.hearing.hearing_date),
                "category": fee.category,
                "amount": str(fee.amount),
                "status": fee.status,
                "invoice_number": fee.invoice_number or None,
                "invoiced_at": as_ist(fee.invoiced_at),
            }
        )
    return ToolOutput(
        data={
            "fees": rows,
            "totals": {key: str(value) for key, value in totals.items()},
            "currency": "INR",
            "total": total,
            "truncated": total > len(rows),
            "as_of": now_ist().isoformat(),
            "timezone": TIMEZONE,
        },
        case_id=case_id,
        rows=len(rows),
        untrusted=True,
    )
