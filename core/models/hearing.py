from django.db import models

from .mixins import OwnedModel


class Hearing(OwnedModel):
    HEARING_TYPE_CHOICES = [
        ("preliminary", "Preliminary Hearing"),
        ("motion", "Motion Hearing"),
        ("trial", "Trial"),
        ("appeal", "Appeal"),
        ("sentencing", "Sentencing"),
        ("arraignment", "Arraignment"),
        ("status", "Status Conference"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("scheduled", "Scheduled"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
        ("postponed", "Postponed"),
    ]

    SOURCE_CHOICES = [
        ("manual", "Manual"),
        ("ecourts", "eCourts"),
    ]

    # Cause-list state. "not_published" and "not_listed" are deliberately
    # separate: before the court publishes, absence from the list means
    # nothing at all ("Not yet listed"), whereas after publication it
    # means the matter genuinely isn't being heard. Collapsing the two
    # would show an advocate a confident "not listed" the evening before
    # a hearing purely because the court hadn't posted yet.
    CAUSE_LIST_NOT_CHECKED = "not_checked"
    CAUSE_LIST_NOT_PUBLISHED = "not_published"
    CAUSE_LIST_LISTED = "listed"
    CAUSE_LIST_NOT_LISTED = "not_listed"

    CAUSE_LIST_STATUS_CHOICES = [
        (CAUSE_LIST_NOT_CHECKED, "Not checked"),
        (CAUSE_LIST_NOT_PUBLISHED, "Not yet listed"),
        (CAUSE_LIST_LISTED, "Listed"),
        (CAUSE_LIST_NOT_LISTED, "Not listed"),
    ]

    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, related_name="hearings"
    )
    hearing_date = models.DateTimeField()
    hearing_type = models.CharField(max_length=50, choices=HEARING_TYPE_CHOICES)
    location = models.CharField(max_length=255, blank=True, null=True)
    judge = models.CharField(max_length=255, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="scheduled")
    notes = models.TextField(blank=True, null=True)
    outcome = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # --- Court tracking (eCourts) ---
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="manual")
    business_date = models.DateField(
        blank=True,
        null=True,
        help_text="eCourts 'business on date' -- the date the case was last acted on, distinct from hearing_date.",
    )
    purpose = models.CharField(
        max_length=255,
        blank=True,
        null=True,
        help_text="eCourts 'purpose of hearing' (e.g. 'CALL WITH IAS', 'FOR DISMISSAL').",
    )

    # --- Cause list (see core/services/cause_list/) ---
    cause_list_status = models.CharField(
        max_length=20,
        choices=CAUSE_LIST_STATUS_CHOICES,
        default=CAUSE_LIST_NOT_CHECKED,
        help_text="Whether this hearing was found in the court's published cause list.",
    )
    cause_list_item_number = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Item/serial number in the cause list, e.g. '3'.",
    )
    cause_list_court_hall = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Court hall the matter is listed in, e.g. '1' from 'COURT NO. 1'.",
    )
    cause_list_stage = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="Cause-list stage heading, e.g. 'FOR ADMISSION (FRESH MATTERS)'.",
    )
    cause_list_checked_at = models.DateTimeField(
        blank=True,
        null=True,
        help_text="When the cause list was last checked for this hearing.",
    )
    cause_list_source = models.CharField(
        max_length=40,
        blank=True,
        default="",
        help_text="Which court's cause list produced this, e.g. 'telangana_hc'.",
    )

    class Meta:
        db_table = "hearings"
        ordering = ["hearing_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "hearing_date", "source"],
                name="unique_hearing_per_case_date_source",
            )
        ]

    def __str__(self):
        return f"{self.get_hearing_type_display()} - {self.hearing_date.strftime('%Y-%m-%d')}"
