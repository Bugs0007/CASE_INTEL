"""Conversation scope and typed message references.

Two additive changes, nothing existing is rewritten or dropped (primary keys,
messages, citations and titles are untouched):

1. `conversations.scope` (case / legacy_documents / practice), backfilled
   from the nullable case FK: a row with a case is `case`, a row without one
   is `legacy_documents`. A CHECK keeps the two in step from then on:
   `case` needs a case, the other two need none.
2. `messages.references`, a jsonb list (default `[]`) of typed pointers to
   owned records, written by the practice assistant.

Both tables hold production rows, so this follows CLAUDE.md's staging and no
statement holds a long ACCESS EXCLUSIVE lock:

    ADD COLUMN ... NOT NULL DEFAULT <constant>   metadata-only on Postgres 11+
    ADD CONSTRAINT ... NOT VALID                 no scan
    UPDATE ... backfill                          row locks only
    VALIDATE CONSTRAINT                          scans under SHARE UPDATE
                                                 EXCLUSIVE; reads and writes
                                                 carry on
    DROP DEFAULT (scope only)                    metadata-only

`atomic = False` is what makes that staging real: inside one migration-wide
transaction the first ALTER TABLE's lock would be held to the very end.

The CHECK goes on before the backfill on purpose. NOT VALID skips existing
rows but applies to every write from then on, so no blank-scope row can slip
in between the backfill and VALIDATE; the backfill itself only writes values
the CHECK accepts.

Deploy window: deploy.yml runs `migrate` and only then restarts the app, so
for a moment the OLD code runs against the NEW schema.
- `messages.references` keeps its column DEFAULT for that reason: old code
  omits the column on INSERT and still gets `[]`. Django supplies the value
  itself, so the default is otherwise unused.
- `conversations.scope` has no constant that is right for every row (it
  depends on the case), so old code cannot START a conversation in that
  window: the insert is refused and the request fails. Continuing an existing
  conversation is unaffected. The window ends at the restart.

Re-runnable: a non-atomic migration that fails part-way is not recorded as
applied and leaves whatever it got through in place, so every statement is
safe to run again (IF NOT EXISTS / IF EXISTS, a backfill that only touches
blank rows).
"""

from django.db import migrations, models

CHECK_NAME = "conversations_scope_matches_case_chk"

ADD_SCOPE_SQL = [
    # 1. Constant default: catalog change only, no table rewrite.
    "ALTER TABLE conversations "
    "ADD COLUMN IF NOT EXISTS scope varchar(20) NOT NULL DEFAULT ''",
    # 1b. A first backfill before the CHECK exists. A CHECK is evaluated on
    # every UPDATE of a row, so once it is on, the old code's update of
    # last_message_at on a still-blank conversation would be refused. Filling
    # the rows first shrinks that gap to almost nothing; step 3 catches any
    # row inserted in between.
    "UPDATE conversations SET scope = CASE WHEN case_id IS NOT NULL "
    "THEN 'case' ELSE 'legacy_documents' END WHERE scope = ''",
    # 2. The CHECK, without scanning the rows that are still blank.
    f"ALTER TABLE conversations DROP CONSTRAINT IF EXISTS {CHECK_NAME}",
    f"ALTER TABLE conversations ADD CONSTRAINT {CHECK_NAME} CHECK ("
    "(scope = 'case' AND case_id IS NOT NULL) OR "
    "(scope IN ('legacy_documents', 'practice') AND case_id IS NULL)"
    ") NOT VALID",
    # 3. Backfill from the case FK.
    "UPDATE conversations SET scope = CASE WHEN case_id IS NOT NULL "
    "THEN 'case' ELSE 'legacy_documents' END WHERE scope = ''",
    # 4. Scan without blocking reads or writes.
    f"ALTER TABLE conversations VALIDATE CONSTRAINT {CHECK_NAME}",
    # 5. Django supplies scope itself; '' is never a valid stored value.
    "ALTER TABLE conversations ALTER COLUMN scope DROP DEFAULT",
]

REMOVE_SCOPE_SQL = [
    f"ALTER TABLE conversations DROP CONSTRAINT IF EXISTS {CHECK_NAME}",
    "ALTER TABLE conversations DROP COLUMN IF EXISTS scope",
]

# "references" is a reserved word in Postgres, hence the quotes.
ADD_REFERENCES_SQL = (
    'ALTER TABLE messages ADD COLUMN IF NOT EXISTS "references" jsonb '
    "NOT NULL DEFAULT '[]'::jsonb"
)

REMOVE_REFERENCES_SQL = 'ALTER TABLE messages DROP COLUMN IF EXISTS "references"'


class Migration(migrations.Migration):
    # See the module docstring: without this the staging above is pointless.
    atomic = False

    dependencies = [
        ("core", "0050_case_business_entry"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(sql=ADD_SCOPE_SQL, reverse_sql=REMOVE_SCOPE_SQL),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="conversation",
                    name="scope",
                    field=models.CharField(
                        blank=True,
                        choices=[
                            ("case", "Case"),
                            ("legacy_documents", "Legacy documents"),
                            ("practice", "Practice"),
                        ],
                        max_length=20,
                    ),
                ),
                migrations.AddConstraint(
                    model_name="conversation",
                    constraint=models.CheckConstraint(
                        condition=models.Q(
                            models.Q(("case__isnull", False), ("scope", "case")),
                            models.Q(
                                ("case__isnull", True),
                                ("scope__in", ["legacy_documents", "practice"]),
                            ),
                            _connector="OR",
                        ),
                        name=CHECK_NAME,
                    ),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=ADD_REFERENCES_SQL, reverse_sql=REMOVE_REFERENCES_SQL
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="message",
                    name="references",
                    field=models.JSONField(blank=True, default=list),
                ),
            ],
        ),
    ]
