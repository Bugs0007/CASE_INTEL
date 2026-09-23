"""
DRF serializers for the Case Intel API.

Re-exports all serializers from domain-specific modules so that
existing imports like ``from core.serializers import CaseSerializer``
continue to work.
"""

from .advocate_profile import AdvocateProfileSerializer
from .appearance_fee import AppearanceFeeSerializer, NestedAppearanceFeeSerializer
from .case import CaseCnrCreateSerializer, CaseCreateSerializer, CaseSerializer
from .chat import (
    ChatRequestSerializer,
    CitationSerializer,
    MessageSerializer,
)
from .client import (
    ClientMessageSerializer,
    ClientSerializer,
    ClientSummarySerializer,
    SentMessageSerializer,
)
from .client_contact import ClientContactSerializer
from .conversation import ConversationDetailSerializer, ConversationListSerializer
from .court_order import CourtOrderSerializer
from .document import DocumentSerializer, DocumentUploadSerializer
from .hearing import HearingSerializer
from .task import TaskSerializer
from .travel_booking import (
    NestedTravelBookingSerializer,
    TravelBookingSerializer,
    TravelBookingUploadSerializer,
)

__all__ = [
    "AdvocateProfileSerializer",
    "AppearanceFeeSerializer",
    "NestedAppearanceFeeSerializer",
    "NestedTravelBookingSerializer",
    "TravelBookingSerializer",
    "TravelBookingUploadSerializer",
    "CaseCnrCreateSerializer",
    "CaseCreateSerializer",
    "CaseSerializer",
    "ChatRequestSerializer",
    "CitationSerializer",
    "ClientContactSerializer",
    "ClientMessageSerializer",
    "ClientSerializer",
    "ClientSummarySerializer",
    "SentMessageSerializer",
    "ConversationDetailSerializer",
    "ConversationListSerializer",
    "CourtOrderSerializer",
    "DocumentSerializer",
    "DocumentUploadSerializer",
    "HearingSerializer",
    "MessageSerializer",
    "TaskSerializer",
]
