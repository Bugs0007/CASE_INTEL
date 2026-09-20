"""A hearing can carry several charges, each with a category.

Two changes to `appearance_fees`:

1. `category`, a new NOT NULL column (appearance / hotel / flight / other).
2. `hearing` OneToOneField -> ForeignKey: the unique constraint on
   hearing_id goes, a plain index takes its place, and the reverse accessor
   becomes `appearance_fees`.

`category` is added the way CLAUDE.md prescribes for a NOT NULL column on a
table that holds real production rows, not with a bare AddField, so RDS is
never held under a long ACCESS EXCLUSIVE lock:

    ADD COLUMN (nullable, no default)   metadata-only, instant
    SET DEFAULT 'appearance'            see "deploy window" below
    UPDATE ... backfill                 existing rows -> 'appearance'
    ADD CONSTRAINT ... NOT VALID        CHECK (category IS NOT NULL); no scan
    VALIDATE CONSTRAINT                 does the scan, but under
                                        SHARE UPDATE EXCLUSIVE, so reads and
                                        writes carry on
    SET NOT NULL                        Postgres 12+ accepts the validated
                                        CHECK as proof and skips the scan
    DROP CONSTRAINT                     redundant once NOT NULL holds

`atomic = False` is what makes that staging real. Inside one migration-wide
transaction the ACCESS EXCLUSIVE lock taken by the first ALTER TABLE would be
held until the very end, and the NOT VALID -> VALIDATE split would buy
nothing. With it off, every statement commits on its own.

Deploy window: deploy.yml runs `migrate` and only then restarts the app, so
for a moment the OLD code runs against the NEW schema. The old code knows
nothing about `category` and omits it on INSERT; the column DEFAULT is what
keeps those inserts valid (and non-NULL, so VALIDATE can't trip over a row
that slipped in after the backfill). The default is set straight after the
column is added and left in place -- Django supplies the value itself, so it
is otherwise unused.

Re-runnable: a non-atomic migration that fails part-way is not recorded as
applied and leaves whatever it got through in place, so the `category`
statements are written to be safe to run again (IF NOT EXISTS / IF EXISTS).

The `hearing` AlterField is the opposite case and is forced atomic on its own
(see the operation below). It is a swap -- drop the FK, drop the unique
constraint, create the index, re-add the FK -- and left in autocommit a
failure part-way would strand hearing_id with no foreign-key constraint at
all, which a re-run would not put back.

Reversing: the AlterField is undone first. Turning `hearing` back into a
OneToOne fails while any hearing has more than one charge (the unique
constraint can't be restored over duplicates) -- expected, since that data
has no home in the old shape -- and because that step is atomic the failure
rolls back cleanly and the schema is left exactly as it was. Once every
hearing is down to one charge, the `category` column comes back off cleanly.

The AlterField's statements are ordinary, non-concurrent ones;
`appearance_fees` holds one advocate's fee rows, so they finish in
milliseconds.
"""

import django.db.models.deletion
from django.db import migrations, models

CHECK_NAME = "appearance_fees_category_not_null_chk"

ADD_CATEGORY_SQL = [
    # 1. Nullable, no default: catalog change only, no table rewrite.
    "ALTER TABLE appearance_fees ADD COLUMN IF NOT EXISTS category varchar(20)",
    # 2. From here on, rows inserted by not-yet-restarted old code get a
    #    value instead of NULL (see "Deploy window" above).
    "ALTER TABLE appearance_fees ALTER COLUMN category SET DEFAULT 'appearance'",
    # 3. Everything that existed before this migration is an appearance fee.
    "UPDATE appearance_fees SET category = 'appearance' WHERE category IS NULL",
    # 4. NOT NULL, staged. NOT VALID adds the CHECK without scanning...
    f"ALTER TABLE appearance_fees DROP CONSTRAINT IF EXISTS {CHECK_NAME}",
    f"ALTER TABLE appearance_fees ADD CONSTRAINT {CHECK_NAME} "
    "CHECK (category IS NOT NULL) NOT VALID",
    # ...VALIDATE scans without blocking reads or writes...
    f"ALTER TABLE appearance_fees VALIDATE CONSTRAINT {CHECK_NAME}",
    # ...and SET NOT NULL then reuses that proof instead of re-scanning.
    "ALTER TABLE appearance_fees ALTER COLUMN category SET NOT NULL",
    f"ALTER TABLE appearance_fees DROP CONSTRAINT {CHECK_NAME}",
]

REMOVE_CATEGORY_SQL = "ALTER TABLE appearance_fees DROP COLUMN IF EXISTS category"

ALTER_HEARING_TO_FK = migrations.AlterField(
    model_name="appearancefee",
    name="hearing",
    field=models.ForeignKey(
        on_delete=django.db.models.deletion.CASCADE,
        related_name="appearance_fees",
        to="core.hearing",
    ),
)
# The migration below is atomic = False, which would leave this operation in
# autocommit too. Operation.atomic is Django's per-operation override (the
# same flag RunPython(atomic=True) uses): a non-atomic migration wraps just
# this operation in a transaction, so the FK swap is all-or-nothing in both
# directions. See "The `hearing` AlterField" in the module docstring.
ALTER_HEARING_TO_FK.atomic = True


class Migration(migrations.Migration):
    # See the module docstring: without this the staging above is pointless.
    atomic = False

    dependencies = [
        ("core", "0031_case_party_names"),
    ]

    operations = [
        # Raw SQL on the database side, a plain AddField on the state side:
        # Django's own AddField would emit a single ADD COLUMN ... NOT NULL
        # DEFAULT statement, which is exactly what we're avoiding.
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(sql=ADD_CATEGORY_SQL, reverse_sql=REMOVE_CATEGORY_SQL),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="appearancefee",
                    name="category",
                    field=models.CharField(
                        choices=[
                            ("appearance", "Appearance Fee"),
                            ("hotel", "Hotel"),
                            ("flight", "Flight"),
                            ("other", "Other"),
                        ],
                        default="appearance",
                        max_length=20,
                    ),
                ),
            ],
        ),
        ALTER_HEARING_TO_FK,
    ]
