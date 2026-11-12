"""Routes mounted under /api/ by core/urls.py."""
from django.urls import path

from core.views.case_assistant_outputs import (
    CaseNoteDetailView,
    CaseNoteListView,
    DraftApproveView,
    DraftOutputCreateView,
    DraftOutputDownloadView,
)

urlpatterns = [
    path(
        "case-assistant/drafts/<int:pk>/approve/",
        DraftApproveView.as_view(),
        name="case-assistant-draft-approve",
    ),
    path(
        "case-assistant/drafts/<int:pk>/outputs/",
        DraftOutputCreateView.as_view(),
        name="case-assistant-draft-outputs",
    ),
    path(
        "case-assistant/outputs/<int:pk>/download/",
        DraftOutputDownloadView.as_view(),
        name="case-assistant-output-download",
    ),
    path("cases/<int:case_id>/notes/", CaseNoteListView.as_view(), name="case-notes"),
    path("case-notes/<int:pk>/", CaseNoteDetailView.as_view(), name="case-note-detail"),
]
