"""Collapse a stray space between a case-type prefix and the slash that
follows it in already-stored Case.case_number values (e.g.
"WP /26147/2026" -> "WP/26147/2026") -- the portal HTML quirk behind this
is now normalized going forward at parse time (see
core.services.court_data.ecourts_parsing.normalize_case_number), but
existing rows imported before that fix need a one-time cleanup.

No portal calls -- this only rewrites the stored string.

case_number is unique per (owner, case_number): if normalizing a row's
case_number would collide with another case this owner already has (a
sign the same real case was imported twice under two differently-
formatted case numbers), that row is skipped and reported rather than
merged -- merging two cases with potentially different linked documents/
hearings needs a human decision, not a silent backfill.

Usage:
    python manage.py backfill_case_number_format --owner recruiter --dry-run
    python manage.py backfill_case_number_format --owner recruiter
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from core.models import Case
from core.services.court_data.ecourts_parsing import normalize_case_number


class Command(BaseCommand):
    help = "Collapse a stray space between a case-number prefix and its slash on already-stored cases."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True, help="Username whose cases to fix.")
        parser.add_argument("--dry-run", action="store_true", help="Report only; write nothing.")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            owner = User.objects.get(username=options["owner"])
        except User.DoesNotExist:
            raise CommandError(f"No user named {options['owner']!r}.")

        dry_run = options["dry_run"]
        updated = 0
        collisions: list[tuple[int, str, str]] = []

        for case in Case.objects.filter(owner=owner).order_by("id").iterator():
            normalized = normalize_case_number(case.case_number)
            if normalized == case.case_number:
                continue

            if (
                Case.objects.filter(owner=owner, case_number=normalized)
                .exclude(pk=case.pk)
                .exists()
            ):
                collisions.append((case.id, case.case_number, normalized))
                continue

            self.stdout.write(f"case {case.id}: {case.case_number!r} -> {normalized!r}")
            if not dry_run:
                try:
                    with transaction.atomic():
                        case.case_number = normalized
                        case.save(update_fields=["case_number"])
                except IntegrityError:
                    collisions.append((case.id, case.case_number, normalized))
                    continue
            updated += 1

        prefix = "[dry run] would update" if dry_run else "Updated"
        self.stdout.write(f"{prefix} {updated} case(s).")
        if collisions:
            self.stdout.write(
                f"Skipped {len(collisions)} case(s) whose normalized case_number collides with "
                "another of this owner's cases -- likely the same real case imported twice under "
                "two differently-formatted case numbers; needs a manual look, not an automatic merge:"
            )
            for case_id, before, after in collisions:
                self.stdout.write(f"  case {case_id}: {before!r} -> {after!r} (collision)")
