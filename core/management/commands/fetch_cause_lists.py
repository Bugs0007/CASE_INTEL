"""Fetch court cause lists and stamp item numbers onto tracked hearings.

SCHEDULING -- this is driven by systemd, not a hand-added crontab.

`deploy/systemd/case-intel-causelist@.service` + `.timer` are instance
units templated on a court KEY (see
`core/services/cause_list/registry.py`). The timer fires twice a day
(19:00 and 06:30, matching the old cron pair) and runs:

    manage.py fetch_cause_lists --court %i

Install per court (Telangana HC is the only one today):

    sudo cp deploy/systemd/case-intel-causelist@.* /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now case-intel-causelist@telangana_hc.timer

Adding a court later is a registry entry + `settings.CAUSE_LIST_COURTS`
key + one more `systemctl enable --now case-intel-causelist@<key>.timer`
-- the unit files never change.

Both daily runs check today and tomorrow and are fully idempotent: a
missed evening run is repaired by the next morning's, and a list
published late is picked up on the next pass, with no per-run state.

Run with no --court to sweep every court in settings.CAUSE_LIST_COURTS
(what a bare `manage.py fetch_cause_lists` does). Use `--check` for a
no-network preflight that every configured court's wiring resolves --
this is what a deploy smoke test / the test suite exercises.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.services.cause_list.exceptions import CauseListNotConfiguredError
from core.services.cause_list.registry import (
    configured_cause_list_courts,
    get_cause_list_court,
)
from core.services.cause_list.service import check_cause_list_for_date

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Fetch configured courts' cause lists for today and tomorrow and "
        "record each tracked hearing's item number / court hall."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--court",
            help=(
                "Only fetch this court (registry key, e.g. 'telangana_hc'). "
                "Default: every key in settings.CAUSE_LIST_COURTS. This is the "
                "value the systemd instance unit passes as %i."
            ),
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help=(
                "Preflight only: verify each selected court's wiring resolves "
                "(registry entry, court identity, hearing filter) and exit. "
                "No network, no CAPTCHA, no hearing rows touched. Non-zero "
                "exit if any court fails -- use it as a deploy smoke test."
            ),
        )
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
                "re-running against core/tests/fixtures/causelists/. "
                "Telangana HC layout only -- combine with --court telangana_hc."
            ),
        )

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        courts = self._select_courts(options.get("court"))

        if options["check"]:
            self._run_check(courts)
            return

        cause_list_day = None
        if options["pdf_dir"]:
            if not options["date"]:
                raise CommandError("--pdf-dir requires --date.")
            if len(courts) != 1:
                raise CommandError(
                    "--pdf-dir needs exactly one --court (the layout is "
                    "court-specific)."
                )
            cause_list_day = self._load_local(options["pdf_dir"])

        dates = self._resolve_dates(options)

        had_error = False
        for court in courts:
            for target in dates:
                try:
                    result = check_cause_list_for_date(
                        target,
                        court_key=court.key,
                        cause_list_day=cause_list_day,
                    )
                except CauseListNotConfiguredError as exc:
                    # Configuration, not a court problem -- fail loudly so the
                    # operator sees it rather than logging every hearing as
                    # "not yet listed" forever.
                    raise CommandError(f"{court.key}: {exc}")
                except Exception as exc:  # noqa: BLE001 -- one bad (court, date) must not kill the rest
                    logger.exception(
                        "Cause-list check failed for %s on %s", court.key, target
                    )
                    self.stderr.write(self.style.ERROR(f"{court.key} {target}: {exc}"))
                    had_error = True
                    continue

                self.stdout.write(self._describe(court, target, result))

        if had_error:
            raise CommandError("One or more cause-list fetches failed (see errors above).")

    # ------------------------------------------------------------------

    def _select_courts(self, court_key: str | None):
        if court_key:
            try:
                return [get_cause_list_court(court_key)]
            except CauseListNotConfiguredError as exc:
                raise CommandError(str(exc))
        try:
            return configured_cause_list_courts()
        except CauseListNotConfiguredError as exc:
            raise CommandError(
                f"settings.CAUSE_LIST_COURTS names an unregistered court: {exc}"
            )

    def _resolve_dates(self, options):
        if options["date"]:
            from datetime import date as date_cls

            try:
                return [date_cls.fromisoformat(options["date"])]
            except ValueError:
                raise CommandError("--date must be YYYY-MM-DD.")
        today = timezone.localdate()
        return [today + timedelta(days=offset) for offset in range(options["days_ahead"] + 1)]

    def _run_check(self, courts) -> None:
        """No-network preflight for each selected court."""
        from core.models import Hearing

        failures: list[str] = []
        for court in courts:
            try:
                court.preflight()
                # Force the hearing filter to compile against the schema --
                # a bad ORM kwarg in the registry entry surfaces here, not
                # at 7pm on the box.
                Hearing.objects.filter(**court.hearing_filter).exists()
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{court.key}: {exc}")
                self.stderr.write(self.style.ERROR(f"FAIL  {court.key}: {exc}"))
                continue
            self.stdout.write(
                self.style.SUCCESS(
                    f"OK    {court.key}  ({court.label}) -- "
                    f"`manage.py fetch_cause_lists --court {court.key}` resolves."
                )
            )

        if failures:
            raise CommandError(
                f"{len(failures)} of {len(courts)} configured court(s) failed preflight."
            )
        self.stdout.write(
            self.style.SUCCESS(f"All {len(courts)} configured court(s) OK.")
        )

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

    def _describe(self, court, target, result: dict) -> str:
        prefix = f"{court.key} {target}"
        status = result.get("status")
        if status == "no_hearings":
            return f"{prefix}: no tracked hearings for this court."
        if status == "not_published":
            return self.style.WARNING(
                f"{prefix}: cause list not published yet -- "
                f"{result.get('marked', 0)} hearing(s) marked 'not yet listed'."
            )
        if status == "parse_error":
            return self.style.ERROR(
                f"{prefix}: cause list could not be parsed (portal layout may have "
                f"changed) -- {result.get('hearings', 0)} hearing(s) left untouched."
            )
        if status == "date_mismatch":
            return self.style.ERROR(
                f"{prefix}: portal served a list for {result.get('document_date')} "
                f"-- not applied."
            )
        halls = result.get("court_halls") or []
        return self.style.SUCCESS(
            f"{prefix}: {result.get('documents', 0)} document(s), "
            f"court hall(s) {', '.join(halls) or '?'} -- "
            f"{result.get('listed', 0)} listed, {result.get('not_listed', 0)} not listed, "
            f"{result.get('unmatchable', 0)} unmatchable "
            f"({result.get('unmatched_items', 0)} of {result.get('total_items', 0)} "
            f"listed matters untracked)."
        )
