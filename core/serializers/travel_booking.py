"""Serializers for per-hearing travel/hotel bookings."""

from rest_framework import serializers

from core.models import Hearing, TravelBooking
from core.services.travel_service import (
    ALLOWED_BOOKING_EXTENSIONS,
    MAX_BOOKING_FILE_BYTES,
)


class TravelBookingSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    booking_type_display = serializers.CharField(
        source="get_booking_type_display", read_only=True
    )
    case_id = serializers.IntegerField(source="hearing.case_id", read_only=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        request = self.context.get("request")
        if request is not None and "hearing" in self.fields:
            self.fields["hearing"].queryset = Hearing.objects.filter(owner=request.user)

    class Meta:
        model = TravelBooking
        fields = [
            "id",
            "hearing",
            "case_id",
            "booking_type",
            "booking_type_display",
            "status",
            "status_display",
            "filename",
            "file_type",
            "file_size",
            "notes",
            "created_at",
            "updated_at",
        ]
        # status is driven by whether a file is attached (see
        # travel_service.attach_booking_file), never set directly; the
        # file_* fields are derived from the upload itself.
        read_only_fields = [
            "id",
            "status",
            "filename",
            "file_type",
            "file_size",
            "created_at",
            "updated_at",
        ]


class TravelBookingUploadSerializer(serializers.Serializer):
    """Validates a booking-file upload (multipart).

    `booking_id` attaches the file to an existing PENDING booking;
    omitting it creates a new booking for `hearing_id` in one call, which
    is the common case (the advocate has the ticket in hand already).
    """

    file = serializers.FileField()
    hearing_id = serializers.IntegerField(required=False, allow_null=True)
    booking_id = serializers.IntegerField(required=False, allow_null=True)
    booking_type = serializers.ChoiceField(
        choices=[c[0] for c in TravelBooking.BOOKING_TYPE_CHOICES],
        required=False,
        default=TravelBooking.TYPE_TRAVEL,
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")

    def validate_file(self, value):
        filename = value.name
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ALLOWED_BOOKING_EXTENSIONS:
            raise serializers.ValidationError(
                f"Unsupported file type '{ext}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_BOOKING_EXTENSIONS))}"
            )
        if value.size > MAX_BOOKING_FILE_BYTES:
            max_mb = MAX_BOOKING_FILE_BYTES // (1024 * 1024)
            raise serializers.ValidationError(f"File size exceeds the {max_mb} MB limit.")
        return value

    def validate_hearing_id(self, value):
        request = self.context.get("request")
        owner = request.user if request is not None else None
        if value is not None and not Hearing.objects.filter(id=value, owner=owner).exists():
            raise serializers.ValidationError(f"Hearing with id {value} does not exist.")
        return value

    def validate_booking_id(self, value):
        request = self.context.get("request")
        owner = request.user if request is not None else None
        if value is not None and not TravelBooking.objects.filter(
            id=value, owner=owner
        ).exists():
            raise serializers.ValidationError(f"Booking with id {value} does not exist.")
        return value

    def validate(self, attrs):
        if not attrs.get("hearing_id") and not attrs.get("booking_id"):
            raise serializers.ValidationError(
                "Provide either hearing_id (to create a booking) or booking_id "
                "(to attach a file to an existing one)."
            )
        return attrs


class NestedTravelBookingSerializer(serializers.ModelSerializer):
    """Compact booking shape embedded in HearingSerializer."""

    status_display = serializers.CharField(source="get_status_display", read_only=True)
    booking_type_display = serializers.CharField(
        source="get_booking_type_display", read_only=True
    )

    class Meta:
        model = TravelBooking
        fields = [
            "id",
            "booking_type",
            "booking_type_display",
            "status",
            "status_display",
            "filename",
            "created_at",
        ]
        read_only_fields = fields
