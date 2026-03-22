"""
Serializers for legal cases.
"""

from rest_framework import serializers

from core.models import Case


class CaseSerializer(serializers.ModelSerializer):
    document_count = serializers.SerializerMethodField()
    thread_count = serializers.IntegerField(read_only=True, default=0)
    conversation_count = serializers.IntegerField(read_only=True, default=0)

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
            "thread_count",
            "conversation_count",
        ]
        read_only_fields = ["id", "created_at"]

    def get_document_count(self, obj: Case) -> int:
        return obj.documents.count()
