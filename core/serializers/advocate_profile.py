"""Serializer for the advocate's invoice letterhead / billing profile."""

from rest_framework import serializers

from core.models import AdvocateProfile


class AdvocateProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdvocateProfile
        fields = [
            "id",
            "letterhead_name",
            "address",
            "bar_registration_number",
            "default_fee_amount",
            "invoice_prefix",
            "last_invoice_sequence",
            "created_at",
            "updated_at",
        ]
        # last_invoice_sequence is the live invoice counter -- writable it
        # would let a client rewind it and mint a duplicate invoice
        # number for an invoice already sent to someone.
        read_only_fields = ["id", "last_invoice_sequence", "created_at", "updated_at"]
