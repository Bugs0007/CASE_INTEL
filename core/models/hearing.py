from django.db import models


class Hearing(models.Model):
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

    class Meta:
        db_table = "hearings"
        ordering = ["hearing_date"]

    def __str__(self):
        return f"{self.get_hearing_type_display()} - {self.hearing_date.strftime('%Y-%m-%d')}"
