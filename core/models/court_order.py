from django.db import models

from .mixins import OwnedModel


class CourtOrder(OwnedModel):
    """An order/judgment PDF fetched from the court portal for a tracked
    case (Phase B).

    The downloaded file itself lives on the linked Document -- orders
    deliberately become normal Documents (document_type='court_order') so
    they flow through the EXISTING processing pipeline (async job queue,
    OCR if scanned, embeddings) and Case Bot cites them like any other
    document. This row is the sync-side metadata: what the portal listed,
    and the dedup identity that makes re-fetching idempotent.
    """

    SOURCE_CHOICES = [
        ("ecourts", "eCourts"),
    ]

    # --- Order Overview (see core/services/order_summary/) ---
    # Generated ONCE, at ingest, and read from these columns on every
    # page view thereafter. "unreadable" and "no_directions" are resolved
    # without any LLM call at all; only "summarized" ever cost money.
    SUMMARY_PENDING = "pending"
    SUMMARY_UNREADABLE = "unreadable"
    SUMMARY_NO_DIRECTIONS = "no_directions"
    SUMMARY_SUMMARIZED = "summarized"
    SUMMARY_FAILED = "failed"

    SUMMARY_STATUS_CHOICES = [
        (SUMMARY_PENDING, "Not yet summarised"),
        (SUMMARY_UNREADABLE, "Unreadable (scanned, no text)"),
        (SUMMARY_NO_DIRECTIONS, "No directions issued"),
        (SUMMARY_SUMMARIZED, "Summarised"),
        (SUMMARY_FAILED, "Summary failed"),
    ]

    SUMMARY_ROUTE_CHOICES = [
        ("unreadable", "Unreadable -- no LLM call"),
        ("short", "Too short -- no LLM call"),
        ("routine", "Routine adjournment -- no LLM call"),
        ("llm", "Sent to the LLM"),
    ]

    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, related_name="court_orders"
    )
    order_number = models.CharField(max_length=50)
    order_date = models.DateField(blank=True, null=True)
    description = models.CharField(max_length=500, blank=True, default="")
    judge = models.CharField(max_length=255, blank=True, default="")
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, default="ecourts")
    # "<cnr>:<order_number>:<order_date iso>" -- stable across fetches
    # (the portals' download tokens are session-bound and excluded).
    # Unique per case so a refresh can never ingest the same order twice.
    dedup_key = models.CharField(max_length=120)
    document = models.OneToOneField(
        "core.Document",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="court_order",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # --- Order Overview summary (generated once at ingest) ---
    summary_status = models.CharField(
        max_length=20, choices=SUMMARY_STATUS_CHOICES, default=SUMMARY_PENDING
    )
    summary_route = models.CharField(
        max_length=20,
        choices=SUMMARY_ROUTE_CHOICES,
        blank=True,
        default="",
        help_text="Which path this order took -- how many orders reach the LLM.",
    )
    summary_what_happened = models.TextField(blank=True, default="")
    # Stored as they appear in the ORDER (petitioner/respondent), not as
    # "your side"/"other side". Which is which for this advocate is
    # applied at render time from Case.user_party_role, so correcting the
    # role later re-renders correctly with no re-generation.
    summary_petitioner_directions = models.JSONField(blank=True, default=list)
    summary_respondent_directions = models.JSONField(blank=True, default=list)
    summary_next_date = models.DateField(blank=True, null=True)
    summary_next_date_purpose = models.CharField(max_length=255, blank=True, default="")
    summary_is_routine_adjournment = models.BooleanField(default=False)
    summary_generated_at = models.DateTimeField(blank=True, null=True)
    summary_error = models.TextField(blank=True, default="")
    summary_llm_calls = models.PositiveSmallIntegerField(
        default=0, help_text="LLM calls spent on this order. 0 for the templated paths."
    )

    class Meta:
        db_table = "court_orders"
        ordering = ["-order_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "dedup_key"], name="unique_court_order_per_case"
            )
        ]

    def __str__(self):
        return f"Order {self.order_number} ({self.dedup_key})"
