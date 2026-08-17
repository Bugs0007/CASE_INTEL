"""Appearance-fee invoicing: number allocation, PDF rendering, delivery
to the client's billing contact, and the PENDING -> INVOICED -> PAID
lifecycle.

This module owns the fee status transitions. Views call these functions
rather than assigning `fee.status` themselves, so the rules ("you cannot
mark a fee paid before it has been invoiced", "an issued invoice number
is never reused") hold no matter which entry point is used.

PDF library: fpdf2. Chosen over WeasyPrint because it is pure Python --
WeasyPrint needs GTK/Pango/Cairo as SYSTEM packages, which would mean an
apt line in deploy/provision.sh and a GTK install on every Windows dev
box. fpdf2 renders identically on Windows and the Linux EC2 host with
nothing but the wheel.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from email.utils import formataddr

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.mail import EmailMessage, get_connection
from django.db import transaction
from django.utils import timezone

from core.models import AdvocateProfile, AppearanceFee, ClientContact

logger = logging.getLogger(__name__)

# Env vars that must be present for invoice email to actually send. Kept
# here (not only in settings.py) so the API can tell the user exactly
# what to set -- see EMAIL_ENV_VARS_REQUIRED in the send result payload.
EMAIL_ENV_VARS_REQUIRED = [
    "RESEND_API_KEY",
    "DEFAULT_FROM_EMAIL",
]


class InvoiceError(Exception):
    """Base for invoicing failures that should surface as a 4xx, not a 500."""


class InvalidFeeTransitionError(InvoiceError):
    """Raised when a status change isn't legal from the fee's current state."""


class MissingBillingContactError(InvoiceError):
    """Raised when a send is attempted for a case with no billing contact
    (or one with no email address)."""


class NotInvoicedError(InvoiceError):
    """Raised when an action needs an invoice PDF that doesn't exist yet."""


# ---------------------------------------------------------------------------
# Profile + invoice numbering
# ---------------------------------------------------------------------------


def get_or_create_profile(user) -> AdvocateProfile:
    """The advocate's billing profile, created empty on first touch.

    Auto-creating means invoice generation never fails just because the
    user hasn't filled the letterhead form in yet -- they get an invoice
    with blank letterhead fields, which is recoverable, instead of an
    error.
    """
    profile, _ = AdvocateProfile.objects.get_or_create(owner=user)
    return profile


def allocate_invoice_number(user) -> tuple[str, int]:
    """Issue the next invoice number for `user`. Returns (number, sequence).

    The counter is per-advocate: user A's numbering is completely
    independent of user B's, and both legitimately have an INV-0001.

    Concurrency: the profile row is locked with select_for_update() for
    the read-increment-write, so two simultaneous generate calls by the
    SAME advocate serialise and get 0001 and 0002 rather than both
    reading 0 and both minting 0001. Different advocates lock different
    rows and never block each other.

    Must be called inside an atomic block (select_for_update requires
    one); generate_invoice() provides it.
    """
    # get_or_create first -- select_for_update can only lock a row that
    # already exists.
    get_or_create_profile(user)
    profile = AdvocateProfile.objects.select_for_update().get(owner=user)
    profile.last_invoice_sequence += 1
    sequence = profile.last_invoice_sequence
    profile.save(update_fields=["last_invoice_sequence", "updated_at"])

    prefix = (profile.invoice_prefix or "INV").strip()
    return f"{prefix}-{sequence:04d}", sequence


# ---------------------------------------------------------------------------
# PDF rendering
# ---------------------------------------------------------------------------

# fpdf2's built-in (core) fonts are Latin-1 only and raise on characters
# outside it. Indian party names routinely carry characters that aren't
# (curly quotes, en-dashes, Devanagari). Substituting instead of raising
# keeps a rendering detail from failing the whole invoice -- the number,
# amount and case reference, which is what the document is actually for,
# are unaffected.
def _pdf_safe(text) -> str:
    if text is None:
        return ""
    return str(text).encode("latin-1", "replace").decode("latin-1")


def _money(amount: Decimal) -> str:
    """Rs. 1234.50 -- 'Rs.' not the rupee sign, which is not Latin-1 and
    would render as '?' under the core fonts (see _pdf_safe)."""
    return f"Rs. {Decimal(amount):,.2f}"


