"""The High Courts side of the redesigned advocate search.

bharat-courts has no High Court advocate search, so the form is ours
(hc_advocate_search_form) and the portal is faked at the library's client. What a
live portal answers is NOT covered here: `manage.py probe_hc_advocate_search` is
how that gets confirmed.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from bharat_courts.hcservices.parser import CaptchaError as HCCaptchaError
from bharat_courts.hcservices.parser import ServerError as HCServerError
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import AdvocateSearchComplexRun, AdvocateSearchPreference, AdvocateSearchProfile, ProcessingJob
from core.services.advocate_search import run_advocate_search
from core.services.advocate_search_v2 import run_retry
from core.services.court_data import CaptchaSolveError, CourtPortalError
from core.services.court_data.ecourts_parsing import hc_advocate_search_form, parse_hc_advocate_search
from core.services.court_data.ecourts_provider import EcourtsProvider
from core.services.court_data.models import AdvocateSearchHit
from core.services.high_court_registry import get_high_court, high_courts, is_default_bench
from core.tests.auth_helpers import token_for

Run = AdvocateSearchComplexRun

BOMBAY_BENCHES = {
    "1": "Appellate Side,Bombay",
    "3": "Bench at Aurangabad",
    "4": "Bench at Nagpur",
    "7": "Bombay High Court,Bench at Kolhapur",
    "5": "High court of Bombay at Goa",
    "2": "Original Side,Bombay",
    "6": "Special Court (TORTS) Bombay",
}


@pytest.fixture
def user_a():
    return User.objects.create_user(username="alice", password="alice-pass-123")


@pytest.fixture
def client_a(user_a):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token_for(user_a)}")
    return client


@pytest.fixture
def profile_a(user_a):
    return AdvocateSearchProfile.objects.create(
        owner=user_a, display_name="Rambabu Samalla", bar_codes=["TS/1234/2009"],
        name_forms=["Rambabu", "S Rambabu"], excluded_names=["T Rambabu"],
    )


@pytest.fixture
def v2_on(settings):
    settings.ADVOCATE_SEARCH_V2 = True


def record(case_no="1234", year="2020", type_name="WP", cino="TSHC010012342020", pet="A B", res="C D"):
    return {
        "orderurlpath": "", "case_no": case_no, "pet_name": pet, "case_no2": "x", "case_year": year,
        "res_name": res, "lpet_name": "", "lres_name": "", "cino": cino, "party_name1": pet,
        "party_name2": res, "type_name": type_name,
    }


def envelope(*records):
    return json.dumps({"con": [json.dumps(list(records))], "totRecords": len(records)})


# ---------------------------------------------------------------------------
# The request and its rows
# ---------------------------------------------------------------------------


class TestForm:
    def test_bar_code_search(self):
        form = hc_advocate_search_form(
            state_code="29", bench_code="1", bar_code="TS/1234/2009", status_filter="Pending", captcha="abc12"
        )
        assert form == {
            "court_code": "1", "state_code": "29", "court_complex_code": "1",
            "caseStatusSearchType": "CSAdvName", "captcha": "abc12", "f": "Pending",
            "search_type": "2", "adv_bar_state": "TS/1234/2009",
        }

    def test_name_search(self):
        form = hc_advocate_search_form(state_code="1", bench_code="4", advocate_name="Rambabu", captcha="x")
        assert form["search_type"] == "1" and form["advocate_name"] == "Rambabu" and form["court_code"] == "4"
        assert "adv_bar_state" not in form and form["f"] == "Both"

    def test_there_is_no_year_field_the_portal_returns_the_whole_book(self):
        form = hc_advocate_search_form(state_code="1", bench_code="1", bar_code="TS/1/2000", captcha="x")
        assert not {"rgyear", "year", "petres_name"} & set(form)


class TestRows:
    def test_a_row_becomes_a_hit_with_the_case_year(self):
        (hit,) = parse_hc_advocate_search([record()], bench_name="Principal Bench at Hyderabad", status="Pending")
        assert hit.case_number == "WP/1234/2020" and hit.case_year == 2020
        assert (hit.cnr_number, hit.petitioner, hit.respondent) == ("TSHC010012342020", "A B", "C D")
        assert (hit.court_name, hit.status) == ("Principal Bench at Hyderabad", "Pending")

    def test_no_advocate_is_listed_on_a_high_court_row(self):
        (hit,) = parse_hc_advocate_search([record()])
        assert hit.listed_advocate_name == "" and hit.listed_advocates == []

    def test_a_missing_or_odd_year_is_none_and_the_case_number_still_reads(self):
        hits = parse_hc_advocate_search([record(year=""), record(year="20")], bench_name="")
        assert [h.case_year for h in hits] == [None, None]
        assert hits[0].case_number == "WP/1234"

    def test_the_hit_dict_carries_the_year(self):
        (hit,) = parse_hc_advocate_search([record(year="2019")])
        assert hit.to_dict()["case_year"] == 2019
        assert AdvocateSearchHit(case_number="OS/1/2020").to_dict()["case_year"] is None  # a District row


# ---------------------------------------------------------------------------
# The provider, with the library's client faked
# ---------------------------------------------------------------------------


def _hc_client(raw=None, *, error=None, submissions=1):
    """A fake HCServicesClient whose retry helper builds the form once per
    submission, as the real one does, then answers `raw` (or raises `error`)."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    async def post(url, form_builder, *, max_retries=5):
        for _ in range(submissions):
            client.last_form = form_builder("cap01")
        if error is not None:
            raise error
        return MagicMock(text=raw)

    client._post_with_captcha_retry = post
    return client


