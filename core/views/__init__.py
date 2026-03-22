"""
REST API views for the Case Intel application.

Re-exports all views from domain-specific modules so that
existing imports like ``from core.views import ChatView``
continue to work.
"""

from .case import CaseDetailView, CaseListCreateView
from .chat import ChatView
from .conversation import ConversationDetailView, ConversationListView
from .dashboard import DashboardView
from .document import (
    DocumentDetailView,
    DocumentListView,
    DocumentProcessView,
    DocumentUploadView,
)
from .gmail import (
    EmailLinkView,
    EmailListView,
    GmailAuthView,
    GmailCallbackView,
    GmailStatusView,
    GmailSyncView,
)

__all__ = [
    "CaseDetailView",
    "CaseListCreateView",
    "ChatView",
    "ConversationDetailView",
    "ConversationListView",
    "DashboardView",
    "DocumentDetailView",
    "DocumentListView",
    "DocumentProcessView",
    "DocumentUploadView",
    "EmailLinkView",
    "EmailListView",
    "GmailAuthView",
    "GmailCallbackView",
    "GmailStatusView",
    "GmailSyncView",
]
