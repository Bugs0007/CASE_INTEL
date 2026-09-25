"""A real session token for a test user -- the same thing /api/auth/login/
issues (core/services/auth_sessions.py)."""

from core.services.auth_sessions import create_session


def token_for(user) -> str:
    _session, key = create_session(user)
    return key
