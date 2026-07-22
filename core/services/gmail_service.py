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

    def get_auth_url(self, state: str) -> str:
        """Generate OAuth authorization URL.

        `state` round-trips through Google back to GmailCallbackView (a
        signed, timestamped user id -- see core/views/gmail.py) so the
        credential created on callback can be attributed to the advocate
        who started the flow, even though the callback itself is
        necessarily unauthenticated (a top-level browser redirect from
        Google, not a token-bearing frontend call).
        """
        try:
            from urllib.parse import urlencode

            client_id = getattr(settings, "GMAIL_CLIENT_ID", "")
            redirect_uri = getattr(
                settings,
                "GMAIL_REDIRECT_URI",
                "http://localhost:8000/api/gmail/callback/",
            )

            params = {
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(self.SCOPES),
                "access_type": "offline",
                "prompt": "consent",
                "state": state,
            }

            auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
            return auth_url
        except ImportError:
            raise ImportError(
                "google-auth-oauthlib is required. "
                "Install it with: pip install google-auth-oauthlib"
            )

    def handle_oauth_callback(self, authorization_code: str, owner) -> GmailCredential:
        """Exchange authorization code for tokens and store credentials."""
        import requests
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        # Exchange authorization code for tokens
        token_url = "https://oauth2.googleapis.com/token"
        data = {
            "code": authorization_code,
            "client_id": getattr(settings, "GMAIL_CLIENT_ID", ""),
            "client_secret": getattr(settings, "GMAIL_CLIENT_SECRET", ""),
            "redirect_uri": getattr(
                settings,
                "GMAIL_REDIRECT_URI",
                "http://localhost:8000/api/gmail/callback/",
            ),
            "grant_type": "authorization_code",
        }
        
        response = requests.post(token_url, data=data)
        response.raise_for_status()
        token_data = response.json()
        
        # Create credentials object
        creds = Credentials(
            token=token_data.get("access_token"),
            refresh_token=token_data.get("refresh_token"),
            token_uri=token_url,
            client_id=data["client_id"],
            client_secret=data["client_secret"],
            scopes=self.SCOPES,
        )

        # Get user email
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        email_address = profile["emailAddress"]

        # Calculate token expiry
        if creds.expiry:
            token_expiry = creds.expiry
        else:
            token_expiry = datetime.now() + timedelta(hours=1)

        # Store or update credentials. email_address is globally unique on
        # this model (one row per Gmail inbox), so if it's already claimed
        # by a DIFFERENT advocate we refuse to silently reassign it to the
        # user who just completed this OAuth flow -- that would hand one
        # user's connected inbox to someone else.
        existing = GmailCredential.objects.filter(email_address=email_address).first()
        if existing is not None and existing.owner_id != owner.id:
            raise ValueError(
                f"{email_address} is already connected to a different Case Intel account."
            )

        credential, created = GmailCredential.objects.update_or_create(
            email_address=email_address,
            defaults={
                "owner": owner,
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
        owner,
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
                owner=owner,
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
                owner=email.owner,
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
