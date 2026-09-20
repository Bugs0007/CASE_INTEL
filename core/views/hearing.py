"""
Hearing views — CRUD operations on case hearings.
"""

from django.db.models import Prefetch
from django.utils import timezone
from rest_framework import generics

from core.models import AppearanceFee, Hearing
from core.serializers import HearingSerializer
from core.views.mixins import OwnerScopedMixin

# A hearing's charges are reverse-FK rows, so Django does not fetch them with
# the hearing -- without a prefetch HearingSerializer's embedded
# `appearance_fees` costs one query per hearing and the calendar scales with
# the diary. Ordered oldest-first (AppearanceFee.Meta orders newest-first) so
# a card lists its charges in the order they were added -- the appearance fee
# usually first -- and a newly added one appends instead of jumping to the
# top. Same single extra query either way.
_FEES_OLDEST_FIRST = Prefetch(
    "appearance_fees", queryset=AppearanceFee.objects.order_by("created_at", "id")
)


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
        # court_orders is prefetched for the same reason as the fees (see
        # _FEES_OLDEST_FIRST), so get_order_summary can match in Python.
        qs = Hearing.objects.select_related("case").prefetch_related(
            "case__court_orders", "travel_bookings", _FEES_OLDEST_FIRST
        )

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
    queryset = Hearing.objects.select_related("case").prefetch_related(
        "case__court_orders", "travel_bookings", _FEES_OLDEST_FIRST
    )
