"""
URL routing for the core application API.

All endpoints are prefixed with /api/ when included in the project root URLconf.
"""

from django.urls import path

from core.views import (
    CaseDetailView,
    CaseListCreateView,
    CaseTrackingRefreshView,
    CaseTrackingSetupView,
    ChatView,
    ConversationDetailView,
    ConversationExportView,
    ConversationListView,
    ConversationMessagesView,
    CourtStructureView,
    DashboardView,
    DocumentDetailView,
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
    LoginView,
    UpcomingHearingsView,
)

app_name = "core"

urlpatterns = [
    # Auth
    path("auth/login/", LoginView.as_view(), name="auth-login"),

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
    path("cases/", CaseListCreateView.as_view(), name="case-list"),
    path("cases/<int:pk>/", CaseDetailView.as_view(), name="case-detail"),
    path(
        "cases/<int:pk>/tracking/",
        CaseTrackingSetupView.as_view(),
        name="case-tracking-setup",
    ),
    path(
        "cases/<int:pk>/tracking/refresh/",
        CaseTrackingRefreshView.as_view(),
        name="case-tracking-refresh",
    ),

    # Court structure (eCourts hierarchy discovery for the tracking form)
    path("court-structure/", CourtStructureView.as_view(), name="court-structure"),

    # Hearings
    path("hearings/", HearingListCreateView.as_view(), name="hearing-list"),
    path("hearings/<int:pk>/", HearingDetailView.as_view(), name="hearing-detail"),

    # Documents
    path("documents/", DocumentListView.as_view(), name="document-list"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("documents/upload/", DocumentUploadView.as_view(), name="document-upload"),
    path(
        "documents/<int:pk>/process/",
        DocumentProcessView.as_view(),
        name="document-process",
    ),

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