def render_invoice_pdf(fee: AppearanceFee, profile: AdvocateProfile) -> bytes:
    """Render the invoice for `fee` and return the PDF bytes.

    Pure function of (fee, profile) -- writes nothing. The caller decides
    where the bytes go, which keeps this directly testable.
    """
    from fpdf import FPDF

    hearing = fee.hearing
    case = hearing.case

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=20)
    pdf.add_page()

    # --- Letterhead ---
    pdf.set_font("Helvetica", "B", 18)
    pdf.cell(0, 10, _pdf_safe(profile.letterhead_name or "Advocate"), new_x="LMARGIN", new_y="NEXT")

    pdf.set_font("Helvetica", "", 10)
    for line in (profile.address or "").splitlines():
        if line.strip():
            pdf.cell(0, 5, _pdf_safe(line.strip()), new_x="LMARGIN", new_y="NEXT")
    if profile.bar_registration_number:
        pdf.cell(
            0,
            5,
            _pdf_safe(f"Bar Registration No.: {profile.bar_registration_number}"),
            new_x="LMARGIN",
            new_y="NEXT",
        )

    pdf.ln(4)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(6)

    # --- Invoice heading ---
    pdf.set_font("Helvetica", "B", 14)
    pdf.cell(0, 8, "INVOICE", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(0, 5, _pdf_safe(f"Invoice No.: {fee.invoice_number}"), new_x="LMARGIN", new_y="NEXT")
    issued = fee.invoiced_at or timezone.now()
    pdf.cell(
        0,
        5,
        _pdf_safe(f"Invoice Date: {timezone.localtime(issued).strftime('%d %b %Y')}"),
        new_x="LMARGIN",
        new_y="NEXT",
    )
    pdf.ln(4)

    # --- Case / hearing detail table ---
    rows = [
        ("Case Title", case.title or ""),
        ("Case Number", case.case_number or ""),
        ("CNR Number", case.cnr_number or "Not available"),
        ("Client", case.client_name or ""),
        ("Hearing Date", timezone.localtime(hearing.hearing_date).strftime("%d %b %Y")),
        ("Court", hearing.location or "Not recorded"),
    ]
    if hearing.judge:
        rows.append(("Judge", hearing.judge))
    if hearing.purpose:
        rows.append(("Purpose", hearing.purpose))

    label_w = 45.0
    value_w = pdf.w - pdf.l_margin - pdf.r_margin - label_w
    for label, value in rows:
        pdf.set_font("Helvetica", "B", 10)
        pdf.cell(label_w, 7, _pdf_safe(label), border=1)
        pdf.set_font("Helvetica", "", 10)
        # multi_cell so a long case title wraps instead of overflowing
        # the page; it also advances to the next line for us.
        pdf.multi_cell(value_w, 7, _pdf_safe(value), border=1, new_x="LMARGIN", new_y="NEXT")

    pdf.ln(6)

    # --- Amount ---
    pdf.set_font("Helvetica", "B", 10)
    pdf.cell(label_w, 9, "Appearance Fee", border=1)
    pdf.set_font("Helvetica", "B", 12)
    pdf.cell(value_w, 9, _pdf_safe(_money(fee.amount)), border=1, align="R",
             new_x="LMARGIN", new_y="NEXT")

    if fee.notes:
        pdf.ln(6)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(0, 5, _pdf_safe(fee.notes))

    pdf.ln(10)
    pdf.set_font("Helvetica", "I", 8)
    pdf.multi_cell(
        0, 4, _pdf_safe("This is a computer-generated invoice issued via Case Intel.")
    )

    # fpdf2 >= 2.7 returns a bytearray from output(); bytes() for a stable
    # type going into storage and email attachments.
    return bytes(pdf.output())


def _invoice_storage_key(fee: AppearanceFee) -> str:
    safe_number = fee.invoice_number.replace("/", "-").replace("\\", "-")
    return f"invoices/{fee.owner_id}/{safe_number}.pdf"


# ---------------------------------------------------------------------------
# Lifecycle actions
# ---------------------------------------------------------------------------


def generate_invoice(fee: AppearanceFee) -> AppearanceFee:
    """Render (or re-render) this fee's invoice PDF and move it to INVOICED.

    First generation allocates a fresh per-user invoice number. A repeat
    call re-renders under the EXISTING number -- deliberately not a new
    one, so a number already sent to a client keeps meaning the same
    document, and the counter isn't burned by a re-download. A PAID fee
    can be re-rendered (clients ask for copies) but is not moved back to
    INVOICED.
    """
    with transaction.atomic():
        # Lock the fee row too: without it, two concurrent generate calls
        # on a not-yet-invoiced fee could both see invoice_number == ""
        # and each allocate a separate number for the same fee.
        fee = AppearanceFee.objects.select_for_update().select_related(
            "hearing__case"
        ).get(pk=fee.pk)

        profile = get_or_create_profile(fee.owner)

        first_issue = not fee.invoice_number
        if first_issue:
            fee.invoice_number, fee.invoice_sequence = allocate_invoice_number(fee.owner)
            fee.invoiced_at = timezone.now()

        pdf_bytes = render_invoice_pdf(fee, profile)

        key = _invoice_storage_key(fee)
        # Overwrite on re-render rather than accumulating INV-0001_x1.pdf
        # copies: one invoice number, one file.
        if default_storage.exists(key):
            default_storage.delete(key)
        fee.invoice_pdf_path = default_storage.save(key, ContentFile(pdf_bytes))

        # PAID is terminal -- re-rendering a receipt must not un-pay it.
        if fee.status == AppearanceFee.STATUS_PENDING:
            fee.status = AppearanceFee.STATUS_INVOICED

        fee.save(
            update_fields=[
                "invoice_number",
                "invoice_sequence",
                "invoice_pdf_path",
                "invoiced_at",
                "status",
                "updated_at",
            ]
        )

    logger.info(
        "Invoice %s %s for fee %d (owner=%d, status=%s)",
        fee.invoice_number,
        "generated" if first_issue else "re-rendered",
        fee.id,
        fee.owner_id,
        fee.status,
    )
    return fee


def mark_paid(fee: AppearanceFee) -> AppearanceFee:
    """PENDING -> (not allowed); INVOICED -> PAID; PAID -> (not allowed).

    Requiring INVOICED first is the point: "paid" against a fee that was
    never billed is a bookkeeping hole, so the caller has to generate the
    invoice first.
    """
    if fee.status == AppearanceFee.STATUS_PENDING:
        raise InvalidFeeTransitionError(
            "This fee has not been invoiced yet. Generate the invoice before marking it paid."
        )
    if fee.status == AppearanceFee.STATUS_PAID:
        raise InvalidFeeTransitionError("This fee is already marked paid.")

    fee.status = AppearanceFee.STATUS_PAID
    fee.paid_at = timezone.now()
    fee.save(update_fields=["status", "paid_at", "updated_at"])
    logger.info("Fee %d marked paid (invoice %s)", fee.id, fee.invoice_number or "-")
    return fee


def get_billing_contact(case) -> ClientContact:
    """The case's billing contact, or raise MissingBillingContactError.

    A contact flagged is_billing_contact but with no email is treated as
    missing: there is nothing to send to, and failing here with a clear
    message beats a downstream SMTP error.
    """
    contact = ClientContact.objects.filter(case=case, is_billing_contact=True).first()
    if contact is None:
        raise MissingBillingContactError(
            "This case has no billing contact. Mark one of its client contacts as the billing contact first."
        )
    if not contact.email:
        raise MissingBillingContactError(
            f"Billing contact '{contact.name}' has no email address on file."
        )
    return contact


def email_is_configured() -> bool:
    """True when a real RESEND_API_KEY is present (see settings.py).

    settings.INVOICE_EMAIL_CONFIGURED is computed once at startup from
    the env; read through this helper so tests can patch one place.
    """
    return bool(getattr(settings, "INVOICE_EMAIL_CONFIGURED", False))


def send_invoice(fee: AppearanceFee) -> dict:
    """Email the invoice PDF to the case's billing contact.

    When SMTP is not configured this does NOT fail -- it logs the full
    delivery intent (recipient, invoice number, amount) at WARNING and
    returns sent=False with the exact env vars that are missing, so the
    feature is usable end-to-end on a box with no mail credentials. The
    fee is recorded as send_status='logged', never 'sent', so a logged
    delivery can't later be mistaken for a real one.

    Returns:
        {"sent": bool, "recipient": str, "detail": str,
         "missing_env_vars": list[str], "required_env_vars": list[str]}
    """
    if not fee.invoice_number or not fee.invoice_pdf_path:
        raise NotInvoicedError("Generate the invoice before sending it.")

    contact = get_billing_contact(fee.hearing.case)
    profile = get_or_create_profile(fee.owner)
    subject = f"Invoice {fee.invoice_number} - {fee.hearing.case.title}"
    body = (
        f"Dear {contact.name},\n\n"
        f"Please find attached invoice {fee.invoice_number} for the appearance on "
        f"{timezone.localtime(fee.hearing.hearing_date).strftime('%d %b %Y')} "
        f"in {fee.hearing.case.title} ({fee.hearing.case.case_number}).\n\n"
        f"Amount due: {_money(fee.amount)}\n\n"
        f"Regards,\n"
        f"{profile.letterhead_name or 'Your advocate'}\n"
    )

    if not email_is_configured():
        logger.warning(
            "EMAIL NOT CONFIGURED -- invoice %s NOT sent. Would have emailed %s <%s>: "
            "%s (amount %s, case %s, hearing %s). Set %s in the environment to enable delivery.",
            fee.invoice_number,
            contact.name,
            contact.email,
            subject,
            _money(fee.amount),
            fee.hearing.case.case_number,
            fee.hearing_id,
            ", ".join(EMAIL_ENV_VARS_REQUIRED),
        )
        fee.sent_at = timezone.now()
        fee.sent_to_email = contact.email
        fee.send_status = AppearanceFee.SEND_LOGGED
        fee.save(update_fields=["sent_at", "sent_to_email", "send_status", "updated_at"])
        return {
            "sent": False,
            "recipient": contact.email,
            "detail": (
                "Email is not configured on this server, so the invoice was logged "
                "instead of sent. Set the environment variables listed in "
                "missing_env_vars and try again."
            ),
            "missing_env_vars": _missing_email_env_vars(),
            "required_env_vars": list(EMAIL_ENV_VARS_REQUIRED),
        }

    with default_storage.open(fee.invoice_pdf_path, "rb") as handle:
        pdf_bytes = handle.read()

    # Display name is the advocate's letterhead, address is the fixed
    # server sender (must be on a Resend-verified domain -- see
    # DEFAULT_FROM_EMAIL in settings.py). Reply-To is the advocate's own
    # account email so a client hitting "reply" reaches the lawyer
    # directly rather than the shared billing@ inbox; omitted entirely
    # when the account has none on file (email was optional at signup).
    from_email = formataddr((profile.letterhead_name or "Advocate", settings.DEFAULT_FROM_EMAIL))
    reply_to = [fee.owner.email] if fee.owner.email else []

    message = EmailMessage(
        subject=subject,
        body=body,
        from_email=from_email,
        to=[contact.email],
        reply_to=reply_to,
        connection=get_connection(),
    )
    message.attach(f"{fee.invoice_number}.pdf", pdf_bytes, "application/pdf")
    message.send(fail_silently=False)

    fee.sent_at = timezone.now()
    fee.sent_to_email = contact.email
    fee.send_status = AppearanceFee.SEND_SENT
    fee.save(update_fields=["sent_at", "sent_to_email", "send_status", "updated_at"])

    logger.info("Invoice %s emailed to %s", fee.invoice_number, contact.email)
    return {
        "sent": True,
        "recipient": contact.email,
        "detail": f"Invoice {fee.invoice_number} sent to {contact.email}.",
        "missing_env_vars": [],
        "required_env_vars": [],
    }


def _missing_email_env_vars() -> list[str]:
    """The mail env vars that still need a value for real delivery.

    Derived from email_is_configured() (settings.INVOICE_EMAIL_CONFIGURED)
    rather than re-inspecting settings.RESEND_API_KEY directly -- the two
    normally agree, but tests patch INVOICE_EMAIL_CONFIGURED directly (see
    email_is_configured()'s docstring), and this needs to stay consistent
    with that single patch point rather than independently re-deriving
    from the env var underneath it, which would go stale the moment a
    real key is actually present in the environment a test runs in.

    DEFAULT_FROM_EMAIL has a working default in settings.py, so it's never
    blank and would never appear here -- it's carried in
    EMAIL_ENV_VARS_REQUIRED instead, which the API returns alongside this
    as the full checklist.
    """
    return [] if email_is_configured() else ["RESEND_API_KEY"]
