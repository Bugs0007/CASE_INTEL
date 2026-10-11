"""District Courts cause lists: parsing the real per-court responses, the
court locator, the fetch flow (portal faked), and the whole pipeline.

Fixtures: core/tests/fixtures/causelists/district_ecourts/ (see SOURCE.md) --
real responses fetched 2026-10-10 from Hyderabad (City Civil + Criminal
complexes) and Bengaluru (City Civil), plus the real CNR case page.
"""

import datetime
import json

import pytest
from bharat_courts.districtcourts.parser import CaptchaError, ServerError

from core.models import CauseListFetch, CauseListMatch, Case, CourtFetchLog, Hearing
from core.services.causelists import locator, registry, service
from core.services.causelists.adapters import district_ecourts as dc
from core.services.causelists.base import RawDoc
from core.services.causelists.exceptions import CauseListParseError
from core.services.court_data.ecourts_parsing import extract_locator_hints, parse_case_history_html
from core.tests.causelist_support import FIXTURES_ROOT, StaticAdapter, make_case, make_doc, make_hearing, target_of

D = FIXTURES_ROOT / "district_ecourts"
HYD_CIVIL_9 = D / "2026-10-09/telangana_hyd_city_civil"
HYD_CRIM_9 = D / "2026-10-09/telangana_hyd_criminal"
HYD_CIVIL_12 = D / "2026-10-12/telangana_hyd_city_civil"
BLR_12 = D / "2026-10-12/karnataka_blr_city_civil"
CNR_PAGE = D / "cnr_case_page/TSHC010030082026.html"

# OS/336/2026 (CNR TSHC010030082026) is real item 3 in Hyderabad City Civil court 2^1 on 9 Oct.
KNOWN_CNR = "TSHC010030082026"
DAY9 = datetime.date(2026, 10, 9)
DAY12 = datetime.date(2026, 10, 12)


def case_data(path):
    return json.loads(path.read_text(encoding="utf-8"))["case_data"]


# ---------------------------------------------------------------------------
# Parsing the real responses
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path,count,list_date,first",
    [
        (HYD_CIVIL_9 / "2_1_civ.json", 55, DAY9, ("1", "O.OP/29/2026", "TSHC010015702026")),
        (HYD_CIVIL_9 / "2_3_civ.json", 86, DAY9, ("1", "OS/521/2013", "TSHC010022862013")),
        (HYD_CRIM_9 / "3_1_cri.json", 76, DAY9, ("1", "CC/100035/2016", "TSHM010019792016")),
        (HYD_CRIM_9 / "3_2_cri.json", 75, DAY9, ("1", "CC/200848/2010", "TSHM010020762010")),
        (HYD_CIVIL_12 / "2_1_civ.json", 45, DAY12, ("1", "OS/316/2018", "TSHC010016732018")),
        (BLR_12 / "3_1_civ.json", 17, DAY12, ("1", "O.S./3436/2026", "KABC010131632026")),
    ],
    ids=lambda v: getattr(v, "name", None) if hasattr(v, "name") else None,
)
def test_golden_parse(path, count, list_date, first):
    parsed = dc.parse_district_list(case_data(path))
    assert len(parsed.entries) == count
    assert parsed.list_date == list_date
    e = parsed.entries[0]
    assert (e.item_number, e.case_token, e.cnr) == first
    assert all(len(x.cnr) == 16 for x in parsed.entries)
    assert all(x.stage for x in parsed.entries)  # every row sits under a case-type heading


def test_the_court_and_mode_are_read_from_the_heading():
    parsed = dc.parse_district_list(case_data(HYD_CIVIL_9 / "2_1_civ.json"))
    assert parsed.entries[0].court_name == "SRI. S SASIDHAR REDDY, CHIEF JUDGE"
    assert parsed.entries[0].list_type == "Civil"
    crim = dc.parse_district_list(case_data(HYD_CRIM_9 / "3_1_cri.json"))
    assert crim.entries[0].list_type == "Criminal"
    assert crim.entries[0].court_name.startswith("Smt P Aruna Kumari")


def test_section_headings_become_the_stage():
    parsed = dc.parse_district_list(case_data(HYD_CIVIL_9 / "2_1_civ.json"))
    stages = [e.stage for e in parsed.entries]
    assert stages[0] == "Other Original Petition"
    assert "MOTOR ACCIDENT OP" in stages and "TRANSFER OP" in stages


