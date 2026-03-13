"""
Serializers for conversations and messages.
"""

from rest_framework import serializers

from core.models import Conversation

from .chat import MessageSerializer


class ConversationListSerializer(serializers.ModelSerializer):
    message_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "case_id",
            "title",
            "started_at",
            "last_message_at",
            "message_count",
        ]


class ConversationDetailSerializer(serializers.ModelSerializer):
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
