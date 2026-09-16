"""Create tasks from court-order directions for orders already summarised.

Order direction tasks are generated at ingest from now on (process_jobs);
this backfills orders summarised before that existed, and re-runs
generation after a bulk change. Same gates as at ingest -- see
core/services/tasks/from_orders.py -- so only each case's most recent
order, and only if it is recent, gets tasks.

Usage:
    python manage.py generate_order_tasks --dry-run
    python manage.py generate_order_tasks --owner bhagath
    python manage.py generate_order_tasks --case 42
"""

from collections import Counter

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Case, CourtOrder
from core.services.tasks.from_orders import sync_order_tasks_for_case


class _DryRunRollback(Exception):
    pass


class Command(BaseCommand):
    help = "Generate tasks from the directions in already-summarised court orders."

    def add_arguments(self, parser):
        parser.add_argument("--owner", help="Only this username's cases.")
        parser.add_argument("--case", type=int, help="Only this case id.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change, then roll everything back.",
        )

    def handle(self, *args, **options):
        cases = Case.objects.filter(
            court_orders__summary_status=CourtOrder.SUMMARY_SUMMARIZED
        ).distinct()
        if options["owner"]:
            cases = cases.filter(owner__username=options["owner"])
        if options["case"]:
            cases = cases.filter(id=options["case"])
        if not cases.exists():
            raise CommandError("No matching cases with summarised orders.")

        totals = Counter()
        reasons = Counter()
        try:
            with transaction.atomic():
                for case in cases.iterator():
                    for result in sync_order_tasks_for_case(case):
                        totals.update(
                            created=result.created,
                            updated=result.updated,
                            pruned=result.pruned,
                            skipped=result.skipped,
                        )
                        if result.reason:
                            reasons[result.reason] += 1
                if options["dry_run"]:
                    raise _DryRunRollback
        except _DryRunRollback:
            pass

        prefix = "[dry run, rolled back] " if options["dry_run"] else ""
        self.stdout.write(
            f"{prefix}{totals['created']} created, {totals['updated']} updated, "
            f"{totals['pruned']} pruned, {totals['skipped']} left alone (edited/closed by the advocate)."
        )
        if reasons:
            self.stdout.write(
                "Orders without tasks: "
                + ", ".join(f"{reason}={count}" for reason, count in sorted(reasons.items()))
            )
