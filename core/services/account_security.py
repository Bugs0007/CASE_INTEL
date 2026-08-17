"""Account-level security checks that have nothing to do with case data.

Currently just the admin-only credentials lock (core/models/account_lock.py)
-- kept as its own tiny service module rather than inline in the auth views
so every self-service credential-change path (present and future) calls the
exact same check rather than re-deriving it.
"""

from __future__ import annotations

from django.contrib.auth.models import User

from core.models import AccountLock


def is_credentials_locked(user: User) -> bool:
    """True if an admin has locked this account against changing its own
    username/password. Most users have no AccountLock row at all -- that
    means "never locked", not "unknown"."""
    return AccountLock.objects.filter(user=user, credentials_locked=True).exists()
