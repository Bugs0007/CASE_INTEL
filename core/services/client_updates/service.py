"""Idempotent creation of client-message drafts.

Generators run more than once for the same event -- a worker retry, a
re-summary, a second refresh the same evening -- so every draft carries a
`dedup_key` stable for its event, and "generate again" is create-or-refresh
on that key rather than a duplicate. A draft is refreshed only while it is
still an untouched draft; once the advocate has edited, sent or discarded
it, generation leaves it alone for good (same contract as
upsert_system_task).

One draft per HEARING EVENT: the key for a case update is the date the
matter was heard, so the refresh that first sees the next date and the
order summary that arrives an hour later both land on the same draft --
the second one simply upgrades its text with what the court did.
"""

from __future__ import annotations

import logging
from datetime import date, datetime

from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import AppearanceFee, ClientContact, ClientMessage, CourtOrder, Hearing
from core.services.invoice_service import get_or_create_profile

from . import compose

logger = logging.getLogger(__name__)

OUTCOME_CREATED = "created"
OUTCOME_UPDATED = "updated"
OUTCOME_UNCHANGED = "unchanged"
OUTCOME_SKIPPED = "skipped"  # edited, sent or discarded by the advocate

_REFRESHABLE_FIELDS = ("subject", "body", "recipients", "hearing", "court_order")


# ---------------------------------------------------------------------------
# Recipients
# ---------------------------------------------------------------------------


def update_recipients(case) -> list[dict]:
    """Contacts on `case` who can receive case updates, as a snapshot."""
    contacts = ClientContact.objects.filter(
        case=case, receive_case_updates=True
    ).exclude(email__isnull=True).exclude(email="")
    return [_snapshot(c) for c in contacts.order_by("-is_billing_contact", "name", "id")]


def reminder_recipients(case) -> list[dict]:
    """The billing contact, if it has an email and hasn't opted out."""
    contact = (
        ClientContact.objects.filter(case=case, is_billing_contact=True)
        .exclude(email__isnull=True)
        .exclude(email="")
        .first()
    )
    if contact is None or not contact.receive_payment_reminders:
        return []
    return [_snapshot(contact)]


def _snapshot(contact: ClientContact) -> dict:
    return {"contact_id": contact.id, "name": contact.name, "email": contact.email}


# ---------------------------------------------------------------------------
# Upsert
# ---------------------------------------------------------------------------


def upsert_draft(
    *,
    case,
    kind: str,
    dedup_key: str,
    subject: str,
    body: str,
    recipients: list[dict],
    hearing=None,
    court_order=None,
    fee=None,
    reminder_number: int | None = None,
) -> tuple[ClientMessage, str]:
    values = {
        "subject": subject[:255],
        "body": body,
        "recipients": recipients,
        "hearing": hearing,
        "court_order": court_order,
    }
    existing = ClientMessage.objects.filter(owner=case.owner, dedup_key=dedup_key).first()
    if existing is None:
        try:
            with transaction.atomic():
                message = ClientMessage.objects.create(
                    owner=case.owner,
                    case=case,
                    kind=kind,
                    dedup_key=dedup_key,
                    fee=fee,
                    reminder_number=reminder_number,
                    **values,
                )
            logger.info("Client message draft %s created (%s).", message.id, dedup_key)
            return message, OUTCOME_CREATED
        except IntegrityError:
            # A concurrent generator won the insert; treat it as existing.
            existing = ClientMessage.objects.get(owner=case.owner, dedup_key=dedup_key)

    if existing.status != ClientMessage.STATUS_DRAFT or existing.edited_by_user:
        return existing, OUTCOME_SKIPPED

    changed = [f for f in _REFRESHABLE_FIELDS if getattr(existing, f) != values[f]]
    if not changed:
        return existing, OUTCOME_UNCHANGED
    for f in changed:
        setattr(existing, f, values[f])
    existing.save(update_fields=[*changed, "updated_at"])
    return existing, OUTCOME_UPDATED


