"""Serializers for a case's client contacts."""

from rest_framework import serializers

from core.models import Case, ClientContact


class ClientContactSerializer(serializers.ModelSerializer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Scope the writable "case" field to the requesting user's own
        # cases -- without this, any case pk (including another user's)
        # would pass field-level validation and let a contact be attached
        # to a case that isn't the caller's. Same pattern as
        # HearingSerializer.
        request = self.context.get("request")
        if request is not None and "case" in self.fields:
            self.fields["case"].queryset = Case.objects.filter(owner=request.user)

    class Meta:
        model = ClientContact
        fields = [
            "id",
            "case",
            "name",
            "email",
            "phone",
            "role",
            "is_billing_contact",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]
