"""
REST API views for the Case Intel application.

Re-exports all views from domain-specific modules so that
existing imports like ``from core.views import ChatView``
continue to work.
"""

from .case import CaseDetailView, CaseListCreateView
from .chat import ChatView
from .conversation import ConversationDetailView, ConversationListView
from .document import (
    DocumentDetailView,
    DocumentListView,
    DocumentProcessView,
    DocumentUploadView,
)

__all__ = [
    "CaseDetailView",
    "CaseListCreateView",
    "ChatView",
    "ConversationDetailView",
    "ConversationListView",
    "DocumentDetailView",
    "DocumentListView",
    "DocumentProcessView",
    "DocumentUploadView",
]
