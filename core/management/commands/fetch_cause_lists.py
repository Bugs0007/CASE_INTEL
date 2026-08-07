"""Fetch the Telangana High Court cause list and stamp item numbers onto
tracked hearings.

SCHEDULING -- read this before deploying.

There is no existing recurring hearing-fetch job in this project to copy:
refresh_case_tracking() is user-triggered only (rate-limited to one fetch
per case per hour), Celery is dead infrastructure (see the Celery section
in settings.py), and deploy/ carries no cron entry or systemd timer. So
this command follows the convention that DOES exist here -- a management
command run by the host, exactly like `process_jobs` -- and is meant to be
driven by two systemd timers (or cron lines):

    evening before:   0 19 * * *   manage.py fetch_cause_lists
    morning of:      30 06 * * *   manage.py fetch_cause_lists

Both runs do the same thing, and BOTH check today and tomorrow by
default. That redundancy is deliberate: each invocation is idempotent, so
a missed evening run is fully repaired by the next morning's, and a list
published late in the evening is picked up the next morning without any
per-run state to keep straight.

The timer/cron units themselves are NOT added here -- deployment configs
are out of scope for automated changes in this repo (see CLAUDE.md); the
two lines above are what an operator needs to add.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.services.cause_list.exceptions import CauseListNotConfiguredError
from core.services.cause_list.service import check_cause_list_for_date

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Fetch the Telangana High Court cause list for today and tomorrow and "
        "record each tracked hearing's item number / court hall."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            help=(
                "Check one specific date (YYYY-MM-DD) instead of today+tomorrow. "
                "Useful for backfilling or re-running a missed day."
            ),
        )
        parser.add_argument(
            "--days-ahead",
            type=int,
            default=1,
            help=(
                "How many days past today to check (default 1, i.e. today and "
                "tomorrow -- covers both the evening-before and morning-of runs)."
            ),
        )
        parser.add_argument(
            "--pdf-dir",
            help=(
                "Parse saved cause-list PDFs from this directory instead of "
                "downloading (every *.pdf in it). Requires --date, since saved "
                "files can't say which day they were fetched for. Useful for "
                "re-running against core/tests/fixtures/causelists/."
            ),
        )

    def handle(self, *args, **options):
        cause_list_day = None
        if options["pdf_dir"]:
            if not options["date"]:
                raise CommandError("--pdf-dir requires --date.")
            cause_list_day = self._load_local(options["pdf_dir"])

        if options["date"]:
            from datetime import date as date_cls

            try:
                dates = [date_cls.fromisoformat(options["date"])]
            except ValueError:
                raise CommandError("--date must be YYYY-MM-DD.")
        else:
            today = timezone.localdate()
            dates = [today + timedelta(days=offset) for offset in range(options["days_ahead"] + 1)]

        for target in dates:
            try:
                result = check_cause_list_for_date(target, cause_list_day=cause_list_day)
            except CauseListNotConfiguredError as exc:
                # Configuration, not a court problem -- fail the whole run
                # loudly so the operator sees it, rather than logging every
                # hearing as "not yet listed" forever.
                raise CommandError(str(exc))
            except Exception as exc:  # noqa: BLE001 -- one bad date must not kill the rest
                logger.exception("Cause-list check failed for %s", target)
                self.stderr.write(self.style.ERROR(f"{target}: {exc}"))
                continue

            self.stdout.write(self._describe(target, result))

    def _load_local(self, pdf_dir: str):
        """Build a CauseListDay from saved PDFs (no network, no CAPTCHA)."""
        import pathlib

        from core.services.cause_list.telangana_hc import (
            CauseListDay,
            parse_cause_list_pdf,
        )

        directory = pathlib.Path(pdf_dir)
        if not directory.is_dir():
            raise CommandError(f"--pdf-dir {pdf_dir!r} is not a directory.")

        paths = sorted(directory.glob("*.pdf"))
        if not paths:
            raise CommandError(f"No *.pdf files in {pdf_dir!r}.")

        documents = []
        for path in paths:
            try:
                documents.append(parse_cause_list_pdf(path.read_bytes()))
            except Exception as exc:  # noqa: BLE001
                self.stderr.write(self.style.WARNING(f"{path.name}: {exc}"))
        if not documents:
            raise CommandError(f"None of the PDFs in {pdf_dir!r} could be parsed.")

        list_date = next((d.list_date for d in documents if d.list_date), None)
        self.stdout.write(f"Loaded {len(documents)} local document(s) from {pdf_dir}.")
        return CauseListDay(list_date=list_date, documents=documents)

    def _describe(self, target, result: dict) -> str:
        status = result.get("status")
        if status == "no_hearings":
            return f"{target}: no tracked High Court hearings."
        if status == "not_published":
            return self.style.WARNING(
                f"{target}: cause list not published yet -- "
                f"{result.get('marked', 0)} hearing(s) marked 'not yet listed'."
            )
        if status == "parse_error":
            return self.style.ERROR(
                f"{target}: cause list could not be parsed (portal layout may have "
                f"changed) -- {result.get('hearings', 0)} hearing(s) left untouched."
            )
        if status == "date_mismatch":
            return self.style.ERROR(
                f"{target}: portal served a list for {result.get('document_date')} "
                f"-- not applied."
            )
        halls = result.get("court_halls") or []
        return self.style.SUCCESS(
            f"{target}: {result.get('documents', 0)} document(s), "
            f"court hall(s) {', '.join(halls) or '?'} -- "
            f"{result.get('listed', 0)} listed, {result.get('not_listed', 0)} not listed, "
            f"{result.get('unmatchable', 0)} unmatchable "
            f"({result.get('unmatched_items', 0)} of {result.get('total_items', 0)} "
            f"listed matters untracked)."
        )
