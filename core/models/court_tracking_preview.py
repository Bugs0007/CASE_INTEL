from django.conf import settings
from django.db import models


class CourtTrackingPreview(models.Model):
    """Postgres-backed store for the preview -> confirm handoff in court
    tracking setup (core/services/court_tracking.py).

    Replaces a LocMemCache-based token store. LocMemCache is per-process,
    and production runs gunicorn with multiple workers -- a preview token
    written by preview_case_tracking() on one worker was invisible to
    confirm_case_tracking() if it landed on a different worker, causing a
    false PreviewExpiredError even for a genuinely fresh token. This table
    is visible to every worker process, since it's just Postgres, so that
    race is gone. The court-structure/hierarchy cache in
    core/services/court_data/ecourts_provider.py stays on LocMemCache --
    that one is read-only, "changes ~never" data, so a per-worker copy is
    harmless.

    Rows are single-use: confirm_case_tracking() deletes the row on a
    successful confirm. Rows that are never confirmed are cleaned up
    opportunistically once past expires_at (see
    court_tracking._cleanup_expired_previews()) -- no Celery/cron needed,
    this table only ever sees setup-flow volume.
    """

    token = models.CharField(max_length=64, unique=True, db_index=True)
    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, related_name="tracking_previews"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+"
    )
    payload = models.JSONField(
        help_text="Fetched CourtCaseData (via CourtCaseData.to_dict()) plus the tracking_config it was fetched with."
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "court_tracking_previews"
        ordering = ["-created_at"]

    def __str__(self):
        return f"preview {self.token[:8]}... for case {self.case_id}"
