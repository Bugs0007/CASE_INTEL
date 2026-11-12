"""Action cards of the practice assistant: proposals, never writes.

Every function here only READS the owner's rows and returns a card. The
advocate reviews it, may edit it, and confirms with a click; the frontend then
calls the existing owner-scoped REST endpoint (the endpoint, not the card,
enforces the rules: the card's `blockers` are a courtesy).

  create_fee        -> POST   /api/appearance-fees/
  update_fee        -> PATCH  /api/appearance-fees/<id>/
  generate_invoice  -> POST   /api/appearance-fees/<id>/invoice/
  delete_fee        -> DELETE /api/appearance-fees/<id>/
  start_draft       -> POST   /api/case-assistant/drafts/

Every field comes from rows or from the advocate's own words (amount,
category, a date), never from model text.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from core.models import AdvocateProfile, AppearanceFee, AssistantDraft, Case, Hearing
from core.services import invoice_service
from core.services.india_time import india_date, india_fmt

from . import parsing
from .contracts import (
    CreateFeeCard,
    DeleteFeeCard,
    GenerateInvoiceCard,
    HearingOption,
    StartDraftCard,
    UpdateFeeCard,
)

MAX_HEARING_OPTIONS = 10
MAX_INSTRUCTIONS = 2000

BLOCKER_NO_HEARING = "This case has no hearing to attach the fee to."
BLOCKER_NO_AMOUNT = "An amount is needed for this kind of charge."
BLOCKER_NO_DEFAULT = "Give an amount, or set your default appearance fee in Settings."
BLOCKER_ZERO_AMOUNT = "The amount is 0. Set an amount first."
BLOCKER_ALREADY_INVOICED = "This fee already has an invoice."

FEE_ACTION_INTENTS = (
    "propose_fee_create",
    "propose_fee_update",
    "propose_invoice_generate",
    "propose_fee_delete",
)


def money(value) -> str:
    return str(Decimal(value).quantize(Decimal("0.01")))


def category_label(category: str) -> str:
    return dict(AppearanceFee.CATEGORY_CHOICES).get(category, category)


# ---------------------------------------------------------------------------
# create_fee
# ---------------------------------------------------------------------------


def _hearing_label(hearing: Hearing) -> str:
    label = (hearing.purpose or "").strip() or hearing.get_hearing_type_display()
    if hearing.status != "scheduled":
        label += f" ({hearing.get_status_display().lower()})"
    return f"{india_fmt(hearing.hearing_date)}, {label}"


def _hearing_options(hearings: list[Hearing]) -> list[HearingOption]:
    return [
        {"id": h.id, "label": _hearing_label(h), "date": india_date(h.hearing_date).isoformat()}
        for h in hearings[:MAX_HEARING_OPTIONS]
    ]


def pick_hearing(
    *, owner, case: Case, category: str, query: str, now: datetime
) -> tuple[Optional[Hearing], list[Hearing], Optional[str]]:
    """(chosen hearing, the case's hearings newest first, blocker).

    A date in the question names the hearing ON that date; if the case has
    none, nothing is chosen (a blocker says so) rather than guessing. With no
    date: for an appearance fee the latest past hearing that has no
    appearance fee yet (else the latest past one); for any other charge the
    latest past hearing; failing that the next upcoming one. Cancelled
    hearings are never picked by default."""
    hearings = list(Hearing.objects.filter(owner=owner, case=case).order_by("-hearing_date", "-id"))
    if not hearings:
        return None, hearings, BLOCKER_NO_HEARING
    live = [h for h in hearings if h.status != "cancelled"]

    wanted = parsing.parse_dates(query, today=now.date())
    if wanted:
        for day in wanted:
            for hearing in live:
                if india_date(hearing.hearing_date) == day:
                    return hearing, hearings, None
        shown = ", ".join(india_fmt(day) for day in wanted[:2])
        return None, hearings, f"No hearing of this case is recorded on {shown}. Pick one of its hearings."

    past = [h for h in live if h.hearing_date <= now]
    if category == AppearanceFee.CATEGORY_APPEARANCE and past:
        billed = set(
            AppearanceFee.objects.filter(
                owner=owner,
                hearing__in=[h.id for h in past],
                category=AppearanceFee.CATEGORY_APPEARANCE,
            ).values_list("hearing_id", flat=True)
        )
        unbilled = [h for h in past if h.id not in billed]
        if unbilled:
            return unbilled[0], hearings, None
    if past:
        return past[0], hearings, None
    upcoming = [h for h in live if h.hearing_date > now]
    if upcoming:
        return upcoming[-1], hearings, None  # list is newest first, so the nearest
    return None, hearings, BLOCKER_NO_HEARING


def build_create_card(*, owner, case: Case, query: str, now: datetime) -> CreateFeeCard:
    category = parsing.parse_category(query, default=AppearanceFee.CATEGORY_APPEARANCE)
    amount = parsing.parse_amount(query)
    hearing, hearings, blocker = pick_hearing(owner=owner, case=case, category=category, query=query, now=now)
    blockers: list[str] = [blocker] if blocker else []
    if amount is None:
        if category != AppearanceFee.CATEGORY_APPEARANCE:
            blockers.append(BLOCKER_NO_AMOUNT)
        else:
            profile = AdvocateProfile.objects.filter(owner=owner).first()
            if profile is None or not profile.default_fee_amount:
                blockers.append(BLOCKER_NO_DEFAULT)
    return {
        "kind": "create_fee",
        "case_id": case.id,
        "case_title": case.title,
        "hearing_id": hearing.id if hearing else None,
        "hearing_options": _hearing_options(hearings),
        "category": category,
        "amount": money(amount) if amount is not None else None,
        "description": parsing.parse_description(query) or "",
        "blockers": blockers,
    }


# ---------------------------------------------------------------------------
# Choosing the fee a command is about
# ---------------------------------------------------------------------------


def _eligible(intent: str, fee: AppearanceFee) -> bool:
    if intent == "propose_fee_update":
        return invoice_service.change_blocker(fee) is None
    if intent == "propose_fee_delete":
        return invoice_service.delete_blocker(fee) is None
    return fee.status == AppearanceFee.STATUS_PENDING  # generate


def select_fee(intent: str, fees_latest_first: list[AppearanceFee]) -> Optional[AppearanceFee]:
    """The newest fee the action can be done to; if none can, the newest fee
    (its card then carries the reason as a blocker)."""
    for fee in fees_latest_first:
        if _eligible(intent, fee):
            return fee
    return fees_latest_first[0] if fees_latest_first else None


# ---------------------------------------------------------------------------
# update_fee / generate_invoice / delete_fee
# ---------------------------------------------------------------------------


def _current(fee: AppearanceFee) -> dict:
    return {"amount": money(fee.amount), "category": fee.category, "description": fee.notes or ""}


def proposed_changes(fee: AppearanceFee, query: str) -> dict:
    """Only the fields the question changes AND that differ from the stored
    values. An amount is read from the words (never from a model)."""
    current = _current(fee)
    proposed: dict = {}
    amount = parsing.parse_amount(query, extra_mask=(fee.invoice_number,))
    if amount is not None and money(amount) != current["amount"]:
        proposed["amount"] = money(amount)
    category = parsing.parse_category_change(query)
    if category and category != current["category"]:
        proposed["category"] = category
    description = parsing.parse_description(query)
    if description is not None and description != current["description"]:
        proposed["description"] = description
    return proposed


def build_update_card(*, fee: AppearanceFee, proposed: dict) -> UpdateFeeCard:
    blocker = invoice_service.change_blocker(fee)
    return {
        "kind": "update_fee",
        "case_id": fee.hearing.case_id,
        "case_title": fee.hearing.case.title,
        "fee_id": fee.id,
        "invoice_number": fee.invoice_number or None,
        "fee_status": fee.status,
        "current": _current(fee),
        "proposed": proposed,
        "regenerates_invoice": bool(
            blocker is None and fee.status == AppearanceFee.STATUS_INVOICED and fee.invoice_number
        ),
        "blockers": [blocker] if blocker else [],
    }


def build_generate_card(*, fee: AppearanceFee) -> GenerateInvoiceCard:
    blockers: list[str] = []
    if fee.status == AppearanceFee.STATUS_PAID:
        blockers.append(invoice_service.MSG_PAID)
    elif fee.status != AppearanceFee.STATUS_PENDING:
        blockers.append(
            f"{fee.invoice_number} has already been made for this fee."
            if fee.invoice_number
            else BLOCKER_ALREADY_INVOICED
        )
    if fee.amount <= 0:
        blockers.append(BLOCKER_ZERO_AMOUNT)
    return {
        "kind": "generate_invoice",
        "case_id": fee.hearing.case_id,
        "case_title": fee.hearing.case.title,
        "fee_id": fee.id,
        "amount": money(fee.amount),
        "category": fee.category,
        "blockers": blockers,
    }


def build_delete_card(*, fee: AppearanceFee) -> DeleteFeeCard:
    blocker = invoice_service.delete_blocker(fee)
    return {
        "kind": "delete_fee",
        "case_id": fee.hearing.case_id,
        "case_title": fee.hearing.case.title,
        "fee_id": fee.id,
        "amount": money(fee.amount),
        "category": fee.category,
        "fee_status": fee.status,
        "blockers": [blocker] if blocker else [],
    }


# ---------------------------------------------------------------------------
# start_draft
# ---------------------------------------------------------------------------

DRAFT_SUBTYPES = dict(AssistantDraft.SUBTYPE_CHOICES)


def build_draft_card(*, case: Case, subtype: str, query: str) -> StartDraftCard:
    if subtype not in DRAFT_SUBTYPES:
        raise ValueError(f"Unknown draft subtype {subtype!r}.")
    return {
        "kind": "start_draft",
        "case_id": case.id,
        "case_title": case.title,
        "subtype": subtype,
        "subtype_label": DRAFT_SUBTYPES[subtype],
        "instructions": " ".join((query or "").split())[:MAX_INSTRUCTIONS],
        "blockers": [],
    }
