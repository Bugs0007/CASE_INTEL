"""OAuth 2.1 authorization server routes for the MCP connector.

Mounted at the site root (case_intel_project/urls.py) under DOT's own
"oauth2_provider" namespace, because DOT's metadata and DCR views reverse
their sibling endpoints by name in that namespace. Only what the MCP flow
needs is routed: no implicit/device/OIDC endpoints, no application
management pages, no introspection.

  /.well-known/oauth-authorization-server   RFC 8414 metadata
  /oauth/authorize/                         sign-in + consent (core/views/oauth.py)
  /oauth/token/                             code + refresh grants
  /oauth/revoke_token/                      RFC 7009
  /oauth/register/                          RFC 7591 DCR (fallback to CIMD)
  /oauth/register/<client_id>/              RFC 7592 (DCR response links it)
  /oauth/login/, /oauth/logout/             the sign-in page's session

The protected-resource metadata (RFC 9728) is served by the MCP process
itself, at /.well-known/oauth-protected-resource/mcp.
"""

from django.urls import path
from oauth2_provider import views as dot_views

from core.views import oauth as oauth_views

app_name = "oauth2_provider"

urlpatterns = [
    path(
        ".well-known/oauth-authorization-server",
        dot_views.OAuthServerMetadataView.as_view(),
        name="oauth-server-metadata",
    ),
    path("oauth/authorize/", oauth_views.ConsentView.as_view(), name="authorize"),
    path("oauth/token/", dot_views.TokenView.as_view(), name="token"),
    path("oauth/revoke_token/", dot_views.RevokeTokenView.as_view(), name="revoke-token"),
    path("oauth/register/", dot_views.DynamicClientRegistrationView.as_view(), name="dcr-register"),
    path(
        "oauth/register/<str:client_id>/",
        dot_views.DynamicClientRegistrationManagementView.as_view(),
        name="dcr-register-management",
    ),
    path("oauth/login/", oauth_views.SignInView.as_view(), name="sign-in"),
    path("oauth/logout/", oauth_views.SignOutView.as_view(), name="sign-out"),
]
