"""One real High Court advocate search, to read what the portal actually returns.

    python manage.py probe_hc_advocate_search --court telangana --bar-code TS/1234/2009
    python manage.py probe_hc_advocate_search --court bombay --bench 4 --name "Rambabu" --status Pending

The redesigned High Courts tab posts a form that bharat-courts has no builder for
(core/services/court_data/ecourts_parsing.py: hc_advocate_search_form). Its field
names come from the portal's own page; what the portal ANSWERS (whether the bar
code format is accepted, which fields a row has, whether an advocate is named on
it) has never been confirmed against a live search. This command does that once.

Read-only and bounded: ONE search (the library submits at most
ADVOCATE_SEARCH_MAX_ATTEMPTS times, each on a fresh CAPTCHA), the total of HTTP
requests is capped (--max-requests) and each is preceded by a pause. Nothing is
written to the database. It prints the shape of the answer, and the first rows (it
is your own search, on your own computer); nothing is logged elsewhere.
"""

from __future__ import annotations

import asyncio
import re

from django.core.management.base import BaseCommand, CommandError

BAR_CODE_RE = re.compile(r"^[A-Za-z]{2,3}/\d+/\d{4}$")


class Command(BaseCommand):
    help = "Make ONE High Court advocate search and print the shape of the portal's answer. Writes nothing."

    def add_arguments(self, parser):
        parser.add_argument("--court", required=True, help="High Court code from the registry, e.g. telangana, bombay")
        parser.add_argument("--bench", default="1", help="Portal bench code (default 1, the principal bench)")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--bar-code", help="STATE/NUMBER/YEAR, e.g. TS/1234/2009")
        group.add_argument("--name", help="Advocate name, at least 3 letters")
        parser.add_argument("--status", default="Both", choices=["Pending", "Disposed", "Both"])
        parser.add_argument("--max-requests", type=int, default=12, help="Hard cap on HTTP requests (default 12)")
        parser.add_argument("--pause", type=float, default=3.0, help="Seconds before each request (default 3)")
        parser.add_argument("--rows", type=int, default=3, help="How many rows to print (default 3)")

    def handle(self, *args, **options):
        import httpx
        from bharat_courts import HCServicesClient, get_court
        from bharat_courts.hcservices import endpoints as hc_endpoints
        from bharat_courts.hcservices.parser import _parse_json_envelope

        from core.services.court_data.ecourts_parsing import hc_advocate_search_form

        court = get_court(options["court"])
        if court is None or court.court_type.value != "high_court":
            raise CommandError(f"{options['court']!r} is not a High Court code in the registry.")
        bar_code = (options["bar_code"] or "").upper()
        name = options["name"] or ""
        if bar_code and not BAR_CODE_RE.match(bar_code):
            raise CommandError("Give the bar code as STATE/NUMBER/YEAR, e.g. TS/1234/2009.")
        if name and len(name.strip()) < 3:
            raise CommandError("A name needs at least 3 letters.")

        cap, pause = options["max_requests"], options["pause"]
        requests_made = {"n": 0}
        real_send = httpx.AsyncClient.send

        async def counted_send(client, request, **kwargs):
            requests_made["n"] += 1
            if requests_made["n"] > cap:
                raise CommandError(f"Stopped: more than {cap} HTTP requests.")
            await asyncio.sleep(pause)
            return await real_send(client, request, **kwargs)

        submissions = {"n": 0}

        def build_form(captcha: str) -> dict[str, str]:
            submissions["n"] += 1
            return hc_advocate_search_form(
                state_code=court.state_code, bench_code=str(options["bench"]), advocate_name=name.strip(),
                bar_code=bar_code, status_filter=options["status"], captcha=captcha,
            )

        async def run():
            async with HCServicesClient() as client:
                response = await client._post_with_captcha_retry(
                    hc_endpoints.SHOW_RECORDS_URL, build_form, max_retries=6
                )
                return response.text

        httpx.AsyncClient.send = counted_send
        try:
            raw = asyncio.run(run())
        finally:
            httpx.AsyncClient.send = real_send

        records, total = _parse_json_envelope(raw)
        self.stdout.write(f"HTTP requests: {requests_made['n']}  |  form submissions: {submissions['n']}")
        self.stdout.write(f"Court: {court.name}, bench {options['bench']}, search by {'bar code' if bar_code else 'name'}, status {options['status']}")
        self.stdout.write(f"Rows: {len(records)} (portal says totRecords={total})")
        keys = sorted({k for record in records for k in record})
        self.stdout.write(f"Fields on a row: {', '.join(keys) if keys else '(no rows)'}")
        advocate_like = [k for k in keys if "adv" in k.lower()]
        self.stdout.write(f"Fields that look like an advocate: {advocate_like or 'none'}")
        years = sorted({str(r.get("case_year", "")) for r in records if r.get("case_year")})
        self.stdout.write(f"Case years seen: {years[:12]}{' ...' if len(years) > 12 else ''}")
        for record in records[: options["rows"]]:
            self.stdout.write(
                "  - {t} {n}/{y}  CNR {c}  {p} vs {r}".format(
                    t=record.get("type_name", ""), n=record.get("case_no", ""), y=record.get("case_year", ""),
                    c=record.get("cino", ""), p=record.get("pet_name", ""), r=record.get("res_name", ""),
                )
            )
        self.stdout.write("Nothing was saved. Share the lines above (not the case details) to settle the open items.")