class TestProvider:
    def _search(self, client, **kwargs):
        args = dict(advocate_name="", bar_code="TS/1234/2009", status_filter="Both")
        args.update(kwargs)
        with patch("core.services.court_data.ecourts_provider.HCServicesClient", return_value=client):
            provider = EcourtsProvider()
            return provider, provider.search_hc_by_advocate("telangana", "1", **args)

    def test_one_search_posts_our_form_and_parses_the_rows(self):
        client = _hc_client(envelope(record(), record(case_no="9", cino="TSHC010000092019", year="2019")), submissions=2)
        provider, hits = self._search(client, bench_name="Principal Bench at Hyderabad")
        assert [h.case_number for h in hits] == ["WP/1234/2020", "WP/9/2019"]
        assert hits[0].court_name == "Principal Bench at Hyderabad" and hits[0].status == ""
        assert provider.last_search_timing["attempts"] == 2  # form submissions, counted for real
        assert client.last_form["adv_bar_state"] == "TS/1234/2009" and client.last_form["state_code"] == "29"

    def test_status_asked_is_the_status_of_every_row(self):
        _, hits = self._search(_hc_client(envelope(record())), status_filter="Disposed")
        assert hits[0].status == "Disposed"

    def test_a_name_search(self):
        client = _hc_client(envelope(record()))
        self._search(client, advocate_name="Rambabu", bar_code="")
        assert client.last_form["search_type"] == "1" and client.last_form["advocate_name"] == "Rambabu"

    def test_a_wrong_captcha_to_the_end_is_a_captcha_failure(self):
        with pytest.raises(CaptchaSolveError):
            self._search(_hc_client(error=HCCaptchaError("wrong")))

    def test_a_portal_error_and_a_dropped_connection_are_portal_errors(self):
        with pytest.raises(CourtPortalError):
            self._search(_hc_client(error=HCServerError("Invalid Request")))
        with pytest.raises(CourtPortalError) as info:
            self._search(_hc_client(error=httpx.RemoteProtocolError("peer closed connection")))
        assert isinstance(info.value.__cause__, httpx.RemoteProtocolError)

    def test_both_or_neither_of_name_and_bar_code_is_refused(self):
        provider = EcourtsProvider()
        with pytest.raises(ValueError):
            provider.search_hc_by_advocate("telangana", "1", advocate_name="Ram", bar_code="TS/1/2000")
        with pytest.raises(ValueError):
            provider.search_hc_by_advocate("telangana", "1")

    def test_a_malformed_bar_code_or_unknown_court_is_refused_before_any_request(self):
        provider = EcourtsProvider()
        with patch("core.services.court_data.ecourts_provider.HCServicesClient") as client_cls:
            with pytest.raises(ValueError):
                provider.search_hc_by_advocate("telangana", "1", bar_code="1234")
            with pytest.raises(ValueError):
                provider.search_hc_by_advocate("atlantis", "1", bar_code="TS/1/2000")
        client_cls.assert_not_called()


