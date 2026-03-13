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
        ("other", "Other"),
    ]

    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, blank=True, null=True, related_name="documents"
    )
    folder = models.ForeignKey(
        "core.Folder", on_delete=models.SET_NULL, blank=True, null=True, related_name="documents"
    )
    filename = models.CharField(max_length=255)
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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "documents"
        ordering = ["-created_at"]

    def __str__(self):
        return self.filename
