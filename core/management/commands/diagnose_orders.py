"""
Tell "the portal lists no orders for this case" from "our parser misses them".

For each selected case it does ONE real CNR search through the same provider
code the order sync uses (EcourtsProvider.fetch_order_page_html: the same
CAPTCHA-gated call list_orders() makes), parses the page with the same
parser, and prints counts -- never names, titles or page text:

    case id | court type | CNR prefix (6 chars) | raw HTML length |
    displayPdf( count | order tables | their data rows | headings above them |
    records the parser returns | verdict

Verdicts:
    MATCH         the page lists orders and the parser returned all of them
    PARSER_MISS   the raw page shows more (links or table rows) than the parser returned
    PORTAL_EMPTY  the page lists no orders at all
    ERROR         the portal call failed (the exception's class only)

READ-ONLY: it writes nothing to the database. It waits at least 5 seconds
between cases, never searches more than --limit cases (default 20), and
refuses to run across several owners' cases (pass --owner).

--save-html DIR saves the raw page of every PARSER_MISS case under DIR so it
can be inspected. The saved file is the portal's page as received and DOES
contain party names: keep it off the repo and out of logs. Nothing else in
this command prints or logs page content.

Usage:
    python manage.py diagnose_orders --case-id 38
    python manage.py diagnose_orders --case-id 38 43
    python manage.py diagnose_orders --owner someone --court-type district
    python manage.py diagnose_orders --owner someone --save-html /tmp/orders
"""

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from bs4 import BeautifulSoup
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from core.models import Case
from core.services.court_data import get_provider
from core.services.court_data.ecourts_parsing import _parse_district_orders, _parse_hc_orders

MIN_SPACING_SECONDS = 5.0
# "order_table", "orders", "interimOrders" -- but not "table-bordered", which
# every Bootstrap table on the page carries.
_ORDER_WORD_RE = re.compile(r"(?:^|[^A-Za-z])[Oo]rders?|[a-z]Orders?")
_SECTION_RE = re.compile(r"\b(interim|final)\s+orders?\b", re.I)

MATCH, PARSER_MISS, PORTAL_EMPTY, ERROR = "MATCH", "PARSER_MISS", "PORTAL_EMPTY", "ERROR"


@dataclass
class PageReport:
    html_length: int = 0
    display_pdf_calls: int = 0
    display_pdf_php_links: int = 0
    order_tables: int = 0
    order_table_rows: int = 0
    headings: list = field(default_factory=list)
    parsed: int = 0
    verdict: str = PORTAL_EMPTY

    @property
    def raw_listed(self) -> int:
        """How many orders the raw page shows, by the larger of its two signals:
        links the portal's own JS would open, and rows in the order tables."""
        return max(self.display_pdf_calls, self.display_pdf_php_links, self.order_table_rows)


def _has_order_marker(tag) -> bool:
    values = tag.get("class") or []
    values = values if isinstance(values, list) else [values]
    return any(_ORDER_WORD_RE.search(str(v)) for v in [*values, tag.get("id") or ""])


def diagnose_page(html: str, court_type: str, cnr: str) -> PageReport:
    """Counts and a verdict for one raw CNR-search page. Pure: no network, no
    database, and nothing in the report is page text beyond a section name
    ("Interim Orders") taken from a heading that matches that pattern."""
    html = html or ""
    soup = BeautifulSoup(html, "lxml")
    tables = [t for t in soup.find_all("table") if _has_order_marker(t)]

    headings = []
    for table in tables:
        heading = table.find_previous(
            lambda tag: tag.name in ("h1", "h2", "h3", "h4", "h5", "caption")
            and _SECTION_RE.search(tag.get_text(" "))
        )
        match = _SECTION_RE.search(heading.get_text(" ")) if heading is not None else None
        headings.append(f"{match.group(1).title()} Orders" if match else "(no Interim/Final heading)")

    if court_type == "district":
        parsed = len(_parse_district_orders(html, cnr))
    else:
        parsed = len(_parse_hc_orders(html, cnr))

    report = PageReport(
        html_length=len(html),
        display_pdf_calls=html.count("displayPdf("),
        display_pdf_php_links=html.count("display_pdf.php"),
        order_tables=len(tables),
        order_table_rows=sum(1 for t in tables for r in t.find_all("tr") if r.find("td")),
        headings=headings,
        parsed=parsed,
    )
    if report.raw_listed == 0 and parsed == 0:
        report.verdict = PORTAL_EMPTY
    elif report.raw_listed > parsed:
        report.verdict = PARSER_MISS
    else:
        report.verdict = MATCH
    return report


