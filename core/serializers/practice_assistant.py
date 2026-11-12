"""Request validation for the practice assistant."""

from rest_framework import serializers

DAY_FORMAT = "%Y-%m-%d"
MAX_QUERY_LENGTH = 2000
MAX_REQUEST_ID_LENGTH = 64


class PracticeChatRequestSerializer(serializers.Serializer):
    """POST /api/practice-assistant/chat/. Scope, owner and as_of are never
    read from the body: the server sets them."""

    query = serializers.CharField(max_length=MAX_QUERY_LENGTH)
    conversation_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    selected_day = serializers.DateField(
        required=False, allow_null=True, input_formats=[DAY_FORMAT]
    )
    case_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    client_request_id = serializers.RegexField(
        r"^[A-Za-z0-9._:\-]+$", max_length=MAX_REQUEST_ID_LENGTH, min_length=1
    )
