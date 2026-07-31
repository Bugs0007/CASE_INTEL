"""Travel/hotel booking views: CRUD, file upload (which is what marks a
booking BOOKED), and the booking-file stream.

Upload/download are plain APIViews scoped to request.user by hand; the
list/detail pair uses OwnerScopedMixin like every other generic view.
"""

import logging

from django.core.files.storage import default_storage
from django.http import FileResponse
from rest_framework import generics, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.models import Hearing, TravelBooking
from core.serializers import TravelBookingSerializer, TravelBookingUploadSerializer
from core.services.travel_service import attach_booking_file
from core.views.mixins import OwnerScopedMixin

logger = logging.getLogger(__name__)


class TravelBookingListCreateView(OwnerScopedMixin, generics.ListCreateAPIView):
    """List or create travel bookings.

    GET  /api/travel-bookings/
    GET  /api/travel-bookings/?hearing_id=1
    GET  /api/travel-bookings/?case_id=2
    POST /api/travel-bookings/     (creates a PENDING booking, no file yet)

    Scoped to request.user (OwnerScopedMixin).
    """

    serializer_class = TravelBookingSerializer

    def get_base_queryset(self):
        qs = TravelBooking.objects.select_related("hearing__case")
        hearing_id = self.request.query_params.get("hearing_id")
        if hearing_id:
            qs = qs.filter(hearing_id=hearing_id)
        case_id = self.request.query_params.get("case_id")
        if case_id:
            qs = qs.filter(hearing__case_id=case_id)
        return qs


class TravelBookingDetailView(OwnerScopedMixin, generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a travel booking.

    GET    /api/travel-bookings/<id>/
    PATCH  /api/travel-bookings/<id>/
    DELETE /api/travel-bookings/<id>/

    Scoped to request.user (OwnerScopedMixin).
    """

    serializer_class = TravelBookingSerializer
    queryset = TravelBooking.objects.select_related("hearing__case")


class TravelBookingUploadView(APIView):
    """Upload a ticket/hotel confirmation; the booking becomes BOOKED.

    POST /api/travel-bookings/upload/   (multipart/form-data)
    Fields:
        file         - the ticket/confirmation
        hearing_id   - create a new booking for this hearing, or
        booking_id   - attach to this existing booking
        booking_type - travel | hotel | other (default travel)
        notes        - optional

    Ownership of hearing_id/booking_id is enforced in
    TravelBookingUploadSerializer (both scoped to request.user), so a
    hearing or booking belonging to another advocate fails validation
    before anything is written.
    """

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request: Request) -> Response:
        serializer = TravelBookingUploadSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)

        uploaded_file = serializer.validated_data["file"]
        booking_id = serializer.validated_data.get("booking_id")
        hearing_id = serializer.validated_data.get("hearing_id")

        if booking_id:
            booking = TravelBooking.objects.get(id=booking_id, owner=request.user)
        else:
            hearing = Hearing.objects.get(id=hearing_id, owner=request.user)
            booking = TravelBooking.objects.create(
                owner=request.user,
                hearing=hearing,
                booking_type=serializer.validated_data.get(
                    "booking_type", TravelBooking.TYPE_TRAVEL
                ),
                notes=serializer.validated_data.get("notes", ""),
            )

        booking = attach_booking_file(booking, uploaded_file)

        return Response(
            TravelBookingSerializer(booking).data, status=status.HTTP_201_CREATED
        )


class TravelBookingFileView(APIView):
    """Stream a booking's uploaded file.

    GET /api/travel-bookings/<id>/file/

    Streamed through the view for the same reason as the invoice and
    court-order files: /media/ is unauthenticated on local disk, and a
    ticket carries the advocate's travel plans and personal details.
    """

    def get(self, request: Request, pk: int) -> Response:
        booking = TravelBooking.objects.filter(id=pk, owner=request.user).first()
        if booking is None:
            return Response(
                {"detail": "Booking not found."}, status=status.HTTP_404_NOT_FOUND
            )
        if not booking.file_path:
            return Response(
                {"detail": "This booking has no file attached."},
                status=status.HTTP_404_NOT_FOUND,
            )

        try:
            handle = default_storage.open(booking.file_path, "rb")
        except Exception as exc:  # noqa: BLE001
            missing = False
            try:
                missing = not default_storage.exists(booking.file_path)
            except Exception:  # noqa: BLE001 -- storage itself is unreachable
                pass
            if missing:
                logger.warning(
                    "Booking %d references a missing file (%s).", pk, booking.file_path
                )
                return Response(
                    {"detail": "The booking file is no longer available."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            logger.exception("Could not open the file for booking %d", pk)
            return Response(
                {"detail": f"File is unavailable: {exc}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        content_type = (
            "application/pdf" if booking.file_type == "pdf" else "application/octet-stream"
        )
        return FileResponse(
            handle,
            content_type=content_type,
            as_attachment=False,
            filename=booking.filename or f"booking-{booking.id}",
        )
