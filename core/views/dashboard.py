"""
Dashboard view — aggregated statistics for the Case Intel platform.
"""

from django.db.models import Count
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import ActivityLog, Case, Document, Email, Hearing


class DashboardView(APIView):
    """Return aggregated dashboard statistics.

    GET /api/dashboard/
    """

    def get(self, request):
        user = request.user

        # Core stats
        active_cases = Case.objects.filter(owner=user, status="open").count()
        total_documents = Document.objects.filter(owner=user).count()
        email_threads = (
            Email.objects.filter(owner=user)
            .exclude(gmail_thread_id__isnull=True)
            .exclude(gmail_thread_id="")
            .values("gmail_thread_id")
            .distinct()
            .count()
        )

        # Documents by processing status
        documents_by_status = dict(
            Document.objects.filter(owner=user)
            .values("processing_status")
            .annotate(count=Count("id"))
            .values_list("processing_status", "count")
        )

        # Cases by priority (only open cases)
        cases_by_priority = dict(
            Case.objects.filter(owner=user, status="open")
            .values("priority")
            .annotate(count=Count("id"))
            .values_list("priority", "count")
        )

        # Cases by status
        cases_by_status = dict(
            Case.objects.filter(owner=user)
            .values("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        # Recent emails (5 most recent)
        recent_emails = (
            Email.objects.filter(owner=user)
            .select_related("case")
            .order_by("-sent_at")[:5]
        )

        # Recent activity (10 most recent)
        recent_activity = (
            ActivityLog.objects.filter(owner=user)
            .select_related("case")
            .order_by("-created_at")[:10]
        )

        # Active cases summary with document counts
        active_cases_qs = (
            Case.objects.filter(owner=user, status="open")
            .annotate(document_count=Count("documents"))
            .order_by("-created_at")[:5]
        )

        return Response(
            {
                "stats": {
                    "active_cases": active_cases,
                    "total_documents": total_documents,
                    "email_threads": email_threads,
                    "documents_by_status": documents_by_status,
                    "cases_by_priority": cases_by_priority,
                    "cases_by_status": cases_by_status,
                },
                "recent_emails": [
                    {
                        "id": e.id,
                        "subject": e.subject,
                        "sender": e.sender,
                        "sent_at": e.sent_at,
                        "case_id": e.case_id,
                        "case_title": e.case.title if e.case else None,
                    }
                    for e in recent_emails
                ],
                "recent_activity": [
                    {
                        "id": a.id,
                        "activity_type": a.activity_type,
                        "description": a.description,
                        "created_at": a.created_at,
                        "case_id": a.case_id,
                    }
                    for a in recent_activity
                ],
                "active_cases_summary": [
                    {
                        "id": c.id,
                        "case_number": c.case_number,
                        "title": c.title,
                        "document_count": c.document_count,
                        "priority": c.priority,
                        "status": c.status,
                    }
                    for c in active_cases_qs
                ],
            }
        )


class UpcomingHearingsView(APIView):
    """All upcoming hearings across every case, for dashboard alerts.

    GET /api/dashboard/upcoming-hearings/
    GET /api/dashboard/upcoming-hearings/?since=2026-07-15T09:00:00Z
        Restricts to hearings whose eCourts tracking last touched them
        (updated_at) after `since` — used to flag hearing dates that
        changed since the caller's last visit.
    """

    def get(self, request):
        today = timezone.localdate()
        hearings = (
            Hearing.objects.filter(owner=request.user)
            .select_related("case")
            .filter(hearing_date__date__gte=today)
            .exclude(status__in=["cancelled", "completed"])
            .order_by("hearing_date")
        )

        since = request.query_params.get("since")
        if since:
            since_dt = parse_datetime(since)
            if since_dt is not None:
                hearings = hearings.filter(source="ecourts", updated_at__gt=since_dt)

        return Response(
            [
                {
                    "id": h.id,
                    "case_id": h.case_id,
                    "case_title": h.case.title,
                    "case_number": h.case.case_number,
                    "hearing_date": h.hearing_date,
                    "hearing_type": h.hearing_type,
                    "judge": h.judge,
                    "purpose": h.purpose,
                    "source": h.source,
                    "status": h.status,
                    "days_until": (h.hearing_date.date() - today).days,
                    "updated_at": h.updated_at,
                }
                for h in hearings
            ]
        )
