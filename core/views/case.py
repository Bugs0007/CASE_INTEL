"""
Case views — CRUD operations on legal cases.
"""

from datetime import timedelta

from django.db.models import BooleanField, Count, Exists, OuterRef, Subquery, Value
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework import generics

from core.models import Case, Document, Hearing
from core.serializers import CaseSerializer
from core.views.mixins import OwnerScopedMixin


def _annotate_needs_attention(qs, since_param):
    """Annotate each case with the three "needs attention this week" signals:
    a hearing within the next 7 days, an eCourts-sourced hearing update since
    `since_param`, or a document that failed processing. Mirrors the signal
    logic used for the Dashboard's "Needs Your Attention" section.
    """
    now = timezone.now()
    week_out = now + timedelta(days=7)

    upcoming_hearing = (
        Hearing.objects.filter(case=OuterRef("pk"), hearing_date__gte=now, hearing_date__lte=week_out)
        .exclude(status__in=["cancelled", "completed"])
    )
    qs = qs.annotate(has_upcoming_hearing=Exists(upcoming_hearing))

    failed_document = Document.objects.filter(case=OuterRef("pk"), processing_status="failed")
    qs = qs.annotate(has_failed_document=Exists(failed_document))

    since_dt = parse_datetime(since_param) if since_param else None
    if since_dt is not None:
        ecourts_update = Hearing.objects.filter(case=OuterRef("pk"), source="ecourts", updated_at__gt=since_dt)
        qs = qs.annotate(has_ecourts_update=Exists(ecourts_update))
    else:
        qs = qs.annotate(has_ecourts_update=Value(False, output_field=BooleanField()))

    return qs


def _annotate_next_hearing_date(qs):
    """Annotate each case with the date of its earliest upcoming scheduled
    hearing, so the serializer can expose `next_hearing_date` without an
    N+1 query per case."""
    next_hearing = (
        Hearing.objects.filter(case=OuterRef("pk"), status="scheduled", hearing_date__gte=timezone.now())
        .order_by("hearing_date")
        .values("hearing_date")[:1]
    )
    return qs.annotate(_next_hearing_date=Subquery(next_hearing))


class CaseListCreateView(OwnerScopedMixin, generics.ListCreateAPIView):
    """List or create cases.

    GET  /api/cases/
    GET  /api/cases/?status=open
    GET  /api/cases/?priority=high
    GET  /api/cases/?case_type=civil
    GET  /api/cases/?since=2026-07-15T09:00:00Z
        Includes `needs_attention` on each case: True if it has a hearing
        within 7 days, an eCourts hearing update after `since`, or a failed
        document. `since` should be the caller's last-visit timestamp;
        omitting it just drops the eCourts-update signal.
    POST /api/cases/

    All results are scoped to request.user (OwnerScopedMixin); POST always
    stamps the new case with owner=request.user regardless of any input.
    """

    serializer_class = CaseSerializer

    def get_base_queryset(self):
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

        qs = _annotate_needs_attention(qs, self.request.query_params.get("since"))
        qs = _annotate_next_hearing_date(qs)

        return qs


class CaseDetailView(OwnerScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a case.

    GET    /api/cases/<id>/
    PATCH  /api/cases/<id>/
    DELETE /api/cases/<id>/

    Scoped to request.user (OwnerScopedMixin) -- a case owned by another
    user 404s here exactly as if it didn't exist.
    """

    serializer_class = CaseSerializer

    def get_base_queryset(self):
        qs = Case.objects.annotate(
            thread_count=Count("emails__gmail_thread_id", distinct=True),
            conversation_count=Count("conversations", distinct=True),
        )
        return _annotate_next_hearing_date(qs)
