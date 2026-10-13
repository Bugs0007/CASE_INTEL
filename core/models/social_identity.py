from django.conf import settings
from django.db import models


class SocialIdentity(models.Model):
    """A third-party (today: Google) account linked to a Case Intel user.

    `subject` is the provider's stable, never-reused account id (Google's
    `sub`). Sign-in matches on it, never on email: a Google account can
    change its address, and an address on an existing Case Intel account was
    never verified, so email alone must not grant access to that account.

    Deliberately a plain `user` FK (CASCADE), not OwnedModel's PROTECT owner,
    for the same reason as AuthSession: this is account-level, not case data,
    and deleting a user must take their linked identities with them. Every
    view that reads or writes these scopes by request.user or by the verified
    provider subject (see core/views/google_auth.py).
    """

    PROVIDER_GOOGLE = "google"
    PROVIDER_CHOICES = [(PROVIDER_GOOGLE, "Google")]

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="social_identities"
    )
    provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    subject = models.CharField(max_length=255)
    email = models.EmailField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    last_login_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "social_identities"
        constraints = [
            models.UniqueConstraint(fields=["provider", "subject"], name="uniq_social_provider_subject"),
            models.UniqueConstraint(fields=["user", "provider"], name="uniq_social_user_provider"),
        ]

    def __str__(self):
        return f"{self.user} ({self.provider}: {self.email or self.subject})"
