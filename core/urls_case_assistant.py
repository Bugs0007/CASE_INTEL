"""Routes mounted under /api/ by core/urls.py."""
from django.urls import path

from core.views.case_assistant import (
    DraftDetailView,
    DraftListCreateView,
    DraftRetryView,
    DraftRevisionCreateView,
    DraftRevisionDetailView,
)

urlpatterns = [
    path("case-assistant/drafts/", DraftListCreateView.as_view(), name="case-assistant-drafts"),
    path("case-assistant/drafts/<int:pk>/", DraftDetailView.as_view(), name="case-assistant-draft"),
    path(
        "case-assistant/drafts/<int:pk>/revisions/",
        DraftRevisionCreateView.as_view(),
        name="case-assistant-revisions",
    ),
    path(
        "case-assistant/drafts/<int:pk>/revisions/<int:version>/",
        DraftRevisionDetailView.as_view(),
        name="case-assistant-revision",
    ),
    path("case-assistant/drafts/<int:pk>/retry/", DraftRetryView.as_view(), name="case-assistant-retry"),
]
