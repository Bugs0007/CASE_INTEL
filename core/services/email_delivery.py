"""The one path every client-facing email takes: invoices, case updates,
payment reminders.

Extracted from invoice_service.send_invoice so all three kinds behave
identically:
  - the advocate's AdvocateProfile.contact_email is required (it becomes
    Reply-To and Cc, so a client's reply reaches the lawyer) -- a hard gate,
    never a silent degrade;
  - when Resend isn't configured, nothing is sent: the delivery intent is
    logged at WARNING and the result says delivery="logged" with the env
    vars still missing, so the caller records "logged", never "sent";
  - every delivery, real or logged, leaves an append-only SentMessage row
    (who, when, to whom, subject, body hash).

Callers own their own domain state (fee.send_status, message.status); this
module only delivers and audits.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass, field
from email.utils import formataddr

from django.conf import settings
from django.core.mail import EmailMessage, get_connection

from core.models import AdvocateProfile, SentMessage

logger = logging.getLogger(__name__)

# Env vars that must be present for email to actually send. Returned to
# the caller so the UI can say exactly what to set.
EMAIL_ENV_VARS_REQUIRED = [
    "RESEND_API_KEY",
    "DEFAULT_FROM_EMAIL",
]


class DeliveryError(Exception):
    """Base for delivery failures that should surface as a 4xx."""


class MissingContactEmailError(DeliveryError):
    """The sending advocate has no contact email set. A client-facing email
    with no way to reply to the actual advocate is a bad default, so this
    blocks the send entirely rather than degrading to no Reply-To/Cc."""


@dataclass
class Attachment:
    filename: str
    content: bytes
    mimetype: str = "application/pdf"


@dataclass
class DeliveryResult:
    delivered: bool
    delivery: str  # SentMessage.DELIVERY_SENT or DELIVERY_LOGGED
    to: list[str]
    audit: SentMessage
    missing_env_vars: list[str] = field(default_factory=list)
    required_env_vars: list[str] = field(default_factory=list)


def email_is_configured() -> bool:
    """True when a real RESEND_API_KEY is present (see settings.py).

    settings.INVOICE_EMAIL_CONFIGURED is computed once at startup from the
    env; read through this helper so tests can patch one place.
    """
    return bool(getattr(settings, "INVOICE_EMAIL_CONFIGURED", False))


def missing_email_env_vars() -> list[str]:
    """The mail env vars that still need a value for real delivery.

    Derived from email_is_configured() rather than re-inspecting
    settings.RESEND_API_KEY directly -- tests patch INVOICE_EMAIL_CONFIGURED,
    and this has to agree with that single patch point. DEFAULT_FROM_EMAIL
    has a working default in settings.py, so it is carried in
    EMAIL_ENV_VARS_REQUIRED (the full checklist) instead.
    """
    return [] if email_is_configured() else ["RESEND_API_KEY"]


def require_contact_email(profile: AdvocateProfile, *, what: str = "emails") -> str:
    if not profile.contact_email:
        raise MissingContactEmailError(
            f"Set your contact email in Settings before sending {what}, "
            "so the client can reply directly to you."
        )
    return profile.contact_email


def body_sha256(body: str) -> str:
    return hashlib.sha256((body or "").encode("utf-8")).hexdigest()


def deliver_email(
    *,
    owner,
    profile: AdvocateProfile,
    to: list[str],
    subject: str,
    body: str,
    kind: str,
    sent_by=None,
    attachments: list[Attachment] | None = None,
    case=None,
    message=None,
    fee=None,
    log_context: str = "",
) -> DeliveryResult:
    """Send (or log) one client email and write its SentMessage row.

    `profile.contact_email` must already be set -- call
    require_contact_email() first, before any caller-side state changes,
    so a blocked send leaves nothing behind.
    """
    reply_to_email = require_contact_email(profile)
    to = [address for address in to if address]
    if not to:
        raise DeliveryError("There is no recipient email address to send to.")

    if not email_is_configured():
        logger.warning(
            "EMAIL NOT CONFIGURED -- %s NOT sent. Would have emailed %s: %s%s. "
            "Set %s in the environment to enable delivery.",
            kind,
            ", ".join(to),
            subject,
            f" ({log_context})" if log_context else "",
            ", ".join(EMAIL_ENV_VARS_REQUIRED),
        )
        audit = _audit(
            owner=owner,
            sent_by=sent_by,
            kind=kind,
            delivery=SentMessage.DELIVERY_LOGGED,
            to=to,
            cc=[],
            subject=subject,
            body=body,
            case=case,
            message=message,
            fee=fee,
        )
        return DeliveryResult(
            delivered=False,
            delivery=SentMessage.DELIVERY_LOGGED,
            to=to,
            audit=audit,
            missing_env_vars=missing_email_env_vars(),
            required_env_vars=list(EMAIL_ENV_VARS_REQUIRED),
        )

    # Display name is the advocate's letterhead, address is the fixed
    # server sender (must be on a Resend-verified domain -- see
    # DEFAULT_FROM_EMAIL in settings.py). Reply-To and Cc use the
    # advocate's own contact email (AdvocateProfile.contact_email, set on
    # the Settings page -- deliberately separate from the User's login
    # email) so a client hitting "reply" reaches the lawyer directly
    # rather than the shared sender inbox, and the advocate keeps a copy
    # of exactly what was sent.
    from_email = formataddr((profile.letterhead_name or "Advocate", settings.DEFAULT_FROM_EMAIL))
    cc = [reply_to_email]

    email = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email,
        to=to,
        cc=cc,
        reply_to=[reply_to_email],
        connection=get_connection(),
    )
    for attachment in attachments or []:
        email.attach(attachment.filename, attachment.content, attachment.mimetype)
    email.send(fail_silently=False)

    audit = _audit(
        owner=owner,
        sent_by=sent_by,
        kind=kind,
        delivery=SentMessage.DELIVERY_SENT,
        to=to,
        cc=cc,
        subject=subject,
        body=body,
        case=case,
        message=message,
        fee=fee,
    )
    logger.info("%s emailed to %s", kind, ", ".join(to))
    return DeliveryResult(
        delivered=True, delivery=SentMessage.DELIVERY_SENT, to=to, audit=audit
    )


def _audit(*, owner, sent_by, kind, delivery, to, cc, subject, body, case, message, fee):
    return SentMessage.objects.create(
        owner=owner,
        sent_by=sent_by,
        kind=kind,
        delivery=delivery,
        to_emails=list(to),
        cc_emails=list(cc),
        subject=subject[:255],
        body_sha256=body_sha256(body),
        case=case,
        message=message,
        fee=fee,
    )
