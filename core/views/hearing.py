"""
Hearing views — CRUD operations on case hearings.
"""

from django.utils import timezone
from rest_framework import generics

from core.models import Hearing
from core.serializers import HearingSerializer
from core.views.mixins import OwnerScopedMixin


class HearingListCreateView(OwnerScopedMixin, generics.ListCreateAPIView):
    """List or create hearings.

    GET  /api/hearings/
    GET  /api/hearings/?case_id=1
    GET  /api/hearings/?status=scheduled
    GET  /api/hearings/?upcoming=true
    GET  /api/hearings/?past=true
    POST /api/hearings/

    Scoped to request.user (OwnerScopedMixin). Note this also correctly
    handles a case_id belonging to another user: filtering by case_id first
    then owner last still yields an empty queryset, since no Hearing owned
    by request.user can carry another user's case_id.
    """

    serializer_class = HearingSerializer

    def get_base_queryset(self):
        qs = Hearing.objects.select_related("case")

        # Filter by case
        case_id = self.request.query_params.get("case_id")
        if case_id:
            qs = qs.filter(case_id=case_id)

        # Filter by status
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)

        # Filter upcoming hearings (hearing_date >= now)
        if self.request.query_params.get("upcoming") == "true":
            qs = qs.filter(hearing_date__gte=timezone.now())

        # Filter past hearings (hearing_date < now)
        if self.request.query_params.get("past") == "true":
            qs = qs.filter(hearing_date__lt=timezone.now())

        return qs


class HearingDetailView(OwnerScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a hearing.

    GET    /api/hearings/<id>/
    PATCH  /api/hearings/<id>/
    DELETE /api/hearings/<id>/

    Scoped to request.user (OwnerScopedMixin).
    """

    serializer_class = HearingSerializer
    queryset = Hearing.objects.select_related("case")
