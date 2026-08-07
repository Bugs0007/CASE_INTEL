"""
Serializer for court orders fetched from the court portal.
"""

from rest_framework import serializers

from core.models import CourtOrder

from .order_summary import build_order_summary


class CourtOrderSerializer(serializers.ModelSerializer):
    """Read-only view of a CourtOrder for the hearing-card order list.

    Deliberately exposes NO storage location: the PDF is reachable only
    through GET /api/orders/<id>/file/, which re-checks ownership and
    streams the bytes. Document.file_path (a storage key that resolves
    under MEDIA_ROOT or as an S3 object key) never leaves the backend.
    """

    filename = serializers.CharField(source="document.filename", read_only=True, default=None)
    file_size = serializers.IntegerField(source="document.file_size", read_only=True, default=None)
    processing_status = serializers.CharField(
        source="document.processing_status", read_only=True, default=None
    )
    # document is nullable (SET_NULL) -- the frontend uses this to decide
    # whether an order is openable at all.
    has_file = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()

    class Meta:
        model = CourtOrder
        fields = [
            "id",
            "order_number",
            "order_date",
            "description",
            "judge",
            "source",
            "has_file",
            "filename",
            "file_size",
            "processing_status",
            "summary",
            "created_at",
        ]
        read_only_fields = fields

    def get_has_file(self, obj) -> bool:
        return obj.document_id is not None

    def get_summary(self, obj) -> dict:
        """The Order Overview, rendered from THIS advocate's point of
        view. Shared with HearingSerializer so the calendar entry and the
        case page can't drift apart -- see build_order_summary."""
        return build_order_summary(obj)
