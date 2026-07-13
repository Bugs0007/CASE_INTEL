"""
Token authentication views.
"""

from rest_framework.authtoken.models import Token
from rest_framework.authtoken.views import ObtainAuthToken
from rest_framework.permissions import AllowAny
from rest_framework.response import Response


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
