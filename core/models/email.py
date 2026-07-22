from django.db import models

from .mixins import OwnedModel


class Email(OwnedModel):
    gmail_message_id = models.CharField(max_length=100, unique=True)
    gmail_thread_id = models.CharField(max_length=100, blank=True, null=True)
    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, blank=True, null=True, related_name="emails"
    )
    subject = models.TextField(blank=True, null=True)
    sender = models.CharField(max_length=255, blank=True, null=True)
    recipients = models.TextField(blank=True, null=True)
    sent_at = models.DateTimeField(blank=True, null=True)
    body_text = models.TextField(blank=True, null=True)
    has_attachments = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "emails"
        ordering = ["-sent_at"]

    def __str__(self):
        return self.subject or f"Email {self.gmail_message_id}"
