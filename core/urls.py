"""
URL routing for the core application API.

All endpoints are prefixed with /api/ when included in the project root URLconf.
"""

from django.urls import path

from core.views import (
    AdvocateProfileView,
    AdvocateSearchImportStatusView,
    AdvocateSearchImportView,
    AdvocateSearchPreferenceView,
    AdvocateSearchRetryFailedView,
    AdvocateSearchStatusView,
    AdvocateSearchView,
    AppearanceFeeDetailView,
    AppearanceFeeInvoiceFileView,
    AppearanceFeeInvoiceView,
    AppearanceFeeListCreateView,
    AppearanceFeeMarkPaidView,
    AppearanceFeeSendView,
    CaseCnrCreateView,
    CaseCnrLookupView,
    CaseDetailView,
    CaseListView,
    CaseOrdersView,
    CaseTrackingConfirmView,
    CaseTrackingPreviewView,
    CaseTrackingRefreshView,
    CaseTrackingView,
    ChangePasswordView,
    ChangeUsernameView,
    ChatView,
    ClientContactDetailView,
    ClientContactListCreateView,
    ConversationDetailView,
    ConversationExportView,
    ConversationListView,
    ConversationMessagesView,
    CourtOrderFileView,
    CourtStructureView,
    DashboardView,
    DocumentDetailView,
    DocumentDownloadView,
    DocumentListView,
    DocumentProcessView,
    DocumentUploadView,
    EmailLinkView,
    EmailListView,
    FolderListView,
    GmailAuthView,
    GmailCallbackView,
    GmailStatusView,
    GmailSyncView,
    HearingDetailView,
    HearingListCreateView,
    InviteValidateView,
    LoginView,
    LogoutView,
    RegisterView,
    TravelBookingDetailView,
    TravelBookingFileView,
    TravelBookingListCreateView,
    TravelBookingUploadView,
    UpcomingHearingsView,
)

app_name = "core"

