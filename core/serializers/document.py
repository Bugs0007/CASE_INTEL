"""
Serializers for documents and document uploads.
"""

from rest_framework import serializers

from core.models import Document, Case, Folder


ALLOWED_UPLOAD_EXTENSIONS = {"pdf", "txt", "docx", "doc"}
MAX_UPLOAD_SIZE_BYTES = 50 * 1024 * 1024  # 50 MB


class CaseNestedSerializer(serializers.ModelSerializer):
    """Nested case serializer for document editing with inline case title editing."""
    
    class Meta:
        model = Case
        fields = ["id", "title", "case_number", "client_name"]
        extra_kwargs = {
            "case_number": {"read_only": True},  # Case number should not be editable
            "client_name": {"read_only": True},  # Keep client name read-only for now
        }


class DocumentSerializer(serializers.ModelSerializer):
    # Add nested case serializer for inline editing
    case = CaseNestedSerializer(required=False, allow_null=True)

    # Add case_title as a separate field for backward compatibility
    case_title = serializers.CharField(source='case.title', read_only=True, required=False)

    # Add folder name for display
    folder_name = serializers.CharField(source='folder.name', read_only=True, required=False)

    # Latest background ProcessingJob (queued/running progress for the
    # frontend). Views prefetch processing_jobs newest-first (see
    # _with_latest_jobs in core/views/document.py) so these don't N+1.
    job_status = serializers.SerializerMethodField()
    job_progress_current = serializers.SerializerMethodField()
    job_progress_total = serializers.SerializerMethodField()
    job_error = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "case_id",
            "case",
            "case_title",
            "folder",
            "folder_name",
            "filename",
            "file_path",
            "file_type",
            "file_size",
            "document_type",
            "document_date",
            "processing_status",
            "chunk_count",
            "ocr_applied",
            "job_status",
            "job_progress_current",
            "job_progress_total",
            "job_error",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "processing_status",
            "chunk_count",
            "ocr_applied",
            "file_path",  # File path should not be user-editable
            "file_type",  # File type is determined by the file
            "file_size",  # File size is determined by the file
        ]

    def _latest_job(self, obj):
        if not hasattr(obj, "_latest_job_cache"):
            # Prefetched newest-first by the document views; fall back to
            # an explicit query for non-prefetched callers.
            prefetched = getattr(obj, "_prefetched_objects_cache", {}).get("processing_jobs")
            if prefetched is not None:
                obj._latest_job_cache = prefetched[0] if prefetched else None
            else:
                obj._latest_job_cache = (
                    obj.processing_jobs.order_by("-created_at").first()
                )
        return obj._latest_job_cache

    def get_job_status(self, obj):
        job = self._latest_job(obj)
        return job.status if job else None

    def get_job_progress_current(self, obj):
        job = self._latest_job(obj)
        return job.progress_current if job else None

    def get_job_progress_total(self, obj):
        job = self._latest_job(obj)
        return job.progress_total if job else None

    def get_job_error(self, obj):
        job = self._latest_job(obj)
        return (job.error or None) if job else None
    
    def update(self, instance, validated_data):
        # Handle nested case update
        case_data = validated_data.pop('case', None)
        
        # Update the document instance
        instance = super().update(instance, validated_data)
        
        # Update the related case if case data is provided and case exists
        if case_data and instance.case:
            case_serializer = CaseNestedSerializer(instance.case, data=case_data, partial=True)
            if case_serializer.is_valid():
                case_serializer.save()
        
        return instance
    
    def to_representation(self, instance):
        # Get the standard representation
        data = super().to_representation(instance)
        
        # If case exists, include nested case data
        if instance.case:
            data['case'] = CaseNestedSerializer(instance.case).data
            
        return data


class DocumentUploadSerializer(serializers.Serializer):
    """Validates document upload requests."""

    file = serializers.FileField()
    case_id = serializers.IntegerField(required=False, allow_null=True)
    folder_id = serializers.IntegerField(required=False, allow_null=True)
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
    
    def validate_case_id(self, value):
        if value is not None and not Case.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Case with id {value} does not exist.")
        return value
    
    def validate_folder_id(self, value):
        if value is not None and not Folder.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"Folder with id {value} does not exist.")
        return value
