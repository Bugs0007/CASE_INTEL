from rest_framework import serializers

from core.models import CaseBusinessEntry


class CaseBusinessEntrySerializer(serializers.ModelSerializer):
    """One District Courts Daily Status entry. Read-only: entries come
    from the portal (core/services/daily_status.py) and are never edited."""

    class Meta:
        model = CaseBusinessEntry
        fields = [
            "business_date",
            "court_name",
            "business_text",
            "next_purpose",
            "next_hearing_date",
            "fetched_at",
        ]
        read_only_fields = fields
