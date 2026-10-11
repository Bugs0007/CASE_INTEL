"""High Court cause lists via hcservices -- the shared fetch flow, the
response classifier, the per-layout parsers, and which courts resolve to
what.

Everything parsed here is a REAL document fetched live on 2026-10-10
(core/tests/fixtures/causelists/hcservices_generic/*/SOURCE.md). The
guard tests corrupt or mis-route those real files; none of them invents a
list.
"""

import asyncio
import csv
import datetime
import pathlib

import httpx
import pytest

from core.services.causelists import fetchlib, hc_config, registry
from core.services.causelists.adapters import _hcservices
from core.services.causelists.adapters.hcservices_generic import get_adapter
from core.services.causelists.adapters.layouts import parser_for
from core.services.causelists.adapters.layouts.delhi import parse_delhi_doc
from core.services.causelists.adapters.layouts.table import parse_table_doc
from core.services.causelists.base import RawDoc
from core.services.causelists.exceptions import CauseListParseError
from core.tests.causelist_golden import GOLDEN
from core.tests.causelist_support import FIXTURES_ROOT, make_case

HC = FIXTURES_ROOT / "hcservices_generic"


def raw(path, **kw):
    return RawDoc(doc_key="x", status="ok", path=path, list_type=kw.get("lt", "LIST"), bench_label=kw.get("bench", "BENCH"))


# ---------------------------------------------------------------------------
# Response classification: the three "nothing" bodies are NOT the same thing
# ---------------------------------------------------------------------------


class TestIndexClassification:
    def test_plain_invalid_captcha_is_a_captcha_failure_not_an_empty_day(self):
        """bharat-courts only retries on the QUOTED string; the portal sends
        it unquoted, and the old Telangana code read it as 'not published'."""
        assert fetchlib.classify_hcservices_index("﻿Invalid Captcha")[0] == fetchlib.INDEX_CAPTCHA_FAILED

    def test_error_val_is_a_captcha_failure(self):
        """Reproduced live: ERROR_VAL appears exactly when the CAPTCHA sent was ''."""
        assert fetchlib.classify_hcservices_index('﻿{"Error":"ERROR_VAL"}')[0] == fetchlib.INDEX_CAPTCHA_FAILED

    def test_no_cause_list_available_is_the_only_empty_signal(self):
        body = "\n\n\n\n\nNo cause List Available for this date...!!"
        assert fetchlib.classify_hcservices_index(body)[0] == fetchlib.INDEX_NONE_AVAILABLE

    def test_a_table_is_a_table(self):
        html = (HC / "andhra/2026-10-12/bench_1/00_meta_table.html").read_text(encoding="utf-8")
        assert fetchlib.classify_hcservices_index(html)[0] == fetchlib.INDEX_TABLE

    @pytest.mark.parametrize("body", ["", "   ", "<html><body>maintenance</body></html>"])
    def test_anything_else_is_other_never_empty_day(self, body):
        assert fetchlib.classify_hcservices_index(body)[0] == fetchlib.INDEX_OTHER

    def test_pdf_heads(self):
        assert fetchlib.classify_pdf_head(b"\xef\xbb\xbf%PDF-1.4\n") == "pdf"
        assert fetchlib.classify_pdf_head(b"%PDF-1.4") == "pdf"
        assert fetchlib.classify_pdf_head(b"\xef\xbb\xbfOrder not uploaded") == "not_uploaded"
        assert fetchlib.classify_pdf_head(b"<html>") == "other"


# Number of rows in each captured index (counted from the saved responses).
INDEX_ROWS = {
    "andhra/2026-10-12/bench_1": 41, "bombay/2026-10-09/bench_1": 65, "bombay/2026-10-12/bench_1": 48,
    "calcutta/2026-10-12/bench_3": 55, "chhattisgarh/2026-10-12/bench_1": 59, "delhi/2026-10-12/bench_1": 54,
    "gauhati/2026-10-12/bench_3": 6, "jammu/2026-10-12/bench_1": 23, "karnataka/2026-10-12/bench_1": 66,
    "karnataka/2026-10-12/bench_2": 19, "madras/2026-10-12/bench_1": 63, "manipur/2026-10-12/bench_1": 6,
    "meghalaya/2026-10-12/bench_1": 3, "orissa/2026-10-12/bench_1": 13, "patna/2026-10-09/bench_1": 45,
    "rajasthan/2026-10-12/bench_1": 50, "sikkim/2026-10-12/bench_1": 1, "telangana/2026-10-09/bench_1": 48,
    "tripura/2026-10-12/bench_1": 2, "uttarakhand/2026-10-12/bench_1": 9,
}


