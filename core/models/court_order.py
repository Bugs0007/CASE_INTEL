from django.db import models


class CourtOrder(models.Model):
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
