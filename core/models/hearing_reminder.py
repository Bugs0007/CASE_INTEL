from django.db import models

from .mixins import OwnedModel


class HearingReminder(OwnedModel):
    """One "your hearing is in N days" email decision for one hearing.

    The audit trail AND the dedup record for core/services/notifications/
    hearing_reminders.py: a hearing is reminded at most once per `lead_days`
    (2 = two days before, 1 = the day before). `hearing_date` snapshots the
    date the reminder was for, so a hearing whose date is later edited
    reminds again for the new date instead of being treated as done.

    `sent` and `logged` (email isn't configured on this box) are final;
    `failed` is retried on the next run, up to a small attempt cap.
    """

    DELIVERY_SENT = "sent"
    DELIVERY_LOGGED = "logged"
    DELIVERY_FAILED = "failed"

    DELIVERY_CHOICES = [
        (DELIVERY_SENT, "Sent"),
        (DELIVERY_LOGGED, "Logged only (email not configured)"),
        (DELIVERY_FAILED, "Failed"),
    ]

    LEAD_CHOICES = [(1, "1 day before"), (2, "2 days before")]

    hearing = models.ForeignKey(
        "core.Hearing", on_delete=models.CASCADE, related_name="reminders"
    )
    hearing_date = models.DateTimeField()
    lead_days = models.PositiveSmallIntegerField(choices=LEAD_CHOICES)
    recipient = models.CharField(max_length=254, blank=True, default="")
    delivery = models.CharField(max_length=10, choices=DELIVERY_CHOICES)
    # A short reason, never a stack trace.
    error = models.CharField(max_length=255, blank=True, default="")
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "hearing_reminders"
        constraints = [
            models.UniqueConstraint(
                fields=["hearing", "hearing_date", "lead_days"],
                name="unique_hearing_reminder_per_date_and_lead",
            )
        ]

    def __str__(self):
        return f"Reminder ({self.lead_days}d) for hearing {self.hearing_id}: {self.delivery}"
