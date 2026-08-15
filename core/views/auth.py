"""
Token authentication views: login, logout.

Self-service registration (POST /api/auth/register/) was retired -- accounts
are created manually (Django admin) after an emailed access request, to keep
AWS usage bounded to advocates the owner has actually vetted. See the
"Request access" flow on the landing page and login page.
"""

from rest_framework import status
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
