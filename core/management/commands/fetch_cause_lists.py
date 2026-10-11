"""Fetch court cause lists and stamp item number / court / bench / list type
onto tracked hearings.

SCHEDULING -- driven by systemd, not cron. `deploy/systemd/case-intel-causelist@.service`
and `.timer` are instance units templated on a key. One instance covers
everything:

    sudo systemctl enable --now case-intel-causelist@all.timer
    # (disable the old @telangana_hc.timer so two runs don't compete)

The timer runs `manage.py fetch_cause_lists --court %i` twice a day (evening
and morning). The unit's OnCalendar should name Asia/Kolkata explicitly; the
code computes every date in IST regardless, so the box clock only decides
WHEN the run starts.

What a run does (core/services/causelists/service.py):
  * takes the scheduled hearings of the next few IST days,
  * decides, per hearing, which court's list could contain it (or that none
    can -> "Not covered"),
  * fetches ONLY those lists (a court nobody tracks is never contacted),
    sharing one fetch between everyone with a hearing in the same court,
  * and writes `listed` / `not listed` / `not published` / `couldn't check`.
"Not listed" is only ever written after the court's whole published list
for that date was read.

    --court all|<adapter>   which adapters (default: settings.CAUSE_LIST_ADAPTERS)
    --check                 no-network preflight of the wiring
    --dry-run               show what WOULD be fetched, touch nothing
    --date YYYY-MM-DD       one specific IST day instead of today..today+N
    --days-ahead N          default 2 (the evening run must reach the next sitting day)
    --max-minutes N         wall-clock budget for the whole run
"""

from __future__ import annotations

import logging
from datetime import date as date_cls
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError

from core.services.causelists import clock, registry, service
from core.services.causelists.exceptions import CauseListNotConfiguredError

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = (
        "Fetch cause lists for tracked hearings (today and the next days, IST) and "
        "record each hearing's item number, court, bench and list type."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--court",
            help=(
                "'all' or one adapter key (telangana_hc, hcservices_generic, "
                "district_ecourts, supreme_court). Default: settings.CAUSE_LIST_ADAPTERS. "
                "This is the value the systemd instance unit passes as %%i."
            ),
        )
        parser.add_argument("--check", action="store_true", help="No-network preflight; non-zero exit on failure.")
        parser.add_argument("--dry-run", action="store_true", help="Show the fetch plan; no network, no writes.")
        parser.add_argument("--date", help="Check one specific IST day (YYYY-MM-DD).")
        parser.add_argument("--days-ahead", type=int, default=2, help="Days past today to include (default 2).")
        parser.add_argument("--max-minutes", type=float, default=None, help="Wall-clock budget for the run.")

    # ------------------------------------------------------------------

    def handle(self, *args, **options):
        keys = self._select_adapters(options.get("court"))

        if options["check"]:
            self._run_check(keys)
            return

        dates = self._resolve_dates(options)

        if options["dry_run"]:
            self._dry_run(dates, keys)
            return

        report = service.run(dates, adapter_keys=keys, max_minutes=options["max_minutes"])
        self._print_report(report)
        if report.not_run_reason:
            # Not a failure: another run (or the same timer's earlier firing)
            # holds the lock and will do the work.
            self.stdout.write(self.style.WARNING(f"Nothing run: {report.not_run_reason}."))

    # ------------------------------------------------------------------

    def _select_adapters(self, court: str | None) -> list[str]:
        try:
            if court and court != "all":
                registry.get_adapter(court)  # validates
                return [court]
            keys = registry.configured_adapter_keys() if court != "all" else registry.configured_adapter_keys()
            for key in keys:
                registry.get_adapter(key)
            return keys
        except CauseListNotConfiguredError as exc:
            raise CommandError(str(exc))

    def _resolve_dates(self, options) -> list[date_cls]:
        if options["date"]:
            try:
                return [date_cls.fromisoformat(options["date"])]
            except ValueError:
                raise CommandError("--date must be YYYY-MM-DD.")
        today = clock.today()
        return [today + timedelta(days=n) for n in range(options["days_ahead"] + 1)]

    def _run_check(self, keys: list[str]) -> None:
        """Wiring preflight, no network."""
        from core.models import Hearing
        from core.services.causelists import hc_config

        failures: list[str] = []
        for key in keys:
            try:
                adapter = registry.get_adapter(key)
                if key == registry.TELANGANA:
                    from core.services.causelists.adapters.telangana_hc import _court

                    _court()
                if key == registry.HCSERVICES:
                    from core.services.causelists.adapters.layouts import parser_for

                    for cfg in hc_config.HC_CONFIGS.values():
                        if cfg.status == hc_config.SUPPORTED and parser_for(cfg.parser) is None:
                            raise CauseListNotConfiguredError(
                                f"{cfg.code} is marked supported but has no parser {cfg.parser!r}"
                            )
                Hearing.objects.filter(status="scheduled").exists()
            except Exception as exc:  # noqa: BLE001
                failures.append(f"{key}: {exc}")
                self.stderr.write(self.style.ERROR(f"FAIL  {key}: {exc}"))
                continue
            self.stdout.write(
                self.style.SUCCESS(f"OK    {key}  ({adapter.display_name}) -- `manage.py fetch_cause_lists --court {key}` resolves.")
            )
        if failures:
            raise CommandError(f"{len(failures)} of {len(keys)} configured adapter(s) failed preflight.")
        self.stdout.write(self.style.SUCCESS(f"All {len(keys)} configured adapter(s) OK."))

    def _dry_run(self, dates, keys) -> None:
        hearings = service.select_hearings(dates)
        groups, unsupported, pending = service.plan(hearings, set(keys))
        self.stdout.write(
            f"{len(hearings)} scheduled hearing(s) on {dates[0]}..{dates[-1]} (IST): "
            f"{sum(len(r) for _, r in groups.values())} to fetch in {len(groups)} group(s), "
            f"{sum(len(r) for r in unsupported.values())} not covered, {len(pending)} awaiting a court location."
        )
        for (adapter_key, target_key, day), (target, rows) in sorted(groups.items(), key=lambda kv: kv[0][::-1]):
            self.stdout.write(f"  fetch  {day}  {adapter_key:18s} {target_key}  ({len(rows)} hearing(s))")
        for reason, rows in unsupported.items():
            self.stdout.write(f"  skip   {len(rows):3d} not covered: {reason}")

    def _print_report(self, report) -> None:
        for g in report.groups:
            self.stdout.write(
                f"{g.list_date} {g.adapter}/{g.target_key}: index={g.index_status} "
                f"docs {g.docs_ok}/{g.docs_total} ok ({g.docs_unavailable} not uploaded, {g.docs_failed} failed) "
                f"entries={g.entries} -> {g.listed} listed, {g.not_listed} not listed, "
                f"{g.not_published} not published, {g.fetch_failed} couldn't check, {g.untouched} unchanged"
                + ("" if g.complete else "  [read incompletely: no 'not listed' possible]")
            )
        self.stdout.write(
            f"{len(report.groups)} group(s) fetched in {report.elapsed:.0f}s; "
            f"{report.unsupported_marked} hearing(s) marked not covered; {report.pending} awaiting a court location."
        )
        for line in report.skipped:
            self.stdout.write(self.style.WARNING(f"skipped: {line}"))
