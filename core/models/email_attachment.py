from django.db import models

from .mixins import OwnedModel


class EmailAttachment(OwnedModel):
    email = models.ForeignKey(
        "core.Email", on_delete=models.CASCADE, related_name="attachments"
    )
    filename = models.CharField(max_length=255)
    file_path = models.CharField(max_length=500, blank=True, null=True)
    gmail_attachment_id = models.CharField(max_length=100, blank=True, null=True)
    document = models.ForeignKey(
        "core.Document", on_delete=models.SET_NULL, blank=True, null=True,
        related_name="email_attachments"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "email_attachments"

    def __str__(self):
        return self.filename
