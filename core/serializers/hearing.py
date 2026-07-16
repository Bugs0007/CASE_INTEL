"""
Serializers for case hearings.
"""

from rest_framework import serializers

from core.models import Hearing


class HearingSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source="case.title", read_only=True)
    hearing_type_display = serializers.CharField(
        source="get_hearing_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Hearing
        fields = [
            "id",
            "case",
            "case_title",
            "hearing_date",
            "hearing_type",
            "hearing_type_display",
            "location",
            "judge",
            "status",
            "status_display",
            "notes",
            "outcome",
            "source",
            "business_date",
            "purpose",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