# ---------------------------------------------------------------------------
# The registry and its endpoints
# ---------------------------------------------------------------------------


class TestRegistry:
    def test_twenty_five_courts_grouped_from_twenty_nine_entries(self):
        courts = high_courts()
        assert len(courts) == 25
        assert len({c["code"] for c in courts}) == 25

    def test_benches_come_from_the_registry_entries(self):
        bombay = get_high_court("bombay")
        assert sorted(b["name"] for b in bombay["registry_benches"]) == ["Aurangabad", "Goa", "Nagpur"]
        assert [b["name"] for b in get_high_court("allahabad")["registry_benches"]] == ["Lucknow"]
        assert get_high_court("telangana")["registry_benches"] == []

    def test_calcutta_is_the_one_unsupported_court_and_says_why(self):
        unsupported = [c for c in high_courts() if not c["supported"]]
        assert [c["code"] for c in unsupported] == ["calcutta"]
        assert "orders" in unsupported[0]["support_note"]

    def test_unknown_code(self):
        assert get_high_court("atlantis") is None

    def test_default_benches_are_the_principal_seat_and_the_registry_named_ones(self):
        registry = get_high_court("bombay")["registry_benches"]
        defaults = [code for code, name in BOMBAY_BENCHES.items() if is_default_bench(code, name, registry)]
        assert sorted(defaults) == ["1", "3", "4", "5"]  # Appellate Side, Aurangabad, Nagpur, Goa


@pytest.mark.django_db
class TestEndpoints:
    def test_list(self, client_a):
        data = client_a.get("/api/cases/high-courts/").data
        assert len(data["courts"]) == 25
        assert {"code", "name", "state_code", "registry_benches", "supported", "support_note"} <= set(data["courts"][0])

    def test_benches_are_the_portals_with_defaults_marked(self, client_a):
        provider = MagicMock()
        provider.list_benches.return_value = BOMBAY_BENCHES
        with patch("core.views.high_court_search.get_provider", return_value=provider):
            data = client_a.get("/api/cases/high-courts/bombay/benches/").data
        provider.list_benches.assert_called_once_with("bombay")
        assert len(data["benches"]) == 7
        assert {b["code"] for b in data["benches"] if b["default"]} == {"1", "3", "4", "5"}

    def test_a_portal_failure_is_a_502_not_a_500(self, client_a):
        provider = MagicMock()
        provider.list_benches.side_effect = CourtPortalError("down")
        with patch("core.views.high_court_search.get_provider", return_value=provider):
            resp = client_a.get("/api/cases/high-courts/bombay/benches/")
        assert resp.status_code == 502 and resp.data["code"] == "portal_error"

    def test_unknown_court_is_a_404(self, client_a):
        assert client_a.get("/api/cases/high-courts/atlantis/benches/").status_code == 404

    def test_authentication_required(self):
        assert APIClient().get("/api/cases/high-courts/").status_code == 401
        assert APIClient().get("/api/cases/high-courts/bombay/benches/").status_code == 401


