"""Single-place enforcement of row-level multi-tenancy for DRF views.

Every generic view (list/create/retrieve/update/destroy) on a model that
holds case data must mix in OwnerScopedMixin FIRST in its base list, so its
get_queryset() always wins over anything a subclass defines. This is what
makes it impossible for user A to list, retrieve, update, or delete user
B's rows through any endpoint: DRF's generics.GenericAPIView.get_object()
(used by retrieve/update/destroy) filters against the SAME get_queryset()
that list uses, so scoping it here covers both list and object-level access
in one place.
"""


class OwnerScopedMixin:
    """Scopes every queryset to request.user and stamps new rows with
    owner=request.user on create.

    Subclasses that need custom filtering (query params, annotations,
    select_related, etc.) should override `get_base_queryset()` instead of
    `get_queryset()` -- this mixin's `get_queryset()` always applies the
    owner filter last, on top of whatever `get_base_queryset()` returns, so
    it can't be bypassed by a subclass overriding `get_queryset()` and
    forgetting to filter by owner.
    """

    owner_field = "owner"

    def get_base_queryset(self):
        return super().get_queryset()

    def get_queryset(self):
        qs = self.get_base_queryset()
        return qs.filter(**{self.owner_field: self.request.user})

    def perform_create(self, serializer):
        serializer.save(**{self.owner_field: self.request.user})
