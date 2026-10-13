"""Per-session, expiring API tokens (core/models/auth_session.py).

The wire format is unchanged -- "Authorization: Token <40 hex chars>" -- so
the frontend's storage and its 401-retry logic work as before. What changed
is what a key means: one signed-in device, with a sliding idle expiry,
revocable on its own.
"""

from __future__ import annotations

import hashlib
import ipaddress
import secrets
from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from core.models import AuthSession

# Don't write last_used_at/expires_at on every request: once a minute is
# plenty for a 7-day window and keeps authentication read-only otherwise.
TOUCH_INTERVAL = timedelta(minutes=1)
# Ended sessions are kept this long (so Settings can show "revoked"), then
# pruned the next time the user signs in.
PRUNE_AFTER = timedelta(days=30)


def idle_window() -> timedelta:
    return timedelta(days=int(getattr(settings, "AUTH_SESSION_IDLE_DAYS", 7)))


def hash_key(raw_key: str) -> str:
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def _valid_ip(value: str) -> str | None:
    value = (value or "").strip()
    try:
        return str(ipaddress.ip_address(value)) if value else None
    except ValueError:
        return None


def client_ip(meta) -> str | None:
    """The caller's IP, without trusting anything the client can forge.

    nginx sets X-Real-IP from $remote_addr (the socket peer), so it is the
    first choice. Failing that, the LAST X-Forwarded-For entry: the proxy
    appends ($proxy_add_x_forwarded_for), so the first entries are whatever
    the client chose to send and can be spoofed. REMOTE_ADDR is last.
    """
    candidates = [meta.get("HTTP_X_REAL_IP") or ""]
    forwarded = [part for part in (meta.get("HTTP_X_FORWARDED_FOR") or "").split(",") if part.strip()]
    candidates.append(forwarded[-1] if forwarded else "")
    candidates.append(meta.get("REMOTE_ADDR") or "")
    for candidate in candidates:
        ip = _valid_ip(candidate)
        if ip:
            return ip
    return None


def _client_details(request) -> dict:
    if request is None:
        return {}
    meta = getattr(request, "META", {})
    return {"user_agent": (meta.get("HTTP_USER_AGENT") or "")[:255], "ip_address": client_ip(meta)}


def create_session(user, request=None, *, source: str = AuthSession.SOURCE_LOGIN) -> tuple[AuthSession, str]:
    """A new session for `user`. Returns (session, raw_key); the raw key is
    never stored and can't be recovered later."""
    now = timezone.now()
    raw_key = secrets.token_hex(20)
    session = AuthSession.objects.create(
        user=user,
        key_hash=hash_key(raw_key),
        source=source,
        last_used_at=now,
        expires_at=now + idle_window(),
        **_client_details(request),
    )
    prune_ended_sessions(user)
    return session, raw_key


def active_sessions(user):
    now = timezone.now()
    return AuthSession.objects.filter(user=user, revoked_at__isnull=True, expires_at__gt=now)


def authenticate_key(raw_key: str):
    """(user, session) for a live key, else None. Slides the expiry."""
    if not raw_key:
        return None
    session = (
        AuthSession.objects.select_related("user")
        .filter(key_hash=hash_key(raw_key), revoked_at__isnull=True)
        .first()
    )
    now = timezone.now()
    if session is None or session.expires_at <= now or not session.user.is_active:
        return None
    if now - session.last_used_at >= TOUCH_INTERVAL:
        session.last_used_at = now
        session.expires_at = now + idle_window()
        AuthSession.objects.filter(id=session.id).update(
            last_used_at=session.last_used_at, expires_at=session.expires_at
        )
    return session.user, session


def revoke(session: AuthSession) -> None:
    if session.revoked_at is None:
        session.revoked_at = timezone.now()
        AuthSession.objects.filter(id=session.id, revoked_at__isnull=True).update(revoked_at=session.revoked_at)


def revoke_all(user, *, except_session: AuthSession | None = None) -> int:
    qs = AuthSession.objects.filter(user=user, revoked_at__isnull=True)
    if except_session is not None:
        qs = qs.exclude(id=except_session.id)
    return qs.update(revoked_at=timezone.now())


def prune_ended_sessions(user) -> int:
    cutoff = timezone.now() - PRUNE_AFTER
    deleted, _ = AuthSession.objects.filter(user=user).filter(
        Q(revoked_at__lt=cutoff) | Q(expires_at__lt=cutoff)
    ).delete()
    return deleted
