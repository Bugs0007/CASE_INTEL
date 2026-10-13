"""Sign in with Google, account linking, set-password and the current-user
summary. Logic lives in core/services/google_auth.py; this is the HTTP layer.

Separate from the old Gmail document-fetch OAuth (core/views/gmail.py): that
needs a client secret and a redirect, this takes a Google ID token the
frontend already holds.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import AuthSession, InviteToken, SocialIdentity
from core.services import auth_sessions, google_auth
from core.services.account_security import is_credentials_locked
from core.views.auth import _credentials_locked_response

PROVIDER = SocialIdentity.PROVIDER_GOOGLE


class _InviteRejected(Exception):
    """Raised inside the creation transaction so it rolls back."""


def _error(code: str, detail: str, http_status: int) -> Response:
    return Response({"code": code, "detail": detail}, status=http_status)


def _verified_claims(request):
    """(claims, None) for a good credential, else (None, error Response)."""
    if not google_auth.is_configured():
        return None, _error("google_not_configured", "Google sign-in is not configured.", 503)
    try:
        return google_auth.verify_google_credential(request.data.get("credential")), None
    except google_auth.GoogleUnavailable:
        return None, _error("google_unavailable", "Could not reach Google. Try again.", 503)
    except google_auth.GoogleAuthError:
        return None, _error("google_token_invalid", "Google sign-in didn't go through.", 401)


def _signup_mode_is_invite() -> bool:
    return str(getattr(settings, "SIGNUP_MODE", "open")).strip().lower() == "invite"


def _consume_invite(token: str, user: User) -> None:
    """Spend a live invite for `user`, under a row lock (same pattern as
    RegisterView). Must run inside the transaction that creates the user."""
    invite = InviteToken.objects.select_for_update().filter(token=token).first()
    if invite is None or not invite.is_valid:
        raise _InviteRejected()
    invite.used_at = timezone.now()
    invite.used_by = user
    invite.save(update_fields=["used_at", "used_by"])


def _invite_is_live(token: str) -> bool:
    invite = InviteToken.objects.filter(token=token).first()
    return invite is not None and invite.is_valid


def _login_response(user: User, request, *, created: bool) -> Response:
    _session, key = auth_sessions.create_session(user, request, source=AuthSession.SOURCE_GOOGLE)
    return Response(
        {"token": key, "user_id": user.pk, "username": user.username, "created": created}
    )


def _sign_in_existing(identity: SocialIdentity, claims: dict, request) -> Response:
    user = identity.user
    if not user.is_active:
        return _error("account_disabled", "This account has been disabled.", status.HTTP_403_FORBIDDEN)
    identity.last_login_at = timezone.now()
    identity.email = claims["email"]
    identity.save(update_fields=["last_login_at", "email"])
    return _login_response(user, request, created=False)


class GoogleLoginView(APIView):
    """Sign in (or sign up) with a Google ID token.

    POST /api/auth/google/
    { "credential": "<Google ID token>", "invite_token": "..." (optional) }
    Returns: { "token", "user_id", "username", "created" } -- the LoginView
    shape, so the frontend reuses its login success handler.

    Matching is by Google's `sub`, never by email. A Google email that matches
    an existing account is a 409, not an auto-link: emails on existing
    accounts were never verified, so linking on them would let anyone with a
    Google account under that address take the account over. The owner links
    Google deliberately from Settings instead (GoogleLinkView).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, *args, **kwargs):
        claims, error = _verified_claims(request)
        if error is not None:
            return error

        sub = claims["sub"]
        identity = SocialIdentity.objects.select_related("user").filter(provider=PROVIDER, subject=sub).first()
        if identity is not None:
            return _sign_in_existing(identity, claims, request)

        if User.objects.filter(email__iexact=claims["email"]).exists():
            return _error(
                "account_exists",
                "An account with this email already exists. Sign in with your username and "
                "password, then connect Google from Settings.",
                status.HTTP_409_CONFLICT,
            )

        invite_token = str(request.data.get("invite_token") or "").strip()
        invite_live = bool(invite_token) and _invite_is_live(invite_token)
        if _signup_mode_is_invite() and not invite_live:
            return _error(
                "invite_required", "Case Intel is invite-only right now.", status.HTTP_403_FORBIDDEN
            )
        # In open mode a stale/spent invite is simply ignored -- it gates nothing.

        def link_and_spend(user: User) -> None:
            SocialIdentity.objects.create(
                user=user, provider=PROVIDER, subject=sub, email=claims["email"], last_login_at=timezone.now()
            )
            if invite_live:
                _consume_invite(invite_token, user)

        try:
            user = google_auth.create_google_user(claims, on_created=link_and_spend)
        except _InviteRejected:
            # Lost the invite to a concurrent signup between the check and the lock.
            return _error(
                "invite_required", "Case Intel is invite-only right now.", status.HTTP_403_FORBIDDEN
            )
        except IntegrityError:
            # A concurrent request linked this same Google account first.
            identity = (
                SocialIdentity.objects.select_related("user").filter(provider=PROVIDER, subject=sub).first()
            )
            if identity is None:
                raise
            return _sign_in_existing(identity, claims, request)

        return _login_response(user, request, created=True)


