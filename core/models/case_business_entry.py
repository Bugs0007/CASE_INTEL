from django.db import models

from .mixins import OwnedModel


class CaseBusinessEntry(OwnedModel):
    """The District Courts "Daily Status" (Business on Date) of one hearing
    date of a tracked case: what the court recorded that day, and the next
    purpose/date it set.

    High Courts publish order documents; most district courts publish only
    this text, so for them it is the record of what happened at a hearing.

    Immutable once stored: a date's business does not change on the portal,
    so the fetch (core/services/daily_status.py, worker only) asks only for
    dates it does not hold yet, and never rewrites a row. Party names are
    never stored.
    """

    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, related_name="business_entries"
    )
    business_date = models.DateField()
    court_name = models.CharField(max_length=255, blank=True, default="")
    business_text = models.TextField(blank=True, default="")
    next_purpose = models.CharField(max_length=255, blank=True, default="")
    next_hearing_date = models.DateField(blank=True, null=True)
    fetched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-business_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["case", "business_date"], name="uniq_case_business_date"
            ),
        ]

    def __str__(self) -> str:
        return f"Case {self.case_id} business on {self.business_date}"
