from django.db import models

from .case import Case
from .mixins import OwnedModel


class AdvocateSearchPreference(OwnedModel):
    """The court hierarchy an advocate last searched with, pre-filled on
    their next visit to the advocate-search page -- most lawyers work
    primarily in one or two courts, so re-selecting state/district/complex
    (or High Court/bench) on every search is repetitive.

    One row per user (upserted on every search), not versioned history.
    """

    court_type = models.CharField(max_length=20, choices=Case.COURT_TYPE_CHOICES)
    hierarchy_config = models.JSONField(
        help_text=(
            "district: state_code/dist_code/court_complex_code/est_code. "
            "high_court: hc_court_code/bench_code."
        )
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "advocate_search_preferences"
        constraints = [
            models.UniqueConstraint(fields=["owner"], name="one_advocate_search_preference_per_user"),
        ]

    def __str__(self):
        return f"Advocate search preference for {self.owner_id}"
