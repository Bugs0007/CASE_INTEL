# Data migration: backfill Case.title to the eCourts case number string
# (overwriting the old auto-generated "Petitioner vs Respondent" title --
# titles are now an advocate-editable label set via the case-details form,
# not an eCourts-derived value), and map any pre-existing Case.client_name
# into a single ClientContact row where one exists. See the case-details
# planning doc for the full mapping rationale: client_name is blank for
# every case created through the advocate-search/import flow (which has
# always passed client_name="" -- see core/services/advocate_import.py),
# so only cases created before that flow (or otherwise carrying a manually
# entered client_name) get a migrated row.

from django.db import migrations
from django.db.migrations.exceptions import IrreversibleError


def backfill(apps, schema_editor):
    Case = apps.get_model("core", "Case")
    ClientContact = apps.get_model("core", "ClientContact")

    for case in Case.objects.all().iterator():
        client_name = (case.client_name or "").strip()
        if client_name:
            ClientContact.objects.create(
                owner_id=case.owner_id,
                case=case,
                name=client_name,
                role="primary",
                is_billing_contact=True,
            )
        if case.title != case.case_number:
            case.title = case.case_number
            case.save(update_fields=["title"])


def unbackfill(apps, schema_editor):
    # Irreversible: the original auto-generated titles and the fact of
    # which ClientContact rows came from this migration (vs. ones the
    # advocate has since added/edited by hand) aren't recoverable.
    raise IrreversibleError(
        "0019_backfill_title_and_client_contacts cannot be reversed -- the "
        "pre-migration titles and migrated ClientContact rows aren't "
        "distinguishable from data added afterward."
    )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0018_case_party_role_clientcontact"),
    ]

    operations = [
        migrations.RunPython(backfill, unbackfill),
    ]
