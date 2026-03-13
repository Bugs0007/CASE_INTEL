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
    DocumentDetailView,
    DocumentListView,
    DocumentProcessView,
    DocumentUploadView,
)

app_name = "core"

urlpatterns = [
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
]
