"""Who is calling, and which rows they may see (docs/MCP_PLAN.md section 4).

`TenantContext` is built per tool call from the verified OAuth token. Today
a member sees exactly their own rows (`owner_ids == {user.id}`); a later
firm/organization model widens `owner_ids` by role here, without changing
any tool. `scoped(Model, ctx)` is the ONLY way tool code obtains a
queryset -- a test fails on any `.objects.` in mcp_server/tools/.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import User


class AccessDenied(Exception):
    """The token's user can no longer act (deleted or deactivated)."""


@dataclass(frozen=True)
class TenantContext:
    user: User  # who is acting
    owner_ids: frozenset  # rows this caller may see: today {user.id}
    org_id: int | None  # None until organizations exist (Phase 3)
    role: str  # "owner" until organizations exist
    scopes: frozenset
    client_id: str
    token_id: int

    @property
    def owner(self) -> User:
        """The single owner today's service functions take as `owner=`."""
        return self.user


def build_context(*, user_id: int, scopes, client_id: str, token_id: int) -> TenantContext:
    user = User.objects.filter(pk=user_id, is_active=True).first()
    if user is None:
        raise AccessDenied()
    return TenantContext(
        user=user,
        owner_ids=frozenset({user.id}),
        org_id=None,
        role="owner",
        scopes=frozenset(scopes),
        client_id=client_id,
        token_id=token_id,
    )


def scoped(model, ctx: TenantContext):
    """`model`'s rows this caller may see. Every owned model has `owner`."""
    return model._default_manager.filter(owner_id__in=ctx.owner_ids)
