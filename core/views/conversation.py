"""
Conversation views — list, retrieve, and delete conversations.
"""

from django.db.models import Count
from rest_framework import generics

from core.models import Conversation
from core.serializers import ConversationDetailSerializer, ConversationListSerializer


class ConversationListView(generics.ListAPIView):
    """List conversations, optionally filtered by case_id.

    GET /api/conversations/
    GET /api/conversations/?case_id=1
    """

    serializer_class = ConversationListSerializer

    def get_queryset(self):
        qs = Conversation.objects.annotate(message_count=Count("messages"))
        case_id = self.request.query_params.get("case_id")
        if case_id is not None:
            qs = qs.filter(case_id=case_id)
        return qs


class ConversationDetailView(generics.RetrieveDestroyAPIView):
    """Retrieve or delete a conversation with its messages.

    GET    /api/conversations/<id>/
    DELETE /api/conversations/<id>/
    """

    serializer_class = ConversationDetailSerializer
    queryset = Conversation.objects.prefetch_related("messages__citations")
