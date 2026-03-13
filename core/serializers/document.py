"""
Serializers for documents and document uploads.
"""

from rest_framework import serializers

from core.models import Document

ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "txt", "docx", "doc"}
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


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
