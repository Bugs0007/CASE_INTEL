"""
Token authentication views: register, login, logout.
"""

from django.contrib.auth.models import User
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


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


class RegisterSerializer(serializers.Serializer):
    """Validates new-account signup. Each registered user is a fully
    independent tenant -- row-level isolation (see core/views/mixins.py)
    means a new account starts with zero visibility into any other
    account's cases/documents/etc."""

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


class RegisterView(APIView):
    """Create a new advocate account and return an auth token.

    POST /api/auth/register/
    { "username": "...", "password": "...", "email": "..." (optional) }
    Returns: { "token": "...", "user_id": 1, "username": "..." }
    """

    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = User.objects.create_user(
            username=serializer.validated_data["username"],
            email=serializer.validated_data.get("email", ""),
            password=serializer.validated_data["password"],
        )
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
