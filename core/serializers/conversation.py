"""
Serializers for conversations and messages.
"""

from rest_framework import serializers

from core.models import Conversation
from core.services.conversation_utils import (
    get_conversation_preview,
    get_display_title,
)

from .chat import MessageSerializer


class ConversationListSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    message_count = serializers.IntegerField(read_only=True)
    preview = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            "id",
            "case_id",
            "title",
            "started_at",
            "last_message_at",
            "message_count",
            "preview",
        ]

    def get_title(self, obj: Conversation) -> str:
        return get_display_title(obj)

    def get_preview(self, obj: Conversation) -> str:
        return get_conversation_preview(obj)


class ConversationDetailSerializer(serializers.ModelSerializer):
    title = serializers.SerializerMethodField()
    messages = MessageSerializer(many=True, read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "case_id",
            "title",
            "started_at",
            "last_message_at",
            "messages",
        ]

    def get_title(self, obj: Conversation) -> str:
        return get_display_title(obj)