# ---------------------------------------------------------------------------
# Starting a High Court search
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStart:
    def _start(self, client, profile, benches=BOMBAY_BENCHES, **body):
        payload = {"profile_id": profile.id, "court_type": "high_court", "hc_court_code": "bombay",
                   "bench_codes": ["1", "4"], **body}
        provider = MagicMock()
        provider.list_benches.return_value = benches
        with patch("core.views.advocate_search.get_provider", return_value=provider):
            return client.post("/api/cases/search-advocate/", payload, format="json")

    def test_off_by_default(self, client_a, profile_a):
        assert self._start(client_a, profile_a).data["code"] == "v2_disabled"

    def test_bar_code_search_one_job_for_the_chosen_benches(self, v2_on, client_a, profile_a):
        resp = self._start(client_a, profile_a, search_by="bar_code")
        assert resp.status_code == 202, resp.data
        assert "warning" not in resp.data
        params = ProcessingJob.objects.get(id=resp.data["job_id"]).payload
        assert params["court_type"] == "high_court" and params["hc_court_code"] == "bombay"
        assert params["bench_codes"] == ["1", "4"]
        assert params["bench_names"] == ["Appellate Side,Bombay", "Bench at Nagpur"]
        assert params["bar_code"] == "TS/1234/2009" and params["queries"] == [] and params["state_code"] == "1"
        assert params["mode"] == "high_court" and "districts_filter" not in params

    def test_a_name_search_is_allowed_but_warns_that_rows_cannot_be_told_apart(self, v2_on, client_a, profile_a):
        resp = self._start(client_a, profile_a, search_by="names")
        assert resp.status_code == 202
        assert "cannot be told apart" in resp.data["warning"]
        assert ProcessingJob.objects.get(id=resp.data["job_id"]).payload["queries"] == ["Rambabu"]

    def test_it_leaves_the_district_tabs_remembered_state_alone(self, v2_on, client_a, user_a, profile_a):
        AdvocateSearchPreference.objects.create(owner=user_a, court_type="district", hierarchy_config={"state_code": "29"})
        self._start(client_a, profile_a, search_by="bar_code")
        pref = AdvocateSearchPreference.objects.get(owner=user_a)
        assert pref.court_type == "district" and pref.hierarchy_config == {"state_code": "29"}

    @pytest.mark.parametrize(
        "body",
        [
            {"hc_court_code": "atlantis"},
            {"hc_court_code": ""},
            {"bench_codes": []},
            {"bench_codes": "1"},
            {"bench_codes": ["1", "99"]},  # not a bench the portal lists
            {"bench_codes": [str(i) for i in range(1, 10)]},  # more than eight
        ],
    )
    def test_bad_court_or_benches_are_refused(self, v2_on, client_a, profile_a, body):
        resp = self._start(client_a, profile_a, search_by="bar_code", **body)
        assert resp.status_code == 400
        assert not ProcessingJob.objects.filter(job_type="advocate_search").exists()

    def test_calcutta_is_refused_with_the_reason(self, v2_on, client_a, profile_a):
        resp = self._start(client_a, profile_a, search_by="bar_code", hc_court_code="calcutta")
        assert resp.status_code == 400 and resp.data["code"] == "high_court_unsupported"

    def test_a_bench_list_failure_is_a_502(self, v2_on, client_a, profile_a):
        provider = MagicMock()
        provider.list_benches.side_effect = CourtPortalError("down")
        with patch("core.views.advocate_search.get_provider", return_value=provider):
            resp = client_a.post(
                "/api/cases/search-advocate/",
                {"profile_id": profile_a.id, "court_type": "high_court", "hc_court_code": "bombay",
                 "bench_codes": ["1"], "search_by": "bar_code"},
                format="json",
            )
        assert resp.status_code == 502

    def test_a_district_search_needs_no_court_code_and_still_needs_a_state(self, v2_on, client_a, profile_a):
        assert client_a.post("/api/cases/search-advocate/", {"profile_id": profile_a.id}, format="json").status_code == 400

    def test_unknown_court_type(self, v2_on, client_a, profile_a):
        resp = client_a.post(
            "/api/cases/search-advocate/", {"profile_id": profile_a.id, "court_type": "supreme"}, format="json"
        )
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# The worker: a bench is the unit, the High Court itself is the "district"
# ---------------------------------------------------------------------------


