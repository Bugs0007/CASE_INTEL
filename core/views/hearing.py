"""
Hearing views — CRUD operations on case hearings.
"""

from django.utils import timezone
from rest_framework import generics

from core.models import Hearing
from core.serializers import HearingSerializer


class HearingListCreateView(generics.ListCreateAPIView):
    """List or create hearings.

    GET  /api/hearings/
    GET  /api/hearings/?case_id=1
    GET  /api/hearings/?status=scheduled
    GET  /api/hearings/?upcoming=true
    GET  /api/hearings/?past=true
    POST /api/hearings/
    """

    serializer_class = HearingSerializer

    def get_queryset(self):
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


class HearingDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a hearing.

    GET    /api/hearings/<id>/
    PATCH  /api/hearings/<id>/
    DELETE /api/hearings/<id>/
    """

    serializer_class = HearingSerializer
    queryset = Hearing.objects.select_related("case")
