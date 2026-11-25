from typing import Annotated, Optional

from django.db.models import F
from pydantic import Field

from core.models import CourtOrder

from ..access import scoped
from ..registry import KIND_READ, READ_HINTS, ToolOutput, tool
from ..safety import TextBudget, clamp_limit, short_text
from .common import TIMEZONE, as_ist, get_case, now_ist

CaseId = Annotated[int, Field(description="A case_id from list_cases.")]


def render_order_summary(order: CourtOrder, budget: TextBudget) -> dict:
    """The stored Order Overview, framed from the case's side -- the same
    shape and party rule as core/serializers/order_summary.build_order_summary
    (a parity test pins them), with every court-derived text in
    `untrusted_text`. Never runs the LLM: a pending summary stays pending."""
    role = order.case.user_party_role
    what_happened = budget.take(order.summary_what_happened)
    petitioner = budget.take_list(order.summary_petitioner_directions)
    respondent = budget.take_list(order.summary_respondent_directions)
    # Each direction appears once: as your side / the other side when the
    # role is known, else under petitioner / respondent (shown neutrally).
    if role == "petitioner":
        your_side, other_side, petitioner, respondent = petitioner, respondent, None, None
    elif role == "respondent":
        your_side, other_side, petitioner, respondent = respondent, petitioner, None, None
    else:
        your_side = other_side = None
    return {
        "status": order.summary_status,
        "route": order.summary_route or None,
        "what_happened": what_happened,
        "petitioner_directions": petitioner,
        "respondent_directions": respondent,
        "your_side_directions": your_side,
        "other_side_directions": other_side,
        "party_role": role,
        "next_date": order.summary_next_date.isoformat() if order.summary_next_date else None,
        "next_date_purpose": budget.take(order.summary_next_date_purpose, per_field=300),
        "is_routine_adjournment": order.summary_is_routine_adjournment,
        "generated_at": as_ist(order.summary_generated_at),
    }


def order_row(order: CourtOrder) -> dict:
    return {
        "order_id": order.id,
        "order_number": short_text(order.order_number),
        "order_date": order.order_date.isoformat() if order.order_date else None,
        "description": short_text(order.description) or None,
        "judge": short_text(order.judge) or None,
        "download_status": order.download_status,
        "summary_status": order.summary_status,
        "document_id": order.document_id,
        "disposes_case": order.disposes_case,
    }


@tool("get_last_order", kind=KIND_READ, title="Get last order", annotations=READ_HINTS)
def get_last_order(ctx, case_id: CaseId):
    """The case's most recent court order and its stored summary: what happened, the directions
    for each side (your side first when your party role is known), the next date and its purpose.
    The summary was made once when the order arrived; this tool never generates one."""
    case = get_case(ctx, case_id)
    order = (
        scoped(CourtOrder, ctx)
        .filter(case=case)
        .select_related("case")
        .order_by(F("order_date").desc(nulls_last=True), "-created_at", "-id")
        .first()
    )
    budget = TextBudget()
    data = {
        "case_id": case.id,
        "order": order_row(order) if order else None,
        "summary": render_order_summary(order, budget) if order else None,
        "as_of": now_ist().isoformat(),
        "timezone": TIMEZONE,
    }
    data["truncated"] = budget.truncated
    return ToolOutput(data=data, case_id=case.id, rows=1 if order else 0, untrusted=True)


@tool("list_orders", kind=KIND_READ, title="List orders", annotations=READ_HINTS)
def list_orders(
    ctx,
    case_id: CaseId,
    limit: Annotated[Optional[int], Field(description="At most 50. Default 20.")] = None,
):
    """The case's court orders, newest first, with download status and summary status. Use
    get_last_order for the latest order's summary."""
    case = get_case(ctx, case_id)
    limit = clamp_limit(limit, 20)
    qs = scoped(CourtOrder, ctx).filter(case=case)
    total = qs.count()
    orders = list(qs.order_by(F("order_date").desc(nulls_last=True), "-created_at", "-id")[:limit])
    return ToolOutput(
        data={
            "case_id": case.id,
            "orders": [order_row(o) for o in orders],
            "total": total,
            "truncated": total > len(orders),
            "as_of": now_ist().isoformat(),
            "timezone": TIMEZONE,
        },
        case_id=case.id,
        rows=len(orders),
        untrusted=True,
    )
