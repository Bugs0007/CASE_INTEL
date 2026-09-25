"""
REST API views for the Case Intel application.

Re-exports all views from domain-specific modules so that
existing imports like ``from core.views import ChatView``
continue to work.
"""

from .advocate_profile import AdvocateProfileView
from .advocate_search import (
    AdvocateSearchActiveListView,
    AdvocateSearchCancelView,
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
from .auth import (
    ChangePasswordView,
    ChangeUsernameView,
    InviteValidateView,
    LoginView,
    LogoutView,
    RegisterView,
    SessionDetailView,
    SessionListView,
    SessionRevokeOthersView,
)
from .case import CaseDetailView, CaseListView
from .case_tracking import (
    CaseCnrCreateView,
    CaseCnrLookupView,
    CaseTrackingConfirmView,
    CaseTrackingPreviewView,
    CaseTrackingRefreshView,
    CaseTrackingView,
    CourtStructureView,
)
from .bulk_refresh import (
    TrackingRefreshCancelView,
    TrackingRefreshStatusView,
    TrackingRefreshView,
)
from .chat import ChatView
from .client import (
    BillingPortfolioView,
    ClientDetailView,
    ClientListCreateView,
    ClientStatementPdfView,
)
from .client_contact import ClientContactDetailView, ClientContactListCreateView
from .client_message import (
    ClientMessageDetailView,
    ClientMessageListView,
    ClientMessageSendView,
    SentMessageListView,
)
from .doc_template import CaseGenerateDocumentView, DocTemplateListView
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
from .limitation import (
    CaseLimitationDeadlineView,
    LimitationComputeView,
    LimitationRulesView,
)
from .hearing_digest import (
    HearingDigestBriefingView,
    HearingDigestPdfView,
    HearingDigestView,
)
from .task import TaskDetailView, TaskListCreateView
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
    "BillingPortfolioView",
    "CaseGenerateDocumentView",
    "ClientDetailView",
    "ClientListCreateView",
    "ClientMessageDetailView",
    "ClientMessageListView",
    "ClientMessageSendView",
    "ClientStatementPdfView",
    "DocTemplateListView",
    "SentMessageListView",
    "TrackingRefreshCancelView",
    "TrackingRefreshStatusView",
    "TrackingRefreshView",
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
    "AdvocateSearchActiveListView",
    "AdvocateSearchCancelView",
    "AdvocateSearchImportStatusView",
    "AdvocateSearchImportView",
    "AdvocateSearchPreferenceView",
    "AdvocateSearchRetryFailedView",
    "AdvocateSearchStatusView",
    "AdvocateSearchView",
    "CaseCnrCreateView",
    "CaseCnrLookupView",
    "CaseDetailView",
    "CaseListView",
    "CaseOrdersView",
    "CaseTrackingConfirmView",
    "CaseTrackingPreviewView",
    "CaseTrackingRefreshView",
    "CaseTrackingView",
    "ChangePasswordView",
    "ChangeUsernameView",
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
    "HearingDigestBriefingView",
    "HearingDigestPdfView",
    "HearingDigestView",
    "HearingListCreateView",
    "InviteValidateView",
    "CaseLimitationDeadlineView",
    "LimitationComputeView",
    "LimitationRulesView",
    "LoginView",
    "LogoutView",
    "SessionDetailView",
    "SessionListView",
    "SessionRevokeOthersView",
    "RegisterView",
    "TaskDetailView",
    "TaskListCreateView",
    "UpcomingHearingsView",
]