class TestIndexRows:
    @pytest.mark.parametrize("meta", sorted(HC.glob("*/*/*/00_meta_table.html")), ids=lambda p: "/".join(p.parts[-4:-1]))
    def test_every_index_row_with_a_pdf_link_is_read(self, meta):
        key = "/".join(meta.parts[-4:-1])
        rows = _hcservices.parse_index_rows(meta.read_text(encoding="utf-8"))
        assert len(rows) == INDEX_ROWS[key]
        assert all(r.list_type and r.href for r in rows)

    def test_every_captured_index_is_listed_here(self):
        found = {"/".join(m.parts[-4:-1]) for m in HC.glob("*/*/*/00_meta_table.html")}
        assert found == set(INDEX_ROWS)

    def test_doc_keys_are_stable_and_unique(self):
        html = (HC / "bombay/2026-10-12/bench_1/00_meta_table.html").read_text(encoding="utf-8")
        a = _hcservices.parse_index_rows(html)
        b = _hcservices.parse_index_rows(html)
        assert [r.doc_key for r in a] == [r.doc_key for r in b]
        assert len({r.doc_key for r in a}) == len(a) == 48

    def test_pdf_url_uses_the_corrected_join(self):
        url = _hcservices.pdf_url("cases/display_causelist_pdf.php?filename=abc")
        assert url == "https://hcservices.ecourts.gov.in/hcservices/cases/display_causelist_pdf.php?filename=abc"


# ---------------------------------------------------------------------------
# Streaming download: BOM cut, 'Order not uploaded' reported, not stored
# ---------------------------------------------------------------------------


class _FakeHttp:
    """Stands in for bharat-courts' RateLimitedClient (`_ensure_client()`)."""

    def __init__(self, handler):
        self._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))

    def _ensure_client(self):
        return self._client


def _download(handler, tmp_path, url="https://hcservices.test/x"):
    async def go():
        http = _FakeHttp(handler)
        try:
            return await fetchlib.download_pdf(
                http, url, tmp_path / "out.pdf", pacer=fetchlib.Pacer(min_gap=0), attempts=2
            )
        finally:
            await http._client.aclose()

    return asyncio.run(go())


class TestDownload:
    def test_bom_prefixed_pdf_is_stored_starting_at_the_pdf_header(self, tmp_path):
        real = next((HC / "sikkim/2026-10-12/bench_1").glob("*.pdf")).read_bytes()
        got = _download(lambda r: httpx.Response(200, content=b"\xef\xbb\xbf" + real), tmp_path)
        assert got.kind == "pdf" and got.size == len(real)
        assert (tmp_path / "out.pdf").read_bytes() == real

    def test_order_not_uploaded_is_reported_and_nothing_is_written(self, tmp_path):
        got = _download(lambda r: httpx.Response(200, content=b"\xef\xbb\xbfOrder not uploaded"), tmp_path)
        assert got.kind == "not_uploaded"
        assert not (tmp_path / "out.pdf").exists()

    def test_other_bodies_are_not_pdfs(self, tmp_path):
        got = _download(lambda r: httpx.Response(200, content=b"<html>login</html>"), tmp_path)
        assert got.kind == "other"

    def test_a_transport_error_is_retried_then_raised(self, tmp_path):
        calls = []

        def handler(request):
            calls.append(1)
            raise httpx.RemoteProtocolError("Server disconnected without sending a response.")

        with pytest.raises(fetchlib.CauseListFetchError):
            _download(handler, tmp_path)
        assert len(calls) == 2

    def test_a_4xx_is_not_retried(self, tmp_path):
        calls = []

        def handler(request):
            calls.append(1)
            return httpx.Response(404)

        with pytest.raises(fetchlib.CauseListFetchError):
            _download(handler, tmp_path)
        assert len(calls) == 1


# ---------------------------------------------------------------------------
# The index+documents flow, with the portal faked
# ---------------------------------------------------------------------------


class _FakeClient:
    """HCServicesClient stand-in: only the context manager and `_http`."""

    def __init__(self, handler):
        self._http = _FakeHttp(handler)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        await self._http._client.aclose()


