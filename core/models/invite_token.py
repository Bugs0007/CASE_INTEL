import secrets

from django.conf import settings
from django.db import models
from django.utils import timezone


def _generate_token():
    return secrets.token_urlsafe(32)


def _default_expiry():
    return timezone.now() + timezone.timedelta(days=7)


class InviteToken(models.Model):
    """Single-use, time-limited token gating new-account registration.

    Self-service signup is retired (see core/views/auth.py) -- the owner
    generates one of these from Django admin and emails the resulting
    /register?token=... link by hand. Registering with the token consumes
    it immediately (used_at set, inside the same transaction that creates
    the User -- see RegisterView), so the same link can't mint a second
    account even if it leaks before it expires.
    """

    token = models.CharField(
        max_length=64, unique=True, db_index=True, default=_generate_token
    )
    email = models.EmailField(
        blank=True,
        help_text="Who this invite is for. Not enforced -- just prefills the signup form.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_default_expiry)
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        db_table = "invite_tokens"
        ordering = ["-created_at"]

    def __str__(self):
        return f"invite {self.token[:10]}... ({self.status})"

    @property
    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    @property
    def is_valid(self) -> bool:
        return self.used_at is None and not self.is_expired

    @property
    def status(self) -> str:
        if self.used_at:
            return "used"
        if self.is_expired:
            return "expired"
        return "active"
