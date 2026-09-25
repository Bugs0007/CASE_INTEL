from django.conf import settings
from django.db import models


class AuthSession(models.Model):
    """One signed-in browser/device: the token behind "Authorization: Token ...".

    Replaces DRF's single, never-expiring authtoken.Token per user. With
    that, every device shared one key, so logging out anywhere signed the
    user out everywhere (the recruiter account, used from several browsers,
    kept bouncing to /login), and a leaked key worked forever.

    Now each login gets its own session that:
      - expires after AUTH_SESSION_IDLE_DAYS without use (a sliding window:
        using it pushes expiry out again -- core/services/auth_sessions.py);
      - can be revoked on its own (logout ends just this one; Settings lists
        and revokes the others).

    Only a SHA-256 of the key is stored: a database leak doesn't hand out
    working credentials. The raw key exists once, in the login response.

    Deliberately a plain `user` FK (CASCADE), not OwnedModel's PROTECT owner:
    deleting a user must take their sessions with them. Every view that reads
    these filters by request.user (see core/views/auth.py).
    """

    SOURCE_LOGIN = "login"
    SOURCE_REGISTER = "register"
    SOURCE_PASSWORD_CHANGE = "password_change"
    SOURCE_LEGACY = "legacy"
    SOURCE_COMMAND = "command"
    SOURCE_CHOICES = [
        (SOURCE_LOGIN, "Signed in"),
        (SOURCE_REGISTER, "Account created"),
        (SOURCE_PASSWORD_CHANGE, "Password changed"),
        (SOURCE_LEGACY, "Carried over from the old sign-in"),
        (SOURCE_COMMAND, "Created by a management command"),
    ]

    id = models.BigAutoField(primary_key=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="auth_sessions"
    )
    key_hash = models.CharField(max_length=64, unique=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default=SOURCE_LOGIN)
    user_agent = models.CharField(max_length=255, blank=True, default="")
    ip_address = models.GenericIPAddressField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField()
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        db_table = "auth_sessions"
        ordering = ["-last_used_at", "-id"]
        indexes = [models.Index(fields=["user", "revoked_at", "expires_at"])]

    def __str__(self):
        state = "revoked" if self.revoked_at else f"expires {self.expires_at:%Y-%m-%d}"
        return f"{self.user} session {self.id} ({state})"