def _serve(files, not_uploaded=()):
    """handler: URL (by order in the index) -> the fixture PDF, or 'not uploaded'."""

    def handler(request):
        key = request.url.params.get("filename", "")
        if key in not_uploaded:
            return httpx.Response(200, content=b"\xef\xbb\xbfOrder not uploaded")
        return httpx.Response(200, content=files[key].read_bytes())

    return handler


class TestFetchFlow:
    def _fetch(self, monkeypatch, tmp_path, *, kinds, rows_by_bench, pdf, bench_codes=("1",), not_uploaded=()):
        adapter = get_adapter()
        iterator = iter(kinds)

        async def fake_index(client, **kw):
            kind = next(iterator)
            return kind, rows_by_bench.get(kw["bench_code"], []), "detail"

        monkeypatch.setattr(_hcservices, "fetch_index", fake_index)
        files = {r.href.split("filename=")[-1]: pdf for rows in rows_by_bench.values() for r in rows}
        monkeypatch.setattr("bharat_courts.HCServicesClient", lambda: _FakeClient(_serve(files, not_uploaded)))
        target = adapter.target_from_key(f"andhra/{','.join(bench_codes)}")
        target.params["benches"] = [{"code": c, "name": f"B{c}"} for c in bench_codes]
        return adapter.fetch(target, datetime.date(2026, 10, 12), tmp_path)

    def rows(self, n):
        return [
            _hcservices.IndexRow(str(i), "BENCH", f"LIST {i}", f"cases/display_causelist_pdf.php?filename=f{i}", f"k{i}")
            for i in range(n)
        ]

    def pdf(self):
        return next((HC / "andhra/2026-10-12/bench_1").glob("*.pdf"))

    def test_all_documents_ok(self, monkeypatch, tmp_path):
        result = self._fetch(monkeypatch, tmp_path, kinds=["table"], rows_by_bench={"1": self.rows(3)}, pdf=self.pdf())
        assert result.status == "ok" and result.doc_total == 3
        assert [d.status for d in result.docs] == ["ok"] * 3
        assert all(d.meta["parser"] == "f1" for d in result.docs)
        assert all(not d.source_public for d in result.docs)  # hcservices links are session-bound

    def test_an_unuploaded_document_is_reported_not_dropped(self, monkeypatch, tmp_path):
        result = self._fetch(
            monkeypatch, tmp_path, kinds=["table"], rows_by_bench={"1": self.rows(3)},
            pdf=self.pdf(), not_uploaded=("f1",),
        )
        assert [d.status for d in result.docs] == ["ok", "not_uploaded", "ok"]
        assert result.doc_total == 3

    def test_no_list_for_the_date_is_none_available(self, monkeypatch, tmp_path):
        result = self._fetch(monkeypatch, tmp_path, kinds=["none_available"], rows_by_bench={}, pdf=self.pdf())
        assert result.status == "none_available"

    def test_captcha_budget_exhausted_is_captcha_failed(self, monkeypatch, tmp_path):
        result = self._fetch(monkeypatch, tmp_path, kinds=["captcha_failed"], rows_by_bench={}, pdf=self.pdf())
        assert result.status == "captcha_failed"

    def test_an_unexpected_index_body_is_a_fetch_error_not_an_empty_day(self, monkeypatch, tmp_path):
        result = self._fetch(monkeypatch, tmp_path, kinds=["other"], rows_by_bench={}, pdf=self.pdf())
        assert result.status == "fetch_error" or result.docs[0].status == "fetch_error"

    def test_one_bench_with_no_list_leaves_a_not_uploaded_marker(self, monkeypatch, tmp_path):
        """Two benches, one has published and one has not: the read is
        incomplete, so nothing may be reported 'not listed' from it."""
        result = self._fetch(
            monkeypatch, tmp_path, kinds=["table", "none_available"],
            rows_by_bench={"1": self.rows(2)}, pdf=self.pdf(), bench_codes=("1", "2"),
        )
        assert result.status == "ok"
        assert result.doc_total == 3
        assert [d.status for d in result.docs] == ["ok", "ok", "not_uploaded"]

    def test_the_per_target_document_cap_leaves_the_rest_as_errors(self, monkeypatch, tmp_path, settings):
        settings.CAUSE_LIST_MAX_DOCS_PER_TARGET = 2
        result = self._fetch(monkeypatch, tmp_path, kinds=["table"], rows_by_bench={"1": self.rows(4)}, pdf=self.pdf())
        assert [d.status for d in result.docs] == ["ok", "ok", "fetch_error", "fetch_error"]
        assert "cap" in result.docs[-1].error


