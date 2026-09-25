"""DRF authentication for per-session tokens (core/services/auth_sessions.py).

Same header as before -- "Authorization: Token <key>" -- so nothing on the
frontend changes; the key now names one expiring, revocable session instead
of the user's single permanent token.
"""

from rest_framework import exceptions
from rest_framework.authentication import BaseAuthentication, get_authorization_header

from core.services import auth_sessions


class SessionTokenAuthentication(BaseAuthentication):
    keyword = "Token"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts or parts[0].lower() != self.keyword.lower().encode():
            return None
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed("Invalid token header.")
        try:
            key = parts[1].decode()
        except UnicodeError:
            raise exceptions.AuthenticationFailed("Invalid token header.") from None
        result = auth_sessions.authenticate_key(key)
        if result is None:
            raise exceptions.AuthenticationFailed("Your session has ended. Please sign in again.")
        return result  # (user, session): request.auth is the AuthSession

    def authenticate_header(self, request):
        # Makes DRF answer 401 (not 403) when credentials are missing or
        # dead -- the status the frontend's retry/redirect logic keys on.
        return self.keyword
