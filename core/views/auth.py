"""
Token authentication views: login, logout, invite-gated register.

Self-service registration with no invite is intentionally not possible --
the owner generates a single-use InviteToken from Django admin and emails
the resulting /register?token=... link by hand, to keep AWS usage bounded
to advocates the owner has actually vetted. See core/models/invite_token.py
and the "Request access" flow on the landing page and login page.
"""

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import InviteToken
from core.services.account_security import is_credentials_locked


class LoginView(ObtainAuthToken):
    """Exchange username + password for an auth token.

    POST /api/auth/login/
    { "username": "...", "password": "..." }
    Returns: { "token": "...", "user_id": 1, "username": "..." }
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.serializer_class(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        token, _ = Token.objects.get_or_create(user=user)
        return Response(
            {
                "token": token.key,
                "user_id": user.pk,
                "username": user.username,
            }
        )


class InviteValidateView(APIView):
    """Check whether an invite token is currently usable.

    GET /api/auth/invite/<token>/
    Returns: { "valid": bool, "reason": "not_found"|"used"|"expired"|null, "email": "..."|null }

    Always 200 -- there's nothing sensitive behind an invalid token that
    would warrant an HTTP error status, and a fixed 200 keeps the frontend
    from branching on status code vs. body. Called by the register page
    before it shows the signup form.
    """

    permission_classes = [AllowAny]

    def get(self, request, token, *args, **kwargs):
        try:
            invite = InviteToken.objects.get(token=token)
        except InviteToken.DoesNotExist:
            return Response({"valid": False, "reason": "not_found", "email": None})

        if invite.used_at is not None:
            return Response({"valid": False, "reason": "used", "email": None})
        if invite.is_expired:
            return Response({"valid": False, "reason": "expired", "email": None})

        return Response({"valid": True, "reason": None, "email": invite.email})


class RegisterSerializer(serializers.Serializer):
    """Validates invite-gated signup. Each registered user is a fully
    independent tenant -- row-level isolation (see core/views/mixins.py)
    means a new account starts with zero visibility into any other
    account's cases/documents/etc."""

    token = serializers.CharField()
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    password = serializers.CharField(write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value

    def validate_password(self, value):
        try:
            validate_password(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value

    def validate_token(self, value):
        try:
            invite = InviteToken.objects.get(token=value)
        except InviteToken.DoesNotExist:
            raise serializers.ValidationError("This invite link is invalid.")
        if invite.used_at is not None:
            raise serializers.ValidationError("This invite link has already been used.")
        if invite.is_expired:
            raise serializers.ValidationError("This invite link has expired.")
        return value


class RegisterView(APIView):
    """Create a new advocate account and return an auth token.

    POST /api/auth/register/
    { "token": "...", "username": "...", "password": "...", "email": "..." (optional) }
    Returns: { "token": "...", "user_id": 1, "username": "..." }

    `token` must be a live InviteToken (core/models/invite_token.py). Consuming
    it happens under select_for_update() inside the same transaction as user
    creation -- the serializer's validate_token() already checked it, but that
    happens outside any lock, so two concurrent requests racing the same
    about-to-expire-or-leak token could otherwise both pass validation and
    both create an account.
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        with transaction.atomic():
            invite = InviteToken.objects.select_for_update().get(
                token=serializer.validated_data["token"]
            )
            if not invite.is_valid:
                raise serializers.ValidationError(
                    {"token": ["This invite link is no longer valid."]}
                )

            user = User.objects.create_user(
                username=serializer.validated_data["username"],
                email=serializer.validated_data.get("email", ""),
                password=serializer.validated_data["password"],
            )
            invite.used_at = timezone.now()
            invite.used_by = user
            invite.save(update_fields=["used_at", "used_by"])
            token = Token.objects.create(user=user)

        return Response(
            {
                "token": token.key,
                "user_id": user.pk,
                "username": user.username,
            },
            status=status.HTTP_201_CREATED,
        )


class LogoutView(APIView):
    """Invalidate the caller's current auth token.

    POST /api/auth/logout/
    Requires the normal Authorization: Token <token> header. Deletes that
    token server-side so it can no longer authenticate -- the frontend
    should also clear its locally-stored copy (see frontend-next/lib/auth.ts).
    """

    def post(self, request, *args, **kwargs):
        request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


def _credentials_locked_response() -> Response:
    return Response(
        {
            "detail": (
                "This account's credentials have been locked by an administrator "
                "and cannot be changed. Contact your administrator if you believe "
                "this is a mistake."
            ),
            "code": "credentials_locked",
        },
        status=status.HTTP_403_FORBIDDEN,
    )


class ChangeUsernameSerializer(serializers.Serializer):
    """current_password is required to confirm the change -- standard
    practice so a hijacked *session* (valid token, e.g. from a shared
    machine or a leaked header) can't silently take over the account's
    identity without also knowing the password."""

    current_password = serializers.CharField(write_only=True)
    new_username = serializers.CharField(max_length=150)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_username(self, value):
        user = self.context["request"].user
        if User.objects.filter(username=value).exclude(pk=user.pk).exists():
            raise serializers.ValidationError("That username is already taken.")
        return value


class ChangeUsernameView(APIView):
    """Self-service username change.

    POST /api/auth/change-username/
    { "current_password": "...", "new_username": "..." }
    Returns: { "username": "..." }

    Rejected with a 403 if core/models/account_lock.py's AccountLock has
    credentials_locked=True for this user -- checked BEFORE validating
    anything else, so a locked account gets a clean, unconditional 403
    rather than "your password was right but..." feedback. This check
    can't be bypassed from the frontend: it's enforced here, server-side,
    for every caller including a direct API request.
    """

    def post(self, request, *args, **kwargs):
        if is_credentials_locked(request.user):
            return _credentials_locked_response()

        serializer = ChangeUsernameSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        request.user.username = serializer.validated_data["new_username"]
        request.user.save(update_fields=["username"])

        return Response({"username": request.user.username})


class ChangePasswordSerializer(serializers.Serializer):
    current_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)

    def validate_current_password(self, value):
        user = self.context["request"].user
        if not user.check_password(value):
            raise serializers.ValidationError("Current password is incorrect.")
        return value

    def validate_new_password(self, value):
        user = self.context["request"].user
        try:
            validate_password(value, user=user)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(list(exc.messages))
        return value


class ChangePasswordView(APIView):
    """Self-service password change.

    POST /api/auth/change-password/
    { "current_password": "...", "new_password": "..." }
    Returns: { "token": "..." }

    Same credentials_locked check (and same reasoning) as
    ChangeUsernameView -- see there. On success, also rotates the auth
    token: deletes every existing token for this user and issues a fresh
    one, so a leaked/stolen token stops authenticating the moment the
    real owner changes their password, instead of quietly continuing to
    work forever regardless of the password change. The caller must swap
    to the returned token; the one that authenticated THIS request is
    deleted too (harmless -- the response has already been built).
    """

    def post(self, request, *args, **kwargs):
        if is_credentials_locked(request.user):
            return _credentials_locked_response()

        serializer = ChangePasswordSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)

        request.user.set_password(serializer.validated_data["new_password"])
        request.user.save(update_fields=["password"])

        Token.objects.filter(user=request.user).delete()
        token = Token.objects.create(user=request.user)

        return Response({"token": token.key})