class GoogleLinkView(APIView):
    """Connect / disconnect the signed-in user's Google account.

    POST   /api/auth/google/link/  { "credential" } -> { "google_email" }
    DELETE /api/auth/google/link/                   -> 204

    Both refuse for a credentials-locked account (the shared recruiter demo
    account): linking would let the first visitor to do it own the demo
    login. Unlinking is refused when the user has no usable password -- they
    would have no way back in.
    """

    def post(self, request, *args, **kwargs):
        if is_credentials_locked(request.user):
            return _credentials_locked_response()
        claims, error = _verified_claims(request)
        if error is not None:
            return error

        if SocialIdentity.objects.filter(user=request.user, provider=PROVIDER).exists():
            return _error(
                "already_linked", "A Google account is already connected.", status.HTTP_409_CONFLICT
            )
        if SocialIdentity.objects.filter(provider=PROVIDER, subject=claims["sub"]).exists():
            return _error(
                "google_account_taken",
                "That Google account is connected to a different Case Intel account.",
                status.HTTP_409_CONFLICT,
            )
        try:
            with transaction.atomic():
                SocialIdentity.objects.create(
                    user=request.user,
                    provider=PROVIDER,
                    subject=claims["sub"],
                    email=claims["email"],
                    last_login_at=timezone.now(),
                )
        except IntegrityError:
            return _error(
                "google_account_taken",
                "That Google account is connected to a different Case Intel account.",
                status.HTTP_409_CONFLICT,
            )
        return Response({"google_email": claims["email"]}, status=status.HTTP_201_CREATED)

    def delete(self, request, *args, **kwargs):
        if is_credentials_locked(request.user):
            return _credentials_locked_response()
        if not request.user.has_usable_password():
            return _error(
                "no_password",
                "Set a password first -- without one you couldn't sign in after disconnecting Google.",
                status.HTTP_400_BAD_REQUEST,
            )
        deleted, _ = SocialIdentity.objects.filter(user=request.user, provider=PROVIDER).delete()
        if not deleted:
            return _error("not_linked", "No Google account is connected.", status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class SetPasswordView(APIView):
    """First password for an account that has none (a Google-only signup).

    POST /api/auth/set-password/  { "new_password": "..." } -> { "revoked": n }

    Needed because change-username/change-password both ask for the current
    password, which a Google-only account doesn't have. Keeps this session and
    ends the others, like change-password. Accounts that already have a
    password use change-password.
    """

    def post(self, request, *args, **kwargs):
        user = request.user
        if is_credentials_locked(user):
            return _credentials_locked_response()
        if user.has_usable_password():
            return _error(
                "has_password",
                "This account already has a password. Use change password instead.",
                status.HTTP_400_BAD_REQUEST,
            )
        new_password = request.data.get("new_password")
        if not isinstance(new_password, str) or not new_password:
            return Response({"new_password": ["This field is required."]}, status=status.HTTP_400_BAD_REQUEST)
        try:
            validate_password(new_password, user=user)
        except DjangoValidationError as exc:
            return Response({"new_password": list(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=["password"])
        revoked = auth_sessions.revoke_all(user, except_session=request.auth)
        return Response({"revoked": revoked})


class MeView(APIView):
    """GET /api/auth/me/ -- who is signed in, and what Settings should offer."""

    def get(self, request, *args, **kwargs):
        user = request.user
        identity = SocialIdentity.objects.filter(user=user, provider=PROVIDER).first()
        return Response(
            {
                "id": user.pk,
                "username": user.username,
                "email": user.email,
                "has_password": user.has_usable_password(),
                "google_linked": identity is not None,
                "google_email": identity.email if identity else None,
                "credentials_locked": is_credentials_locked(user),
            }
        )
