"""Client contact views — CRUD operations on a case's client contacts."""

from rest_framework import generics

from core.models import ClientContact
from core.serializers import ClientContactSerializer
from core.views.mixins import OwnerScopedMixin


class ClientContactListCreateView(OwnerScopedMixin, generics.ListCreateAPIView):
    """List or create client contacts.

    GET  /api/client-contacts/
    GET  /api/client-contacts/?case_id=1
    POST /api/client-contacts/

    Scoped to request.user (OwnerScopedMixin) -- same as Hearing, this also
    correctly handles a case_id belonging to another user: filtering by
    case_id first then owner last still yields an empty queryset, since no
    ClientContact owned by request.user can carry another user's case_id.
    """

    serializer_class = ClientContactSerializer

    def get_base_queryset(self):
        qs = ClientContact.objects.select_related("case")
        case_id = self.request.query_params.get("case_id")
        if case_id:
            qs = qs.filter(case_id=case_id)
        return qs


class ClientContactDetailView(OwnerScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a client contact.

    GET    /api/client-contacts/<id>/
    PATCH  /api/client-contacts/<id>/
    DELETE /api/client-contacts/<id>/

    Scoped to request.user (OwnerScopedMixin).
    """

    serializer_class = ClientContactSerializer
    queryset = ClientContact.objects.select_related("case")
