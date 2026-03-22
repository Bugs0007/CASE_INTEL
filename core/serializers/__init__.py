"""
DRF serializers for the Case Intel API.

Re-exports all serializers from domain-specific modules so that
existing imports like ``from core.serializers import CaseSerializer``
continue to work.
"""

from .case import CaseSerializer
from .chat import (
    ChatRequestSerializer,
    ChatResponseSerializer,
    CitationSerializer,
    MessageSerializer,
)
from .conversation import ConversationDetailSerializer, ConversationListSerializer
from .document import DocumentSerializer, DocumentUploadSerializer
from .hearing import HearingSerializer

__all__ = [
    "CaseSerializer",
    "ChatRequestSerializer",
    "ChatResponseSerializer",
    "CitationSerializer",
    "ConversationDetailSerializer",
    "ConversationListSerializer",
    "DocumentSerializer",
    "DocumentUploadSerializer",
    "HearingSerializer",
    "MessageSerializer",
]
