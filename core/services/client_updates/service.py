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

And one OPEN case update per case. Drafts are news, so:
  - nothing is drafted when no contact can receive it (no opted-in contact
    with an email) -- the case page asks for a client email instead;
  - nothing is drafted for a hearing older than CLIENT_UPDATE_MAX_AGE_DAYS,
    or older than an update the case already has (sent, discarded or
    waiting) -- a first order sync on an old case used to draft one email
    per back-order;
  - an order is only drafted for when it is the case's latest hearing
    event (no newer order, no newer hearing already held);
  - a draft for a newer event REPLACES an untouched older draft instead of
    stacking next to it. A draft the advocate edited is theirs and is left
    alone.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from core.models import AppearanceFee, ClientContact, ClientMessage, CourtOrder, Hearing
from core.services.invoice_service import get_or_create_profile

from . import compose

logger = logging.getLogger(__name__)

OUTCOME_CREATED = "created"
OUTCOME_UPDATED = "updated"
OUTCOME_REPLACED = "replaced"  # an older untouched draft now carries this event
OUTCOME_UNCHANGED = "unchanged"
OUTCOME_SKIPPED = "skipped"  # edited/sent/discarded, or not news (see module doc)

_REFRESHABLE_FIELDS = ("subject", "body", "recipients", "hearing", "court_order")
_SUPERSEDED_REASON = "Replaced by a newer update for this case."


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
    event_date: date | None = None,
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
                    event_date=event_date,
                    **values,
                )
            logger.info("Client message draft %s created (%s).", message.id, dedup_key)
            return message, OUTCOME_CREATED
        except IntegrityError:
            # A concurrent generator won the insert; treat it as existing.
            existing = ClientMessage.objects.get(owner=case.owner, dedup_key=dedup_key)

    return _refresh(existing, values)


def _refresh(existing: ClientMessage, values: dict) -> tuple[ClientMessage, str]:
    if existing.status != ClientMessage.STATUS_DRAFT or existing.edited_by_user:
        return existing, OUTCOME_SKIPPED

    changed = [f for f in _REFRESHABLE_FIELDS if getattr(existing, f) != values[f]]
    if not changed:
        return existing, OUTCOME_UNCHANGED
    for f in changed:
        setattr(existing, f, values[f])
    existing.save(update_fields=[*changed, "updated_at"])
    return existing, OUTCOME_UPDATED


def upsert_case_update(
    *,
    case,
    dedup_key: str,
    event_date: date,
    subject: str,
    body: str,
    recipients: list[dict],
    hearing=None,
    court_order=None,
) -> tuple[ClientMessage | None, str]:
    """upsert_draft for the one-open-update-per-case chain (module doc).

    Same event (same key): refresh as usual. Otherwise, older news than
    anything the case already has is dropped, and the newest untouched
    draft is re-pointed at this event instead of a second row appearing.
    """
    values = {
        "subject": subject[:255],
        "body": body,
        "recipients": recipients,
        "hearing": hearing,
        "court_order": court_order,
    }
    existing = ClientMessage.objects.filter(owner=case.owner, dedup_key=dedup_key).first()
    if existing is not None:
        return _refresh(existing, values)

    chain = ClientMessage.objects.filter(
        case=case, kind=ClientMessage.KIND_CASE_UPDATE, event_date__isnull=False
    )
    newer = chain.filter(event_date__gt=event_date).order_by("-event_date", "-id").first()
    if newer is not None:
        logger.info(
            "Case %s: no draft for %s -- update %s already covers %s.",
            case.id, event_date, newer.id, newer.event_date,
        )
        return None, OUTCOME_SKIPPED

    replaceable = list(
        chain.filter(status=ClientMessage.STATUS_DRAFT, edited_by_user=False).order_by(
            "-event_date", "-id"
        )
    )
    if not replaceable:
        return upsert_draft(
            case=case,
            kind=ClientMessage.KIND_CASE_UPDATE,
            dedup_key=dedup_key,
            event_date=event_date,
            **{k: values[k] for k in ("subject", "body", "recipients", "hearing", "court_order")},
        )

    target, stale = replaceable[0], replaceable[1:]
    with transaction.atomic():
        for f, value in values.items():
            setattr(target, f, value)
        target.dedup_key = dedup_key
        target.event_date = event_date
        target.save(update_fields=[*values, "dedup_key", "event_date", "updated_at"])
        if stale:
            ClientMessage.objects.filter(id__in=[m.id for m in stale]).update(
                status=ClientMessage.STATUS_DISCARDED,
                discard_reason=_SUPERSEDED_REASON,
                updated_at=timezone.now(),
            )
    logger.info("Client update draft %s now reports %s (%s).", target.id, event_date, dedup_key)
    return target, OUTCOME_REPLACED


