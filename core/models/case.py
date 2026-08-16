from django.db import models

from .mixins import OwnedModel


class Case(OwnedModel):
    CASE_TYPE_CHOICES = [
        ("civil", "Civil"),
        ("criminal", "Criminal"),
        ("family", "Family"),
        ("corporate", "Corporate"),
        ("ip", "Intellectual Property"),
        ("labor", "Labor"),
        ("tax", "Tax"),
        ("other", "Other"),
    ]

    STATUS_CHOICES = [
        ("open", "Open"),
        ("closed", "Closed"),
        ("pending", "Pending"),
        ("archived", "Archived"),
    ]

    PRIORITY_CHOICES = [
        ("low", "Low"),
        ("medium", "Medium"),
        ("high", "High"),
        ("critical", "Critical"),
    ]

    COURT_TYPE_CHOICES = [
        ("district", "District Court"),
        ("high_court", "High Court"),
    ]

    FETCH_STATUS_CHOICES = [
        ("never_fetched", "Never Fetched"),
        ("success", "Success"),
        ("failed", "Failed"),
    ]

    USER_PARTY_ROLE_CHOICES = [
        ("unknown", "Unknown"),
        ("petitioner", "Petitioner"),
        ("respondent", "Respondent"),
    ]

    case_number = models.CharField(max_length=100, unique=True)
    title = models.CharField(max_length=500)
    client_name = models.CharField(max_length=255)
    opposing_party = models.CharField(max_length=255, blank=True, null=True)
    case_type = models.CharField(max_length=50, choices=CASE_TYPE_CHOICES, blank=True, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="open")
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default="medium")
    filing_date = models.DateField(blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # --- Court tracking (eCourts) ---
    cnr_number = models.CharField(max_length=16, blank=True, null=True, db_index=True)
    court_type = models.CharField(
        max_length=20, choices=COURT_TYPE_CHOICES, blank=True, null=True
    )
    tracking_config = models.JSONField(
        blank=True,
        null=True,
        help_text=(
            "Court hierarchy + case_type/case_number/year used to look this "
            "case up on eCourts. Shape depends on court_type: district needs "
            "state_code/dist_code/court_complex_code/est_code; high_court "
            "needs hc_court_code/state_code/bench_code. Both need "
            "case_type/case_number/year."
        ),
    )
    last_fetched_at = models.DateTimeField(blank=True, null=True)
    fetch_status = models.CharField(
        max_length=20, choices=FETCH_STATUS_CHOICES, default="never_fetched"
    )
    tracking_enabled = models.BooleanField(default=False)
    party_advocate_data = models.JSONField(
        blank=True,
        null=True,
        help_text=(
            "Raw per-party advocate name(s) as returned by eCourts case "
            "details, e.g. {'petitioner_advocates': [...], "
            "'respondent_advocates': [...]}. Captured during the full CNR "
            "fetch for party-role detection."
        ),
    )
    user_party_role = models.CharField(
        max_length=20, choices=USER_PARTY_ROLE_CHOICES, default="unknown"
    )

    class Meta:
        db_table = "cases"
        ordering = ["-created_at"]
        constraints = [
            # DB-level backstop for the same-user CNR duplicate check the
            # "Track by CNR" quick-add flow does in application code (see
            # create_case_from_cnr_preview in core/services/court_tracking.py).
            # cnr_number is nullable, and Postgres treats NULLs as distinct
            # in unique constraints, so cases with no CNR yet are unaffected.
            models.UniqueConstraint(
                fields=["owner", "cnr_number"], name="unique_case_owner_cnr_number"
            )
        ]

    def __str__(self):
        return f"{self.case_number} - {self.title}"
