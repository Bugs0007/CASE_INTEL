"""Fetch, parse and match ONE cause-list target and print what happened --
writing nothing to the database.

    manage.py causelist_doctor --adapter hcservices_generic --target andhra/1 --date 2026-10-12
    manage.py causelist_doctor --adapter district_ecourts   --target 29/2/1290019/2^1 --date 2026-10-09
    manage.py causelist_doctor --adapter telangana_hc       --target telangana_hc/1 --date 2026-10-12 --number "WP/29408/2026"

It runs the real adapter (so it does hit the portal, CAPTCHA and all) and
the real service logic with `write=False`. Matching is shown for:
  * every scheduled hearing in the database that resolves to this target
    (read-only), and
  * anything you ask for with --cnr / --number (nothing is stored).

Target keys: telangana_hc/<bench>  |  <hc>/<bench,bench>  |  <state>/<dist>/<complex>/<est>^<court>
"""

from __future__ import annotations

from datetime import date as date_cls

from django.core.management.base import BaseCommand, CommandError

from core.models import Case, Hearing
from core.services.causelists import clock, registry, service
from core.services.causelists.exceptions import CauseListError
from core.services.causelists.normalize import canonical_case_key


class Command(BaseCommand):
    help = "Fetch + parse + match one cause-list target without writing to the database."

    def add_arguments(self, parser):
        parser.add_argument("--adapter", required=True, help="telangana_hc | hcservices_generic | district_ecourts | supreme_court")
        parser.add_argument("--target", required=True, help="Target key (see the module docstring).")
        parser.add_argument("--date", required=True, help="List date, YYYY-MM-DD (IST).")
        parser.add_argument("--cnr", action="append", default=[], help="Also look for this CNR (repeatable).")
        parser.add_argument("--number", action="append", default=[], help="Also look for this case number (repeatable).")
        parser.add_argument("--show", type=int, default=8, help="Entries to print per document (default 8).")

    def handle(self, *args, **options):
        try:
            adapter = registry.get_adapter(options["adapter"])
            list_date = date_cls.fromisoformat(options["date"])
        except (CauseListError, ValueError) as exc:
            raise CommandError(str(exc))
        if not hasattr(adapter, "target_from_key"):
            raise CommandError(f"{adapter.key} cannot build a target from a key.")
        try:
            target = adapter.target_from_key(options["target"])
        except CauseListError as exc:
            raise CommandError(str(exc))

        hearings = self._hearings_for(adapter, target, list_date)
        for cnr in options["cnr"]:
            hearings.append(self._adhoc(cnr=cnr))
        for number in options["number"]:
            if canonical_case_key(number) is None:
                raise CommandError(f"{number!r} is not a case number.")
            hearings.append(self._adhoc(number=number))
        target = adapter.finalize_target(target, hearings) if hearings else target

        self.stdout.write(f"Adapter {adapter.key}, target {target.key} ({target.label}), list date {list_date}")
        self.stdout.write(f"Looking for {len(hearings)} hearing(s): {len([h for h in hearings if h.pk])} from the database (read-only), {len([h for h in hearings if not h.pk])} ad hoc.")
        collected: list = []
        report = service.process_group(adapter, target, list_date, hearings, write=False, collect=collected)

        self.stdout.write(
            f"\nIndex: {report.index_status}; documents {report.docs_ok} ok / {report.docs_total} listed "
            f"({report.docs_unavailable} not uploaded, {report.docs_failed} failed); entries {report.entries}; "
            f"read completely: {'yes' if report.complete else 'NO -- no hearing can be reported as not listed'}"
        )
        for doc, entries in collected:
            self.stdout.write(f"\n- {doc.list_type or '?'} | {doc.bench_label or '?'} | {len(entries)} entries")
            for e in entries[: options["show"]]:
                self.stdout.write(f"    item {e.item_number:>8}  {e.case_token or '-':28s} {e.cnr or '':16s} hall {e.court_hall or '-'}")
        self.stdout.write("\nWould write:")
        for hearing_id, status, note in report.outcomes:
            label = f"hearing {hearing_id}" if hearing_id else "ad hoc"
            self.stdout.write(f"  {label}: {status}{(' -- ' + note) if note else ''}")
        if not report.outcomes:
            self.stdout.write("  (nothing: no hearings to decide)")

    def _hearings_for(self, adapter, target, list_date: date_cls) -> list[Hearing]:
        matched = []
        for hearing in service.select_hearings([list_date]):
            if clock.ist_date_of(hearing.hearing_date) != list_date:
                continue
            res = registry.resolve_case(hearing.case)
            if res.is_target and res.target.adapter == adapter.key and res.target.key == target.key:
                matched.append(hearing)
        return matched

    def _adhoc(self, *, cnr: str = "", number: str = "") -> Hearing:
        case = Case(case_number=number or cnr, title=number or cnr, cnr_number=cnr or None)
        return Hearing(case=case, case_id=None, hearing_date=None, status="scheduled")