def test_the_known_case_is_item_3_of_court_2_1():
    parsed = dc.parse_district_list(case_data(HYD_CIVIL_9 / "2_1_civ.json"))
    hit = [e for e in parsed.entries if e.cnr == KNOWN_CNR]
    assert [(e.item_number, e.case_token) for e in hit] == [("3", "OS/336/2026")]


def test_record_not_found_is_a_genuine_empty_list():
    parsed = dc.parse_district_list(case_data(HYD_CIVIL_9 / "2_1_cri.json"))
    assert parsed.entries == [] and parsed.genuinely_empty


def test_a_response_with_neither_cases_nor_the_empty_marker_is_a_failure():
    with pytest.raises(CauseListParseError):
        dc.parse_district_list("<div>Something went wrong</div>")
    with pytest.raises(CauseListParseError):
        dc.parse_district_list("")


def test_a_dropped_row_is_a_failure_not_a_shorter_list():
    """Corrupt one real row so the table walk skips it while its case link
    is still on the page: the cross-check against the raw link count must
    refuse the parse."""
    html = case_data(HYD_CIVIL_9 / "2_1_civ.json")
    at = html.index("viewHistory('201700002432026'")
    start = html.rindex("<a", 0, at)
    broken = html[:start] + "<span" + html[start + 2 :]
    with pytest.raises(CauseListParseError):
        dc.parse_district_list(broken)


def test_the_adapter_parse_stamps_the_court_number_as_the_hall(tmp_path):
    path = tmp_path / "x.html"
    path.write_text(case_data(HYD_CIVIL_9 / "2_1_civ.json"), encoding="utf-8")
    parsed = dc.get_adapter().parse(RawDoc(doc_key="2^1:civ", status="ok", path=path, meta={"court_no": "1"}))
    assert {e.court_hall for e in parsed.entries} == {"1"}


# ---------------------------------------------------------------------------
# The court locator: what the real CNR page carries, and what it doesn't
# ---------------------------------------------------------------------------


class TestLocatorFromTheRealCasePage:
    def test_state_district_establishment_and_court_number_are_read(self):
        html = CNR_PAGE.read_text(encoding="utf-8")
        data = parse_case_history_html(html)
        assert data.court_and_judge == "1-CHIEF JUDGE"
        assert data.locator_hints == {"state_code": "29", "dist_code": "2", "est_code": "2", "court_no": "1"}

    def test_no_link_means_no_hints_never_half_a_locator(self):
        assert extract_locator_hints("<html>no link</html>", "1-CHIEF JUDGE") == {}
        assert extract_locator_hints(CNR_PAGE.read_text(encoding="utf-8"), "CHIEF JUDGE") == {}

    def test_the_hints_survive_the_preview_round_trip(self):
        from core.services.court_data.models import CourtCaseData

        data = parse_case_history_html(CNR_PAGE.read_text(encoding="utf-8"))
        again = CourtCaseData.from_dict({**data.to_dict(), "cnr": KNOWN_CNR})
        assert again.locator_hints == data.locator_hints

    def test_court_number_parsing(self):
        assert locator.court_no_from_text("1-CHIEF JUDGE") == "1"
        assert locator.court_no_from_text(" 12 - Sri X") == "12"
        assert locator.court_no_from_text("APARESH KUMAR SINGH , G.M. MOHIUDDIN") == ""

    def test_locator_from_hints_keeps_the_complex_when_the_establishment_is_unchanged(self):
        hints = {"state_code": "29", "dist_code": "2", "est_code": "2", "court_no": "1"}
        existing = {"kind": "district", "state_code": "29", "dist_code": "2", "est_code": "2", "complex_code": "1290019", "court_no": "7"}
        loc = locator.locator_from_hints(hints, None, existing)
        assert loc["complex_code"] == "1290019" and loc["court_no"] == "1"  # the court moved, the complex did not
        moved = locator.locator_from_hints({**hints, "est_code": "6"}, None, existing)
        assert moved["complex_code"] == ""  # a different establishment: do not carry the complex over

    def test_partial_hints_give_no_locator(self):
        assert locator.locator_from_hints({"state_code": "29"}, None, None) is None


