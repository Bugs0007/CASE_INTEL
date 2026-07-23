"""
Serializers for legal cases.
"""

from django.utils import timezone
from rest_framework import serializers

from core.models import Case


class CaseSerializer(serializers.ModelSerializer):
    document_count = serializers.SerializerMethodField()
    hearing_count = serializers.SerializerMethodField()
    thread_count = serializers.IntegerField(read_only=True, default=0)
    conversation_count = serializers.IntegerField(read_only=True, default=0)
    needs_attention = serializers.SerializerMethodField()
    next_hearing_date = serializers.SerializerMethodField()

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
            "hearing_count",
            "thread_count",
            "conversation_count",
            "cnr_number",
            "court_type",
            "tracking_config",
            "tracking_enabled",
            "fetch_status",
            "last_fetched_at",
            "party_advocate_data",
            "needs_attention",
            "next_hearing_date",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "cnr_number",
            "fetch_status",
            "last_fetched_at",
            "party_advocate_data",
        ]

    def get_document_count(self, obj: Case) -> int:
        return obj.documents.count()

    def get_hearing_count(self, obj: Case) -> int:
        return obj.hearings.count()

    def get_next_hearing_date(self, obj: Case):
        # Populated via queryset annotation (see core/views/case.py) when
        # available; falls back to a direct query otherwise (e.g. CaseDetailView).
        if hasattr(obj, "_next_hearing_date"):
            return obj._next_hearing_date
        hearing = (
            obj.hearings.filter(status="scheduled", hearing_date__gte=timezone.now())
            .order_by("hearing_date")
            .first()
        )
        return hearing.hearing_date if hearing else None

    def get_needs_attention(self, obj: Case) -> bool:
        # Populated via queryset annotation (see core/views/case.py); defaults
        # to False when the annotations aren't present (e.g. CaseDetailView).
        return bool(
            getattr(obj, "has_upcoming_hearing", False)
            or getattr(obj, "has_ecourts_update", False)
            or getattr(obj, "has_failed_document", False)
        )
