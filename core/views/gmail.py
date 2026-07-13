"""
Gmail OAuth and sync views.
"""

import logging
from datetime import datetime, timedelta

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Case, Email, GmailCredential

logger = logging.getLogger(__name__)


class GmailAuthView(APIView):
    """Initiate Gmail OAuth flow.

    GET /api/gmail/auth/
    Returns: { "auth_url": "https://accounts.google.com/..." }
    """

    def get(self, request: Request) -> Response:
        try:
            from core.services.gmail_service import GmailService

            service = GmailService()
            auth_url = service.get_auth_url()
            return Response({"auth_url": auth_url})
        except ImportError as e:
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
        except Exception as e:
            logger.exception("Gmail auth failed")
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GmailCallbackView(APIView):
    """Handle Gmail OAuth callback.

    GET /api/gmail/callback/?code=...

    Left public: this is hit directly by Google's OAuth redirect (a
    top-level browser navigation), which carries no Authorization header.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        code = request.query_params.get("code")
        if not code:
            return Response(
                {"detail": "Authorization code required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            from core.services.gmail_service import GmailService

            service = GmailService()
            credential = service.handle_oauth_callback(code)
            return Response(
                {
                    "message": "Gmail connected successfully",
                    "email": credential.email_address,
                }
            )
        except Exception as e:
            logger.exception("Gmail OAuth failed")
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class GmailStatusView(APIView):
    """Check Gmail connection status.

    GET /api/gmail/status/
    """

    def get(self, request: Request) -> Response:
        credential = GmailCredential.objects.filter(is_active=True).first()
        if not credential:
            return Response({"connected": False})

        return Response(
            {
                "connected": True,
                "email": credential.email_address,
                "last_sync": None,
            }
        )


class GmailSyncView(APIView):
    """Trigger email sync.

    POST /api/gmail/sync/
    {
        "labels": ["INBOX"],
        "max_results": 50,
        "days_back": 7
    }
    """

    def post(self, request: Request) -> Response:
        credential = GmailCredential.objects.filter(is_active=True).first()
        if not credential:
            return Response(
                {"detail": "Gmail not connected"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        labels = request.data.get("labels")
        max_results = request.data.get("max_results", 50)
        days_back = request.data.get("days_back")

        after_date = None
        if days_back:
            after_date = datetime.now() - timedelta(days=days_back)

        try:
            from core.services.gmail_service import GmailService

            service = GmailService()
            synced = service.sync_emails(
                credential,
                labels=labels,
                max_results=max_results,
                after_date=after_date,
            )
            return Response(
                {
                    "synced_count": len(synced),
                    "emails": [{"id": e.id, "subject": e.subject} for e in synced],
                }
            )
        except Exception as e:
            logger.exception("Gmail sync failed")
            return Response(
                {"detail": str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class EmailListView(APIView):
    """List synced emails with AI case suggestions.

    GET /api/emails/
    GET /api/emails/?case_id=1
    GET /api/emails/?unlinked=true
    """

    def get(self, request: Request) -> Response:
        qs = Email.objects.select_related("case").order_by("-sent_at")

        case_id = request.query_params.get("case_id")
        if case_id:
            qs = qs.filter(case_id=case_id)

        unlinked = request.query_params.get("unlinked")
        if unlinked == "true":
            qs = qs.filter(case__isnull=True)

        emails = []
        for email in qs[:50]:
            data = {
                "id": email.id,
                "subject": email.subject,
                "sender": email.sender,
                "sent_at": email.sent_at,
                "has_attachments": email.has_attachments,
                "case_id": email.case_id,
                "case_title": email.case.title if email.case else None,
            }
            emails.append(data)

        return Response(emails)


class EmailLinkView(APIView):
    """Link an email to a case.

    POST /api/emails/<id>/link/
    { "case_id": 1 }
    """

    def post(self, request: Request, pk: int) -> Response:
        try:
            email = Email.objects.get(id=pk)
        except Email.DoesNotExist:
            return Response(
                {"detail": "Email not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        case_id = request.data.get("case_id")
        if not case_id:
            return Response(
                {"detail": "case_id required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            case = Case.objects.get(id=case_id)
        except Case.DoesNotExist:
            return Response(
                {"detail": "Case not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        email.case = case
        email.save()

        return Response({"message": "Email linked to case", "case_id": case_id})