class TestCompleteComplex:
    COMPLEXES = json.loads((D / "complexes.json").read_text(encoding="utf-8"))

    class _Provider:
        def __init__(self, complexes):
            self.complexes = complexes
            self.calls = []

        def list_complexes(self, state, dist):
            self.calls.append((state, dist))
            return self.complexes

    def test_establishment_2_is_in_the_city_civil_complex(self):
        provider = self._Provider(self.COMPLEXES["telangana_hyderabad_ccc"]["complexes"])
        loc = {"kind": "district", "state_code": "29", "dist_code": "2", "est_code": "2", "court_no": "1", "complex_code": ""}
        assert locator.complete_complex(loc, provider)["complex_code"] == "1290019"
        assert provider.calls == [("29", "2")]

    def test_bengaluru_city_civil(self):
        provider = self._Provider(self.COMPLEXES["karnataka_bengaluru"]["complexes"])
        loc = {"kind": "district", "state_code": "3", "dist_code": "20", "est_code": "3", "court_no": "1", "complex_code": ""}
        assert locator.complete_complex(loc, provider)["complex_code"] == "1030135"

    def test_an_establishment_no_complex_lists_is_never_guessed(self):
        provider = self._Provider(self.COMPLEXES["telangana_hyderabad_ccc"]["complexes"])
        loc = {"kind": "district", "state_code": "29", "dist_code": "2", "est_code": "999", "court_no": "1", "complex_code": ""}
        assert locator.complete_complex(loc, provider) is None

    def test_a_locator_that_already_has_its_complex_makes_no_call(self):
        provider = self._Provider({})
        loc = {"complex_code": "1290019", "est_code": "2"}
        assert locator.complete_complex(loc, provider) is loc
        assert provider.calls == []


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


@pytest.fixture
def advocate(db):
    from django.contrib.auth.models import User

    return User.objects.create_user(username="district-advocate", password="pw-123456")


LOCATOR = {
    "kind": "district", "state_code": "29", "dist_code": "2", "est_code": "2",
    "complex_code": "1290019", "court_no": "1",
}


def district_case(owner, number="OS/336/2026", *, cnr=KNOWN_CNR, court_locator=None, **config):
    return make_case(
        owner, number, court_type="district", tracking_config=config or None,
        cnr_number=cnr, court_locator=court_locator,
    )


@pytest.mark.django_db
class TestResolution:
    def test_a_located_case_resolves_to_its_court(self, advocate):
        res = registry.resolve_case(district_case(advocate, court_locator=LOCATOR))
        assert res.is_target
        assert res.target.key == "29/2/1290019/2^1"
        assert res.target.params["court_value"] == "2^1"

    def test_a_case_without_a_locator_is_pending_never_unsupported_or_guessed(self, advocate):
        res = registry.resolve_case(district_case(advocate))
        assert res.kind == "pending" and "refresh" in res.reason

    def test_a_locator_without_its_complex_is_pending(self, advocate):
        res = registry.resolve_case(district_case(advocate, court_locator={**LOCATOR, "complex_code": ""}))
        assert res.kind == "pending"

    def test_a_cascade_case_is_located_from_stored_data_alone(self, advocate):
        case = district_case(
            advocate, state_code="29", dist_code="2", court_complex_code="1290019", est_code="2",
        )
        CourtFetchLog.objects.create(
            owner=advocate, case=case, success=True,
            fields_changed={"snapshot": {"court_and_judge": "1-CHIEF JUDGE"}},
        )
        res = registry.resolve_case(case)
        assert res.is_target and res.target.key == "29/2/1290019/2^1"

    def test_a_pending_hearing_is_left_exactly_as_it_was(self, advocate):
        case = district_case(advocate)
        hearing = make_hearing(advocate, case, DAY9)
        report = service.run([DAY9])
        hearing.refresh_from_db()
        assert report.pending == 1 and report.groups == []
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED

    def test_known_case_types_pick_their_mode_and_unknown_ones_fetch_both(self, advocate):
        civil = district_case(advocate, "OS/336/2026", court_locator=LOCATOR)
        crim = district_case(advocate, "CC/1/2026", cnr="TSHM010000012026", court_locator=LOCATOR)
        unknown = district_case(advocate, "ZZ/1/2026", cnr="TSHC010000022026", court_locator=LOCATOR)
        adapter = dc.get_adapter()

        hearings = {c.pk: make_hearing(advocate, c, DAY9) for c in (civil, crim, unknown)}

        def modes(*cases):
            target = registry.resolve_case(cases[0]).target
            return adapter.finalize_target(target, [hearings[c.pk] for c in cases]).params["modes"]

        assert modes(civil) == ["civ"]
        assert modes(crim) == ["cri"]
        assert modes(unknown) == ["civ", "cri"]
        assert modes(civil, crim) == ["civ", "cri"]

    def test_want_cnrs_are_collected_for_the_early_exit(self, advocate):
        case = district_case(advocate, court_locator=LOCATOR)
        target = registry.resolve_case(case).target
        final = dc.get_adapter().finalize_target(target, [make_hearing(advocate, case, DAY9)])
        assert final.params["want_cnrs"] == [KNOWN_CNR]


