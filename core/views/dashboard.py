"""
Dashboard view — aggregated statistics for the Case Intel platform.
"""

from django.db.models import Count
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import ActivityLog, Case, Document, Email


class DashboardView(APIView):
    """Return aggregated dashboard statistics.

    GET /api/dashboard/
    """

    def get(self, request):
        # Core stats
        active_cases = Case.objects.filter(status="open").count()
        total_documents = Document.objects.count()
        email_threads = (
            Email.objects.exclude(gmail_thread_id__isnull=True)
            .exclude(gmail_thread_id="")
            .values("gmail_thread_id")
            .distinct()
            .count()
        )

        # Documents by processing status
        documents_by_status = dict(
            Document.objects.values("processing_status")
            .annotate(count=Count("id"))
            .values_list("processing_status", "count")
        )

        # Cases by priority (only open cases)
        cases_by_priority = dict(
            Case.objects.filter(status="open")
            .values("priority")
            .annotate(count=Count("id"))
            .values_list("priority", "count")
        )

        # Cases by status
        cases_by_status = dict(
            Case.objects.values("status")
            .annotate(count=Count("id"))
            .values_list("status", "count")
        )

        # Recent emails (5 most recent)
        recent_emails = Email.objects.select_related("case").order_by("-sent_at")[:5]

        # Recent activity (10 most recent)
        recent_activity = ActivityLog.objects.select_related("case").order_by(
            "-created_at"
        )[:10]

        # Active cases summary with document counts
        active_cases_qs = (
            Case.objects.filter(status="open")
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
