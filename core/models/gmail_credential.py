"""
Gmail OAuth credential storage.
"""

from django.db import models

from .mixins import OwnedModel


class GmailCredential(OwnedModel):
    """Stores Gmail OAuth tokens."""

    email_address = models.EmailField(unique=True)
    access_token = models.TextField()
    refresh_token = models.TextField()
    token_expiry = models.DateTimeField()
    scope = models.TextField(
        default="https://www.googleapis.com/auth/gmail.readonly"
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "gmail_credentials"

    def __str__(self):
        return self.email_address
