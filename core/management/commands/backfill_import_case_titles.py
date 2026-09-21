"""Give already-imported advocate-search cases a real title and opposing party.

run_advocate_import used to create every case titled with its case number
and with no opposing party. New imports now get "Petitioner vs Respondent"
and, where the advocate's side was detected, the other side (see
party_labels in core/services/advocate_import.py); this repairs the rows
created before that. No portal calls.

It works from Case.petitioner_name / respondent_name. A case where those are
still blank is skipped and reported -- run `backfill_party_names` first,
which fills them from the stored search results.

Only fills in what is still untouched, so it is safe to re-run:
  - title changes only if it still equals case_number (the old import
    default); a title the advocate edited is never overwritten.
  - opposing_party is set only if blank, and only when user_party_role is
    known -- with the role unknown, which side is theirs would be a guess.

Usage:
    python manage.py backfill_import_case_titles --owner recruiter --min-id 32 --max-id 48 --dry-run
    python manage.py backfill_import_case_titles --owner recruiter --min-id 32 --max-id 48
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Case
from core.services.advocate_import import party_labels


class Command(BaseCommand):
    help = (
        "Give already-imported advocate-search cases a 'Petitioner vs Respondent' "
        "title and opposing party from their stored party names (no portal calls)."
    )

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True, help="Username whose cases to fix.")
        parser.add_argument("--min-id", type=int, help="Only case ids >= this.")
        parser.add_argument("--max-id", type=int, help="Only case ids <= this.")
        parser.add_argument("--dry-run", action="store_true", help="Report only; write nothing.")

    def handle(self, *args, **options):
        User = get_user_model()
        try:
            owner = User.objects.get(username=options["owner"])
        except User.DoesNotExist:
            raise CommandError(f"No user named {options['owner']!r}.")

        # Imported cases always carry a CNR; the party-name lookup is keyed on
        # the case's own stored names, so this never reaches another owner's rows.
        cases = (
            Case.objects.filter(owner=owner)
            .exclude(cnr_number__isnull=True)
            .exclude(cnr_number="")
            .order_by("id")
        )
        if options["min_id"] is not None:
            cases = cases.filter(id__gte=options["min_id"])
        if options["max_id"] is not None:
            cases = cases.filter(id__lte=options["max_id"])

        dry_run = options["dry_run"]
        updated = unchanged = 0
        no_parties: list[int] = []
        role_unknown: list[int] = []

        with transaction.atomic():
            for case in cases.iterator():
                if not (case.petitioner_name or case.respondent_name):
                    if case.title == case.case_number:
                        no_parties.append(case.id)
                    else:
                        unchanged += 1
                    continue

                title, opposing_party = party_labels(
                    case.case_number, case.petitioner_name, case.respondent_name, case.user_party_role
                )
                fields = []
                if case.title == case.case_number and title != case.title:
                    case.title = title
                    fields.append("title")
                if not case.opposing_party and opposing_party:
                    case.opposing_party = opposing_party
                    fields.append("opposing_party")
                if not case.opposing_party and case.user_party_role == "unknown":
                    role_unknown.append(case.id)

                if not fields:
                    unchanged += 1
                    continue
                self.stdout.write(
                    f"case {case.id} ({case.case_number}): title={case.title!r}, "
                    f"opposing_party={case.opposing_party!r}"
                )
                if not dry_run:
                    case.save(update_fields=fields)
                updated += 1

        prefix = "[dry run] would update" if dry_run else "Updated"
        self.stdout.write(f"{prefix} {updated} case(s); {unchanged} already fine.")
        if no_parties:
            self.stdout.write(
                f"Skipped {len(no_parties)} case(s) with no party names on record -- run "
                f"`backfill_party_names` first: {', '.join(map(str, no_parties))}"
            )
        if role_unknown:
            self.stdout.write(
                f"{len(role_unknown)} case(s) have no opposing party because your side "
                "(petitioner or respondent) isn't set. Set it on the case and re-run, or fill "
                f"the opposing party in by hand: {', '.join(map(str, role_unknown))}"
            )
