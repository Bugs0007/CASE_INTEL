from django.conf import settings
from django.db import models

from .mixins import OwnedModel


class ClientMessage(OwnedModel):
    """An email to a client, from draft to delivery.

    Two kinds today, both created by the system and never sent without the
    advocate pressing Send:
      - case_update: "your matter was heard on X, next date Y" after an
        order syncs or a hearing date changes (core/services/client_updates/)
      - payment_reminder: a follow-up on an invoice still unpaid after the
        advocate's reminder interval (manage.py draft_payment_reminders)

    `dedup_key` makes generation idempotent: one row per hearing event /
    per reminder number, however many times the generator runs. A draft the
    advocate has edited, sent or discarded is never rewritten by a later
    run -- same contract as upsert_system_task for Tasks.
    """

    KIND_CASE_UPDATE = "case_update"
    KIND_PAYMENT_REMINDER = "payment_reminder"

    KIND_CHOICES = [
        (KIND_CASE_UPDATE, "Case update"),
        (KIND_PAYMENT_REMINDER, "Payment reminder"),
    ]

    STATUS_DRAFT = "draft"
    STATUS_SENT = "sent"
    STATUS_LOGGED = "logged"
    STATUS_DISCARDED = "discarded"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_SENT, "Sent"),
        # Same meaning as AppearanceFee.SEND_LOGGED: recorded in the
        # server log because email isn't configured -- never a delivery.
        (STATUS_LOGGED, "Logged only (email not configured)"),
        (STATUS_DISCARDED, "Discarded"),
    ]

    id = models.BigAutoField(primary_key=True)
    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, related_name="client_messages"
    )
    hearing = models.ForeignKey(
        "core.Hearing",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="client_messages",
    )
    court_order = models.ForeignKey(
        "core.CourtOrder",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="client_messages",
    )
    fee = models.ForeignKey(
        "core.AppearanceFee",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
        related_name="client_messages",
    )
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    dedup_key = models.CharField(max_length=120)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_DRAFT)
    subject = models.CharField(max_length=255)
    body = models.TextField()
    # Snapshot at draft time: [{"contact_id", "name", "email"}]. Re-checked
    # against opt-outs at send time, so a contact who opts out after the
    # draft was written is still skipped.
    recipients = models.JSONField(blank=True, default=list)
    edited_by_user = models.BooleanField(default=False)
    reminder_number = models.PositiveSmallIntegerField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    send_result = models.JSONField(blank=True, null=True)
    discard_reason = models.CharField(max_length=255, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "client_messages"
        ordering = ["-created_at", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "dedup_key"], name="unique_client_message_per_owner"
            )
        ]
        indexes = [models.Index(fields=["owner", "status"])]

    @property
    def is_open(self) -> bool:
        return self.status == self.STATUS_DRAFT

    def __str__(self):
        return f"{self.get_kind_display()} [{self.status}] case={self.case_id}"


class SentMessage(OwnedModel):
    """Append-only audit record of every client-facing email.

    One row per delivery attempt that left the app -- really sent, or
    logged because email isn't configured. Written by
    core/services/email_delivery.py for invoices, case updates and payment
    reminders alike. The body itself is not kept here (it lives on the
    ClientMessage / invoice), only its SHA-256, so the record proves what
    was sent without becoming a second copy of client correspondence.
    """

    KIND_INVOICE = "invoice"
    KIND_CHOICES = [
        (ClientMessage.KIND_CASE_UPDATE, "Case update"),
        (ClientMessage.KIND_PAYMENT_REMINDER, "Payment reminder"),
        (KIND_INVOICE, "Invoice"),
    ]

    DELIVERY_SENT = "sent"
    DELIVERY_LOGGED = "logged"
    DELIVERY_CHOICES = [
        (DELIVERY_SENT, "Sent"),
        (DELIVERY_LOGGED, "Logged only (email not configured)"),
    ]

    id = models.BigAutoField(primary_key=True)
    sent_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        blank=True,
        null=True,
        related_name="+",
        help_text="Who pressed Send. Null only for a system-initiated send.",
    )
    sent_at = models.DateTimeField(auto_now_add=True)
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    delivery = models.CharField(max_length=20, choices=DELIVERY_CHOICES)
    to_emails = models.JSONField(default=list)
    cc_emails = models.JSONField(blank=True, default=list)
    subject = models.CharField(max_length=255)
    body_sha256 = models.CharField(max_length=64)
    case = models.ForeignKey(
        "core.Case",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="sent_messages",
    )
    message = models.ForeignKey(
        ClientMessage,
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="deliveries",
    )
    fee = models.ForeignKey(
        "core.AppearanceFee",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="deliveries",
    )

    class Meta:
        db_table = "sent_messages"
        ordering = ["-sent_at", "-id"]

    def __str__(self):
        return f"{self.get_kind_display()} {self.delivery} to {', '.join(self.to_emails)}"