# ---------------------------------------------------------------------------
# Case updates
# ---------------------------------------------------------------------------


def max_age_days() -> int:
    return int(getattr(settings, "CLIENT_UPDATE_MAX_AGE_DAYS", 7))


def is_too_old(day: date, today: date | None = None) -> bool:
    """A hearing heard longer ago than the setting is history, not news."""
    today = today or timezone.localdate()
    return day < today - timedelta(days=max_age_days())


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
    summary's next date. With neither, the email says the date isn't fixed
    -- or, when the order or eCourts says the case was disposed of, says
    that instead.
    """
    recipients = update_recipients(case)
    if not recipients:
        # Nobody could receive it. The case page asks for a client email
        # instead of the inbox filling with unsendable drafts.
        logger.info("Case %s: no client update drafted -- no contact with an email opted in.", case.id)
        return None, OUTCOME_SKIPPED

    today = timezone.localdate()
    if heard_on is not None and is_too_old(heard_on, today):
        if next_date is None:
            logger.info("Case %s: no draft for the hearing on %s -- older than %d days.", case.id, heard_on, max_age_days())
            return None, OUTCOME_SKIPPED
        # A new date after a long gap is still news; the old hearing isn't.
        heard_on, order = None, None

    hearing = _hearing_on(case, heard_on) if heard_on else None
    if next_date is None and heard_on is not None:
        nxt = _next_hearing_after(case, heard_on)
        if nxt is not None:
            next_date, next_purpose = _hearing_day(nxt), (nxt.purpose or "")
    if next_date is None and order is not None and order.summary_next_date:
        next_date, next_purpose = order.summary_next_date, order.summary_next_date_purpose

    if heard_on is not None:
        key, event_date = case_update_key(case, heard_on), heard_on
    elif next_date is not None:
        key, event_date = f"case_update:{case.id}:next:{next_date.isoformat()}", today
    else:
        return None, OUTCOME_SKIPPED

    disposed = False
    if next_date is None:
        from core.services.disposal import case_disposal

        disposed = (order is not None and order.disposes_case) or case_disposal(case) is not None

    subject, body = compose.compose_case_update(
        case=case,
        profile=get_or_create_profile(case.owner),
        recipient_names=[r["name"] for r in recipients],
        heard_on=heard_on,
        order=order,
        next_date=next_date,
        next_purpose=next_purpose,
        disposed=disposed,
    )
    return upsert_case_update(
        case=case,
        dedup_key=key,
        event_date=event_date,
        subject=subject,
        body=body,
        recipients=recipients,
        hearing=hearing,
        court_order=order,
    )


def _newer_event_than(order: CourtOrder) -> str:
    """Why `order` isn't the case's latest hearing event, or ""."""
    case = order.case
    if CourtOrder.objects.filter(case=case, order_date__gt=order.order_date).exists():
        return "a later order exists"
    held = (
        Hearing.objects.filter(
            case=case,
            hearing_date__date__gt=order.order_date,
            hearing_date__date__lte=timezone.localdate(),
        )
        .exclude(status="cancelled")
        .exists()
    )
    return "a later hearing has already been held" if held else ""


def draft_update_for_order(order: CourtOrder) -> tuple[ClientMessage | None, str]:
    """After an order has been summarised: the update for the hearing the
    order was passed on -- only when that hearing is the case's latest
    event. Orders with no date can't be tied to a hearing."""
    if order.order_date is None:
        return None, OUTCOME_SKIPPED
    reason = _newer_event_than(order)
    if reason:
        logger.info("Order %s: no client update drafted -- %s.", order.id, reason)
        return None, OUTCOME_SKIPPED
    return draft_case_update(order.case, heard_on=order.order_date, order=order)


def draft_updates_for_new_dates(case, new_dates: list[date]) -> int:
    """After a refresh found hearing dates that weren't there before.

    Only a NEW FUTURE date is news for the client ("next date is Y"); the
    matching heard-on date is the latest hearing on or before today. Past
    dates alone wait for their order, which drafts the update itself.
    Returns the number of drafts created -- at most one per refresh.
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
    return 1 if outcome in (OUTCOME_CREATED, OUTCOME_REPLACED) else 0


def draft_update_for_reschedule(hearing: Hearing, old_datetime: datetime) -> tuple[ClientMessage | None, str]:
    """The advocate moved a scheduled hearing by hand. Its own draft per
    move -- outside the one-open-update chain, since it's the advocate's
    own action, not court news."""
    old_day = old_datetime.date()
    new_day = _hearing_day(hearing)
    if old_day == new_day or hearing.status != "scheduled" or new_day < timezone.localdate():
        return None, OUTCOME_SKIPPED
    case = hearing.case
    recipients = update_recipients(case)
    if not recipients:
        return None, OUTCOME_SKIPPED
    profile = get_or_create_profile(case.owner)
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