class FakeHCProvider:
    """Only what a High Court run may call: no list_districts, no list_complexes."""

    def __init__(self, script):
        self.script = list(script)
        self.calls: list[dict] = []
        self.last_search_timing: dict = {}

    def advocate_search_session(self):  # the District portal's reusable session: must never be used here
        raise AssertionError("a High Court bench must not use the District Courts session")

    def search_hc_by_advocate(self, hc_court_code, bench_code, *, advocate_name="", bar_code="", status_filter="Both", bench_name=""):
        self.calls.append(
            {"court": hc_court_code, "bench": bench_code, "name": advocate_name, "bar": bar_code,
             "status": status_filter, "bench_name": bench_name}
        )
        outcome, attempts = self.script.pop(0)
        self.last_search_timing = {"attempts": attempts}
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def hc_hit(cnr, year=2020, advocate=""):
    return AdvocateSearchHit(
        case_number=f"WP/{cnr[-2:]}/{year}", cnr_number=cnr, case_year=year, petitioner="A", respondent="B",
        listed_advocate_name=advocate, listed_advocates=[advocate] if advocate else [],
    )


def hc_job(user, profile, **overrides):
    params = {
        "v2": True, "court_type": "high_court", "hc_court_code": "bombay", "hc_court_name": "Bombay High Court",
        "state_code": "1", "bench_codes": ["1", "4"], "bench_names": ["Appellate Side,Bombay", "Bench at Nagpur"],
        "search_by": "bar_code", "queries": [], "bar_code": "TS/1234/2009", "advocate_name": "",
        "status_filter": "Both", "profile_id": profile.id, "mode": "high_court",
    }
    params.update(overrides)
    return ProcessingJob.enqueue_advocate_search(user, params)


def run_hc(job, provider, **kwargs):
    with patch("core.services.advocate_search_v2.get_provider", return_value=provider), \
            patch("core.services.advocate_search_v2.time.sleep"):
        run_advocate_search(job, **kwargs)
    job.refresh_from_db()


