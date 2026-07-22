"""
REST API views for the Case Intel application.

Re-exports all views from domain-specific modules so that
existing imports like ``from core.views import ChatView``
continue to work.
"""

from .auth import LoginView, LogoutView, RegisterView
from .case import CaseDetailView, CaseListCreateView
from .case_tracking import (
    CaseTrackingConfirmView,
    CaseTrackingPreviewView,
    CaseTrackingRefreshView,
    CaseTrackingView,
    CourtStructureView,
)
from .chat import ChatView
from .conversation import (
    ConversationDetailView,
    ConversationExportView,
    ConversationListView,
    ConversationMessagesView,
)
from .dashboard import DashboardView, UpcomingHearingsView
from .document import (
    DocumentDetailView,
    DocumentDownloadView,
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
    "CaseTrackingConfirmView",
    "CaseTrackingPreviewView",
    "CaseTrackingRefreshView",
    "CaseTrackingView",
    "ChatView",
    "ConversationDetailView",
    "ConversationExportView",
    "ConversationListView",
    "ConversationMessagesView",
    "CourtStructureView",
    "DashboardView",
    "DocumentDetailView",
    "DocumentDownloadView",
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
    "LoginView",
    "LogoutView",
    "RegisterView",
    "UpcomingHearingsView",
]
