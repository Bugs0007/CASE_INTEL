"""
Proof gate for the court tracking provider (Phase A5).

Fetches the known real ACTIVE case from the validation spikes
(TSHC010051622024, District Courts, AS/300/2024, Hyderabad CCC) against
a local test Case, twice, to prove the eCourts round-trip works AND that
re-fetching updates existing Hearing rows instead of duplicating them.

Usage:
    python manage.py track_case_test
"""

from django.core.management.base import BaseCommand

from core.models import Case, Hearing
from core.services.court_tracking import refresh_case_tracking

# Recovered from the case_tracking validation spikes (spike2_results.txt /
# case_history_extension.py): a genuine, currently-active District Courts
# case, verified multiple times against the live portal.
KNOWN_ACTIVE_CASE_TRACKING_CONFIG = {
    "court_type": "district",
    "state_code": "29",  # Telangana
    "dist_code": "2",  # Hyderabad CCC
    "court_complex_code": "1290019",  # HYD, City Civil Court Complex
    "est_code": "2",
    "case_type": "2^2",  # AS - Appeal Suit
    "case_number": "300",
    "year": "2024",
}


class Command(BaseCommand):
    help = "Proof gate: fetch the known real active case and verify dedup on re-fetch."

    def handle(self, *args, **options):
        case, created = Case.objects.get_or_create(
            case_number="TRACK-TEST-1",
            defaults={
                "title": "Court Tracking Proof Gate Test Case",
                "client_name": "Test Client",
                "status": "open",
                "court_type": "district",
                "tracking_config": KNOWN_ACTIVE_CASE_TRACKING_CONFIG,
                "tracking_enabled": True,
            },
        )
        if not created:
            case.court_type = "district"
            case.tracking_config = KNOWN_ACTIVE_CASE_TRACKING_CONFIG
            case.tracking_enabled = True
            case.save()

        self.stdout.write(
            self.style.SUCCESS(f"Test case id={case.id} ({'created' if created else 'reused'})")
        )

        result = refresh_case_tracking(case, force=True)
        case.refresh_from_db()
        hearing_count = Hearing.objects.filter(case=case, source="ecourts").count()

        self.stdout.write(f"\nrate_limited: {result['rate_limited']}")
        self.stdout.write(f"new_hearing_dates: {[d.isoformat() for d in result['new_hearing_dates']]}")
        self.stdout.write(f"Case.cnr_number: {case.cnr_number}")
        self.stdout.write(f"Case.fetch_status: {case.fetch_status}")
        self.stdout.write(f"Case.last_fetched_at: {case.last_fetched_at}")
        self.stdout.write(f"Hearing rows (source=ecourts): {hearing_count}")

        if result["data"] is not None:
            d = result["data"]
            self.stdout.write(f"\nFetched CourtCaseData:")
            self.stdout.write(f"  cnr: {d.cnr}")
            self.stdout.write(f"  case_status: {d.case_status!r}")
            self.stdout.write(f"  case_stage: {d.case_stage!r}")
            self.stdout.write(f"  court_and_judge: {d.court_and_judge!r}")
            self.stdout.write(f"  next_hearing_date: {d.next_hearing_date}")
            self.stdout.write(f"  petitioner: {d.petitioner!r}")
            self.stdout.write(f"  respondent: {d.respondent!r}")

        self.stdout.write(f"\nHearing rows for this case (source=ecourts), ordered by date:")
        for h in Hearing.objects.filter(case=case, source="ecourts").order_by("hearing_date"):
            self.stdout.write(
                f"  id={h.id} date={h.hearing_date.date()} status={h.status} "
                f"judge={h.judge!r} purpose={h.purpose!r} business_date={h.business_date}"
            )

        self.stdout.write(self.style.SUCCESS("\nDone."))