@pytest.mark.django_db
class TestWorker:
    def test_one_request_per_bench_one_run_row_per_bench(self, user_a, profile_a, settings):
        settings.ADVOCATE_SEARCH_REUSE_SESSION = True  # must not matter to a High Court
        job = hc_job(user_a, profile_a)
        provider = FakeHCProvider([([hc_hit("CNR01", 2018), hc_hit("CNR02", 2022)], 1), ([hc_hit("CNR03")], 2)])
        run_hc(job, provider)

        assert [(c["court"], c["bench"], c["bar"], c["name"]) for c in provider.calls] == [
            ("bombay", "1", "TS/1234/2009", ""), ("bombay", "4", "TS/1234/2009", ""),
        ]  # sequential, one each
        assert provider.calls[1]["bench_name"] == "Bench at Nagpur"
        runs = list(Run.objects.filter(job=job).order_by("id"))
        assert [(r.dist_code, r.dist_name, r.complex_code, r.complex_name, r.status) for r in runs] == [
            ("bombay", "Bombay High Court", "1", "Appellate Side,Bombay", "done"),
            ("bombay", "Bombay High Court", "4", "Bench at Nagpur", "done"),
        ]
        assert [r.attempts for r in runs] == [1, 2] and [r.raw_count for r in runs] == [2, 1]
        assert job.payload["districts_status"]["bombay"]["status"] == "success"

    def test_rows_carry_the_case_year_for_the_clients_year_range(self, user_a, profile_a):
        job = hc_job(user_a, profile_a)
        run_hc(job, FakeHCProvider([([hc_hit("CNR01", 2018), hc_hit("CNR02", 2022)], 1), ([], 1)]))
        rows = {r["cnr_number"]: r for r in job.payload["results"]}
        assert (rows["CNR01"]["case_year"], rows["CNR02"]["case_year"]) == (2018, 2022)
        assert rows["CNR01"]["complex_name"] == "Appellate Side,Bombay"
        assert rows["CNR01"]["match_source"] == "bar_code"  # the portal matched the bar number itself

    def test_a_bench_that_fails_is_isolated_and_says_why(self, user_a, profile_a):
        job = hc_job(user_a, profile_a)
        dropped = CourtPortalError("High Court portal error")
        dropped.__cause__ = httpx.RemoteProtocolError("peer closed connection")
        run_hc(job, FakeHCProvider([(dropped, 3), ([hc_hit("CNR03")], 1)]))
        failed, done = Run.objects.filter(job=job).order_by("id")
        assert (failed.status, failed.last_error_code, failed.attempts) == ("failed", "portal_disconnect", 3)
        assert done.status == "done"
        assert [r["cnr_number"] for r in job.payload["results"]] == ["CNR03"]
        assert job.payload["districts_status"]["bombay"]["status"] == "partial"

    def test_a_name_search_runs_each_query_on_each_bench_and_labels_every_row_check(self, user_a, profile_a):
        from core.services.advocate_results import annotate_rows

        job = hc_job(user_a, profile_a, search_by="names", queries=["Rambabu"], bar_code="", bench_codes=["1"],
                     bench_names=["Appellate Side,Bombay"])
        provider = FakeHCProvider([([hc_hit("CNR01")], 1)])
        run_hc(job, provider)
        assert provider.calls == [
            {"court": "bombay", "bench": "1", "name": "Rambabu", "bar": "", "status": "Both", "bench_name": "Appellate Side,Bombay"}
        ]
        labelled, counts = annotate_rows(job.payload["results"], profile_a)
        assert counts["check"] == 1 and labelled[0]["match_status"] == "check"  # no advocate on the row to judge by

    def test_a_failed_bench_can_be_retried_alone_and_merges_in(self, v2_on, user_a, profile_a):
        job = hc_job(user_a, profile_a)
        run_hc(job, FakeHCProvider([(CaptchaSolveError("x"), 6), ([hc_hit("CNR03")], 1)]))
        ProcessingJob.objects.filter(pk=job.pk).update(status="succeeded")
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token_for(user_a)}")
        resp = client.post(f"/api/cases/search-advocate/{job.id}/retry/", {"only_failed": True}, format="json")
        assert resp.status_code == 202 and resp.data["courts"] == 1
        child = ProcessingJob.objects.get(id=resp.data["job_id"])

        provider = FakeHCProvider([([hc_hit("CNR01", 2019)], 1)])
        with patch("core.services.advocate_search_v2.get_provider", return_value=provider), \
                patch("core.services.advocate_search_v2.time.sleep"):
            run_retry(child)
        assert [(c["bench"], c["court"]) for c in provider.calls] == [("1", "bombay")]  # only the failed bench
        job.refresh_from_db()
        assert sorted(r["cnr_number"] for r in job.payload["results"]) == ["CNR01", "CNR03"]
        assert {r.status for r in Run.objects.filter(job=job)} == {"done"}

    def test_the_district_path_is_untouched(self, user_a, profile_a):
        """A High Court job never calls the District provider methods; a district job
        never calls the High Court one."""
        job = ProcessingJob.enqueue_advocate_search(
            user_a,
            {"v2": True, "state_code": "29", "court_type": "district", "queries": ["Rambabu"], "bar_code": "",
             "status_filter": "Both", "profile_id": profile_a.id},
        )
        provider = MagicMock()
        provider.list_districts.return_value = {"1": "Adilabad"}
        provider.list_complexes.return_value = {"c1@e1@N": "Court"}
        provider.search_by_advocate.return_value = []
        with patch("core.services.advocate_search_v2.get_provider", return_value=provider), \
                patch("core.services.advocate_search_v2.time.sleep"):
            run_advocate_search(job)
        provider.search_by_advocate.assert_called_once()
        provider.search_hc_by_advocate.assert_not_called()
