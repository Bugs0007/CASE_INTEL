"""Serializers for clients (billing entities) and client-message drafts."""

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from core.models import Client, ClientMessage, SentMessage
from core.models.client import validate_gstin


class ClientSerializer(serializers.ModelSerializer):
    client_type_display = serializers.CharField(source="get_client_type_display", read_only=True)
    case_count = serializers.IntegerField(read_only=True, default=0)
    # Declared explicitly so the value is upper-cased BEFORE the format
    # check -- the model's validator would otherwise reject "36abcde...".
    gstin = serializers.CharField(max_length=15, required=False, allow_blank=True)

    class Meta:
        model = Client
        fields = [
            "id",
            "name",
            "client_type",
            "client_type_display",
            "gstin",
            "email",
            "phone",
            "address",
            "notes",
            "case_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_gstin(self, value: str) -> str:
        value = (value or "").strip().upper()
        try:
            validate_gstin(value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError(exc.messages) from None
        return value

    def validate(self, attrs):
        client_type = attrs.get("client_type", getattr(self.instance, "client_type", Client.TYPE_INDIVIDUAL))
        gstin = attrs.get("gstin", getattr(self.instance, "gstin", ""))
        if gstin and client_type != Client.TYPE_BUSINESS:
            raise serializers.ValidationError(
                {"gstin": "A GSTIN only applies to a business-entity client."}
            )
        return attrs


class ClientSummarySerializer(serializers.ModelSerializer):
    """Compact client shape embedded in a Case."""

    class Meta:
        model = Client
        fields = ["id", "name", "client_type"]


class ClientMessageSerializer(serializers.ModelSerializer):
    case_title = serializers.CharField(source="case.title", read_only=True)
    case_number = serializers.CharField(source="case.case_number", read_only=True)
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    invoice_number = serializers.CharField(source="fee.invoice_number", read_only=True, default=None)
    hearing_date = serializers.DateTimeField(source="hearing.hearing_date", read_only=True, default=None)
    eligible_recipients = serializers.SerializerMethodField()
    # Write-only: which of the case's eligible contacts a draft goes to.
    recipient_contact_ids = serializers.ListField(
        child=serializers.IntegerField(), write_only=True, required=False
    )

    class Meta:
        model = ClientMessage
        fields = [
            "id",
            "case",
            "case_title",
            "case_number",
            "kind",
            "kind_display",
            "status",
            "status_display",
            "subject",
            "body",
            "recipients",
            "eligible_recipients",
            "recipient_contact_ids",
            "edited_by_user",
            "reminder_number",
            "fee",
            "invoice_number",
            "hearing",
            "hearing_date",
            "court_order",
            "sent_at",
            "send_result",
            "discard_reason",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "case",
            "kind",
            "status",
            "recipients",
            "edited_by_user",
            "reminder_number",
            "fee",
            "hearing",
            "court_order",
            "sent_at",
            "send_result",
            "discard_reason",
            "created_at",
            "updated_at",
        ]

    def get_eligible_recipients(self, obj):
        """Only meaningful while the message is still a draft."""
        if obj.status != ClientMessage.STATUS_DRAFT:
            return []
        from core.services.client_updates import eligible_contacts

        return [{"contact_id": c.id, "name": c.name, "email": c.email} for c in eligible_contacts(obj)]

    def validate_subject(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("A subject is required.")
        return value

    def validate_body(self, value: str) -> str:
        if not (value or "").strip():
            raise serializers.ValidationError("The message can't be empty.")
        return value


class SentMessageSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    delivery_display = serializers.CharField(source="get_delivery_display", read_only=True)
    sent_by_username = serializers.CharField(source="sent_by.username", read_only=True, default=None)
    case_title = serializers.CharField(source="case.title", read_only=True, default=None)
    case_number = serializers.CharField(source="case.case_number", read_only=True, default=None)

    class Meta:
        model = SentMessage
        fields = [
            "id",
            "sent_at",
            "sent_by",
            "sent_by_username",
            "kind",
            "kind_display",
            "delivery",
            "delivery_display",
            "to_emails",
            "cc_emails",
            "subject",
            "body_sha256",
            "case",
            "case_title",
            "case_number",
            "message",
            "fee",
        ]
        read_only_fields = fields


def scope_client_field(serializer, request) -> None:
    """Limit a writable `client` FK to the caller's own clients -- an
    unscoped PK field is an IDOR path even behind a scoped view.

    Fails closed: a serializer built without a request in its context
    accepts no client at all, rather than every client in the table."""
    if "client" not in serializer.fields:
        return
    field = serializer.fields["client"]
    if getattr(field, "read_only", False):
        return
    field.queryset = (
        Client.objects.filter(owner=request.user) if request is not None else Client.objects.none()
    )


__all__ = [
    "ClientMessageSerializer",
    "ClientSerializer",
    "ClientSummarySerializer",
    "SentMessageSerializer",
    "scope_client_field",
]
