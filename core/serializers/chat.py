"""
Serializers for the AI chat workflow.
"""

from rest_framework import serializers

from core.models import Citation, Message


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
