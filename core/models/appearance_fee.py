from django.db import models

from .mixins import OwnedModel


class AppearanceFee(OwnedModel):
    """What the advocate charges for appearing at one hearing, and where
    that charge has got to: PENDING -> INVOICED -> PAID.

    One fee per hearing (OneToOne). The lifecycle is deliberately
    forward-only and is enforced in core/services/invoice_service.py, not
    here -- the model stores state, the service owns the legal
    transitions, so every caller (API, admin, management command) goes
    through the same rules.

    `invoice_number` is assigned once, at generation, from the owner's
    AdvocateProfile counter and never reissued: regenerating the PDF for
    an already-invoiced fee re-renders it under the SAME number, so a
    number that has been sent to a client can't silently come to mean a
    different document.
    """

    STATUS_PENDING = "pending"
    STATUS_INVOICED = "invoiced"
    STATUS_PAID = "paid"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_INVOICED, "Invoiced"),
        (STATUS_PAID, "Paid"),
    ]

    SEND_NOT_SENT = "not_sent"
    SEND_SENT = "sent"
    SEND_LOGGED = "logged"

    SEND_STATUS_CHOICES = [
        (SEND_NOT_SENT, "Not sent"),
        (SEND_SENT, "Sent"),
        # "Logged" is the no-SMTP-configured path: the invoice was
        # rendered and its delivery recorded in the log, but no mail
        # actually left the box. Kept distinct from "sent" so this never
        # reads as a real delivery.
        (SEND_LOGGED, "Logged only (email not configured)"),
    ]

    hearing = models.OneToOneField(
        "core.Hearing", on_delete=models.CASCADE, related_name="appearance_fee"
    )
    amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    invoice_number = models.CharField(max_length=64, blank=True, default="")
    invoice_sequence = models.PositiveIntegerField(blank=True, null=True)
    # Storage-relative key (e.g. "invoices/INV-0001.pdf"), never an
    # absolute path -- same convention as Document.file_path, so local
    # disk and S3 both work without touching this code.
    invoice_pdf_path = models.CharField(max_length=500, blank=True, default="")

    invoiced_at = models.DateTimeField(blank=True, null=True)
    paid_at = models.DateTimeField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    sent_to_email = models.EmailField(blank=True, default="")
    send_status = models.CharField(
        max_length=20, choices=SEND_STATUS_CHOICES, default=SEND_NOT_SENT
    )

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "appearance_fees"
        ordering = ["-created_at"]
        constraints = [
            # Invoice numbers are unique per advocate, not globally --
            # two advocates both having an "INV-0001" is correct and
            # expected. Partial (invoice_number != "") so the many
            # not-yet-invoiced rows, which all share the empty default,
            # don't collide with each other.
            models.UniqueConstraint(
                fields=["owner", "invoice_number"],
                condition=~models.Q(invoice_number=""),
                name="unique_invoice_number_per_owner",
            )
        ]

    def __str__(self):
        label = self.invoice_number or "no invoice"
        return f"Fee {self.amount} [{self.status}] hearing={self.hearing_id} ({label})"
