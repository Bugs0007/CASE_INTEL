"""
DRF serializers for the Case Intel conversation API.
"""

from rest_framework import serializers

from core.models import Citation, Conversation, Message


class ChatRequestSerializer(serializers.Serializer):
    """Validates incoming chat requests."""

    query = serializers.CharField(
        max_length=5000,
        help_text="The user's legal question.",
    )
    case_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Optional case ID to scope the search.",
    )
    conversation_id = serializers.IntegerField(
        required=False,
        allow_null=True,
        help_text="Optional conversation ID to continue an existing conversation.",
    )


class CitationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Citation
        fields = [
            "id",
            "source_type",
            "document_id",
            "chunk_id",
            "citation_text",
            "created_at",
        ]


class MessageSerializer(serializers.ModelSerializer):
    citations = CitationSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = ["id", "role", "content", "created_at", "citations"]


class ChatResponseSerializer(serializers.Serializer):
    """Serializes AI workflow responses."""

    answer = serializers.CharField()
    confidence = serializers.FloatField()
    query_type = serializers.CharField()
    requires_clarification = serializers.BooleanField()
    clarification_question = serializers.CharField(
        allow_null=True, allow_blank=True
    )
    message_id = serializers.IntegerField(allow_null=True)
    conversation_id = serializers.IntegerField()
    citations = serializers.ListField(child=serializers.DictField())


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
