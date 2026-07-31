from django.db import models

from .mixins import OwnedModel


class AdvocateProfile(OwnedModel):
    """The advocate's own billing identity: what goes on the invoice
    letterhead, plus their default appearance fee and invoice counter.

    One row per user, enforced by a UniqueConstraint on `owner` rather
    than a OneToOneField -- OwnedModel supplies `owner` as a plain FK for
    every model in this project, and keeping that uniform (instead of
    special-casing the field type here) is what lets OwnerScopedMixin and
    the rest of the multi-tenancy machinery treat this model like any
    other owned row.

    `last_invoice_sequence` is the per-user invoice counter. It lives
    here, on a single row per advocate, precisely so issuing a number can
    be a SELECT ... FOR UPDATE on one row (see
    core/services/invoice_service.py: allocate_invoice_number) -- two
    advocates never contend, and one advocate's concurrent requests can't
    both read the same value and mint a duplicate number.
    """

    letterhead_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Name/firm as it should appear at the top of the invoice.",
    )
    address = models.TextField(
        blank=True, default="", help_text="Letterhead address block (free text, multi-line)."
    )
    bar_registration_number = models.CharField(
        max_length=100, blank=True, default="", help_text="Bar Council registration number."
    )
    default_fee_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        help_text="Pre-filled as the appearance fee amount for new hearings.",
    )
    invoice_prefix = models.CharField(
        max_length=16,
        blank=True,
        default="INV",
        help_text="Prefix for generated invoice numbers, e.g. 'INV' -> INV-0001.",
    )
    last_invoice_sequence = models.PositiveIntegerField(
        default=0,
        help_text=(
            "Highest invoice sequence issued to THIS advocate. Never "
            "decremented -- a deleted invoice does not free its number."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "advocate_profiles"
        constraints = [
            models.UniqueConstraint(
                fields=["owner"], name="unique_advocate_profile_per_owner"
            )
        ]

    def __str__(self):
        return self.letterhead_name or f"Advocate profile for user {self.owner_id}"