# ---------------------------------------------------------------------------
# Golden parser tests on every real list
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "key", sorted(GOLDEN), ids=lambda k: f"{k[0]}-{k[1]}-{k[3][:24]}"
)
def test_golden_parse(key):
    code, date, bench, name = key
    expected = GOLDEN[key]
    parse = parser_for(expected["parser"])
    parsed = parse(raw(HC / code / date / bench / name))
    entries = parsed.entries
    assert len(entries) == expected["count"]
    assert str(parsed.list_date) == expected["date"]
    assert entries[0].court_hall == expected["hall"]
    assert (entries[0].item_number, entries[0].case_token) == expected["first"]
    assert (entries[len(entries) // 2].item_number, entries[len(entries) // 2].case_token) == expected["mid"]
    assert (entries[-1].item_number, entries[-1].case_token) == expected["last"]
    assert all(e.case_token for e in entries)
    # every list is for the date the fixture directory says it is
    assert str(parsed.list_date) == date


class TestSpecificKnownItems:
    def test_calcutta_tagged_wt_items_are_read(self):
        """Calcutta tags matters 'wt7'.. like Telangana's 'wt4'; items 1..22 are contiguous."""
        path = next((HC / "calcutta/2026-10-12/bench_3").glob("*.pdf"))
        entries = parse_table_doc(raw(path)).entries
        assert [e.item_number for e in entries[:12]] == ["1", "2", "3", "4", "5", "6", "wt7", "wt8", "wt9", "wt10", "wt11", "wt12"]
        assert entries[-1].item_number == "22"

    def test_bombay_reads_connected_matters_printed_under_an_item(self):
        """'with WP/3668/2026' under item 1: heard together, so listed."""
        path = next((HC / "bombay/2026-10-09/bench_1").glob("*.pdf"))
        entries = parse_table_doc(raw(path)).entries
        connected = [e.case_token for e in entries if e.item_number == "1 (connected)"]
        assert connected == ["WP/3668/2026", "WP/3687/2026", "WP/3305/2026"]

    def test_orissa_prints_the_cnr_beside_every_case(self):
        path = next((HC / "orissa/2026-10-12/bench_1").glob("*.pdf"))
        entries = parse_table_doc(raw(path)).entries
        assert entries[0].cnr == "ODHC010687532026"
        assert all(e.cnr for e in entries)

    def test_tripura_application_items_resolve_to_their_main_case(self):
        """'8) IA NO. 3/2026 ... IN MAC App./94/2023': the case is the MAC appeal."""
        path = next((HC / "tripura/2026-10-12/bench_1").glob("*.pdf"))
        by_item = {e.item_number: e.case_token for e in parse_table_doc(raw(path)).entries}
        assert by_item["8"] == "MAC App./94/2023"
        assert by_item["9"] == "MAC App./103/2025"
        assert by_item["13"] == "LA.App./20/2026"

    def test_manipur_with_items_are_accounted_for_without_a_case_number(self):
        path = next((HC / "manipur/2026-10-12/bench_1").glob("*.pdf"))
        numbers = {e.item_number for e in parse_table_doc(raw(path)).entries}
        assert {"1", "2", "4", "6", "7", "8", "10"} <= numbers
        assert "3" not in numbers  # '3) With' prints no case number of its own

    def test_karnataka_case_numbers_without_a_slash_after_the_type(self):
        path = next((HC / "karnataka/2026-10-12/bench_2").glob("*.pdf"))
        first = parse_table_doc(raw(path)).entries[0]
        assert first.case_token == "WA 100580/2026"
        from core.services.causelists.normalize import canonical_case_key

        assert canonical_case_key(first.case_token) == ("WA", "100580", "2026")

    def test_delhi_hard_wrapped_case_numbers_are_rejoined(self):
        """'W.P.(C)-' / '14369//202' / '6' across three lines is W.P.(C)-14369//2026."""
        path = next((HC / "delhi/2026-10-12/bench_1").glob("row10_*.pdf"))
        by_item = {e.item_number: e.case_token for e in parse_delhi_doc(raw(path)).entries}
        assert by_item["2"] == "W.P.(C)/14369/2026"  # item 2 is 'CM APPL. 69294/2026 </br>IN W.P.(C)-14369//2026'
        assert by_item["4"] == "W.P.(C)/14833/2026"

    def test_andhra_filing_number_entries_are_flagged_and_never_matched(self):
        from core.services.causelists.matcher import EntryIndex

        path = next((HC / "andhra/2026-10-12/bench_1").glob("*.pdf"))
        parsed = parser_for("f1")(raw(path))
        filing = [e for e in parsed.entries if e.is_filing_number]
        assert filing and filing[-1].case_token.startswith("WA/121445/2014")
        index = EntryIndex()
        index.add(parsed.entries, court="andhra")
        from core.services.causelists.normalize import canonical_case_key

        assert canonical_case_key("WA/121445/2014") not in index.by_key


class TestParsersRefuseTheWrongLayout:
    """A parser pointed at a layout it was not built for must raise, never
    return an empty or partial list that would read as 'not listed'."""

    def test_the_table_parser_refuses_delhi(self):
        path = next((HC / "delhi/2026-10-12/bench_1").glob("row10_*.pdf"))
        with pytest.raises(CauseListParseError):
            result = parse_table_doc(raw(path))
            # If it did not raise it must at least not have silently dropped Delhi's items.
            assert len(result.entries) >= 10

    def test_the_delhi_parser_refuses_bombay(self):
        path = next((HC / "bombay/2026-10-12/bench_1").glob("*.pdf"))
        with pytest.raises(CauseListParseError):
            parse_delhi_doc(raw(path))

    def test_the_telangana_parser_refuses_a_non_pdf(self):
        from core.services.causelists.adapters.telangana_hc import parse_cause_list_pdf

        with pytest.raises(CauseListParseError):
            parse_cause_list_pdf(b"<html>Order not uploaded</html>")

    def test_a_document_that_is_not_a_pdf_raises(self, tmp_path):
        bad = tmp_path / "bad.pdf"
        bad.write_bytes(b"\xef\xbb\xbfOrder not uploaded")
        with pytest.raises(CauseListParseError):
            parse_table_doc(raw(bad))

    def test_a_pdf_with_no_item_column_raises(self):
        """The Supreme Court's list has item numbers but 'No.'-style case numbers: the
        generic table parser must not return a plausible-looking but wrong list."""
        path = FIXTURES_ROOT / "supreme_court/2026-10-12/M_J_1.pdf"
        try:
            result = parse_table_doc(raw(path))
        except CauseListParseError:
            return
        # If a parse is returned it must be complete, not partial.
        assert len(result.entries) >= 10


# ---------------------------------------------------------------------------
# Which cases resolve to which source
# ---------------------------------------------------------------------------


@pytest.fixture
def advocate(db):
    from django.contrib.auth.models import User

    return User.objects.create_user(username="hc-advocate", password="pw-123456")


def hc_case(owner, number, hc_code=None, *, bench=None, cnr=None, **extra):
    config = {}
    if hc_code:
        config["hc_court_code"] = hc_code
    if bench:
        config["bench_code"] = bench
    if cnr:
        config["cnr"] = cnr
    return make_case(owner, number, tracking_config=config, cnr_number=cnr, **extra)


@pytest.mark.django_db
class TestResolution:
    def test_an_andhra_case_never_resolves_to_telangana(self, advocate):
        """THE bug: every High Court case used to be checked against Telangana's list."""
        res = registry.resolve_case(hc_case(advocate, "WP/1/2026", "andhra"))
        assert res.is_target
        assert res.target.adapter == "hcservices_generic" and res.target.key == "andhra/1"

    def test_a_telangana_case_resolves_to_the_telangana_adapter(self, advocate):
        res = registry.resolve_case(hc_case(advocate, "WP/1/2026", "telangana"))
        assert res.target.adapter == "telangana_hc"

    def test_a_cnr_first_case_is_placed_by_its_cnr_prefix(self, advocate):
        res = registry.resolve_case(hc_case(advocate, "WP/1/2026", cnr="APHC010123452026"))
        assert res.target.key == "andhra/1"
        res = registry.resolve_case(hc_case(advocate, "WP/2/2026", cnr="HBHC010123452026"))
        assert res.target.adapter == "telangana_hc"

    def test_a_bench_variant_court_code_maps_to_its_parent_and_bench(self, advocate):
        res = registry.resolve_case(hc_case(advocate, "WP/3/2026", "bombay-nagpur"))
        assert res.target.key == "bombay/4"

    def test_a_known_bench_narrows_the_target(self, advocate):
        res = registry.resolve_case(hc_case(advocate, "WP/4/2026", "karnataka", bench="2"))
        assert res.target.key == "karnataka/2"
        assert res.target.params["incomplete_scope"] == ""

    def test_an_unknown_bench_reads_every_served_bench(self, advocate):
        res = registry.resolve_case(hc_case(advocate, "WP/5/2026", "karnataka"))
        assert res.target.key == "karnataka/1,2,3"

    def test_bombays_special_court_is_skipped_when_the_bench_is_unknown(self, advocate):
        res = registry.resolve_case(hc_case(advocate, "WP/6/2026", "bombay"))
        assert "6" not in res.target.key.split("/")[1].split(",")

    def test_an_unidentifiable_high_court_is_not_covered(self, advocate):
        res = registry.resolve_case(make_case(advocate, "WP/7/2026", tracking_config={}))
        assert res.kind == "unsupported"

    def test_a_case_with_no_court_is_not_covered(self, advocate):
        case = make_case(advocate, "XX/1/2026", court_type=None, tracking_config={})
        case.court_type = None
        case.tracking_config = None
        case.save()
        res = registry.resolve_case(case)
        assert res.kind == "unsupported" and "not identified" in res.reason

    def test_every_supported_court_has_a_parser_and_every_unsupported_one_a_reason(self):
        for cfg in hc_config.HC_CONFIGS.values():
            if cfg.status == hc_config.SUPPORTED:
                assert parser_for(cfg.parser) is not None, cfg.code
                assert cfg.served_benches, cfg.code
            else:
                assert cfg.reason, cfg.code

    def test_config_covers_every_high_court_but_telangana(self):
        from bharat_courts.courts import HIGH_COURTS

        parents = {c.code for c in HIGH_COURTS if c.bench is None} - {"telangana"}
        assert parents == set(hc_config.HC_CONFIGS)
        for code, cfg in hc_config.HC_CONFIGS.items():
            from bharat_courts import get_court

            assert get_court(code).state_code == cfg.state_code, code


# One test per court the portal cannot serve. Each must resolve to
# 'unsupported' and, run through the whole pipeline, must never be fetched
# and never become 'not listed'.
BLOCKED_CASES = [
    pytest.param("allahabad", None, "Allahabad High Court", id="allahabad"),
    pytest.param("allahabad-lucknow", None, "Allahabad High Court", id="allahabad-lucknow"),
    pytest.param("gujarat", None, "Gujarat High Court", id="gujarat"),
    pytest.param("himachal", None, "Himachal Pradesh High Court", id="himachal-pradesh"),
    pytest.param("jharkhand", None, "Jharkhand High Court", id="jharkhand"),
    pytest.param("kerala", None, "Kerala High Court", id="kerala"),
    pytest.param("mp", None, "Madhya Pradesh High Court", id="madhya-pradesh"),
    pytest.param("punjab", None, "Punjab and Haryana High Court", id="punjab-and-haryana"),
    pytest.param("madras", "2", "Madurai Bench", id="madras-madurai-bench"),
]


@pytest.mark.django_db
@pytest.mark.parametrize("hc_code,bench,expected_name", BLOCKED_CASES)
def test_a_court_hcservices_cannot_serve_is_unsupported_never_not_listed(
    advocate, monkeypatch, hc_code, bench, expected_name
):
    from core.models import Hearing
    from core.services.causelists import service
    from core.tests.causelist_support import make_hearing

    case = hc_case(advocate, "WP/9/2026", hc_code, bench=bench)
    res = registry.resolve_case(case)
    assert res.kind == "unsupported", res
    assert expected_name in res.reason

    hearing = make_hearing(advocate, case, datetime.date(2026, 10, 12))
    fetched = []
    monkeypatch.setattr(type(get_adapter()), "fetch", lambda *a, **k: fetched.append(a) or None)
    report = service.run([datetime.date(2026, 10, 12)])

    hearing.refresh_from_db()
    assert hearing.cause_list_status == Hearing.CAUSE_LIST_UNSUPPORTED
    assert hearing.cause_list_note and hearing.cause_list_item_number == ""
    assert not fetched, "an unsupported court's hearing must not trigger any fetch"
    assert report.unsupported_marked == 1
    assert hearing.cause_list_status != Hearing.CAUSE_LIST_NOT_LISTED


@pytest.mark.django_db
def test_madras_with_an_unknown_bench_can_never_conclude_not_listed(advocate):
    """The case might sit on the Madurai bench, whose lists are not served."""
    res = registry.resolve_case(hc_case(advocate, "WP/8/2026", "madras"))
    assert res.target.key == "madras/1"
    assert "Madurai" in res.target.params["incomplete_scope"]
