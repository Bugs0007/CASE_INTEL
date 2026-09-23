import re

from django.core.exceptions import ValidationError
from django.db import models

from .mixins import OwnedModel

# 15 characters: 2-digit state code, 10-character PAN, entity number,
# a literal "Z", checksum character.
GSTIN_RE = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$")


def validate_gstin(value: str) -> None:
    if value and not GSTIN_RE.match(value):
        raise ValidationError(
            "Enter a valid 15-character GSTIN (e.g. 36ABCDE1234F1Z5)."
        )


class Client(OwnedModel):
    """The advocate's client as a billing entity, spanning cases.

    ClientContact rows belong to one case each (the people to write to on
    that matter); a Client is who is actually billed, so it is what the
    per-client outstanding statement groups on and where GST details live.
    A case links to at most one Client. Case.client_name stays as the
    free-text name the conflict check and invoices already read.
    """

    TYPE_INDIVIDUAL = "individual"
    TYPE_BUSINESS = "business"

    CLIENT_TYPE_CHOICES = [
        (TYPE_INDIVIDUAL, "Individual"),
        (TYPE_BUSINESS, "Business entity"),
    ]

    name = models.CharField(max_length=255)
    client_type = models.CharField(
        max_length=20, choices=CLIENT_TYPE_CHOICES, default=TYPE_INDIVIDUAL
    )
    # Only printed (never used to compute tax): a business-entity client
    # gets the reverse-charge line and this GSTIN on its invoices.
    gstin = models.CharField(
        max_length=15, blank=True, default="", validators=[validate_gstin]
    )
    email = models.EmailField(blank=True, default="", help_text="Billing email for statements.")
    phone = models.CharField(max_length=50, blank=True, default="")
    address = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "clients"
        ordering = ["name", "id"]

    @property
    def is_business(self) -> bool:
        return self.client_type == self.TYPE_BUSINESS

    def __str__(self):
        return self.name