# ---------------------------------------------------------------------------
# Case updates
# ---------------------------------------------------------------------------


def _hearing_day(hearing: Hearing) -> date:
    # TIME_ZONE is UTC and eCourts hearings are stored at midnight UTC on
    # the portal's date (see HearingSerializer.get_order_summary).
    return hearing.hearing_date.date()


def _hearing_on(case, day: date) -> Hearing | None:
    return (
        Hearing.objects.filter(case=case, hearing_date__date=day)
        .order_by("source", "id")  # the eCourts row ahead of a manual duplicate
        .first()
    )


def _next_hearing_after(case, day: date) -> Hearing | None:
    return (
        Hearing.objects.filter(case=case, hearing_date__date__gt=day)
        .exclude(status="cancelled")
        .order_by("hearing_date")
        .first()
    )


def case_update_key(case, heard_on: date) -> str:
    return f"case_update:{case.id}:{heard_on.isoformat()}"


def draft_case_update(
    case,
    *,
    heard_on: date | None,
    order: CourtOrder | None = None,
    next_date: date | None = None,
    next_purpose: str = "",
) -> tuple[ClientMessage | None, str]:
    """Create or refresh the update for the hearing on `heard_on`.

    The next date comes, in order of preference, from the case's own next
    Hearing row (eCourts is authoritative) and then from the order
    summary's next date. With neither, the email says the date isn't fixed.
    """
    profile = get_or_create_profile(case.owner)
    recipients = update_recipients(case)

    hearing = _hearing_on(case, heard_on) if heard_on else None
    if next_date is None and heard_on is not None:
        nxt = _next_hearing_after(case, heard_on)
        if nxt is not None:
            next_date, next_purpose = _hearing_day(nxt), (nxt.purpose or "")
    if next_date is None and order is not None and order.summary_next_date:
        next_date, next_purpose = order.summary_next_date, order.summary_next_date_purpose

    if heard_on is not None:
        key = case_update_key(case, heard_on)
    elif next_date is not None:
        key = f"case_update:{case.id}:next:{next_date.isoformat()}"
    else:
        return None, OUTCOME_SKIPPED

    subject, body = compose.compose_case_update(
        case=case,
        profile=profile,
        recipient_names=[r["name"] for r in recipients],
        heard_on=heard_on,
        order=order,
        next_date=next_date,
        next_purpose=next_purpose,
    )
    return upsert_draft(
        case=case,
        kind=ClientMessage.KIND_CASE_UPDATE,
        dedup_key=key,
        subject=subject,
        body=body,
        recipients=recipients,
        hearing=hearing,
        court_order=order,
    )


def draft_update_for_order(order: CourtOrder) -> tuple[ClientMessage | None, str]:
    """After an order has been summarised: the update for the hearing the
    order was passed on. Orders with no date can't be tied to a hearing."""
    if order.order_date is None:
        return None, OUTCOME_SKIPPED
    return draft_case_update(order.case, heard_on=order.order_date, order=order)


def draft_updates_for_new_dates(case, new_dates: list[date]) -> int:
    """After a refresh found hearing dates that weren't there before.

    Only a NEW FUTURE date is news for the client ("next date is Y"); the
    matching heard-on date is the latest hearing on or before today. Past
    dates alone wait for their order, which drafts the update itself.
    Returns the number of drafts created.
    """
    today = timezone.localdate()
    future = sorted(d for d in new_dates if d > today)
    if not future:
        return 0
    next_date = future[0]

    last_heard = (
        Hearing.objects.filter(case=case, hearing_date__date__lte=today)
        .exclude(status="cancelled")
        .order_by("-hearing_date")
        .first()
    )
    heard_on = _hearing_day(last_heard) if last_heard else None
    order = None
    if heard_on is not None:
        order = (
            CourtOrder.objects.filter(case=case, order_date=heard_on)
            .order_by("-created_at")
            .first()
        )
    nxt = _hearing_on(case, next_date)
    _, outcome = draft_case_update(
        case,
        heard_on=heard_on,
        order=order,
        next_date=next_date,
        next_purpose=(nxt.purpose if nxt else "") or "",
    )
    return 1 if outcome == OUTCOME_CREATED else 0


