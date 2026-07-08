"""
Case views — CRUD operations on legal cases.
"""

from django.db.models import Count
from rest_framework import generics

from core.models import Case
from core.serializers import CaseSerializer


class CaseListCreateView(generics.ListCreateAPIView):
    """List or create cases.

    GET  /api/cases/
    GET  /api/cases/?status=open
    GET  /api/cases/?priority=high
    GET  /api/cases/?case_type=civil
    POST /api/cases/
    """

    serializer_class = CaseSerializer

    def get_queryset(self):
        qs = Case.objects.annotate(
            thread_count=Count("emails__gmail_thread_id", distinct=True),
            conversation_count=Count("conversations", distinct=True),
        )

        # Filter by status
        status = self.request.query_params.get("status")
        if status:
            qs = qs.filter(status=status)

        # Filter by priority
        priority = self.request.query_params.get("priority")
        if priority:
            qs = qs.filter(priority=priority)

        # Filter by case_type
        case_type = self.request.query_params.get("case_type")
        if case_type:
            qs = qs.filter(case_type=case_type)

        return qs


class CaseDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a case.

    GET    /api/cases/<id>/
    PATCH  /api/cases/<id>/
    DELETE /api/cases/<id>/
    """

    serializer_class = CaseSerializer

    def get_queryset(self):
        return Case.objects.annotate(
            thread_count=Count("emails__gmail_thread_id", distinct=True),
            conversation_count=Count("conversations", distinct=True),
        )
