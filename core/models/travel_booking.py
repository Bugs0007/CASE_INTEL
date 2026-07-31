from django.db import models

from .mixins import OwnedModel


class TravelBooking(OwnedModel):
    """A travel or hotel booking attached to a hearing -- the advocate
    uploads the ticket/confirmation PDF and the row records it.

    Several per hearing is normal (a flight AND a hotel AND a return
    leg), so this is a plain FK, not a OneToOne like AppearanceFee.

    A row can exist before its file does (status PENDING -- "I still need
    to book this"); attaching a file flips it to BOOKED. That transition
    lives in core/services/travel_service.py so the upload endpoint and
    any future importer agree on what "booked" means.
    """

    TYPE_TRAVEL = "travel"
    TYPE_HOTEL = "hotel"
    TYPE_OTHER = "other"

    BOOKING_TYPE_CHOICES = [
        (TYPE_TRAVEL, "Travel"),
        (TYPE_HOTEL, "Hotel"),
        (TYPE_OTHER, "Other"),
    ]

    STATUS_PENDING = "pending"
    STATUS_BOOKED = "booked"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_BOOKED, "Booked"),
    ]

    hearing = models.ForeignKey(
        "core.Hearing", on_delete=models.CASCADE, related_name="travel_bookings"
    )
    booking_type = models.CharField(
        max_length=20, choices=BOOKING_TYPE_CHOICES, default=TYPE_TRAVEL
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    filename = models.CharField(max_length=255, blank=True, default="")
    # Storage-relative key, same convention as Document.file_path.
    file_path = models.CharField(max_length=500, blank=True, default="")
    file_type = models.CharField(max_length=20, blank=True, default="")
    file_size = models.BigIntegerField(blank=True, null=True)

    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "travel_bookings"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.get_booking_type_display()} [{self.status}] hearing={self.hearing_id}"
