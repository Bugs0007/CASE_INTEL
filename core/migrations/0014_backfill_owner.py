"""Backfill owner on all pre-existing rows to a single 'bhagath' account.

This repo is going from single-tenant (implicit -- no ownership at all) to
row-level multi-tenant. Every row that existed before this migration
predates per-user isolation, so it's attributed to a newly-created
'bhagath' user rather than left ownerless (owner is about to become
NOT NULL in the next migration).

The account is created with an unusable password on purpose -- Bhagath
sets the real password manually afterwards (e.g. `manage.py changepassword
bhagath`), so this migration can't accidentally leave a guessable/blank
credential sitting in any environment it runs in (including production).
"""

from django.contrib.auth.hashers import make_password
from django.db import migrations

OWNED_MODELS = [
    "Case",
    "Hearing",
    "Document",
    "DocumentChunk",
    "DocumentVersion",
    "Conversation",
    "Message",
    "Citation",
    "Folder",
    "Email",
    "EmailAttachment",
    "CourtOrder",
    "CourtFetchLog",
    "Task",
    "ActivityLog",
    "ProcessingJob",
    "GmailCredential",
]


def backfill_owner(apps, schema_editor):
    User = apps.get_model("auth", "User")
    bhagath, created = User.objects.get_or_create(
        username="bhagath",
        defaults={"is_staff": True, "is_superuser": True},
    )
    if created:
        # Historical models (as used in RunPython) don't carry custom
        # methods like set_unusable_password() -- only fields/Meta -- so
        # replicate what it does directly: make_password(None) produces
        # the same "unusable password" marker.
        bhagath.password = make_password(None)
        bhagath.save()

    for model_name in OWNED_MODELS:
        model = apps.get_model("core", model_name)
        model.objects.filter(owner__isnull=True).update(owner=bhagath)


def noop_reverse(apps, schema_editor):
    # Intentionally irreversible in the direction that would matter (there's
    # no way to know which rows were "really" ownerless before forward()
    # ran), and unsetting owner would just violate the NOT NULL constraint
    # added in the next migration anyway. Leaving owner set on reverse is
    # the only sane behavior.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_add_owner_fields"),
    ]

    operations = [
        migrations.RunPython(backfill_owner, noop_reverse),
    ]
