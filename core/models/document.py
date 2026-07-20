from django.db import models


class Document(models.Model):
    PROCESSING_STATUS_CHOICES = [
        ("pending", "Pending"),
        ("processing", "Processing"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    DOCUMENT_TYPE_CHOICES = [
        ("contract", "Contract"),
        ("pleading", "Pleading"),
        ("evidence", "Evidence"),
        ("correspondence", "Correspondence"),
        ("brief", "Brief"),
        ("motion", "Motion"),
        ("order", "Order"),
        # Fetched automatically from the court portal by order sync (Phase
        # B) -- the frontend renders these with a "From eCourts" badge.
        ("court_order", "Court Order (eCourts)"),
        ("other", "Other"),
    ]

    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, blank=True, null=True, related_name="documents"
    )
    folder = models.ForeignKey(
        "core.Folder", on_delete=models.SET_NULL, blank=True, null=True, related_name="documents"
    )
    filename = models.CharField(max_length=255)
    # Storage-relative key (e.g. "documents/foo.pdf"), resolved through
    # django.core.files.storage.default_storage -- NOT an absolute
    # filesystem path. This is what lets USE_S3 swap local disk for S3
    # without a schema change: the same key resolves under MEDIA_ROOT
    # locally or as an S3 object key in the bucket.
    file_path = models.CharField(max_length=500)
    file_type = models.CharField(max_length=10, blank=True, null=True)
    file_size = models.BigIntegerField(blank=True, null=True)
    document_type = models.CharField(
        max_length=50, choices=DOCUMENT_TYPE_CHOICES, blank=True, null=True
    )
    document_date = models.DateField(blank=True, null=True)
    processing_status = models.CharField(
        max_length=20, choices=PROCESSING_STATUS_CHOICES, default="pending"
    )
    extracted_text = models.TextField(blank=True, null=True)
    chunk_count = models.IntegerField(blank=True, null=True)
    # True when the processing worker detected a scanned PDF (negligible
    # extractable text) and ran it through ocrmypdf before chunking.
    ocr_applied = models.BooleanField(default=False)

    # --- Deduplication: SHA-256 hash of the raw file bytes ---
    # If two uploads have the same hash, we skip re-embedding and
    # copy chunk references from the existing document instead.
    # Set db_index=True so the lookup is O(log n), not a full scan.
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        db_index=True,
        help_text="SHA-256 hex digest of the uploaded file. Used to skip duplicate processing.",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "documents"
        ordering = ["-created_at"]

    def __str__(self):
        return self.filename
