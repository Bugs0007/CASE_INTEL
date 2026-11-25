"""Bearer-token check for the MCP endpoint (docs/MCP_PLAN.md section 4).

Tokens are django-oauth-toolkit AccessToken rows in the shared database,
stored hashed (COMPLIANT_BCP_RFC9700_TOKEN_STORAGE): the lookup is by the
SHA-256 checksum, as DOT does itself. A token passes only when:

  - the row exists (revoking deletes it) and has not expired;
  - its user exists and is active;
  - its `resource` list is non-empty and every entry is exactly
    settings.MCP_RESOURCE_URL. DOT treats an empty list as "any resource";
    this server does not.

The SDK's bearer middleware then compares `AccessToken.resource` with the
configured resource URL again (validate_token_resource=True) and enforces
the `cases:read` scope for every request.

A Case Intel REST session token ("Authorization: Token ...") is a different
row type and is never looked up here. Tokens are never logged.
"""

from __future__ import annotations

import hashlib

import anyio
from django.conf import settings
from django.db import close_old_connections
from mcp.server.auth.provider import AccessToken as McpAccessToken
from oauth2_provider.models import get_access_token_model

from core.services.oauth_policy import resource_is_ours

from .registry import limiter


def verify_sync(raw_token: str) -> McpAccessToken | None:
    if not raw_token or len(raw_token) > 512:
        return None
    close_old_connections()
    try:
        checksum = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        row = (
            get_access_token_model()
            .objects.select_related("user", "application")
            .filter(token_checksum=checksum)
            .first()
        )
        if row is None or row.is_expired() or row.user is None or not row.user.is_active:
            return None
        resources = list(row.resource or [])
        if not resources or not all(resource_is_ours(res) for res in resources):
            return None
        return McpAccessToken(
            token=raw_token,
            client_id=row.application.client_id if row.application_id else "",
            scopes=(row.scope or "").split(),
            expires_at=int(row.expires.timestamp()),
            resource=settings.MCP_RESOURCE_URL,
            subject=str(row.user_id),
            claims={"iss": settings.OAUTH_ISSUER, "user_id": row.user_id, "token_id": row.id},
        )
    finally:
        close_old_connections()


class DjangoTokenVerifier:
    """mcp.server.auth.provider.TokenVerifier over DOT's AccessToken table."""

    async def verify_token(self, token: str) -> McpAccessToken | None:
        return await anyio.to_thread.run_sync(verify_sync, token, limiter=limiter())
