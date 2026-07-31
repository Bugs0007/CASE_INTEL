"""Travel/hotel bookings attached to a hearing.

Thin by design -- the only real rule is "a booking with a file attached
is BOOKED" -- but it lives here rather than in the view so the upload
endpoint and any future importer (an email-attachment sweep, say) agree
on what booked means and write the same fields.
"""

from __future__ import annotations

import logging

from django.core.files.storage import default_storage

from core.models import TravelBooking

logger = logging.getLogger(__name__)

ALLOWED_BOOKING_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "txt", "docx", "doc"}
MAX_BOOKING_FILE_BYTES = 20 * 1024 * 1024  # 20 MB -- tickets are small


def attach_booking_file(booking: TravelBooking, uploaded_file) -> TravelBooking:
    """Store `uploaded_file` against `booking` and flip it to BOOKED.

    Replaces any previously attached file (re-uploading a corrected
    ticket is the expected flow, and leaving the old one orphaned in
    storage would slowly leak files).
    """
    filename = uploaded_file.name
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if booking.file_path:
        try:
            default_storage.delete(booking.file_path)
        except Exception:  # noqa: BLE001 -- a missing/unreachable old file must not block the new one
            logger.warning(
                "Could not delete replaced booking file %s", booking.file_path, exc_info=True
            )

    # default_storage.save() de-duplicates the name itself on both the
    # local and S3 backends, so two tickets called "ticket.pdf" don't
    # overwrite each other.
    saved_name = default_storage.save(
        f"travel_bookings/{booking.owner_id}/{filename}", uploaded_file
    )

    booking.filename = filename
    booking.file_path = saved_name
    booking.file_type = ext
    booking.file_size = uploaded_file.size
    booking.status = TravelBooking.STATUS_BOOKED
    booking.save(
        update_fields=[
            "filename",
            "file_path",
            "file_type",
            "file_size",
            "status",
            "updated_at",
        ]
    )

    logger.info(
        "Travel booking %d for hearing %d marked BOOKED (%s, %d bytes)",
        booking.id,
        booking.hearing_id,
        filename,
        uploaded_file.size,
    )
    return booking
