"""Create Client records for existing cases and link them.

Cases created before the Client model have none. This groups each owner's
UNLINKED cases into would-be clients -- by the billing contact's email
(case-insensitive), falling back to the normalised client name -- creates
one Client per group and links the cases. Grouping never crosses owners,
and a case that is already linked is never touched.

Grouping is a heuristic (two different people can share a name), so run it
with --dry-run first and read the groups; anything wrong can be re-assigned
from the case page afterwards.

Usage:
    python manage.py backfill_clients --dry-run
    python manage.py backfill_clients
    python manage.py backfill_clients --owner <username>
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import Case, Client
from core.services.billing_portfolio import group_cases_for_backfill


class Command(BaseCommand):
    help = "Create Client records for unlinked cases, grouped per owner (heuristic -- dry-run first)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print the groups; write nothing.")
        parser.add_argument("--owner", help="Only this username's cases.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        User = get_user_model()
        owners = User.objects.all().order_by("id")
        if options["owner"]:
            owners = owners.filter(username=options["owner"])
            if not owners.exists():
                raise CommandError(f"No user called {options['owner']!r}.")

        created = linked = 0
        for owner in owners:
            cases = list(
                Case.objects.filter(owner=owner, client__isnull=True)
                .prefetch_related("client_contacts")
                .order_by("id")
            )
            if not cases:
                continue
            plan = group_cases_for_backfill(cases)
            if not plan:
                continue
            self.stdout.write(f"\n{owner.username}: {len(plan)} client(s) from {len(cases)} unlinked case(s)")
            with transaction.atomic():
                for group in plan:
                    numbers = ", ".join(c.case_number for c in group["cases"])
                    self.stdout.write(f"  {group['name']!r} <{group['email'] or '-'}>  ({group['key']}): {numbers}")
                    if dry_run:
                        continue
                    client = Client.objects.create(owner=owner, name=group["name"][:255], email=group["email"])
                    Case.objects.filter(
                        owner=owner, id__in=[c.id for c in group["cases"]], client__isnull=True
                    ).update(client=client)
                    created += 1
                    linked += len(group["cases"])

        if dry_run:
            self.stdout.write(self.style.WARNING("\n[dry run] nothing written."))
        else:
            self.stdout.write(self.style.SUCCESS(f"\nCreated {created} client(s), linked {linked} case(s)."))
