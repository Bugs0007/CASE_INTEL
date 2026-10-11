"""Fill `Case.court_locator` for district cases that will have a hearing soon.

The locator says which court (judge) a district case is heard in, in the
terms the cause-list portal needs. New fetches fill it automatically
(`court_tracking._apply_case_data`); this command catches up the cases that
were last fetched before that existed. Cheapest source first:

  1. STORED DATA (free): cascade-form cases carry the hierarchy in
     tracking_config, and the court number is in the latest stored fetch
     snapshot.
  2. A CAPTCHA-free dropdown call to find the court complex of an
     establishment already known (cached per district).
  3. ONE CNR lookup on the portal (CAPTCHA-gated, slow), only for cases that
     still have no locator after 1 and 2.

Only stage 3 is capped by --limit and throttled by --sleep. It stops when an
advocate search/import (or a tracked-case refresh) is running, exactly like
the cause-list run itself.

    manage.py backfill_court_locators --dry-run
    manage.py backfill_court_locators --limit 25 --sleep 6
"""

from __future__ import annotations

import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Case
from core.services.causelists import lock
from core.services.causelists.base import PORTAL_DISTRICT
from core.services.causelists.locator import complete_complex, derive_from_stored, locator_from_hints


class Command(BaseCommand):
    help = "Backfill Case.court_locator for district cases with an upcoming hearing."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what would happen; write and fetch nothing.")
        parser.add_argument("--limit", type=int, default=25, help="Max portal CNR lookups (stage 3). Default 25.")
        parser.add_argument("--sleep", type=float, default=6.0, help="Seconds between portal lookups. Default 6.")
        parser.add_argument("--days", type=int, default=14, help="Only cases with a scheduled hearing within N days. Default 14.")
        parser.add_argument("--owner", help="Only this user's cases (username).")

    def handle(self, *args, **options):
        dry = options["dry_run"]
        horizon = timezone.now() + timedelta(days=options["days"])
        cases = (
            Case.objects.filter(
                court_type="district",
                hearings__status="scheduled",
                hearings__hearing_date__gte=timezone.now() - timedelta(days=1),
                hearings__hearing_date__lte=horizon,
            )
            .distinct()
            .order_by("id")
        )
        if options["owner"]:
            cases = cases.filter(owner__username=options["owner"])

        counts = {"complete": 0, "from_stored": 0, "complex_resolved": 0, "needs_lookup": 0, "looked_up": 0, "failed": 0}
        needs_lookup: list[Case] = []
        for case in cases:
            loc = case.court_locator if (case.court_locator or {}).get("kind") == "district" else None
            if loc and loc.get("complex_code") and loc.get("court_no"):
                counts["complete"] += 1
                continue
            if not loc:
                loc = derive_from_stored(case)
                if loc:
                    counts["from_stored"] += 1
            if loc and not loc.get("complex_code"):
                if dry:
                    counts["complex_resolved"] += 1
                    continue
                completed = complete_complex(loc)
                if completed is None:
                    counts["failed"] += 1
                    continue
                loc = completed
                counts["complex_resolved"] += 1
            if loc and loc.get("complex_code") and loc.get("court_no"):
                if not dry:
                    case.court_locator = loc
                    case.save(update_fields=["court_locator"])
                continue
            if case.cnr_number:
                needs_lookup.append(case)
                counts["needs_lookup"] += 1

        self.stdout.write(
            f"{'[dry run] ' if dry else ''}already complete: {counts['complete']}; "
            f"filled from stored data: {counts['from_stored']}; complex resolved: {counts['complex_resolved']}; "
            f"need a portal lookup: {counts['needs_lookup']}; failed: {counts['failed']}"
        )
        if dry or not needs_lookup:
            return

        from core.services.court_data.ecourts_provider import EcourtsProvider
        from core.services.court_data.exceptions import CourtDataError

        provider = EcourtsProvider()
        done = 0
        for case in needs_lookup[: options["limit"]]:
            reason = lock.blocked_reason(PORTAL_DISTRICT)
            if reason:
                self.stdout.write(self.style.WARNING(f"Stopping: {reason}."))
                break
            try:
                data = provider.fetch_case_by_cnr(case.cnr_number, "district")
            except CourtDataError as exc:
                counts["failed"] += 1
                self.stderr.write(f"case {case.pk} ({case.cnr_number}): {exc}")
                continue
            loc = locator_from_hints(data.locator_hints, case.tracking_config, case.court_locator)
            if loc is not None:
                loc = complete_complex(loc, provider) or loc
                case.court_locator = loc
                case.save(update_fields=["court_locator"])
                counts["looked_up"] += 1
            else:
                counts["failed"] += 1
                self.stderr.write(f"case {case.pk}: the court page carried no location facts.")
            done += 1
            time.sleep(options["sleep"])
        self.stdout.write(f"Portal lookups: {done} (located {counts['looked_up']}); {len(needs_lookup) - done} left for the next run.")
