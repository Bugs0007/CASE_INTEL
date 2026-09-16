"""Fill Case.petitioner_name / respondent_name for cases imported before
those columns existed -- without touching the court portal.

Every advocate search already stored each result's parties in its job
payload (advocate_search: payload["results"]; advocate_import:
payload["selected"]), keyed by CNR. This reads those, newest job first,
and fills blanks on the same owner's cases with a matching CNR. Cases no
job mentions get their names on their next tracking refresh.

Only blank fields are filled; a name already set (by a fetch) is never
overwritten, since the fetch is more recent than any search.

Usage:
    python manage.py backfill_party_names --dry-run
    python manage.py backfill_party_names
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import Case, ProcessingJob


class Command(BaseCommand):
    help = "Backfill case party names from stored advocate-search results (no portal calls)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report only; write nothing.")

    def handle(self, *args, **options):
        names = self._names_by_owner_and_cnr()

        updated = 0
        cases = Case.objects.filter(cnr_number__isnull=False).exclude(cnr_number="")
        with transaction.atomic():
            for case in cases.iterator():
                found = names.get((case.owner_id, case.cnr_number))
                if not found:
                    continue
                fields = []
                for field, value in zip(("petitioner_name", "respondent_name"), found):
                    if value and not getattr(case, field):
                        setattr(case, field, value)
                        fields.append(field)
                if fields:
                    updated += 1
                    if not options["dry_run"]:
                        case.save(update_fields=fields)

        prefix = "[dry run] would update" if options["dry_run"] else "Updated"
        self.stdout.write(f"{prefix} {updated} case(s) from {len(names)} stored search result(s).")

    @staticmethod
    def _names_by_owner_and_cnr() -> dict[tuple[int, str], tuple[str, str]]:
        names: dict[tuple[int, str], tuple[str, str]] = {}
        jobs = ProcessingJob.objects.filter(
            job_type__in=["advocate_search", "advocate_import"]
        ).order_by("-created_at")
        for job in jobs.iterator():
            payload = job.payload or {}
            items = payload.get("results") or payload.get("selected") or []
            for item in items:
                if not isinstance(item, dict):
                    continue
                cnr = (item.get("cnr_number") or "").strip()
                petitioner = (item.get("petitioner") or "").strip()
                respondent = (item.get("respondent") or "").strip()
                key = (job.owner_id, cnr)
                # Newest job first: keep the first value seen for each CNR.
                if cnr and (petitioner or respondent) and key not in names:
                    names[key] = (petitioner, respondent)
        return names