# ---------------------------------------------------------------------------
# The fetch flow, with the portal faked (the real responses are the data)
# ---------------------------------------------------------------------------


class FakeDistrictClient:
    """_TokenSeedingDistrictClient stand-in: scripted `submitCauseList` answers."""

    answers: list = []
    options = {"2^1": "1-SRI. S SASIDHAR REDDY-CHIEF JUDGE"}
    posts = 0
    captchas: list = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def list_cause_list_courts(self, *args):
        return type(self).options

    async def _init_session(self):
        pass

    async def _setup_court(self, **kw):
        pass

    async def _solve_captcha(self):
        return type(self).captchas.pop(0) if type(self).captchas else "abc123"

    async def _post_ajax(self, action, form):
        type(self).posts += 1
        answer = type(self).answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer


@pytest.fixture
def fake_portal(monkeypatch, settings):
    settings.CAUSE_LIST_MIN_REQUEST_GAP_SECONDS = 0
    FakeDistrictClient.answers = []
    FakeDistrictClient.captchas = []
    FakeDistrictClient.posts = 0
    FakeDistrictClient.options = {"2^1": "1-SRI. S SASIDHAR REDDY-CHIEF JUDGE"}
    monkeypatch.setattr(
        "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", FakeDistrictClient
    )
    return FakeDistrictClient


def env(path):
    return json.loads(path.read_text(encoding="utf-8"))


def target(modes, want=()):
    return dc.get_adapter().target_from_key("29/2/1290019/2^1").__class__(
        adapter="district_ecourts", key="29/2/1290019/2^1", label="x",
        params={
            "state_code": "29", "dist_code": "2", "complex_code": "1290019", "est_code": "2",
            "court_value": "2^1", "modes": list(modes), "want_cnrs": list(want),
        },
    )


