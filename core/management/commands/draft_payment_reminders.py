"""Prepare payment-reminder DRAFTS for invoices left unpaid too long.

Nothing is sent: each reminder lands in the advocate's drafts inbox to be
reviewed and sent by hand, through the same delivery / opt-out / audit path
as client updates. Rules, per invoice (one AppearanceFee):

  - only while INVOICED -- never once PAID (marking a fee paid also
    discards any reminder draft still waiting);
  - first reminder after the advocate's AdvocateProfile.reminder_after_days
    (default 15) since invoicing, then the same gap after each sent one;
  - at most 3 reminders; never a second draft while one is waiting;
  - never to a billing contact with no email or who has opted out;
  - discarding a reminder draft stops further reminders for that invoice.

Idempotent: safe to run as often as you like (the reminder number is part
of each draft's dedup key). Meant to run once a day from cron / a systemd
timer -- TIME_ZONE is UTC, so 04:00 UTC is 09:30 IST.

Usage:
    python manage.py draft_payment_reminders --dry-run
    python manage.py draft_payment_reminders
"""

from collections import Counter

from django.core.management.base import BaseCommand

from core.models import AdvocateProfile, AppearanceFee
from core.services.client_updates import draft_payment_reminder, next_reminder_due
from core.services.client_updates.service import reminder_recipients


class Command(BaseCommand):
    help = "Create payment-reminder drafts for overdue invoices (never sends)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Report what would be drafted.")

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        intervals = dict(AdvocateProfile.objects.values_list("owner_id", "reminder_after_days"))
        default_days = AdvocateProfile._meta.get_field("reminder_after_days").default

        fees = (
            AppearanceFee.objects.filter(status=AppearanceFee.STATUS_INVOICED)
            .select_related("hearing__case")
            .order_by("owner_id", "invoiced_at", "id")
        )
        outcomes: Counter = Counter()
        for fee in fees.iterator():
            days = intervals.get(fee.owner_id, default_days)
            number, reason = next_reminder_due(fee, after_days=days)
            if number is None:
                outcomes[reason] += 1
                continue
            if not reminder_recipients(fee.hearing.case):
                outcomes["no billing contact email (or opted out)"] += 1
                continue
            if dry_run:
                outcomes["would draft"] += 1
                self.stdout.write(
                    f"  would draft reminder {number} for {fee.invoice_number} "
                    f"(owner {fee.owner_id}, case {fee.hearing.case.case_number})"
                )
                continue
            message, outcome = draft_payment_reminder(fee, number)
            outcomes["drafted" if outcome == "created" else outcome] += 1

        summary = ", ".join(f"{count} {label}" for label, count in sorted(outcomes.items())) or "no invoiced fees"
        prefix = "[dry run] " if dry_run else ""
        self.stdout.write(self.style.SUCCESS(f"{prefix}Payment reminders: {summary}."))
