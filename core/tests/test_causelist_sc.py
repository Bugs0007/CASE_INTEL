"""Supreme Court daily lists (dormant adapter) against the real files from
2026-10-12 (core/tests/fixtures/causelists/supreme_court/ -- trimmed to the
first three pages of each PDF; see SOURCE.md)."""

import datetime
import pathlib

import pytest

from core.services.causelists import registry
from core.services.causelists.adapters import supreme_court as sc
from core.services.causelists.base import RawDoc
from core.services.causelists.exceptions import CauseListParseError
from core.tests.causelist_support import FIXTURES_ROOT, make_case

SC = FIXTURES_ROOT / "supreme_court/2026-10-12"
DAY = datetime.date(2026, 10, 12)


class TestIndex:
    def setup_method(self):
        self.html = (SC / "index_page.html").read_text(encoding="utf-8")

    def test_daily_links_for_the_date_are_read_off_the_page(self):
        links = sc.parse_index(self.html, DAY)
        assert [l.stem for l in links] == ["M_J_1", "M_J_2", "M_C_1", "M_C_2", "M_S_1", "M_S_2", "M_R_1"]
        assert links[0].url == "https://api.sci.gov.in/jonew/cl/2026-10-12/M_J_1.pdf"
        assert all(l.list_date == DAY for l in links)

    def test_another_day_has_its_own_files(self):
        stems = [l.stem for l in sc.parse_index(self.html, datetime.date(2026, 10, 13))]
        assert stems == ["M_J_1", "F_J_1", "M_CC_1", "M_R_1"]

    def test_advance_and_weekly_lists_are_not_daily_lists(self):
        every = sc.parse_index(self.html)
        assert not any("/advance/" in l.url or "/wk/" in l.url for l in every)

    def test_a_date_with_no_list_has_no_links(self):
        assert sc.parse_index(self.html, datetime.date(2026, 1, 1)) == []
        assert sc.parse_index("", DAY) == []


class TestPdf:
    def test_the_main_miscellaneous_list(self):
        parsed = sc.parse_sc_pdf(SC / "M_J_1.pdf", list_type="M_J_1")
        assert parsed.list_date == DAY
        assert len(parsed.entries) == 42
        assert (parsed.entries[0].item_number, parsed.entries[0].case_token) == ("1", "C.A/5981/2023")
        assert parsed.entries[1].case_token == "C.A/4876/2024"

    def test_a_number_range_expands_to_one_entry_per_case(self):
        """'C.A. No. 8264-8292/2023' wraps its number onto the next line."""
        entries = sc.parse_sc_pdf(SC / "M_J_1.pdf").entries
        item3 = [e.case_token for e in entries if e.item_number == "3"]
        assert item3[0] == "C.A/8264/2023" and item3[-1] == "C.A/8292/2023" and len(item3) == 29

    def test_a_type_that_wraps_its_number_is_joined(self):
        """'SLP(Crl) No.' / '18602/2026'."""
        tokens = {e.case_token for e in sc.parse_sc_pdf(SC / "M_J_1.pdf").entries}
        assert "SLP(Crl)/18602/2026" in tokens

    def test_diary_numbers_are_kept_but_never_matchable(self):
        entries = sc.parse_sc_pdf(SC / "M_J_1.pdf").entries
        diary = [e for e in entries if e.case_token.startswith("Diary No.")]
        assert diary and all(e.is_filing_number for e in diary)

    def test_the_supplementary_list_has_item_and_case_on_one_line(self):
        parsed = sc.parse_sc_pdf(SC / "M_J_2.pdf", list_type="M_J_2")
        assert [(e.item_number, e.case_token) for e in parsed.entries] == [
            ("51", "W.P.(C)/1049/2026"),
            ("52", "W.P.(C)/1307/2026"),
        ]

    def test_a_non_supreme_court_pdf_is_refused(self):
        hc = next((FIXTURES_ROOT / "hcservices_generic/delhi/2026-10-12/bench_1").glob("row10_*.pdf"))
        with pytest.raises(CauseListParseError):
            sc.parse_sc_pdf(hc)

    def test_the_canonical_key_matches_a_supreme_court_case_number(self):
        from core.services.causelists.normalize import canonical_case_key

        assert canonical_case_key("C.A/5981/2023") == canonical_case_key("CA 5981/2023") == ("CA", "5981", "2023")


class TestDormant:
    @pytest.mark.django_db
    def test_no_case_ever_resolves_to_the_supreme_court(self):
        from django.contrib.auth.models import User

        owner = User.objects.create_user(username="sc-owner", password="pw-123456")
        for n, kwargs in enumerate(
            (
                {"court_type": "high_court", "cnr_number": "ESCR010000012026"},
                {"court_type": "district", "cnr_number": "ESCR010000022026"},
            )
        ):
            case = make_case(owner, f"C.A. {n + 1}/2026", tracking_config={"cnr": kwargs["cnr_number"]}, **kwargs)
            res = registry.resolve_case(case)
            assert not res.is_target or res.target.adapter != "supreme_court"

    @pytest.mark.django_db
    def test_the_adapter_itself_says_not_tracked_and_is_flagged_dormant(self):
        adapter = registry.get_adapter("supreme_court")
        assert adapter.dormant
        assert adapter.resolve(None).kind == "unsupported"

    def test_the_scheduled_run_does_not_include_it_by_default(self, settings):
        assert "supreme_court" not in registry.configured_adapter_keys()

    def test_published_links_are_public_so_they_may_be_shown(self, monkeypatch, tmp_path):
        """sci.gov.in PDFs need no session, unlike hcservices' (the one place
        a source link is shown to the user)."""
        pdf = (SC / "M_J_2.pdf").read_bytes()
        index = (SC / "index_page.html").read_text(encoding="utf-8")

        class Http:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, **kw):
                class R:
                    text = index

                return R()

        async def fake_download(http, url, dest, **kw):
            dest.write_bytes(pdf)
            from core.services.causelists.fetchlib import Download

            return Download(kind="pdf", size=len(pdf), sha256="x")

        monkeypatch.setattr("bharat_courts.http.RateLimitedClient", Http)
        monkeypatch.setattr("core.services.causelists.fetchlib.download_pdf", fake_download)
        monkeypatch.setattr("core.services.causelists.fetchlib.Pacer.wait", lambda self: _noop())
        result = sc.get_adapter().fetch(sc.get_adapter().target_from_key("daily"), DAY, tmp_path)
        assert result.status == "ok" and result.doc_total == 7
        assert all(d.source_public and d.source_ref.startswith("https://api.sci.gov.in/") for d in result.docs)

    def test_nothing_published_is_none_available(self, monkeypatch, tmp_path):
        class Http:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def get(self, url, **kw):
                class R:
                    text = "<html></html>"

                return R()

        monkeypatch.setattr("bharat_courts.http.RateLimitedClient", Http)
        monkeypatch.setattr("core.services.causelists.fetchlib.Pacer.wait", lambda self: _noop())
        result = sc.get_adapter().fetch(sc.get_adapter().target_from_key("daily"), DAY, tmp_path)
        assert result.status == "none_available"


async def _noop():
    return None
