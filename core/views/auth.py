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
