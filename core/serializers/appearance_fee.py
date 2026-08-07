"""Serializers for per-hearing appearance fees."""

from rest_framework import serializers

from core.models import AppearanceFee, Hearing


class AppearanceFeeSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    case_id = serializers.IntegerField(source="hearing.case_id", read_only=True)
    case_title = serializers.CharField(source="hearing.case.title", read_only=True)
    hearing_date = serializers.DateTimeField(source="hearing.hearing_date", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Scope the writable "hearing" field to the caller's own hearings
        # -- same pattern as HearingSerializer.case. Without it any
        # hearing pk, including another advocate's, would pass field
        # validation and let a fee be attached to someone else's hearing.
        request = self.context.get("request")
        if request is not None and "hearing" in self.fields:
            self.fields["hearing"].queryset = Hearing.objects.filter(owner=request.user)

    class Meta:
        model = AppearanceFee
        fields = [
            "id",
            "hearing",
            "case_id",
            "case_title",
            "hearing_date",
            "amount",
            "status",
            "status_display",
            "invoice_number",
            "invoice_sequence",
            "invoiced_at",
            "paid_at",
            "sent_at",
            "sent_to_email",
            "send_status",
            "notes",
            "created_at",
            "updated_at",
        ]
        # Everything the invoicing lifecycle owns is read-only over the
        # API: status moves only through the generate/send/mark-paid
        # endpoints (core/services/invoice_service.py), never by PATCHing
        # a field, so the transition rules can't be stepped around.
        read_only_fields = [
            "id",
            "status",
            "invoice_number",
            "invoice_sequence",
            "invoiced_at",
            "paid_at",
            "sent_at",
            "sent_to_email",
            "send_status",
            "created_at",
            "updated_at",
        ]

    def validate_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("Amount cannot be negative.")
        return value


class NestedAppearanceFeeSerializer(serializers.ModelSerializer):
    """Compact fee shape embedded in HearingSerializer -- just what the
    hearing card's badge needs, without the case/hearing back-references
    the card already has."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = AppearanceFee
        fields = [
            "id",
            "amount",
            "status",
            "status_display",
            "invoice_number",
            "invoiced_at",
            "paid_at",
            "sent_at",
            "send_status",
        ]
        read_only_fields = fields
