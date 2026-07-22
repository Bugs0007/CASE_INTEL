from django.db import models

from .mixins import OwnedModel


class ActivityLog(OwnedModel):
    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, blank=True, null=True,
        related_name="activity_logs"
    )
    activity_type = models.CharField(max_length=50, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "activity_logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.activity_type}: {self.description[:50] if self.description else ''}"
