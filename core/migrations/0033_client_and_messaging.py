"""Clients, client-message drafts and the sent-message audit log.

New tables only (plus two choices-only AlterFields, which emit no SQL), so
this is an ordinary atomic migration: every CREATE runs against an empty
table and the FK constraints it adds to existing tables validate instantly.
The columns this feature adds to EXISTING tables (client_contacts,
advocate_profiles, cases) are staged separately in 0034.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import core.models.client


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_appearancefee_category_hearing_fk"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="document",
            name="document_type",
            field=models.CharField(
                blank=True,
                choices=[
                    ("contract", "Contract"),
                    ("pleading", "Pleading"),
                    ("evidence", "Evidence"),
                    ("correspondence", "Correspondence"),
                    ("brief", "Brief"),
                    ("motion", "Motion"),
                    ("order", "Order"),
                    ("court_order", "Court Order (eCourts)"),
                    ("generated", "Generated from template"),
                    ("other", "Other"),
                ],
                max_length=50,
                null=True,
            ),
        ),
        migrations.AlterField(
            model_name="processingjob",
            name="job_type",
            field=models.CharField(
                choices=[
                    ("document", "Document Processing"),
                    ("order_sync", "Court Order Sync"),
                    ("advocate_import", "Advocate Case Import"),
                    ("advocate_search", "Advocate Search (state-wide fan-out)"),
                    ("case_briefing", "Case Briefing (hearing prep sheet)"),
                    ("tracking_refresh", "Refresh All Tracked Cases"),
                ],
                default="document",
                max_length=20,
            ),
        ),
        migrations.CreateModel(
            name="Client",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255)),
                (
                    "client_type",
                    models.CharField(
                        choices=[("individual", "Individual"), ("business", "Business entity")],
                        default="individual",
                        max_length=20,
                    ),
                ),
                (
                    "gstin",
                    models.CharField(
                        blank=True,
                        default="",
                        max_length=15,
                        validators=[core.models.client.validate_gstin],
                    ),
                ),
                ("email", models.EmailField(blank=True, default="", help_text="Billing email for statements.", max_length=254)),
                ("phone", models.CharField(blank=True, default="", max_length=50)),
                ("address", models.TextField(blank=True, default="")),
                ("notes", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)ss",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "clients",
                "ordering": ["name", "id"],
            },
        ),
        migrations.CreateModel(
            name="ClientMessage",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                (
                    "kind",
                    models.CharField(
                        choices=[("case_update", "Case update"), ("payment_reminder", "Payment reminder")],
                        max_length=20,
                    ),
                ),
                ("dedup_key", models.CharField(max_length=120)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("draft", "Draft"),
                            ("sent", "Sent"),
                            ("logged", "Logged only (email not configured)"),
                            ("discarded", "Discarded"),
                        ],
                        default="draft",
                        max_length=20,
                    ),
                ),
                ("subject", models.CharField(max_length=255)),
                ("body", models.TextField()),
                ("recipients", models.JSONField(blank=True, default=list)),
                ("edited_by_user", models.BooleanField(default=False)),
                ("reminder_number", models.PositiveSmallIntegerField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("send_result", models.JSONField(blank=True, null=True)),
                ("discard_reason", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="client_messages",
                        to="core.case",
                    ),
                ),
                (
                    "court_order",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="client_messages",
                        to="core.courtorder",
                    ),
                ),
                (
                    "fee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="client_messages",
                        to="core.appearancefee",
                    ),
                ),
                (
                    "hearing",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="client_messages",
                        to="core.hearing",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)ss",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "client_messages",
                "ordering": ["-created_at", "-id"],
            },
        ),
        migrations.CreateModel(
            name="SentMessage",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("sent_at", models.DateTimeField(auto_now_add=True)),
                (
                    "kind",
                    models.CharField(
                        choices=[
                            ("case_update", "Case update"),
                            ("payment_reminder", "Payment reminder"),
                            ("invoice", "Invoice"),
                        ],
                        max_length=20,
                    ),
                ),
                (
                    "delivery",
                    models.CharField(
                        choices=[("sent", "Sent"), ("logged", "Logged only (email not configured)")],
                        max_length=20,
                    ),
                ),
                ("to_emails", models.JSONField(default=list)),
                ("cc_emails", models.JSONField(blank=True, default=list)),
                ("subject", models.CharField(max_length=255)),
                ("body_sha256", models.CharField(max_length=64)),
                (
                    "case",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="sent_messages",
                        to="core.case",
                    ),
                ),
                (
                    "fee",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deliveries",
                        to="core.appearancefee",
                    ),
                ),
                (
                    "message",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deliveries",
                        to="core.clientmessage",
                    ),
                ),
                (
                    "owner",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="%(class)ss",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "sent_by",
                    models.ForeignKey(
                        blank=True,
                        help_text="Who pressed Send. Null only for a system-initiated send.",
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "sent_messages",
                "ordering": ["-sent_at", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="clientmessage",
            index=models.Index(fields=["owner", "status"], name="client_mess_owner_i_aa6428_idx"),
        ),
        migrations.AddConstraint(
            model_name="clientmessage",
            constraint=models.UniqueConstraint(
                fields=("owner", "dedup_key"), name="unique_client_message_per_owner"
            ),
        ),
    ]
