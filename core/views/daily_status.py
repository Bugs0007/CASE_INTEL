"""
GET /api/cases/<id>/daily-status/ -- the District Courts "Daily Status"
(Business on Date) entries stored for one case, newest first.

Read-only and portal-free: entries are fetched by the order_sync worker job
(core/services/daily_status.py), never from a request. A plain APIView, so it
scopes to request.user by hand (see the Multi-tenancy note in CLAUDE.md): a
case belonging to another advocate is a 404, same as one that doesn't exist.
"""

from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Case, CaseBusinessEntry
from core.serializers.daily_status import CaseBusinessEntrySerializer


class CaseDailyStatusView(APIView):
    def get(self, request: Request, pk: int) -> Response:
        if not Case.objects.filter(id=pk, owner=request.user).exists():
            return Response({"detail": "Case not found."}, status=status.HTTP_404_NOT_FOUND)
        entries = CaseBusinessEntry.objects.filter(case_id=pk, owner=request.user).order_by(
            "-business_date", "-id"
        )
        return Response(CaseBusinessEntrySerializer(entries, many=True).data)
