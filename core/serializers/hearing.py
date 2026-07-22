"""
Serializers for case hearings.
"""

from rest_framework import serializers

from core.models import Case, Hearing


class HearingSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source="case.title", read_only=True)
    hearing_type_display = serializers.CharField(
        source="get_hearing_type_display", read_only=True
    )
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Scope the writable "case" field to the requesting user's own
        # cases -- without this, any case pk (including another user's)
        # would pass field-level validation and let a hearing be attached
        # to a case that isn't the caller's.
        request = self.context.get("request")
        if request is not None and "case" in self.fields:
            self.fields["case"].queryset = Case.objects.filter(owner=request.user)

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