urlpatterns = [
    # Auth. Registration requires a live InviteToken -- the owner generates
    # one from Django admin and emails the link (see core/views/auth.py).
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path(
        "auth/invite/<str:token>/",
        InviteValidateView.as_view(),
        name="auth-invite-validate",
    ),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path(
        "auth/change-username/",
        ChangeUsernameView.as_view(),
        name="auth-change-username",
    ),
    path(
        "auth/change-password/",
        ChangePasswordView.as_view(),
        name="auth-change-password",
    ),

    # Dashboard
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path(
        "dashboard/upcoming-hearings/",
        UpcomingHearingsView.as_view(),
        name="dashboard-upcoming-hearings",
    ),

    # Chat
    path("chat/", ChatView.as_view(), name="chat"),

    # Conversations
    path("conversations/", ConversationListView.as_view(), name="conversation-list"),
    path(
        "conversations/<int:pk>/",
        ConversationDetailView.as_view(),
        name="conversation-detail",
    ),
    path(
        "conversations/<int:pk>/messages/",
        ConversationMessagesView.as_view(),
        name="conversation-messages",
    ),
    path(
        "conversations/<int:pk>/export/",
        ConversationExportView.as_view(),
        name="conversation-export",
    ),

    # Cases
    path("cases/", CaseListView.as_view(), name="case-list"),
    path("cases/<int:pk>/", CaseDetailView.as_view(), name="case-detail"),
    path(
        "cases/<int:pk>/orders/",
        CaseOrdersView.as_view(),
        name="case-orders",
    ),
    path(
        "cases/<int:pk>/tracking/",
        CaseTrackingView.as_view(),
        name="case-tracking",
    ),
    path(
        "cases/<int:pk>/tracking/preview/",
        CaseTrackingPreviewView.as_view(),
        name="case-tracking-preview",
    ),
    path(
        "cases/<int:pk>/tracking/confirm/",
        CaseTrackingConfirmView.as_view(),
        name="case-tracking-confirm",
    ),
    path(
        "cases/<int:pk>/tracking/refresh/",
        CaseTrackingRefreshView.as_view(),
        name="case-tracking-refresh",
    ),

    # "Track by CNR" quick-add (manual case entry page): a case-less CNR
    # fetch/preview, then a confirm step that creates the Case itself --
    # unlike the tracking/preview|confirm routes above, which require an
    # already-existing case.
    path(
        "cases/cnr-lookup/",
        CaseCnrLookupView.as_view(),
        name="case-cnr-lookup",
    ),
    path(
        "cases/cnr-lookup/create/",
        CaseCnrCreateView.as_view(),
        name="case-cnr-lookup-create",
    ),

    # Court structure (eCourts hierarchy discovery for the tracking form)
    path("court-structure/", CourtStructureView.as_view(), name="court-structure"),

    # Advocate search (search-by-name/bar-code + bulk import, secondary to
    # the manual CNR entry above)
    path("cases/search-advocate/", AdvocateSearchView.as_view(), name="advocate-search"),
    path(
        "cases/search-advocate/import/",
        AdvocateSearchImportView.as_view(),
        name="advocate-search-import",
    ),
    path(
        "cases/search-advocate/import/<int:job_id>/",
        AdvocateSearchImportStatusView.as_view(),
        name="advocate-search-import-status",
    ),
    path(
        "cases/search-advocate/preference/",
        AdvocateSearchPreferenceView.as_view(),
        name="advocate-search-preference",
    ),
    # Status poll for a state-wide search job. Placed after the literal
    # "import/"/"preference/" routes above; <int:job_id> can't match those
    # strings anyway, but order keeps it unambiguous.
    path(
        "cases/search-advocate/<int:job_id>/",
        AdvocateSearchStatusView.as_view(),
        name="advocate-search-status",
    ),
    path(
        "cases/search-advocate/<int:job_id>/retry-failed/",
        AdvocateSearchRetryFailedView.as_view(),
        name="advocate-search-retry-failed",
    ),

    # Hearings
    path("hearings/", HearingListCreateView.as_view(), name="hearing-list"),
    path("hearings/<int:pk>/", HearingDetailView.as_view(), name="hearing-detail"),

    # Advocate billing profile (invoice letterhead + default fee). A
    # singleton per user -- no id in the path, see AdvocateProfileView.
    path("advocate-profile/", AdvocateProfileView.as_view(), name="advocate-profile"),

    # Appearance fees + invoicing. The literal "invoice/file/" route is
    # listed before "invoice/" only for readability; they can't shadow
    # each other (different trailing segments).
    path(
        "appearance-fees/",
        AppearanceFeeListCreateView.as_view(),
        name="appearance-fee-list",
    ),
    path(
        "appearance-fees/<int:pk>/",
        AppearanceFeeDetailView.as_view(),
        name="appearance-fee-detail",
    ),
    path(
        "appearance-fees/<int:pk>/invoice/",
        AppearanceFeeInvoiceView.as_view(),
        name="appearance-fee-invoice",
    ),
    path(
        "appearance-fees/<int:pk>/invoice/file/",
        AppearanceFeeInvoiceFileView.as_view(),
        name="appearance-fee-invoice-file",
    ),
    path(
        "appearance-fees/<int:pk>/send/",
        AppearanceFeeSendView.as_view(),
        name="appearance-fee-send",
    ),
    path(
        "appearance-fees/<int:pk>/mark-paid/",
        AppearanceFeeMarkPaidView.as_view(),
        name="appearance-fee-mark-paid",
    ),

    # Travel/hotel bookings. "upload/" is declared before the
    # <int:pk> detail route so it can never be swallowed by it.
    path(
        "travel-bookings/",
        TravelBookingListCreateView.as_view(),
        name="travel-booking-list",
    ),
    path(
        "travel-bookings/upload/",
        TravelBookingUploadView.as_view(),
        name="travel-booking-upload",
    ),
    path(
        "travel-bookings/<int:pk>/",
        TravelBookingDetailView.as_view(),
        name="travel-booking-detail",
    ),
    path(
        "travel-bookings/<int:pk>/file/",
        TravelBookingFileView.as_view(),
        name="travel-booking-file",
    ),

    # Client contacts
    path("client-contacts/", ClientContactListCreateView.as_view(), name="client-contact-list"),
    path(
        "client-contacts/<int:pk>/",
        ClientContactDetailView.as_view(),
        name="client-contact-detail",
    ),

    # Documents
    path("documents/", DocumentListView.as_view(), name="document-list"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("documents/upload/", DocumentUploadView.as_view(), name="document-upload"),
    path(
        "documents/<int:pk>/process/",
        DocumentProcessView.as_view(),
        name="document-process",
    ),
    path(
        "documents/<int:pk>/download/",
        DocumentDownloadView.as_view(),
        name="document-download",
    ),

    # Court orders (the PDF itself is streamed by this view, never exposed
    # as a storage URL -- see CourtOrderFileView)
    path("orders/<int:pk>/file/", CourtOrderFileView.as_view(), name="court-order-file"),

    # Folders
    path("folders/", FolderListView.as_view(), name="folder-list"),

    # Gmail
    path("gmail/auth/", GmailAuthView.as_view(), name="gmail-auth"),
    path("gmail/callback/", GmailCallbackView.as_view(), name="gmail-callback"),
    path("gmail/status/", GmailStatusView.as_view(), name="gmail-status"),
    path("gmail/sync/", GmailSyncView.as_view(), name="gmail-sync"),

    # Emails
    path("emails/", EmailListView.as_view(), name="email-list"),
    path("emails/<int:pk>/link/", EmailLinkView.as_view(), name="email-link"),
]