class TestFetchFlow:
    def test_a_listed_case_in_the_first_mode_skips_the_second(self, fake_portal, tmp_path):
        fake_portal.answers = [env(HYD_CIVIL_9 / "2_1_civ.json")]
        result = dc.get_adapter().fetch(target(["civ", "cri"], want=[KNOWN_CNR]), DAY9, tmp_path)
        assert result.status == "ok" and result.early_exit
        assert fake_portal.posts == 1
        assert [d.status for d in result.docs] == ["ok"] and result.doc_total == 2

    def test_a_case_not_in_the_first_mode_reads_the_second(self, fake_portal, tmp_path):
        fake_portal.answers = [env(HYD_CIVIL_9 / "2_1_civ.json"), env(HYD_CIVIL_9 / "2_1_cri.json")]
        result = dc.get_adapter().fetch(target(["civ", "cri"], want=["TSHC010099992026"]), DAY9, tmp_path)
        assert not result.early_exit and fake_portal.posts == 2
        assert [d.list_type for d in result.docs] == ["Civil", "Criminal"]

    def test_captcha_rejections_are_retried_within_the_budget(self, fake_portal, tmp_path, settings):
        settings.CAUSE_LIST_CAPTCHA_ATTEMPTS_DISTRICT = 4
        fake_portal.answers = [CaptchaError("x"), ServerError("Invalid Captcha... "), env(HYD_CIVIL_9 / "2_1_civ.json")]
        result = dc.get_adapter().fetch(target(["civ"]), DAY9, tmp_path)
        assert result.status == "ok" and fake_portal.posts == 3

    def test_an_unreadable_captcha_is_never_submitted(self, fake_portal, tmp_path, settings):
        settings.CAUSE_LIST_CAPTCHA_ATTEMPTS_DISTRICT = 3
        fake_portal.captchas = ["", "ab", ""]
        result = dc.get_adapter().fetch(target(["civ"]), DAY9, tmp_path)
        assert result.status == "captcha_failed" and fake_portal.posts == 0

    def test_exhausted_captcha_attempts_are_captcha_failed_not_empty(self, fake_portal, tmp_path, settings):
        settings.CAUSE_LIST_CAPTCHA_ATTEMPTS_DISTRICT = 2
        fake_portal.answers = [CaptchaError("x"), CaptchaError("x")]
        result = dc.get_adapter().fetch(target(["civ"]), DAY9, tmp_path)
        assert result.status == "captcha_failed"

    def test_a_real_server_error_is_a_fetch_error_and_not_retried(self, fake_portal, tmp_path):
        fake_portal.answers = [ServerError("Invalid Request")]
        result = dc.get_adapter().fetch(target(["civ"]), DAY9, tmp_path)
        assert result.status == "fetch_error" and "Invalid Request" in result.error
        assert fake_portal.posts == 1

    def test_a_court_missing_from_the_dropdown_is_a_fetch_error(self, fake_portal, tmp_path):
        fake_portal.options = {"2^9": "9-Someone"}
        result = dc.get_adapter().fetch(target(["civ"]), DAY9, tmp_path)
        assert result.status == "fetch_error" and "not in the complex" in result.error

    def test_a_response_without_case_data_is_never_an_empty_list(self, fake_portal, tmp_path, settings):
        settings.CAUSE_LIST_CAPTCHA_ATTEMPTS_DISTRICT = 2
        fake_portal.answers = [{"status": 1}, {"status": 1}]
        result = dc.get_adapter().fetch(target(["civ"]), DAY9, tmp_path)
        assert result.status == "fetch_error"

    def test_the_second_mode_failing_leaves_a_failed_document_behind(self, fake_portal, tmp_path, settings):
        settings.CAUSE_LIST_CAPTCHA_ATTEMPTS_DISTRICT = 1
        fake_portal.answers = [env(HYD_CIVIL_9 / "2_1_civ.json"), CaptchaError("x")]
        result = dc.get_adapter().fetch(target(["civ", "cri"], want=["TSHC010099992026"]), DAY9, tmp_path)
        assert [d.status for d in result.docs] == ["ok", "fetch_error"]


# ---------------------------------------------------------------------------
# End to end: fetch -> parse -> match -> write, on the real responses
# ---------------------------------------------------------------------------


def run_district(hearings, answers, fake_portal, *, modes=("civ", "cri"), day=DAY9):
    fake_portal.answers = list(answers)
    adapter = dc.get_adapter()
    tgt = adapter.finalize_target(target(modes), hearings)
    return service.process_group(adapter, tgt, day, hearings)


