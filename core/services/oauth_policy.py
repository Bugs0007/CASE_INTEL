"""Case Intel's rules on top of django-oauth-toolkit (DOT) for the MCP connector.

DOT is the authorization server (docs/MCP_PLAN.md section 4). These are the
few places where Case Intel is stricter than DOT's defaults:

  - Redirect URIs. Only hosted Claude's callback and a loopback callback
    (localhost / 127.0.0.1, any port) are ever allowed -- at Dynamic Client
    Registration, and again on every authorize request (which also covers
    clients created from a Client ID Metadata Document).
  - Audience. The only `resource` (RFC 8707) a client may ask a token for is
    settings.MCP_RESOURCE_URL. The MCP process also refuses a token whose
    resource is not exactly that URL (mcp_server/auth.py).
  - Revocation. One user's grants can be revoked per application (the
    connected-apps API) or all at once (password change).

No code here reads case data.
"""

from __future__ import annotations

import json
from urllib.parse import urlsplit

from django.conf import settings
from django.db import transaction
from oauthlib.oauth2.rfc6749 import errors
from oauth2_provider.models import get_access_token_model, get_grant_model, get_refresh_token_model
from oauth2_provider.oauth2_validators import OAuth2Validator

ALLOWED_DCR_GRANT_TYPES = {"authorization_code", "refresh_token"}


def redirect_allowed_by_policy(uri: str) -> bool:
    """True for hosted Claude's callback or an http loopback callback."""
    if not isinstance(uri, str) or not uri or "#" in uri:
        return False
    if uri in settings.OAUTH_HOSTED_REDIRECT_URIS:
        return True
    try:
        parts = urlsplit(uri)
        parts.port  # noqa: B018 -- raises ValueError on a bad port
    except ValueError:
        return False
    if "@" in parts.netloc:
        return False
    return parts.scheme == "http" and parts.hostname in settings.OAUTH_LOOPBACK_HOSTS


def resource_is_ours(resource: str) -> bool:
    return (resource or "").rstrip("/") == settings.MCP_RESOURCE_URL.rstrip("/")


class CaseIntelOAuth2Validator(OAuth2Validator):
    def validate_redirect_uri(self, client_id, redirect_uri, request, *args, **kwargs):
        if not redirect_allowed_by_policy(redirect_uri):
            return False
        return super().validate_redirect_uri(client_id, redirect_uri, request, *args, **kwargs)

    def _validate_resource_uris(self, request, resources):
        super()._validate_resource_uris(request, resources)
        for res in resources:
            if not resource_is_ours(res):
                raise errors.CustomOAuth2Error(
                    error="invalid_target",
                    description="Tokens are only issued for the Case Intel MCP server.",
                    request=request,
                )


class McpDCRPermission:
    """Open Dynamic Client Registration, limited to Claude's redirect URIs.

    Claude registers itself without credentials, so registration cannot
    require a signed-in user. What keeps it safe: every redirect URI must
    pass redirect_allowed_by_policy, and only the authorization-code grant
    (with refresh) can be registered. A registered client still needs the
    user to sign in and consent before it gets any token.
    """

    def has_permission(self, request) -> bool:
        try:
            data = json.loads(request.body or b"{}")
        except (ValueError, UnicodeDecodeError):
            return False
        if not isinstance(data, dict):
            return False
        uris = data.get("redirect_uris")
        if not isinstance(uris, list) or not uris:
            return False
        if not all(redirect_allowed_by_policy(uri) for uri in uris):
            return False
        grant_types = data.get("grant_types", ["authorization_code"])
        if not isinstance(grant_types, list) or not set(grant_types) <= ALLOWED_DCR_GRANT_TYPES:
            return False
        return True


def revoke_user_grants(user, *, application=None) -> int:
    """Revoke `user`'s OAuth access: refresh tokens, access tokens and
    unused authorization codes, for one application or all. Returns the
    number of access + refresh tokens ended."""
    AccessToken = get_access_token_model()
    RefreshToken = get_refresh_token_model()
    Grant = get_grant_model()
    filters = {"user": user}
    if application is not None:
        filters["application"] = application
    ended = 0
    with transaction.atomic():
        for refresh in RefreshToken.objects.filter(revoked__isnull=True, **filters):
            refresh.revoke()  # also deletes its access token
            ended += 1
        for access in AccessToken.objects.filter(**filters):
            access.revoke()
            ended += 1
        Grant.objects.filter(**filters).delete()
    return ended