def run_diagnosis(cases, fetch, *, sleep=time.sleep, spacing=MIN_SPACING_SECONDS, save_dir=None, write=print):
    """Diagnose `cases` one at a time, `spacing` seconds apart. `fetch(case)`
    returns the raw page. Returns [(case, PageReport | None, error_class)]."""
    spacing = max(spacing, MIN_SPACING_SECONDS)
    results = []
    for index, case in enumerate(cases):
        if index:
            sleep(spacing)
        report, error = None, ""
        try:
            html = fetch(case)
            report = diagnose_page(html, case.court_type, case.cnr_number or "")
            if report.verdict == PARSER_MISS and save_dir:
                path = Path(save_dir) / f"case{case.id}.html"
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(html, encoding="utf-8")
                write(f"saved the raw page of case {case.id} to {path} (contains party names; do not commit it)")
        except Exception as exc:  # noqa: BLE001 -- class name only: messages can carry page text
            error = type(exc).__name__
        results.append((case, report, error))
    return results


def format_table(results) -> str:
    header = (
        f"{'case':>6}  {'court':<10} {'cnr':<7} {'html':>8} {'displayPdf(':>11} {'tables':>6} "
        f"{'rows':>5} {'parsed':>6}  {'verdict':<12} headings"
    )
    lines = [header, "-" * len(header)]
    for case, report, error in results:
        cnr = (case.cnr_number or "")[:6]
        if report is None:
            lines.append(f"{case.id:>6}  {case.court_type or '-':<10} {cnr:<7} {'-':>8} {'-':>11} {'-':>6} {'-':>5} {'-':>6}  {ERROR:<12} {error}")
            continue
        lines.append(
            f"{case.id:>6}  {case.court_type or '-':<10} {cnr:<7} {report.html_length:>8} {report.display_pdf_calls:>11} "
            f"{report.order_tables:>6} {report.order_table_rows:>5} {report.parsed:>6}  {report.verdict:<12} "
            f"{'; '.join(report.headings) or '-'}"
        )
    return "\n".join(lines)


class Command(BaseCommand):
    help = (
        "Read-only: one real CNR search per case, to tell PORTAL_EMPTY from PARSER_MISS "
        "for the order listing. Prints counts, never names."
    )

    def add_arguments(self, parser):
        parser.add_argument("--case-id", type=int, nargs="+", help="One or more case ids.")
        parser.add_argument("--owner", help="Only this user's cases (username).")
        parser.add_argument(
            "--court-type", choices=["district", "high_court", "all"], default="district",
            help="With --owner: which tracked cases (default district).",
        )
        parser.add_argument("--limit", type=int, default=20, help="Search at most this many cases (default 20).")
        parser.add_argument(
            "--spacing", type=float, default=MIN_SPACING_SECONDS,
            help=f"Seconds between cases (default and minimum {MIN_SPACING_SECONDS:g}).",
        )
        parser.add_argument("--save-html", metavar="DIR", help="Save the raw page of each PARSER_MISS case here.")

    def handle(self, *args, **options):
        if not options["case_id"] and not options["owner"]:
            raise CommandError("Give --case-id and/or --owner.")
        if options["limit"] < 1:
            raise CommandError("--limit must be at least 1.")

        qs = Case.objects.filter(tracking_enabled=True).filter(
            Q(tracking_config__cnr__gt="") | Q(cnr_number__gt="")
        )
        if options["owner"]:
            owner = get_user_model().objects.filter(username=options["owner"]).first()
            if owner is None:
                raise CommandError(f"No user named {options['owner']!r}.")
            qs = qs.filter(owner=owner)
        if options["case_id"]:
            qs = qs.filter(id__in=options["case_id"])
        elif options["court_type"] != "all":
            qs = qs.filter(court_type=options["court_type"])

        cases = list(qs.order_by("id")[: options["limit"]])
        if not cases:
            raise CommandError("No tracked case with a CNR matches.")
        if not options["owner"] and len({c.owner_id for c in cases}) > 1:
            raise CommandError("These cases belong to several owners; pass --owner so only one account's cases are searched.")

        provider = get_provider()

        def fetch(case):
            config = dict(case.tracking_config or {})
            if not config.get("cnr"):
                config["cnr"] = case.cnr_number
            config["court_type"] = case.court_type or config.get("court_type")
            return provider.fetch_order_page_html(config)

        self.stdout.write(
            f"Searching {len(cases)} case(s), one CNR search each, at least "
            f"{max(options['spacing'], MIN_SPACING_SECONDS):g}s apart. Nothing is written."
        )
        results = run_diagnosis(
            cases, fetch, spacing=options["spacing"], save_dir=options["save_html"], write=self.stdout.write
        )
        self.stdout.write(format_table(results))
        counts = {}
        for _case, report, error in results:
            key = report.verdict if report else ERROR
            counts[key] = counts.get(key, 0) + 1
        self.stdout.write("  ".join(f"{k}={v}" for k, v in sorted(counts.items())))
