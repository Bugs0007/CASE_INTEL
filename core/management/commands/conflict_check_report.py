"""Read-only: run the intake conflict check across one advocate's existing
portfolio and print every hit.

For tuning core/services/conflict_check.py's thresholds against real
names before (and after) changing them -- how many hits a portfolio
produces, and whether the "likely" ones really are the same party.

Usage:
    python manage.py conflict_check_report --owner bhagath
    python manage.py conflict_check_report --owner bhagath --band likely
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.models import Case
from core.services.conflict_check import BAND_LIKELY, find_conflicts


class Command(BaseCommand):
    help = "Report possible conflicts of interest within one advocate's cases (writes nothing)."

    def add_arguments(self, parser):
        parser.add_argument("--owner", required=True, help="Username whose cases to check.")
        parser.add_argument(
            "--band", choices=["likely", "possible"], help="Only show hits in this band."
        )

    def handle(self, *args, **options):
        owner = get_user_model().objects.filter(username=options["owner"]).first()
        if owner is None:
            raise CommandError(f"No user {options['owner']!r}.")

        seen: set[tuple[int, int, str, str]] = set()
        total = 0
        for case in Case.objects.filter(owner=owner).order_by("id"):
            hits = find_conflicts(
                owner,
                petitioner=case.petitioner_name,
                respondent=case.respondent_name,
                client_name=case.client_name or "",
                opposing_party=case.opposing_party or "",
                user_party_role=case.user_party_role,
                title=case.title,
                exclude_case_id=case.id,
            )
            for hit in hits:
                if options["band"] and hit.band != options["band"]:
                    continue
                # Each pair of cases shows up once, not once per direction.
                pair = (min(case.id, hit.case_id), max(case.id, hit.case_id), *sorted(
                    (hit.new_party.lower(), hit.existing_party.lower())
                ))
                if pair in seen:
                    continue
                seen.add(pair)
                total += 1
                marker = "!!" if hit.band == BAND_LIKELY else " ?"
                self.stdout.write(
                    f"{marker} {hit.score:>3} {hit.kind:<12} {case.case_number}: {hit.new_party!r} "
                    f"({hit.new_side}) ~ {hit.case_number}: {hit.existing_party!r} ({hit.existing_side})"
                )

        self.stdout.write(f"{total} possible conflict pair(s) across {owner.username}'s cases.")
