from django.conf import settings
from django.db import models


class AccountLock(models.Model):
    """Admin-only kill switch: while credentials_locked is True, the
    account cannot change its own username or password through ANY
    self-service path (Settings' "Change Username"/"Change Password"
    forms -- see core/views/auth.py's ChangeUsernameView/
    ChangePasswordView -- and any future path that touches
    User.username/User.password). Enforced server-side in those views,
    not just hidden in the frontend, so a locked account gets a clear 403
    even calling the API directly with a valid session and correct
    current password.

    Deliberately has NO user-facing API at all -- toggle-able only from
    Django admin (see core/admin.py's inline on the User admin page),
    since the whole point is that the account holder can't undo this
    themselves.

    Most users never get a row here -- absence of a row means "not
    locked" (see core/services/account_security.py's
    is_credentials_locked()), so this only exists for accounts an admin
    has actually locked.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="account_lock"
    )
    credentials_locked = models.BooleanField(
        default=False,
        help_text=(
            "When checked, this account cannot change its own username or "
            "password through any self-service path -- rejected with a 403, "
            "even with a valid session and the correct current password. "
            "Toggle only from here -- there is no user-facing way to undo this."
        ),
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "account_locks"

    def __str__(self):
        return f"{self.user.username}: {'locked' if self.credentials_locked else 'unlocked'}"
