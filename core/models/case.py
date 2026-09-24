from django.db import models

from core.services.case_numbers import normalize_case_number

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

    case_number = models.CharField(max_length=100)
    # The case number exactly as it first arrived, when tidying changed it
    # ("WP /26147/2026" from the portal -> case_number "WP/26147/2026").
    # Blank when it arrived clean. Kept for search and for matching the
    # portal's own spelling; never shown as the case number.
    case_number_raw = models.CharField(max_length=100, blank=True, default="")
    title = models.CharField(max_length=500)
    client_name = models.CharField(max_length=255)
    # The billing entity this matter belongs to (see core/models/client.py).
    # Optional: set by the advocate or by manage.py backfill_clients, never
    # guessed automatically at intake.
    client = models.ForeignKey(
        "core.Client",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        related_name="cases",
    )
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
    # Party names as the court record gives them, kept current on every
    # successful fetch (court_tracking._apply_case_data). Record-absolute --
    # which side is the advocate's comes from user_party_role -- unlike
    # client_name/opposing_party, which the advocate edits. Read by the
    # intake conflict check (core/services/conflict_check.py).
    petitioner_name = models.TextField(blank=True, default="")
    respondent_name = models.TextField(blank=True, default="")

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
            ),
            # Scoped per owner, not global: the same real court case is
            # routinely tracked by more than one advocate (co-counsel,
            # opposing counsel, different firms), each with their own
            # independent row -- own fee status, notes, documents. Only
            # one owner may hold a given case_number twice.
            models.UniqueConstraint(
                fields=["owner", "case_number"], name="unique_case_owner_case_number"
            ),
        ]

    def save(self, *args, **kwargs):
        """Every way a case is made -- manual entry, Track by CNR, advocate
        import -- lands here, so this is where the case number is tidied
        (and the original kept in case_number_raw)."""
        update_fields = kwargs.get("update_fields")
        if update_fields is None or "case_number" in update_fields:
            normalized = normalize_case_number(self.case_number)
            if normalized and normalized != self.case_number:
                if not self.case_number_raw:
                    self.case_number_raw = self.case_number
                self.case_number = normalized
                if update_fields is not None:
                    kwargs["update_fields"] = {*update_fields, "case_number_raw"}
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.case_number} - {self.title}"
