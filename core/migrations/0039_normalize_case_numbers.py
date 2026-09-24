"""Tidy case numbers stored before intake normalised them.

"WP /26147/2026" (a stray space the portal HTML puts after the case-type
prefix) becomes "WP/26147/2026", with the original kept in
case_number_raw. Every owner's cases, not just one -- the older
backfill_case_number_format command took a single --owner and was never
run in production.

A case whose tidied number would collide with another case of the same
owner (the same real case imported twice under two spellings) is left
alone and printed: merging two cases needs a person, not a migration.

Plain row UPDATEs, one per changed case; no schema change here (0038 added
the column). Reverse puts the raw value back.
"""

from django.db import migrations

from core.services.case_numbers import normalize_case_number


def forwards(apps, schema_editor):
    Case = apps.get_model("core", "Case")
    changed = skipped = 0
    for case in Case.objects.only("id", "owner_id", "case_number", "case_number_raw").iterator():
        normalized = normalize_case_number(case.case_number)
        if not normalized or normalized == case.case_number:
            continue
        if Case.objects.filter(owner_id=case.owner_id, case_number=normalized).exclude(pk=case.pk).exists():
            skipped += 1
            print(f"\n  case {case.id}: {case.case_number!r} left as is -- {normalized!r} is another of this owner's cases.")
            continue
        Case.objects.filter(pk=case.pk).update(
            case_number=normalized, case_number_raw=case.case_number_raw or case.case_number
        )
        changed += 1
    if changed or skipped:
        print(f"\n  Case numbers: {changed} tidied, {skipped} left for review (collisions).")


def backwards(apps, schema_editor):
    Case = apps.get_model("core", "Case")
    for case in Case.objects.exclude(case_number_raw="").only("id", "case_number_raw").iterator():
        Case.objects.filter(pk=case.pk).update(case_number=case.case_number_raw)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0038_case_number_raw"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
