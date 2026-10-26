"""
Re-queue the court-order check for tracked cases that have no downloaded order.

Why it exists: order sync used to record nothing when a listing failed or a
download was swallowed, and a CAPTCHA'd portal run only happens when a case
is refreshed. Cases checked back then show "0 docs" with nothing to say
whether the portal has no orders or the check never worked. This enqueues
an order_sync job (the normal worker then does the real work, with its
retries and its recorded result) for each such case.

Selects TRACKED cases of --court-type (default district) that
  * have no downloaded court order, and
  * have no order_sync job queued or running, and
  * were not cleanly checked in the last --min-age-hours (a zero-order
    answer is the likely one for a case just checked; a failed or partial
    last check is always eligible).

Dry run by default: it prints what it would enqueue and writes nothing.
--apply enqueues. Throttled three ways, because every job costs the portal
CAPTCHA-gated searches: at most --limit jobs per run, never more than
--max-in-flight order_sync jobs queued/running system-wide, and --spacing
seconds between enqueues. Idempotent: ProcessingJob.enqueue_order_sync
dedupes an already-queued case, those cases are excluded anyway, and a case
whose job then succeeds drops out of the selection.

--retry-failed also puts CourtOrder rows that gave up (download_status
"failed") back to "pending" for the selected cases, so the job tries them
again (--apply only).

Usage:
    python manage.py requeue_order_sync                      # dry run
    python manage.py requeue_order_sync --apply --limit 10
    python manage.py requeue_order_sync --apply --owner someone --retry-failed
"""

import time
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, F, OuterRef, Q, Subquery
from django.utils import timezone

from core.models import Case, CourtOrder, ProcessingJob

IN_FLIGHT = ("queued", "running")


def select_cases(*, court_type: str, min_age_hours: float, owner=None):
    """The cases to re-queue, least-recently-checked first (never-checked
    first of all)."""
    jobs = ProcessingJob.objects.filter(case=OuterRef("pk"), job_type="order_sync")
    recently_clean = jobs.filter(
        status="succeeded", finished_at__gte=timezone.now() - timedelta(hours=min_age_hours)
    )
    downloaded = CourtOrder.objects.filter(
        case=OuterRef("pk"), download_status=CourtOrder.DOWNLOAD_DOWNLOADED, document__isnull=False
    )
    last_finished = jobs.exclude(finished_at__isnull=True).order_by("-finished_at").values("finished_at")[:1]
    # The portals' order listing is CNR-keyed: skip cases with no CNR at all.
    has_cnr = Q(tracking_config__cnr__isnull=False) & ~Q(tracking_config__cnr="") | Q(cnr_number__gt="")
    qs = (
        Case.objects.filter(tracking_enabled=True, tracking_config__isnull=False)
        .filter(has_cnr)
        .annotate(
            _has_download=Exists(downloaded),
            _in_flight=Exists(jobs.filter(status__in=IN_FLIGHT)),
            _recently_clean=Exists(recently_clean),
            _last_checked=Subquery(last_finished),
        )
        .filter(_has_download=False, _in_flight=False, _recently_clean=False)
    )
    if court_type != "all":
        qs = qs.filter(court_type=court_type)
    if owner is not None:
        qs = qs.filter(owner=owner)
    return qs.order_by(F("_last_checked").asc(nulls_first=True), "id")


class Command(BaseCommand):
    help = (
        "Re-queue the court-order check (order_sync) for tracked cases with no "
        "downloaded order. Dry run unless --apply."
    )

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Actually enqueue (default: dry run).")
        parser.add_argument("--limit", type=int, default=20, help="Max jobs to enqueue this run (default 20).")
        parser.add_argument(
            "--max-in-flight", type=int, default=5,
            help="Never exceed this many queued+running order_sync jobs system-wide (default 5).",
        )
        parser.add_argument(
            "--spacing", type=float, default=2.0,
            help="Seconds to wait between enqueues when applying (default 2).",
        )
        parser.add_argument(
            "--min-age-hours", type=float, default=24.0,
            help="Skip cases cleanly checked within this many hours (default 24).",
        )
        parser.add_argument(
            "--court-type", choices=["district", "high_court", "all"], default="district",
            help="Which tracked cases to consider (default district).",
        )
        parser.add_argument("--owner", help="Only this user's cases (username).")
        parser.add_argument(
            "--retry-failed", action="store_true",
            help='Also reset orders that gave up (download_status "failed") to "pending".',
        )

    def handle(self, *args, **options):
        apply = options["apply"]
        if options["limit"] < 1 or options["max_in_flight"] < 1:
            raise CommandError("--limit and --max-in-flight must be at least 1.")

        owner = None
        if options["owner"]:
            owner = get_user_model().objects.filter(username=options["owner"]).first()
            if owner is None:
                raise CommandError(f"No user named {options['owner']!r}.")

        candidates = list(
            select_cases(
                court_type=options["court_type"], min_age_hours=options["min_age_hours"], owner=owner
            )
        )
        in_flight = ProcessingJob.objects.filter(job_type="order_sync", status__in=IN_FLIGHT).count()
        slots = max(options["max_in_flight"] - in_flight, 0)
        budget = min(options["limit"], slots)
        chosen = candidates[:budget]

        self.stdout.write(
            f"{len(candidates)} case(s) eligible; {in_flight} order_sync job(s) already in flight; "
            f"enqueueing up to {budget} (limit {options['limit']}, max in flight {options['max_in_flight']})."
        )
        if not apply:
            self.stdout.write(self.style.WARNING("DRY RUN -- nothing will be written. Pass --apply to enqueue."))

        enqueued = 0
        reset = 0
        for i, case in enumerate(chosen):
            failed_rows = CourtOrder.objects.filter(case=case, download_status=CourtOrder.DOWNLOAD_FAILED)
            label = f"case {case.id} ({case.case_number}, {case.court_type})"
            note = f", {failed_rows.count()} failed order(s) to retry" if options["retry_failed"] else ""
            if not apply:
                self.stdout.write(f"  would enqueue {label}{note}")
                continue
            if options["retry_failed"]:
                reset += failed_rows.update(
                    download_status=CourtOrder.DOWNLOAD_PENDING, download_attempts=0, last_download_error=""
                )
            _job, created = ProcessingJob.enqueue_order_sync(case)
            enqueued += int(created)
            self.stdout.write(f"  {'enqueued' if created else 'already queued'} {label}{note}")
            if options["spacing"] and i < len(chosen) - 1:
                time.sleep(options["spacing"])

        if len(candidates) > budget:
            self.stdout.write(f"{len(candidates) - budget} more eligible case(s) left for a later run.")
        if apply:
            self.stdout.write(
                self.style.SUCCESS(f"Enqueued {enqueued} job(s); reset {reset} failed order(s) to pending.")
            )
