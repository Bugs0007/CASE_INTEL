# Hand-written (not via makemigrations --noinput, which can't skip the
# interactive "provide a default" prompt for NOT NULL alterations even
# though 0014_backfill_owner already guarantees no NULLs remain).

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

OWNED_MODELS = [
    "activitylog",
    "case",
    "citation",
    "conversation",
    "courtfetchlog",
    "courtorder",
    "document",
    "documentchunk",
    "documentversion",
    "email",
    "emailattachment",
    "folder",
    "gmailcredential",
    "hearing",
    "message",
    "processingjob",
    "task",
]


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_backfill_owner"),
    ]

    operations = [
        migrations.AlterField(
            model_name=model_name,
            name="owner",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="%(class)ss",
                to=settings.AUTH_USER_MODEL,
            ),
        )
        for model_name in OWNED_MODELS
    ]
