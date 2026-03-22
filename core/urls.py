"""
URL routing for the core application API.

All endpoints are prefixed with /api/ when included in the project root URLconf.
"""

from django.urls import path

from core.views import (
    CaseDetailView,
    CaseListCreateView,
    ChatView,
    ConversationDetailView,
    ConversationListView,
    DashboardView,
    DocumentDetailView,
    DocumentListView,
    DocumentProcessView,
    DocumentUploadView,
    EmailLinkView,
    EmailListView,
    GmailAuthView,
    GmailCallbackView,
    GmailStatusView,
    GmailSyncView,
)

app_name = "core"

urlpatterns = [
    # Dashboard
    path("dashboard/", DashboardView.as_view(), name="dashboard"),

    # Chat
    path("chat/", ChatView.as_view(), name="chat"),

    # Conversations
    path("conversations/", ConversationListView.as_view(), name="conversation-list"),
    path(
        "conversations/<int:pk>/",
        ConversationDetailView.as_view(),
        name="conversation-detail",
    ),

    # Cases
    path("cases/", CaseListCreateView.as_view(), name="case-list"),
    path("cases/<int:pk>/", CaseDetailView.as_view(), name="case-detail"),

    # Documents
    path("documents/", DocumentListView.as_view(), name="document-list"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("documents/upload/", DocumentUploadView.as_view(), name="document-upload"),
    path(
        "documents/<int:pk>/process/",
        DocumentProcessView.as_view(),
        name="document-process",
    ),

    # Gmail
    path("gmail/auth/", GmailAuthView.as_view(), name="gmail-auth"),
    path("gmail/callback/", GmailCallbackView.as_view(), name="gmail-callback"),
    path("gmail/status/", GmailStatusView.as_view(), name="gmail-status"),
    path("gmail/sync/", GmailSyncView.as_view(), name="gmail-sync"),

    # Emails
    path("emails/", EmailListView.as_view(), name="email-list"),
    path("emails/<int:pk>/link/", EmailLinkView.as_view(), name="email-link"),
]
