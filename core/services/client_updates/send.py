"""Sending (and editing) a client-message draft. Always an explicit
advocate action -- nothing in this package sends on its own."""

from __future__ import annotations

import logging

from django.core.files.storage import default_storage
from django.utils import timezone

from core.models import AppearanceFee, ClientContact, ClientMessage
from core.services import email_delivery
from core.services.invoice_service import get_or_create_profile

logger = logging.getLogger(__name__)


class ClientMessageError(Exception):
    """A send/edit that can't go ahead; surfaces as a 4xx."""


class NotADraftError(ClientMessageError):
    pass


class NoRecipientsError(ClientMessageError):
    pass


class InvoiceAlreadyPaidError(ClientMessageError):
    pass


def _opted_in(contact: ClientContact, kind: str) -> bool:
    if kind == ClientMessage.KIND_PAYMENT_REMINDER:
        return contact.receive_payment_reminders
    return contact.receive_case_updates


def eligible_contacts(message: ClientMessage) -> list[ClientContact]:
    """Contacts on the message's case who may receive this kind of email."""
    contacts = (
        ClientContact.objects.filter(case_id=message.case_id)
        .exclude(email__isnull=True)
        .exclude(email="")
        .order_by("-is_billing_contact", "name", "id")
    )
    return [c for c in contacts if _opted_in(c, message.kind)]


def set_recipients(message: ClientMessage, contact_ids: list[int]) -> ClientMessage:
    """Choose which of the case's eligible contacts the draft goes to."""
    if message.status != ClientMessage.STATUS_DRAFT:
        raise NotADraftError("Only a draft can be edited.")
    eligible = {c.id: c for c in eligible_contacts(message)}
    unknown = [cid for cid in contact_ids if cid not in eligible]
    if unknown:
        raise ClientMessageError(
            "Recipients must be contacts on this case with an email address who "
            "haven't opted out of these emails."
        )
    message.recipients = [
        {"contact_id": c.id, "name": c.name, "email": c.email}
        for cid in dict.fromkeys(contact_ids)
        for c in [eligible[cid]]
    ]
    message.edited_by_user = True
    message.save(update_fields=["recipients", "edited_by_user", "updated_at"])
    return message


def _current_recipients(message: ClientMessage) -> list[dict]:
    """The draft's recipients re-checked NOW: a contact deleted, emptied of
    its email, or opted out since the draft was written is dropped."""
    eligible = {c.id: c for c in eligible_contacts(message)}
    current = []
    for recipient in message.recipients or []:
        contact = eligible.get(recipient.get("contact_id"))
        if contact is not None:
            current.append({"contact_id": contact.id, "name": contact.name, "email": contact.email})
    return current


def send_client_message(message: ClientMessage, *, user) -> dict:
    """Send (or log, with no mail credentials) one draft.

    Returns the same shape as the invoice send: {"sent", "recipients",
    "detail", "missing_env_vars", "required_env_vars"}.
    """
    if message.status != ClientMessage.STATUS_DRAFT:
        raise NotADraftError(f"This message is already {message.get_status_display().lower()}.")

    fee = message.fee
    if message.kind == ClientMessage.KIND_PAYMENT_REMINDER and fee is not None:
        fee.refresh_from_db(fields=["status"])
        if fee.status != AppearanceFee.STATUS_INVOICED:
            message.status = ClientMessage.STATUS_DISCARDED
            message.discard_reason = "Invoice is no longer awaiting payment."
            message.save(update_fields=["status", "discard_reason", "updated_at"])
            raise InvoiceAlreadyPaidError(
                "This invoice has been marked paid, so the reminder was discarded instead of sent."
            )

    recipients = _current_recipients(message)
    if not recipients:
        raise NoRecipientsError(
            "No one to send this to: add an email address to a client contact on this "
            "case (or check they haven't opted out), then choose them as a recipient."
        )

    profile = get_or_create_profile(message.owner)
    email_delivery.require_contact_email(profile, what="client emails")
    email_delivery.require_advocate_name(profile)

    attachments = []
    if (
        message.kind == ClientMessage.KIND_PAYMENT_REMINDER
        and fee is not None
        and fee.invoice_pdf_path
        and email_delivery.email_is_configured()
    ):
        with default_storage.open(fee.invoice_pdf_path, "rb") as handle:
            attachments.append(
                email_delivery.Attachment(f"{fee.invoice_number}.pdf", handle.read())
            )

    result = email_delivery.deliver_email(
        owner=message.owner,
        profile=profile,
        to=[r["email"] for r in recipients],
        subject=message.subject,
        body=message.body,
        kind=message.kind,
        sent_by=user,
        attachments=attachments,
        case=message.case,
        message=message,
        fee=fee,
        log_context=f"client message {message.id}, case {message.case.case_number}",
    )

    message.status = (
        ClientMessage.STATUS_SENT if result.delivered else ClientMessage.STATUS_LOGGED
    )
    message.recipients = recipients
    message.sent_at = timezone.now()
    message.send_result = {
        "delivery": result.delivery,
        "to": result.to,
        "missing_env_vars": result.missing_env_vars,
        "sent_by": user.id if user is not None else None,
    }
    message.save(update_fields=["status", "recipients", "sent_at", "send_result", "updated_at"])

    emails = ", ".join(result.to)
    if result.delivered:
        detail = f"Sent to {emails}."
    else:
        detail = (
            "Email is not configured on this server, so the message was logged "
            "instead of sent. Set the environment variables listed in "
            "missing_env_vars and try again."
        )
    return {
        "sent": result.delivered,
        "recipients": result.to,
        "detail": detail,
        "missing_env_vars": result.missing_env_vars,
        "required_env_vars": result.required_env_vars,
    }


_SIGN_OFF = "Regards,\n"


def resign_open_drafts(owner) -> int:
    """Re-sign the owner's untouched drafts after their name or firm
    changed in Settings, so a draft written before "Your Name" was filled
    in doesn't go out under the old signature. Only the lines after the
    last "Regards," change; an edited draft is the advocate's own text and
    is never touched. Returns the number of drafts re-signed."""
    from . import compose

    new_signature = compose.signature(get_or_create_profile(owner))
    count = 0
    drafts = ClientMessage.objects.filter(
        owner=owner, status=ClientMessage.STATUS_DRAFT, edited_by_user=False
    )
    for message in drafts:
        head, sign_off, _old = message.body.rpartition(_SIGN_OFF)
        if not sign_off:
            continue
        body = f"{head}{sign_off}{new_signature}\n"
        if body != message.body:
            message.body = body
            message.save(update_fields=["body", "updated_at"])
            count += 1
    return count


def discard_client_message(message: ClientMessage, *, reason: str = "Discarded by the advocate.") -> ClientMessage:
    """Kept, not deleted: the row's dedup_key is what stops the same draft
    being generated again on the next run."""
    if message.status != ClientMessage.STATUS_DRAFT:
        raise NotADraftError("Only a draft can be discarded.")
    message.status = ClientMessage.STATUS_DISCARDED
    message.discard_reason = reason[:255]
    message.save(update_fields=["status", "discard_reason", "updated_at"])
    return message
