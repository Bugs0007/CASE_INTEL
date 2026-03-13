"""
Case views — CRUD operations on legal cases.
"""

from rest_framework import generics

from core.models import Case
from core.serializers import CaseSerializer


class CaseListCreateView(generics.ListCreateAPIView):
    """List or create cases.

    GET  /api/cases/
    POST /api/cases/
    """

    serializer_class = CaseSerializer
    queryset = Case.objects.all()


class CaseDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a case.

    GET    /api/cases/<id>/
    PATCH  /api/cases/<id>/
    DELETE /api/cases/<id>/
    """

    serializer_class = CaseSerializer
    queryset = Case.objects.all()
