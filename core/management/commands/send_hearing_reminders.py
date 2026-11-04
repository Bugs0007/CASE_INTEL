"""Email each advocate a digest of their hearings two days and one day ahead.

SCHEDULING -- driven by systemd, like fetch_cause_lists, not cron. Run it
twice a day, in India time: 09:00 (the normal send) and 19:45 (after the
19:00 cause-list fetch; catches a hearing discovered during the day and
retries a failed send). The unit's OnCalendar should name Asia/Kolkata
explicitly; the code computes the India date itself, whatever the box clock.
Reference units are in the project handover notes, not provisioned.

What a run does (core/services/notifications/hearing_reminders.py):
  * takes scheduled hearings whose India date is today+1 or today+2,
  * skips advocates who turned reminders off, and closed/archived cases,
  * sends ONE plain-text digest per advocate, at most once per hearing per
    lead (HearingReminder is the dedup record),
  * with no RESEND_API_KEY, records "logged" and sends nothing.

    --dry-run          print each digest; write nothing, send nothing
    --owner <username> only this user's hearings
    --today YYYY-MM-DD override the India date (testing)
"""

from __future__ import annotations

from datetime import date

from django.contrib.auth.models import User
from django.core.management.base import BaseCommand, CommandError

from core.services.notifications import hearing_reminders


class Command(BaseCommand):
    help = "Send hearing-reminder digest emails (two days and one day before each hearing)."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Print each digest; send and write nothing.")
        parser.add_argument("--owner", help="Limit to one user (username).")
        parser.add_argument("--today", help="Override the India date (YYYY-MM-DD).")

    def handle(self, *args, **options):
        today = None
        if options["today"]:
            try:
                today = date.fromisoformat(options["today"])
            except ValueError:
                raise CommandError("--today must be YYYY-MM-DD.")
        owner = options["owner"]
        if owner and not User.objects.filter(username=owner).exists():
            raise CommandError(f"No user {owner!r}.")

        dry_run = options["dry_run"]
        report = hearing_reminders.run(today=today, owner_username=owner, dry_run=dry_run)

        if report.not_run_reason:
            self.stdout.write(self.style.WARNING(f"Nothing run: {report.not_run_reason}."))
            return

        if dry_run:
            for digest in report.digests:
                self.stdout.write(self.style.MIGRATE_HEADING(f"To: {digest.recipient}"))
                self.stdout.write(f"Subject: {digest.subject}\n")
                self.stdout.write(digest.body)
                self.stdout.write("\n" + "=" * 60 + "\n")

        self.stdout.write(
            f"{'Dry run' if dry_run else 'Run'} for {report.today} (India): "
            f"{len(report.digests)} digest(s) "
            + (
                "composed"
                if dry_run
                else f"-> {report.sent} sent, {report.logged} logged (email not configured), "
                f"{report.failed} failed, {report.crashed} errored"
            )
            + f"; {report.opted_out} hearing(s) skipped (reminders off)."
        )
        if report.no_recipient:
            self.stdout.write(
                self.style.WARNING(
                    "No email address for: " + ", ".join(report.no_recipient)
                    + " -- set a contact email in Settings."
                )
            )
        if report.logged:
            self.stdout.write(
                self.style.WARNING("RESEND_API_KEY is not set: reminders were logged only, nothing was emailed.")
            )
