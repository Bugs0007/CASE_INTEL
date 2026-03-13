"""
DRF serializers for the Case Intel API.

Covers: Chat, Conversations, Cases, Documents.
"""

from rest_framework import serializers

from core.models import Case, Citation, Conversation, Document, Message


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
    conversation_id = serializers.IntegerField(allow_null=True)
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


# ------------------------------------------------------------------
# Cases
# ------------------------------------------------------------------


class CaseSerializer(serializers.ModelSerializer):
    document_count = serializers.SerializerMethodField()

    class Meta:
        model = Case
        fields = [
            "id",
            "case_number",
            "title",
            "client_name",
            "opposing_party",
            "case_type",
            "status",
            "priority",
            "filing_date",
            "notes",
            "created_at",
            "document_count",
        ]
        read_only_fields = ["id", "created_at"]

    def get_document_count(self, obj: Case) -> int:
        return obj.documents.count()


# ------------------------------------------------------------------
# Documents
# ------------------------------------------------------------------


class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = [
            "id",
            "case_id",
            "filename",
            "file_path",
            "file_type",
            "file_size",
            "document_type",
            "document_date",
            "processing_status",
            "chunk_count",
            "created_at",
        ]
        read_only_fields = ["id", "created_at", "processing_status", "chunk_count"]


ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "txt", "docx", "doc"}
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class DocumentUploadSerializer(serializers.Serializer):
    """Validates document upload requests."""

    file = serializers.FileField()
    case_id = serializers.IntegerField(required=False, allow_null=True)
    document_type = serializers.ChoiceField(
        choices=[c[0] for c in Document.DOCUMENT_TYPE_CHOICES],
        required=False,
        default="other",
    )

    def validate_file(self, value):
        # Validate extension
        filename = value.name
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_UPLOAD_EXTENSIONS:
            raise serializers.ValidationError(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_UPLOAD_EXTENSIONS))}"
            )

        # Validate file size
        if value.size > MAX_UPLOAD_SIZE_BYTES:
            max_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
            raise serializers.ValidationError(
                f"File size exceeds the {max_mb} MB limit."
            )

        return value