def draft_update_for_reschedule(hearing: Hearing, old_datetime: datetime) -> tuple[ClientMessage | None, str]:
    """The advocate moved a scheduled hearing by hand."""
    old_day = old_datetime.date()
    new_day = _hearing_day(hearing)
    if old_day == new_day or hearing.status != "scheduled" or new_day < timezone.localdate():
        return None, OUTCOME_SKIPPED
    case = hearing.case
    profile = get_or_create_profile(case.owner)
    recipients = update_recipients(case)
    subject, body = compose.compose_reschedule_update(
        case=case,
        profile=profile,
        recipient_names=[r["name"] for r in recipients],
        old_date=old_day,
        new_date=new_day,
        purpose=hearing.purpose or "",
    )
    return upsert_draft(
        case=case,
        kind=ClientMessage.KIND_CASE_UPDATE,
        dedup_key=f"case_update:{case.id}:resched:{hearing.id}:{new_day.isoformat()}",
        subject=subject,
        body=body,
        recipients=recipients,
        hearing=hearing,
    )


# ---------------------------------------------------------------------------
# Payment reminders
# ---------------------------------------------------------------------------

MAX_REMINDERS = 3
_DELIVERED = (ClientMessage.STATUS_SENT, ClientMessage.STATUS_LOGGED)


def reminder_key(fee: AppearanceFee, number: int) -> str:
    return f"reminder:{fee.id}:{number}"


def next_reminder_due(fee: AppearanceFee, *, after_days: int, now=None):
    """(reminder_number, reason) for `fee`, reminder_number None when no
    reminder is due. Pure read -- used by the command's dry run too."""
    now = now or timezone.now()
    if fee.status != AppearanceFee.STATUS_INVOICED or fee.invoiced_at is None:
        return None, "not awaiting payment"

    reminders = ClientMessage.objects.filter(fee=fee, kind=ClientMessage.KIND_PAYMENT_REMINDER)
    delivered = reminders.filter(status__in=_DELIVERED)
    count = delivered.count()
    if count >= MAX_REMINDERS:
        return None, "already reminded 3 times"
    if reminders.filter(status=ClientMessage.STATUS_DRAFT).exists():
        return None, "a reminder draft is already waiting"
    number = count + 1
    if reminders.filter(dedup_key=reminder_key(fee, number), status=ClientMessage.STATUS_DISCARDED).exists():
        # Discarding a reminder draft is the advocate saying "not for this
        # invoice" -- don't keep proposing it.
        return None, "reminder discarded by the advocate"

    last = delivered.order_by("-sent_at").values_list("sent_at", flat=True).first()
    since = last or fee.invoiced_at
    if now - since < timezone.timedelta(days=after_days):
        return None, "not due yet"
    return number, "due"


def draft_payment_reminder(fee: AppearanceFee, number: int) -> tuple[ClientMessage | None, str]:
    case = fee.hearing.case
    recipients = reminder_recipients(case)
    if not recipients:
        return None, OUTCOME_SKIPPED
    profile = get_or_create_profile(case.owner)
    subject, body = compose.compose_payment_reminder(
        fee=fee, profile=profile, recipient_name=recipients[0]["name"], reminder_number=number
    )
    return upsert_draft(
        case=case,
        kind=ClientMessage.KIND_PAYMENT_REMINDER,
        dedup_key=reminder_key(fee, number),
        subject=subject,
        body=body,
        recipients=recipients,
        hearing=fee.hearing,
        fee=fee,
        reminder_number=number,
    )