@pytest.mark.django_db
class TestEndToEnd:
    def test_the_known_case_is_listed_with_its_item_court_and_judge(self, advocate, fake_portal):
        # an unrecognised case type, so both civil and criminal lists would be asked for
        hearing = make_hearing(advocate, district_case(advocate, "ZZ/336/2026", court_locator=LOCATOR), DAY9)
        report = run_district([hearing], [env(HYD_CIVIL_9 / "2_1_civ.json")], fake_portal)

        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert hearing.cause_list_item_number == "3"
        assert hearing.cause_list_court_hall == "1"
        assert hearing.cause_list_bench == "SRI. S SASIDHAR REDDY, CHIEF JUDGE"
        assert hearing.cause_list_list_type == "Civil"
        assert hearing.cause_list_stage == "ORIGINAL SUIT"
        assert report.listed == 1 and report.docs_total == 2  # early exit: criminal never asked for
        match = hearing.cause_list_matches.get()
        assert match.matched_by == "cnr" and match.owner_id == advocate.id

    def test_a_case_absent_from_both_complete_lists_is_not_listed(self, advocate, fake_portal):
        case = district_case(advocate, "ZZ/999/2026", cnr="TSHC010099992026", court_locator=LOCATOR)
        hearing = make_hearing(advocate, case, DAY9)
        report = run_district([hearing], [env(HYD_CIVIL_9 / "2_1_civ.json"), env(HYD_CIVIL_9 / "2_1_cri.json")], fake_portal)

        hearing.refresh_from_db()
        assert report.complete and report.docs_ok == 2
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_LISTED

    def test_absent_from_one_mode_while_the_other_could_not_be_read_is_couldnt_check(self, advocate, fake_portal, settings):
        settings.CAUSE_LIST_CAPTCHA_ATTEMPTS_DISTRICT = 1
        case = district_case(advocate, "ZZ/999/2026", cnr="TSHC010099992026", court_locator=LOCATOR)
        hearing = make_hearing(advocate, case, DAY9)
        report = run_district([hearing], [env(HYD_CIVIL_9 / "2_1_civ.json"), CaptchaError("x")], fake_portal)

        hearing.refresh_from_db()
        assert not report.complete
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_FETCH_FAILED

    def test_a_case_known_to_be_civil_only_needs_only_the_civil_list(self, advocate, fake_portal):
        case = district_case(advocate, "OS/999/2026", cnr="TSHC010099992026", court_locator=LOCATOR)
        hearing = make_hearing(advocate, case, DAY9)
        fake_portal.answers = [env(HYD_CIVIL_9 / "2_1_civ.json")]
        report = service.process_group(dc.get_adapter(), dc.get_adapter().finalize_target(target(["civ", "cri"]), [hearing]), DAY9, [hearing])
        hearing.refresh_from_db()
        assert report.complete and fake_portal.posts == 1
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_LISTED

    def test_two_advocates_with_cases_in_one_court_share_one_fetch(self, advocate, fake_portal):
        from django.contrib.auth.models import User

        other = User.objects.create_user(username="other-advocate", password="pw-123456")
        mine = make_hearing(advocate, district_case(advocate, court_locator=LOCATOR), DAY9)
        theirs = make_hearing(other, district_case(other, "ZZ/999/2026", cnr="TSHC010099992026", court_locator=LOCATOR), DAY9)
        groups, unsupported, pending = service.plan([mine, theirs])
        assert len(groups) == 1 and {h.pk for h in next(iter(groups.values()))[1]} == {mine.pk, theirs.pk}

        fake_portal.answers = [env(HYD_CIVIL_9 / "2_1_civ.json"), env(HYD_CIVIL_9 / "2_1_cri.json")]
        (key, (tgt, rows)), = groups.items()
        service.process_group(dc.get_adapter(), tgt, DAY9, rows)
        mine.refresh_from_db(); theirs.refresh_from_db()
        assert mine.cause_list_status == Hearing.CAUSE_LIST_LISTED
        assert theirs.cause_list_status == Hearing.CAUSE_LIST_NOT_LISTED
        # tenancy: each advocate's match rows belong to that advocate only
        assert CauseListMatch.objects.filter(owner=other).count() == 0
        assert fake_portal.posts == 2

    def test_the_ledger_records_the_index_and_each_document(self, advocate, fake_portal):
        hearing = make_hearing(advocate, district_case(advocate, "ZZ/999/2026", cnr="TSHC010099992026", court_locator=LOCATOR), DAY9)
        run_district([hearing], [env(HYD_CIVIL_9 / "2_1_civ.json"), env(HYD_CIVIL_9 / "2_1_cri.json")], fake_portal)
        rows = {(r.kind, r.list_type): r for r in CauseListFetch.objects.all()}
        assert rows[("index", "")].status == "ok" and rows[("index", "")].doc_total == 2
        assert rows[("document", "Civil")].entry_count == 55 and rows[("document", "Civil")].status == "ok"
        assert rows[("document", "Criminal")].status == "empty_ok"

    def test_rerunning_is_idempotent(self, advocate, fake_portal):
        hearing = make_hearing(advocate, district_case(advocate, court_locator=LOCATOR), DAY9)
        for _ in range(2):
            run_district([hearing], [env(HYD_CIVIL_9 / "2_1_civ.json")], fake_portal)
        assert CauseListFetch.objects.filter(kind="document").count() == 1
        assert hearing.cause_list_matches.count() == 1

    def test_the_12_oct_list_for_the_same_court_is_independent(self, advocate, fake_portal):
        case = district_case(advocate, "OS/316/2018", cnr="TSHC010016732018", court_locator=LOCATOR)
        hearing = make_hearing(advocate, case, DAY12)
        run_district([hearing], [env(HYD_CIVIL_12 / "2_1_civ.json")], fake_portal, day=DAY12)
        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_LISTED and hearing.cause_list_item_number == "1"
