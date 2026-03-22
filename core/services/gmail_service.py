"""
Gmail API integration service.

Handles OAuth flow, email sync, and attachment processing.
"""

import base64
import logging
from datetime import datetime, timedelta
from typing import List, Optional

from django.conf import settings

from core.models import Case, Email, EmailAttachment, GmailCredential

logger = logging.getLogger(__name__)


class GmailService:
    """Service for Gmail API operations."""

    SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

    def __init__(self):
        self.client_config = {
            "web": {
                "client_id": getattr(settings, "GMAIL_CLIENT_ID", ""),
                "client_secret": getattr(settings, "GMAIL_CLIENT_SECRET", ""),
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "redirect_uris": [
                    getattr(
                        settings,
                        "GMAIL_REDIRECT_URI",
                        "http://localhost:8000/api/gmail/callback/",
                    )
                ],
            }
        }

    def get_auth_url(self) -> str:
        """Generate OAuth authorization URL."""
        try:
            from google_auth_oauthlib.flow import Flow

            flow = Flow.from_client_config(
                self.client_config,
                scopes=self.SCOPES,
                redirect_uri=getattr(
                    settings,
                    "GMAIL_REDIRECT_URI",
                    "http://localhost:8000/api/gmail/callback/",
                ),
            )
            auth_url, _ = flow.authorization_url(
                access_type="offline",
                include_granted_scopes="true",
                prompt="consent",
            )
            return auth_url
        except ImportError:
            raise ImportError(
                "google-auth-oauthlib is required. "
                "Install it with: pip install google-auth-oauthlib"
            )

    def handle_oauth_callback(self, authorization_code: str) -> GmailCredential:
        """Exchange authorization code for tokens and store credentials."""
        from google_auth_oauthlib.flow import Flow
        from googleapiclient.discovery import build

        flow = Flow.from_client_config(
            self.client_config,
            scopes=self.SCOPES,
            redirect_uri=getattr(
                settings,
                "GMAIL_REDIRECT_URI",
                "http://localhost:8000/api/gmail/callback/",
            ),
        )
        flow.fetch_token(code=authorization_code)

        creds = flow.credentials

        # Get user email
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        email_address = profile["emailAddress"]

        # Calculate token expiry
        if creds.expiry:
            token_expiry = creds.expiry
        else:
            token_expiry = datetime.now() + timedelta(hours=1)

        # Store or update credentials
        credential, created = GmailCredential.objects.update_or_create(
            email_address=email_address,
            defaults={
                "access_token": creds.token,
                "refresh_token": creds.refresh_token or "",
                "token_expiry": token_expiry,
                "scope": " ".join(creds.scopes or self.SCOPES),
                "is_active": True,
            },
        )

        logger.info("Gmail credentials %s for %s", "created" if created else "updated", email_address)
        return credential

    def sync_emails(
        self,
        credential: GmailCredential,
        labels: Optional[List[str]] = None,
        max_results: int = 50,
        after_date: Optional[datetime] = None,
    ) -> List[Email]:
        """Sync emails from Gmail to local database."""
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        creds = Credentials(
            token=credential.access_token,
            refresh_token=credential.refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=getattr(settings, "GMAIL_CLIENT_ID", ""),
            client_secret=getattr(settings, "GMAIL_CLIENT_SECRET", ""),
        )

        service = build("gmail", "v1", credentials=creds)

        # Build query
        query_parts = []
        if after_date:
            query_parts.append(f"after:{after_date.strftime('%Y/%m/%d')}")

        query = " ".join(query_parts) if query_parts else None

        # List messages
        label_ids = labels or ["INBOX"]
        results = (
            service.users()
            .messages()
            .list(
                userId="me",
                labelIds=label_ids,
                maxResults=max_results,
                q=query,
            )
            .execute()
        )

        messages = results.get("messages", [])
        synced_emails = []

        for msg_meta in messages:
            msg_id = msg_meta["id"]

            # Skip if already synced
            if Email.objects.filter(gmail_message_id=msg_id).exists():
                continue

            # Fetch full message
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=msg_id, format="full")
                .execute()
            )

            # Parse headers
            headers = {h["name"]: h["value"] for h in msg["payload"]["headers"]}

            # Parse sent time
            internal_date = msg.get("internalDate")
            sent_at = None
            if internal_date:
                sent_at = datetime.fromtimestamp(int(internal_date) / 1000)

            # Create Email record
            email = Email.objects.create(
                gmail_message_id=msg_id,
                gmail_thread_id=msg.get("threadId"),
                subject=headers.get("Subject"),
                sender=headers.get("From"),
                recipients=headers.get("To"),
                sent_at=sent_at,
                body_text=self._extract_body(msg["payload"]),
                has_attachments=self._has_attachments(msg["payload"]),
            )

            # Process attachments
            self._process_attachments(service, msg_id, msg["payload"], email)

            synced_emails.append(email)
            logger.info("Synced email: %s", email.subject)

        return synced_emails

    def _extract_body(self, payload: dict) -> str:
        """Extract text body from email payload."""
        if "body" in payload and payload["body"].get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode(
                "utf-8", errors="replace"
            )

        if "parts" in payload:
            for part in payload["parts"]:
                if part["mimeType"] == "text/plain":
                    if part["body"].get("data"):
                        return base64.urlsafe_b64decode(
                            part["body"]["data"]
                        ).decode("utf-8", errors="replace")

        return ""

    def _has_attachments(self, payload: dict) -> bool:
        """Check if email has attachments."""
        if "parts" in payload:
            for part in payload["parts"]:
                if part.get("filename"):
                    return True
        return False

    def _process_attachments(
        self, service, msg_id: str, payload: dict, email: Email
    ):
        """Download and store email attachments."""
        if "parts" not in payload:
            return

        for part in payload["parts"]:
            filename = part.get("filename")
            if not filename:
                continue

            attachment_id = part["body"].get("attachmentId")
            if not attachment_id:
                continue

            EmailAttachment.objects.create(
                email=email,
                filename=filename,
                gmail_attachment_id=attachment_id,
            )

    def suggest_case_for_email(self, email: Email) -> Optional[Case]:
        """Use AI to suggest which case an email belongs to."""
        from core.services.ai_service_factory import get_llm_client

        # Get all open cases
        cases = Case.objects.filter(status="open").values(
            "id", "case_number", "title", "client_name"
        )

        if not cases:
            return None

        cases_text = "\n".join(
            [
                f"ID: {c['id']}, Number: {c['case_number']}, "
                f"Title: {c['title']}, Client: {c['client_name']}"
                for c in cases
            ]
        )

        prompt = f"""Given this email:
Subject: {email.subject}
From: {email.sender}
Body excerpt: {email.body_text[:500] if email.body_text else '(empty)'}

And these open cases:
{cases_text}

Which case ID does this email most likely belong to?
Reply with just the case ID number, or "none" if no match."""

        llm = get_llm_client()
        response = llm.generate(prompt, temperature=0)

        try:
            case_id = int(response.strip())
            return Case.objects.filter(id=case_id).first()
        except (ValueError, TypeError):
            return None
