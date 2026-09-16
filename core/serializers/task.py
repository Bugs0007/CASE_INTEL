"""Serializer for tasks -- manual to-dos and system-generated deadlines."""

from django.utils import timezone
from rest_framework import serializers

from core.models import Case, Task

# Editing any of these marks a task as the advocate's own, so regeneration
# never overwrites it. Confirming a suggestion (needs_review) does not.
_USER_EDIT_FIELDS = ("case", "title", "description", "due_date", "status")


class TaskSerializer(serializers.ModelSerializer):
    title = serializers.CharField(max_length=255)
    case_title = serializers.CharField(source="case.title", read_only=True, default=None)
    case_number = serializers.CharField(source="case.case_number", read_only=True, default=None)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    due_date_basis_display = serializers.CharField(
        source="get_due_date_basis_display", read_only=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Scope the writable "case" field to the requesting user's own
        # cases, same as HearingSerializer / ClientContactSerializer --
        # otherwise a task could be attached to another advocate's case.
        request = self.context.get("request")
        if request is not None and "case" in self.fields:
            self.fields["case"].queryset = Case.objects.filter(owner=request.user)

    class Meta:
        model = Task
        fields = [
            "id",
            "case",
            "case_title",
            "case_number",
            "title",
            "description",
            "status",
            "kind",
            "kind_display",
            "due_date",
            "due_date_basis",
            "due_date_basis_display",
            "source_order",
            "source_text",
            "rule_key",
            "trigger_date",
            "needs_review",
            "user_modified",
            "completed_at",
            "created_at",
            "updated_at",
        ]
        # Provenance is written only by the generators
        # (core/services/tasks). Tasks created through the API are always
        # manual.
        read_only_fields = [
            "id",
            "kind",
            "due_date_basis",
            "source_order",
            "source_text",
            "rule_key",
            "trigger_date",
            "user_modified",
            "completed_at",
            "created_at",
            "updated_at",
        ]

    def create(self, validated_data):
        validated_data.setdefault("needs_review", False)
        _stamp_completion(validated_data, previous_status=None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if any(
            field in validated_data and validated_data[field] != getattr(instance, field)
            for field in _USER_EDIT_FIELDS
        ):
            validated_data["user_modified"] = True
        _stamp_completion(validated_data, previous_status=instance.status)
        return super().update(instance, validated_data)


def _stamp_completion(validated_data: dict, *, previous_status: str | None) -> None:
    status = validated_data.get("status")
    if status is None or status == previous_status:
        return
    validated_data["completed_at"] = (
        timezone.now() if status == Task.STATUS_COMPLETED else None
    )
