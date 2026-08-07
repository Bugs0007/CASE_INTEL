"""
REST API views for the Case Intel application.

Re-exports all views from domain-specific modules so that
existing imports like ``from core.views import ChatView``
continue to work.
"""

from .advocate_profile import AdvocateProfileView
from .advocate_search import (
    AdvocateSearchImportStatusView,
    AdvocateSearchImportView,
    AdvocateSearchPreferenceView,
    AdvocateSearchRetryFailedView,
    AdvocateSearchStatusView,
    AdvocateSearchView,
)
from .appearance_fee import (
    AppearanceFeeDetailView,
    AppearanceFeeInvoiceFileView,
    AppearanceFeeInvoiceView,
    AppearanceFeeListCreateView,
    AppearanceFeeMarkPaidView,
    AppearanceFeeSendView,
)
from .auth import LoginView, LogoutView, RegisterView
from .case import CaseDetailView, CaseListView
from .case_tracking import (
    CaseTrackingConfirmView,
    CaseTrackingPreviewView,
    CaseTrackingRefreshView,
    CaseTrackingView,
    CourtStructureView,
)
from .chat import ChatView
from .client_contact import ClientContactDetailView, ClientContactListCreateView
from .conversation import (
    ConversationDetailView,
    ConversationExportView,
    ConversationListView,
    ConversationMessagesView,
)
from .court_order import CaseOrdersView, CourtOrderFileView
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
from .travel_booking import (
    TravelBookingDetailView,
    TravelBookingFileView,
    TravelBookingListCreateView,
    TravelBookingUploadView,
)

__all__ = [
    "AdvocateProfileView",
    "AppearanceFeeDetailView",
    "AppearanceFeeInvoiceFileView",
    "AppearanceFeeInvoiceView",
    "AppearanceFeeListCreateView",
    "AppearanceFeeMarkPaidView",
    "AppearanceFeeSendView",
    "TravelBookingDetailView",
    "TravelBookingFileView",
    "TravelBookingListCreateView",
    "TravelBookingUploadView",
    "AdvocateSearchImportStatusView",
    "AdvocateSearchImportView",
    "AdvocateSearchPreferenceView",
    "AdvocateSearchRetryFailedView",
    "AdvocateSearchStatusView",
    "AdvocateSearchView",
    "CaseDetailView",
    "CaseListView",
    "CaseOrdersView",
    "CaseTrackingConfirmView",
    "CaseTrackingPreviewView",
    "CaseTrackingRefreshView",
    "CaseTrackingView",
    "ChatView",
    "ClientContactDetailView",
    "ClientContactListCreateView",
    "ConversationDetailView",
    "ConversationExportView",
    "ConversationListView",
    "ConversationMessagesView",
    "CourtOrderFileView",
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
