from django.db import models

from .mixins import OwnedModel


class CaseBriefing(OwnedModel):
    """The cached "state of the matter" paragraph on a hearing prep sheet.

    Same principle as the Order Overview on CourtOrder: generated in the
    process_jobs worker, read from this row on every view, so opening a
    prep sheet never costs an LLM call. Unlike an order, a case keeps
    changing, so the row records a fingerprint of the facts it was written
    from (core/services/hearing_digest/briefing.py); when the facts move on,
    the paragraph is stale and can be regenerated.

    The paragraph names the petitioner and respondent, never "you" -- which
    side is the advocate's is applied when the sheet is rendered, so
    correcting the party role needs no regeneration.
    """

    STATUS_READY = "ready"
    STATUS_FAILED = "failed"

    STATUS_CHOICES = [
        (STATUS_READY, "Ready"),
        (STATUS_FAILED, "Failed"),
    ]

    case = models.OneToOneField(
        "core.Case", on_delete=models.CASCADE, related_name="briefing"
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES)
    # sha256 of the facts the text was generated from.
    input_fingerprint = models.CharField(max_length=64)
    text = models.TextField(blank=True, default="")
    error = models.TextField(blank=True, default="")
    llm_calls = models.PositiveSmallIntegerField(default=0)
    generated_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "case_briefings"

    def __str__(self):
        return f"Briefing for case {self.case_id} ({self.status})"
