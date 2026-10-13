"""Sign in with Google: ID-token verification and Google-backed user creation.

The frontend (Google Identity Services) hands us a signed ID token; we check
its signature, audience, expiry and issuer with google-auth and trust only the
claims inside it. No redirect URI, client secret or cookie is involved.

Completely separate from the old Gmail document-fetch integration
(gmail_service.py / GMAIL_CLIENT_ID) -- different client, different purpose.
"""

from __future__ import annotations

import logging
import re

from django.conf import settings
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from google.auth import exceptions as google_exceptions
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

logger = logging.getLogger(__name__)

GOOGLE_ISSUERS = ("accounts.google.com", "https://accounts.google.com")
# Google's iat is occasionally a second or two ahead of our clock; verify_oauth2_token
# otherwise rejects those as "Token used too early".
CLOCK_SKEW_SECONDS = 10

_USERNAME_MAX = 150
_USERNAME_DISALLOWED = re.compile(r"[^a-z0-9._-]+")
_MAX_CREATE_ATTEMPTS = 8


class GoogleAuthError(Exception):
    """Base class for Google sign-in failures."""


class GoogleNotConfigured(GoogleAuthError):
    """GOOGLE_OAUTH_CLIENT_ID is empty."""


class GoogleTokenInvalid(GoogleAuthError):
    """The credential is malformed, expired, for another audience, from the
    wrong issuer, or carries an unverified email."""


class GoogleUnavailable(GoogleAuthError):
    """Google's signing keys could not be fetched (network); not the user's fault."""


def is_configured() -> bool:
    return bool(getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", ""))


def verify_google_credential(credential: str) -> dict:
    """Verified claims for a Google ID token, or a typed error.

    Requires a verified email and a Google issuer. The raw credential is never
    logged -- it is a bearer proof of the user's Google sign-in until it expires.
    """
    client_id = getattr(settings, "GOOGLE_OAUTH_CLIENT_ID", "")
    if not client_id:
        raise GoogleNotConfigured()
    if not credential or not isinstance(credential, str):
        raise GoogleTokenInvalid("missing credential")

    try:
        claims = id_token.verify_oauth2_token(
            credential,
            google_requests.Request(),
            client_id,
            clock_skew_in_seconds=CLOCK_SKEW_SECONDS,
        )
    except ValueError as exc:
        logger.info("Google credential rejected: %s", type(exc).__name__)
        raise GoogleTokenInvalid("verification failed") from exc
    except google_exceptions.TransportError as exc:
        logger.warning("Could not fetch Google signing keys: %s", type(exc).__name__)
        raise GoogleUnavailable() from exc

    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleTokenInvalid("wrong issuer")
    if claims.get("email_verified") is not True:
        raise GoogleTokenInvalid("email not verified")
    if not claims.get("sub") or not claims.get("email"):
        raise GoogleTokenInvalid("missing sub or email")
    return claims


def _username_base(email: str) -> str:
    local = (email or "").split("@", 1)[0].lower()
    base = _USERNAME_DISALLOWED.sub("", local)
    return base or "user"


def _username_candidate(base: str, n: int) -> str:
    """`base` for n == 1, else `base` + n, with the base trimmed so the
    result never exceeds Django's 150-character username limit."""
    suffix = "" if n == 1 else str(n)
    return base[: _USERNAME_MAX - len(suffix)] + suffix


def generate_username(email: str) -> str:
    """First unused of ramesh, ramesh2, ramesh3, ... for this email.

    Only a best-effort pre-check: two signups can pick the same name at once,
    so create_google_user() re-runs this (which then sees the winner's row) on IntegrityError.
    """
    base = _username_base(email)
    n = 1
    while User.objects.filter(username__iexact=_username_candidate(base, n)).exists():
        n += 1
    return _username_candidate(base, n)


def create_google_user(claims: dict, *, on_created=None) -> User:
    """Create the User for a first-time Google sign-in.

    `on_created(user)` runs inside the same transaction as the insert (used to
    link the SocialIdentity and consume an invite), so either everything
    happens or nothing does. A username collision from a concurrent signup is
    retried with a fresh pick. Any other IntegrityError propagates
    after the attempts run out, for the caller to inspect.
    """
    email = claims["email"]
    last_error: IntegrityError | None = None
    for _ in range(_MAX_CREATE_ATTEMPTS):
        username = generate_username(email)
        try:
            with transaction.atomic():
                user = User(
                    username=username,
                    email=email,
                    first_name=(claims.get("given_name") or "")[:150],
                    last_name=(claims.get("family_name") or "")[:150],
                )
                user.set_unusable_password()
                user.save()
                if on_created is not None:
                    on_created(user)
            return user
        except IntegrityError as exc:
            if not User.objects.filter(username__iexact=username).exists():
                # Not a username race (e.g. the Google account got linked by a
                # concurrent request) -- let the caller decide.
                raise
            last_error = exc
    assert last_error is not None
    raise last_error
