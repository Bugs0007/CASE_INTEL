from django.db import models


class CourtFetchLog(models.Model):
    """Audit trail for every real eCourts fetch attempt (not cache hits)."""

    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, related_name="fetch_logs"
    )
    timestamp = models.DateTimeField(auto_now_add=True)
    success = models.BooleanField(default=False)
    error_message = models.TextField(blank=True, null=True)
    fields_changed = models.JSONField(
        blank=True,
        null=True,
        help_text="Diff of what changed on this fetch (e.g. {'next_hearing_date': ['2026-07-20', '2026-08-03']}).",
    )
    duration_ms = models.IntegerField(blank=True, null=True)

    class Meta:
        db_table = "court_fetch_logs"
        ordering = ["-timestamp"]

    def __str__(self):
        outcome = "OK" if self.success else "FAILED"
        return f"{self.case_id} @ {self.timestamp} [{outcome}]"
