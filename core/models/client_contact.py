from django.db import models, transaction

from .mixins import OwnedModel


class ClientContact(OwnedModel):
    """A contact for the advocate's own client on a case -- name/email/phone
    plus a flat PRIMARY/ASSISTANT role (no hierarchy). A case can have
    several; exactly one may be the billing contact at a time.
    """

    ROLE_CHOICES = [
        ("primary", "Primary"),
        ("assistant", "Assistant"),
    ]

    # How the executant is described on a vakalatnama: "S/o Venkat Rao".
    RELATION_CHOICES = [
        ("", "Not set"),
        ("s/o", "S/o"),
        ("d/o", "D/o"),
        ("w/o", "W/o"),
        ("c/o", "C/o"),
    ]

    case = models.ForeignKey(
        "core.Case", on_delete=models.CASCADE, related_name="client_contacts"
    )
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True, null=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="primary")
    is_billing_contact = models.BooleanField(default=False)

    # Opt-outs, checked when a draft is written AND again at send time.
    receive_case_updates = models.BooleanField(
        default=True, help_text="Send this contact 'your matter was heard' updates."
    )
    receive_payment_reminders = models.BooleanField(
        default=True, help_text="Send this contact reminders about unpaid invoices."
    )

    # Executant details for generated documents (vakalatnama). Blank ones
    # are asked for at generation time instead -- see
    # core/services/doc_templates/.
    relation_type = models.CharField(
        max_length=5, choices=RELATION_CHOICES, blank=True, default=""
    )
    relation_name = models.CharField(
        max_length=255, blank=True, default="", help_text="Father's / husband's name."
    )
    age = models.PositiveSmallIntegerField(blank=True, null=True)
    address = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "client_contacts"
        ordering = ["-is_billing_contact", "name"]

    def save(self, *args, **kwargs):
        # Enforce at most one billing contact per case at save time: saving
        # this one as the billing contact demotes any other row on the same
        # case. Not a DB constraint -- "exactly one" in practice is upheld
        # by the frontend always submitting a single radio selection, not
        # by auto-promoting a replacement here.
        if self.is_billing_contact:
            with transaction.atomic():
                ClientContact.objects.filter(
                    case_id=self.case_id, is_billing_contact=True
                ).exclude(pk=self.pk).update(is_billing_contact=False)
                super().save(*args, **kwargs)
        else:
            super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.get_role_display()}) - case {self.case_id}"
