"""Serializer for case events -- the advocate's own appointments on a case."""

from rest_framework import serializers

from core.models import Case, CaseEvent


class CaseEventSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source="case.title", read_only=True)
    case_number = serializers.CharField(source="case.case_number", read_only=True)
    event_type_display = serializers.CharField(
        source="get_event_type_display", read_only=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Scope the writable "case" field to the requesting user's own
        # cases, same as HearingSerializer / TaskSerializer -- otherwise an
        # event could be attached to another advocate's case.
        request = self.context.get("request")
        if request is not None and "case" in self.fields:
            self.fields["case"].queryset = Case.objects.filter(owner=request.user)

    def validate(self, attrs):
        # PATCH may send only one of the two times, so judge the result.
        instance = self.instance
        start = attrs.get("start_time", getattr(instance, "start_time", None))
        end = attrs.get("end_time", getattr(instance, "end_time", None))
        if end is not None:
            if start is None:
                raise serializers.ValidationError(
                    {"end_time": "Set a start time before an end time."}
                )
            if end <= start:
                raise serializers.ValidationError(
                    {"end_time": "The end time must be after the start time."}
                )
        return attrs

    class Meta:
        model = CaseEvent
        fields = [
            "id",
            "case",
            "case_title",
            "case_number",
            "title",
            "event_type",
            "event_type_display",
            "date",
            "start_time",
            "end_time",
            "location",
            "notes",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
