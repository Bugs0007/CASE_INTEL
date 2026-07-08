"""
REST API views for the Case Intel application.

Re-exports all views from domain-specific modules so that
existing imports like ``from core.views import ChatView``
continue to work.
"""

from .case import CaseDetailView, CaseListCreateView
from .chat import ChatView
from .conversation import (
    ConversationDetailView,
    ConversationExportView,
    ConversationListView,
    ConversationMessagesView,
)
from .dashboard import DashboardView
from .document import (
    DocumentDetailView,
    DocumentListView,
    DocumentProcessView,
    DocumentUploadView,
)
from .folder import FolderListView
from .gmail import (
    EmailLinkView,
    EmailListView,
    GmailAuthView,
    GmailCallbackView,
    GmailStatusView,
    GmailSyncView,
)
from .hearing import HearingDetailView, HearingListCreateView

__all__ = [
    "CaseDetailView",
    "CaseListCreateView",
    "ChatView",
    "ConversationDetailView",
    "ConversationExportView",
    "ConversationListView",
    "ConversationMessagesView",
    "DashboardView",
    "DocumentDetailView",
    "DocumentListView",
    "DocumentProcessView",
    "DocumentUploadView",
    "EmailLinkView",
    "EmailListView",
    "FolderListView",
    "GmailAuthView",
    "GmailCallbackView",
    "GmailStatusView",
    "GmailSyncView",
    "HearingDetailView",
    "HearingListCreateView",
]
