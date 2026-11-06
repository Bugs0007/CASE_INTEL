"""Advocate search speed work: worker lanes, the timing summary, Quick search,
the multi-district payload, live progress counters, and the two provider flags
(which default to OFF).

No live portal: the court client is a mock, the provider a MagicMock, the
clock is whatever the test patches.
"""

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bharat_courts import CaseInfo
from bharat_courts.districtcourts.parser import CaptchaError as DistrictCaptchaError
from bharat_courts.districtcourts.parser import ServerError as DistrictServerError
from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from core.management.commands.process_jobs import (
    LANES,
    PORTAL_JOB_TYPES,
    SEARCH_JOB_TYPES,
    Command,
)
from core.models import (
    ActivityLog,
    AdvocateSearchPreference,
    Case,
    Document,
    ProcessingJob,
)
from core.services.advocate_quick_search import (
    MAX_REMEMBERED_QUERIES,
    query_key,
    quick_search_summary,
    remember_search,
    remembered_complexes,
)
from core.services.advocate_search import run_advocate_search
from core.services.court_data import CourtPortalError
from core.services.court_data.ecourts_provider import (
    ADVOCATE_SEARCH_MAX_ATTEMPTS,
    EcourtsProvider,
    _AdvocateSearchSession,
)
from core.tests.auth_helpers import token_for

HIERARCHY = {"state_code": "1", "dist_code": "26", "court_complex_code": "1010307", "est_code": "2"}


@pytest.fixture
def user_a(db):
    return User.objects.create_user(username="speed-alice", password="alice-pass-123")


@pytest.fixture
def user_b(db):
    return User.objects.create_user(username="speed-bob", password="bob-pass-123")


def _client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token_for(user)}")
    return client


def _ci(cnr: str) -> CaseInfo:
    return CaseInfo(
        case_number="123/2024", case_type="Civil Suit", cnr_number=cnr,
        petitioner="Suresh Kumar", respondent="State Bank", status="Pending", court_name="Civil Court",
    )


# ---------------------------------------------------------------------------
# C1: worker lanes
# ---------------------------------------------------------------------------


def _job(owner, job_type, *, document_type="other", case=None, minutes=0):
    document = None
    if job_type == "document":
        document = Document.objects.create(
            owner=owner, filename="f.pdf", file_path=f"documents/{job_type}{minutes}{document_type}.pdf",
            file_type="pdf", file_size=1, document_type=document_type, processing_status="pending",
        )
    job = ProcessingJob.objects.create(owner=owner, job_type=job_type, document=document, case=case)
    ProcessingJob.objects.filter(id=job.id).update(
        created_at=timezone.now() - timezone.timedelta(days=1) + timezone.timedelta(minutes=minutes)
    )
    return job


@pytest.mark.django_db
class TestSearchAndPortalLanes:
    def test_every_job_type_belongs_to_exactly_one_of_the_two_lanes(self):
        every_type = {value for value, _label in ProcessingJob.JOB_TYPE_CHOICES}
        assert set(SEARCH_JOB_TYPES) | set(PORTAL_JOB_TYPES) == every_type
        assert set(SEARCH_JOB_TYPES) & set(PORTAL_JOB_TYPES) == set()
        assert set(SEARCH_JOB_TYPES) == {"advocate_search", "advocate_import"}

    def test_the_search_lane_claims_only_search_and_import(self, user_a):
        case = Case.objects.create(owner=user_a, case_number="OS/1/2026", title="t", client_name="")
        for n, kind in enumerate(("order_sync", "tracking_refresh", "case_briefing")):
            _job(user_a, kind, case=case, minutes=n)
        _job(user_a, "document", minutes=5)
        search = _job(user_a, "advocate_search", minutes=6)
        imp = _job(user_a, "advocate_import", minutes=7)

        claimed = [Command()._claim_next_job("search").id for _ in range(2)]

        assert claimed == [search.id, imp.id]  # same tier: oldest first
        assert Command()._claim_next_job("search") is None

    def test_the_portal_lane_never_claims_search_or_import(self, user_a):
        _job(user_a, "advocate_search", minutes=0)
        _job(user_a, "advocate_import", minutes=1)
        assert Command()._claim_next_job("portal") is None

    def test_the_portal_lane_keeps_the_priority_order(self, user_a):
        case = Case.objects.create(owner=user_a, case_number="OS/1/2026", title="t", client_name="")
        # Oldest first: a refresh-all, an order sync, three fetched order PDFs...
        bulk = _job(user_a, "tracking_refresh", minutes=0)
        order_sync = _job(user_a, "order_sync", case=case, minutes=1)
        fetched = [_job(user_a, "document", document_type="court_order", minutes=2 + n) for n in range(2)]
        # ...a search nobody in this lane may touch, and the advocate's own upload and briefing.
        _job(user_a, "advocate_search", minutes=5)
        upload = _job(user_a, "document", minutes=6)
        briefing = _job(user_a, "case_briefing", case=case, minutes=7)

        claimed = [Command()._claim_next_job("portal").id for _ in range(6)]

        assert set(claimed[:2]) == {upload.id, briefing.id}  # the user's own work first
        assert claimed[2:4] == [j.id for j in fetched]  # then fetched order PDFs
        assert set(claimed[4:]) == {bulk.id, order_sync.id}  # then the long portal jobs
        assert Command()._claim_next_job("portal") is None

    def test_the_default_lane_still_claims_everything(self, user_a):
        search = _job(user_a, "advocate_search")
        assert Command()._claim_next_job().id == search.id

    def test_lane_choices_and_the_command_reports_them(self, user_a):
        assert LANES == ("all", "interactive", "search", "portal")
        for lane in ("search", "portal"):
            from io import StringIO

            out = StringIO()
            with patch.object(Command, "_process_job"), patch(
                "core.management.commands.process_jobs.close_old_connections"
            ):
                call_command("process_jobs", "--once", "--lane", lane, "--max-jobs", "0", "--max-rss-mb", "0", stdout=out)
            assert f"lane={lane}" in out.getvalue()


# ---------------------------------------------------------------------------
# C2: timing logs and the summary
# ---------------------------------------------------------------------------


def _search_job(user, **overrides):
    params = {
        "state_code": "1", "court_type": "district",
        "advocate_name": "Zebulon Quillfeather", "bar_code": "", "status_filter": "Both",
    }
    params.update(overrides)
    return ProcessingJob.enqueue_advocate_search(user, params)


class _Provider:
    """list_districts/list_complexes from dicts; search_by_advocate plays a
    script of (result_or_exception, per-step timing) per call, exposing the
    timing as `last_search_timing` the way EcourtsProvider does."""

    def __init__(self, districts, complexes, script):
        self.districts = districts
        self.complexes = complexes
        self.script = list(script)
        self.calls = []
        self.last_search_timing = None

    def list_districts(self, state_code):
        return self.districts

    def list_complexes(self, state_code, dist_code):
        return self.complexes[dist_code]

    def search_by_advocate(self, hierarchy, *, advocate_name="", bar_code="", status_filter="Both"):
        self.calls.append(hierarchy["court_complex_code"] + "/" + hierarchy["est_code"])
        outcome, timing = self.script.pop(0)
        self.last_search_timing = timing
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _timing(attempts=1, init=1.0, setup=0.5, captcha=1.5, submit=0.5):
    return {"init_s": init, "setup_s": setup, "captcha_s": captcha, "submit_s": submit, "attempts": attempts}


def _run(job, provider, **patches):
    with patch("core.services.advocate_search.get_provider", return_value=provider), \
         patch("core.services.advocate_search.time.sleep"):
        run_advocate_search(job)
    job.refresh_from_db()


@pytest.mark.django_db
class TestTimingSummary:
    def _provider(self):
        return _Provider(
            {"1": "Dist A"},
            {"1": {"c1@e1@N": "Complex 1", "c2@e2@N": "Complex 2", "c3@e3@N": "Complex 3"}},
            [
                ([_ci("CNR1")], _timing(attempts=1)),
                (CourtPortalError("District Courts advocate search failed after 6 attempts: Invalid Captcha"),
                 _timing(attempts=6, init=6.0, setup=3.0, captcha=9.0, submit=3.0)),
                ([], _timing(attempts=3, init=3.0, setup=1.5, captcha=4.5, submit=1.5)),
            ],
        )

    def test_the_payload_and_activity_log_carry_a_summary(self, user_a):
        job = _search_job(user_a)
        _run(job, self._provider())

        timing = job.payload["timing"]
        assert timing["complexes_searched"] == 3
        assert (timing["complexes_ok"], timing["complexes_failed"]) == (2, 1)
        assert timing["attempt_histogram"] == {"1": 1, "2": 0, "3+": 2}
        assert timing["failure_classes"] == {"captcha": 1}
        assert timing["step_seconds"]["init_s"] == pytest.approx(10.0, abs=0.1)
        assert timing["step_seconds"]["captcha_s"] == pytest.approx(15.0, abs=0.1)
        assert timing["avg_seconds_per_complex"] is not None
        assert timing["total_seconds"] >= 0
        assert timing["reuse_session"] is False
        assert "captcha_only_retry" not in timing

        entry = ActivityLog.objects.get(owner=user_a, activity_type="advocate_search")
        assert "Timing:" in entry.description
        assert "3 court complex(es)" in entry.description
        assert "Attempts: 1x 1, 2x 0, 3+ 2." in entry.description
        assert "Failures: captcha 1." in entry.description
        assert "1 case(s) found" in entry.description  # the existing sentence is still there

    def test_the_slowest_part_is_named_per_complex_in_the_log_without_any_names(self, user_a):
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record.getMessage())

        logger = logging.getLogger("core.services.advocate_search")
        handler = Capture(level=logging.INFO)
        previous = logger.level
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        try:
            job = _search_job(user_a)
            _run(job, self._provider())
        finally:
            logger.removeHandler(handler)
            logger.setLevel(previous)

        lines = [m for m in records if m.startswith("Advocate search timing")]
        assert len(lines) == 3
        assert "dist=1 complex=c1" in lines[0]
        assert "init=1.00s setup=0.50s captcha=1.50s submit=0.50s" in lines[0]
        assert "attempts=6 outcome=captcha" in lines[1]
        everything = "\n".join(records)
        for private in ("Zebulon", "Quillfeather", "Suresh Kumar", "State Bank", "Dist A", "Complex 1"):
            assert private not in everything

    def test_a_provider_that_reports_no_timing_still_gets_a_summary(self, user_a):
        provider = MagicMock()
        provider.list_districts.return_value = {"1": "Dist A"}
        provider.list_complexes.return_value = {"c1@e1@N": "Complex 1"}
        provider.search_by_advocate.return_value = [_ci("CNR1")]
        job = _search_job(user_a)
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
             patch("core.services.advocate_search.parse_complex_code", return_value=("cc", "ec")), \
             patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job)
        job.refresh_from_db()
        assert job.payload["timing"]["complexes_searched"] == 1
        assert job.payload["timing"]["attempt_histogram"] == {"1": 0, "2": 0, "3+": 0}

    def test_a_cancelled_search_still_leaves_its_timing(self, user_a):
        from core.services.advocate_search import AdvocateSearchCancelled

        job = _search_job(user_a)
        ProcessingJob.objects.filter(id=job.id).update(cancel_requested=True)
        with pytest.raises(AdvocateSearchCancelled):
            _run(job, self._provider())
        job.refresh_from_db()
        assert "timing" in job.payload
        assert "Timing:" in ActivityLog.objects.get(owner=user_a).description


# ---------------------------------------------------------------------------
# C3: live progress
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLiveProgress:
    def test_counters_and_results_are_written_after_every_complex(self, user_a):
        job = _search_job(user_a)
        seen = []

        provider = _Provider(
            {"1": "Dist A", "2": "Dist B"},
            {
                "1": {"c1@e1@N": "C1", "c2@e2@N": "C2"},
                "2": {"c3@e3@N": "C3"},
            },
            [([_ci("CNR1")], _timing()), ([_ci("CNR2")], _timing()), ([], _timing())],
        )
        real = provider.search_by_advocate

        def snooping(*args, **kwargs):
            payload = ProcessingJob.objects.get(id=job.id).payload
            seen.append((
                payload.get("complexes_done"), payload.get("complexes_total_known"),
                payload.get("complexes_searched"), sorted(r["cnr_number"] for r in payload.get("results", [])),
                payload.get("current_district"),
            ))
            return real(*args, **kwargs)

        provider.search_by_advocate = snooping
        _run(job, provider)

        # Read just before each complex is searched: what the page would show.
        assert seen == [
            (0, 2, 0, [], "Dist A"),                    # Dist A listed: 2 complexes, none done
            (1, 2, 1, ["CNR1"], "Dist A"),              # first done, its case already visible
            (2, 3, 2, ["CNR1", "CNR2"], "Dist B"),      # Dist B listed: the known total grows to 3
        ]
        assert job.payload["complexes_done"] == 3
        assert job.payload["complexes_total_known"] == 3
        assert job.payload["complexes_searched"] == 3
        assert sorted(r["cnr_number"] for r in job.payload["results"]) == ["CNR1", "CNR2"]

    def test_a_failed_complex_counts_as_done_but_not_as_searched(self, user_a):
        job = _search_job(user_a)
        provider = _Provider(
            {"1": "Dist A"}, {"1": {"c1@e1@N": "C1", "c2@e2@N": "C2"}},
            [(CourtPortalError("down"), _timing(attempts=6)), ([], _timing())],
        )
        _run(job, provider)
        assert job.payload["complexes_done"] == 2
        assert job.payload["complexes_searched"] == 1

    def test_the_status_endpoint_carries_the_counters(self, user_a):
        job = _search_job(user_a)
        ProcessingJob.objects.filter(id=job.id).update(
            status="running",
            started_at=timezone.now(),
            payload={**job.payload, "complexes_done": 4, "complexes_total_known": 9,
                     "current_district": "Dist A", "mode": "quick", "districts_status": {}},
        )
        data = _client(user_a).get(f"/api/cases/search-advocate/{job.id}/").data
        assert (data["complexes_done"], data["complexes_total_known"]) == (4, 9)
        assert data["current_district"] == "Dist A"
        assert data["mode"] == "quick"
        assert data["created_at"] is not None and data["started_at"] is not None


# ---------------------------------------------------------------------------
# C3: multi-district payload
# ---------------------------------------------------------------------------


def _post(client, **body):
    payload = {"name_or_bar_code": "Zebulon Quillfeather", "court_type": "district", "state_code": "29"}
    payload.update(body)
    return client.post("/api/cases/search-advocate/", payload, format="json")


@pytest.mark.django_db
class TestMultiDistrictSearch:
    def test_dist_codes_become_the_districts_filter(self, user_a):
        resp = _post(_client(user_a), dist_codes=["3", "5", "3"])
        assert resp.status_code == 202
        payload = ProcessingJob.objects.get(id=resp.data["job_id"]).payload
        assert payload["districts_filter"] == ["3", "5"]  # de-duplicated, order kept
        assert payload["mode"] == "districts"

    def test_the_older_single_dist_code_still_works(self, user_a):
        resp = _post(_client(user_a), dist_code="26")
        assert ProcessingJob.objects.get(id=resp.data["job_id"]).payload["districts_filter"] == ["26"]

    def test_no_districts_means_the_whole_state(self, user_a):
        resp = _post(_client(user_a))
        payload = ProcessingJob.objects.get(id=resp.data["job_id"]).payload
        assert "districts_filter" not in payload and payload["mode"] == "state"

    def test_an_empty_list_is_the_whole_state(self, user_a):
        resp = _post(_client(user_a), dist_codes=[])
        payload = ProcessingJob.objects.get(id=resp.data["job_id"]).payload
        assert "districts_filter" not in payload

    @pytest.mark.parametrize("bad", ["3", {"a": 1}, [""], [None], [["3"]], [True]])
    def test_a_malformed_dist_codes_is_rejected(self, user_a, bad):
        resp = _post(_client(user_a), dist_codes=bad)
        assert resp.status_code == 400
        assert not ProcessingJob.objects.filter(job_type="advocate_search").exists()

    def test_too_many_districts_is_rejected(self, user_a):
        assert _post(_client(user_a), dist_codes=[str(n) for n in range(101)]).status_code == 400

    def test_the_chosen_districts_are_saved_and_come_back(self, user_a):
        client = _client(user_a)
        _post(client, dist_codes=["3", "5"])
        pref = AdvocateSearchPreference.objects.get(owner=user_a)
        assert pref.hierarchy_config == {"state_code": "29", "dist_codes": ["3", "5"]}
        got = client.get("/api/cases/search-advocate/preference/").data
        assert got["hierarchy_config"] == {"state_code": "29", "dist_codes": ["3", "5"]}

    def test_searching_all_districts_forgets_the_saved_choice(self, user_a):
        client = _client(user_a)
        ProcessingJob.objects.all().delete()
        _post(client, dist_codes=["3"])
        ProcessingJob.objects.filter(job_type="advocate_search").update(status="succeeded")
        _post(client)
        assert AdvocateSearchPreference.objects.get(owner=user_a).hierarchy_config == {"state_code": "29"}


# ---------------------------------------------------------------------------
# C3: Quick search
# ---------------------------------------------------------------------------


def _hit(dist, cplx, cases, est="e1"):
    return {"dist_code": dist, "dist_name": f"D{dist}", "complex_code": cplx, "est_code": est,
            "complex_name": f"C{cplx}", "cases": cases}


NAME = "Zebulon Quillfeather"


@pytest.mark.django_db
class TestQuickSearchHistory:
    def test_only_complexes_with_cases_are_remembered(self, user_a):
        remember_search(user_a, advocate_name=NAME, bar_code="", state_code="29",
                        searched_ok=[_hit("1", "10", 3), _hit("1", "11", 0), _hit("2", "20", 1)])
        got = remembered_complexes(user_a, NAME, "", "29")
        assert sorted((c["dist_code"], c["complex_code"], c["cases"]) for c in got) == [("1", "10", 3), ("2", "20", 1)]
        summary = quick_search_summary(user_a, NAME, "", "29")
        assert (summary["complexes"], summary["districts"]) == (2, 2)
        assert summary["updated_at"]

    def test_the_key_ignores_case_and_spacing_and_is_per_state(self, user_a):
        assert query_key("  Zebulon   QUILLFEATHER ", "", "29") == query_key(NAME.lower(), "", "29")
        assert query_key(NAME, "", "29") != query_key(NAME, "", "1")
        remember_search(user_a, advocate_name=NAME, bar_code="", state_code="29", searched_ok=[_hit("1", "10", 1)])
        assert remembered_complexes(user_a, "zebulon quillfeather", "", "29")
        assert remembered_complexes(user_a, NAME, "", "1") == []

    def test_a_bar_code_is_its_own_advocate(self, user_a):
        remember_search(user_a, advocate_name="", bar_code="KAR/123/2015", state_code="29", searched_ok=[_hit("1", "10", 2)])
        assert remembered_complexes(user_a, "", "kar/123/2015", "29")
        assert remembered_complexes(user_a, NAME, "", "29") == []

    def test_a_later_search_replaces_only_the_complexes_it_read(self, user_a):
        remember_search(user_a, advocate_name=NAME, bar_code="", state_code="29",
                        searched_ok=[_hit("1", "10", 3), _hit("1", "11", 2), _hit("2", "20", 1)])
        # Next search read 10 (now empty), 11 (more cases) and a new complex 30; it never reached 2/20.
        remember_search(user_a, advocate_name=NAME, bar_code="", state_code="29",
                        searched_ok=[_hit("1", "10", 0), _hit("1", "11", 5), _hit("3", "30", 1)])
        got = {(c["dist_code"], c["complex_code"]): c["cases"] for c in remembered_complexes(user_a, NAME, "", "29")}
        assert got == {("1", "11"): 5, ("2", "20"): 1, ("3", "30"): 1}

    def test_nothing_remembered_means_no_summary(self, user_a):
        assert quick_search_summary(user_a, NAME, "", "29") is None
        remember_search(user_a, advocate_name=NAME, bar_code="", state_code="29", searched_ok=[_hit("1", "10", 0)])
        assert quick_search_summary(user_a, NAME, "", "29") is None

    def test_only_the_most_recent_queries_are_kept(self, user_a):
        for n in range(MAX_REMEMBERED_QUERIES + 3):
            remember_search(user_a, advocate_name=f"Advocate Number{n}", bar_code="", state_code="29",
                            searched_ok=[_hit("1", "10", 1)])
        quick = AdvocateSearchPreference.objects.get(owner=user_a).hierarchy_config["quick"]
        assert len(quick) == MAX_REMEMBERED_QUERIES
        assert query_key("Advocate Number0", "", "29") not in quick
        assert query_key(f"Advocate Number{MAX_REMEMBERED_QUERIES + 2}", "", "29") in quick

    def test_it_is_one_owners_history_only(self, user_a, user_b):
        remember_search(user_a, advocate_name=NAME, bar_code="", state_code="29", searched_ok=[_hit("1", "10", 3)])
        assert remembered_complexes(user_b, NAME, "", "29") == []
        assert quick_search_summary(user_b, NAME, "", "29") is None


@pytest.mark.django_db
class TestQuickSearchSelection:
    def _remember(self, user):
        remember_search(user, advocate_name=NAME, bar_code="", state_code="29",
                        searched_ok=[_hit("1", "10", 3), _hit("2", "20", 1)])

    def test_a_finished_search_records_the_complexes_that_returned_cases(self, user_a):
        job = _search_job(user_a, state_code="29")
        provider = _Provider(
            {"1": "Dist A", "2": "Dist B"},
            {"1": {"c1@e1@N": "C1", "c2@e2@N": "C2"}, "2": {"c3@e3@N": "C3"}},
            [([_ci("CNR1")], _timing()), ([], _timing()), (CourtPortalError("down"), _timing(attempts=6))],
        )
        _run(job, provider)

        got = remembered_complexes(user_a, NAME, "", "29")
        assert [(c["dist_code"], c["complex_code"], c["est_code"], c["cases"]) for c in got] == [("1", "c1", "e1", 1)]

    def test_a_cancelled_search_remembers_nothing(self, user_a):
        from core.services.advocate_search import AdvocateSearchCancelled

        job = _search_job(user_a, state_code="29")
        ProcessingJob.objects.filter(id=job.id).update(cancel_requested=True)
        provider = _Provider({"1": "Dist A"}, {"1": {"c1@e1@N": "C1"}}, [([_ci("CNR1")], _timing())])
        with pytest.raises(AdvocateSearchCancelled):
            _run(job, provider)
        assert remembered_complexes(user_a, NAME, "", "29") == []

    def test_a_quick_search_visits_only_the_remembered_complexes(self, user_a):
        job = _search_job(user_a, state_code="29", complexes_filter=[
            {"dist_code": "1", "complex_code": "c2", "est_code": "e2"},
            {"dist_code": "2", "complex_code": "c3", "est_code": "e3"},
        ])
        provider = _Provider(
            {"1": "Dist A", "2": "Dist B", "3": "Dist C"},
            {
                "1": {"c1@e1@N": "C1", "c2@e2@N": "C2"},
                "2": {"c3@e3@N": "C3", "c4@e4@N": "C4"},
                "3": {"c5@e5@N": "C5"},
            },
            [([_ci("CNR2")], _timing()), ([_ci("CNR3")], _timing())],
        )
        _run(job, provider)

        assert provider.calls == ["c2/e2", "c3/e3"]  # nothing else, and Dist C is never listed
        assert job.payload["districts_total"] == 2
        assert job.payload["districts_status"]["1"]["complexes_total"] == 1
        assert sorted(r["cnr_number"] for r in job.payload["results"]) == ["CNR2", "CNR3"]

    def test_the_view_turns_the_history_into_a_complexes_filter(self, user_a):
        self._remember(user_a)
        resp = _post(_client(user_a), mode="quick", name_or_bar_code="  zebulon QUILLFEATHER")
        assert resp.status_code == 202
        payload = ProcessingJob.objects.get(id=resp.data["job_id"]).payload
        assert payload["mode"] == "quick"
        assert sorted((c["dist_code"], c["complex_code"], c["est_code"]) for c in payload["complexes_filter"]) == [
            ("1", "10", "e1"), ("2", "20", "e1"),
        ]
        assert "districts_filter" not in payload

    def test_quick_without_history_is_refused(self, user_a):
        resp = _post(_client(user_a), mode="quick")
        assert resp.status_code == 400
        assert resp.data["code"] == "no_quick_history"
        assert not ProcessingJob.objects.filter(job_type="advocate_search").exists()

    def test_another_owners_history_is_never_used(self, user_a, user_b):
        self._remember(user_b)
        resp = _post(_client(user_a), mode="quick")
        assert resp.status_code == 400 and resp.data["code"] == "no_quick_history"

    def test_an_unknown_mode_is_rejected(self, user_a):
        assert _post(_client(user_a), mode="turbo").status_code == 400

    def test_a_quick_search_keeps_the_saved_districts_and_the_history(self, user_a):
        client = _client(user_a)
        _post(client, dist_codes=["3"])
        ProcessingJob.objects.filter(job_type="advocate_search").update(status="succeeded")
        self._remember(user_a)
        _post(client, mode="quick")
        config = AdvocateSearchPreference.objects.get(owner=user_a).hierarchy_config
        assert config["dist_codes"] == ["3"]
        assert query_key(NAME, "", "29") in config["quick"]

    def test_retrying_a_quick_search_stays_inside_its_remembered_complexes(self, user_a):
        original = _search_job(user_a, state_code="29", mode="quick", complexes_filter=[
            {"dist_code": "1", "complex_code": "10", "est_code": "e1"},
            {"dist_code": "2", "complex_code": "20", "est_code": "e1"},
            {"dist_code": "2", "complex_code": "21", "est_code": "e1"},
        ])
        ProcessingJob.objects.filter(id=original.id).update(
            status="succeeded",
            payload={**original.payload, "results": [], "districts_status": {
                "1": {"name": "A", "status": "success", "complexes_total": 1, "complexes_ok": 1, "complexes_failed": 0},
                "2": {"name": "B", "status": "partial", "complexes_total": 2, "complexes_ok": 1, "complexes_failed": 1},
            }},
        )
        resp = _client(user_a).post(f"/api/cases/search-advocate/{original.id}/retry-failed/")
        assert resp.status_code == 202
        payload = ProcessingJob.objects.get(id=resp.data["job_id"]).payload
        assert payload["districts_filter"] == ["2"]
        assert payload["mode"] == "quick"
        assert [(c["dist_code"], c["complex_code"]) for c in payload["complexes_filter"]] == [("2", "20"), ("2", "21")]

    def test_retrying_an_ordinary_search_is_unchanged(self, user_a):
        original = _search_job(user_a)
        ProcessingJob.objects.filter(id=original.id).update(
            status="succeeded",
            payload={**original.payload, "results": [], "districts_status": {
                "1": {"name": "A", "status": "failed", "complexes_total": 0, "complexes_ok": 0, "complexes_failed": 0},
            }},
        )
        resp = _client(user_a).post(f"/api/cases/search-advocate/{original.id}/retry-failed/")
        payload = ProcessingJob.objects.get(id=resp.data["job_id"]).payload
        assert "complexes_filter" not in payload and payload["districts_filter"] == ["1"]

    def test_the_preference_endpoint_reports_the_quick_search_for_a_query(self, user_a):
        self._remember(user_a)
        client = _client(user_a)
        ProcessingJob.objects.all().delete()
        _post(client, name_or_bar_code="Someone Else")  # makes the saved state 29
        base = "/api/cases/search-advocate/preference/"

        quick = client.get(base, {"name_or_bar_code": NAME, "state_code": "29"}).data
        assert quick["quick_search"]["complexes"] == 2 and quick["quick_search"]["districts"] == 2
        assert "quick" not in quick["hierarchy_config"]  # the history itself is not sent

        assert client.get(base, {"name_or_bar_code": "Nobody Known", "state_code": "29"}).data["quick_search"] is None
        assert client.get(base, {"name_or_bar_code": NAME, "state_code": "1"}).data["quick_search"] is None
        assert client.get(base).data["quick_search"] is None
        assert client.get(base, {"name_or_bar_code": "ab"}).data["quick_search"] is None

    def test_one_owner_never_sees_anothers_quick_search_summary(self, user_a, user_b):
        self._remember(user_a)
        _post(_client(user_b), name_or_bar_code="Different Person")  # gives user_b a preference row
        got = _client(user_b).get(
            "/api/cases/search-advocate/preference/", {"name_or_bar_code": NAME, "state_code": "29"}
        ).data
        assert got["quick_search"] is None


# ---------------------------------------------------------------------------
# C4: the provider flags (default OFF) and the per-step timing
# ---------------------------------------------------------------------------


def _fake_client(script):
    """A mock court client that logs its calls in order into `client.calls`.
    `script` is a list of per-submit outcomes: a dict (portal reply) or an
    exception to raise."""
    client = MagicMock()
    client.calls = []
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)

    async def init():
        client.calls.append("init")
        await asyncio.sleep(0.002)

    async def setup(**kwargs):
        client.calls.append("setup:" + kwargs["court_complex_code"])
        await asyncio.sleep(0.002)

    async def captcha():
        client.calls.append("captcha")
        await asyncio.sleep(0.002)
        return "abc123"

    outcomes = list(script)

    async def post(action, form):
        client.calls.append("submit")
        await asyncio.sleep(0.002)
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    client._init_session = init
    client._setup_court = setup
    client._solve_captcha = captcha
    client._post_ajax = post
    return client


OK = {"adv_data": "<table></table>"}


def _search(provider, client, hierarchy=HIERARCHY, via=None):
    with patch("core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", return_value=client), \
         patch("core.services.court_data.ecourts_provider.asyncio.sleep", new=AsyncMock()) as _sleep:
        # asyncio.sleep is stubbed for the retry back-off; the fake client's own sleeps use the
        # real one through `asyncio` imported in this module.
        return (via or provider).search_by_advocate(hierarchy, advocate_name="Zebulon Quillfeather")


class TestFlagsDefaultOff:
    def test_the_flag_is_off_unless_the_environment_turns_it_on(self):
        assert settings.ADVOCATE_SEARCH_REUSE_SESSION is False

    def test_the_rejected_captcha_only_retry_flag_is_gone(self):
        assert not hasattr(settings, "ADVOCATE_SEARCH_CAPTCHA_ONLY_RETRY")


class TestAttemptSequences:
    """The order of portal calls. The default must be exactly the old one."""

    def test_default_path_redoes_init_and_setup_on_every_attempt(self):
        provider = EcourtsProvider()
        client = _fake_client([DistrictServerError("Invalid Captcha... "), DistrictServerError("Invalid Captcha"), OK])
        _search(provider, client)
        assert client.calls == [
            "init", "setup:1010307", "captcha", "submit",
            "init", "setup:1010307", "captcha", "submit",
            "init", "setup:1010307", "captcha", "submit",
        ]
        assert provider.last_search_timing["attempts"] == 3

    def test_a_wrong_captcha_starts_the_session_over_like_any_other_failure(self):
        # Tried live and rejected (6 Nov 2026): the portal drops the session after a
        # wrong CAPTCHA, so refetching the image and resubmitting without a new
        # _init_session got "Invalid Request". Every failure restarts the session.
        provider = EcourtsProvider()
        client = _fake_client([DistrictServerError("Invalid Captcha... "), DistrictCaptchaError("wrong"), OK])
        _search(provider, client)
        assert client.calls.count("init") == 3 and client.calls.count("setup:1010307") == 3
        assert client.calls.count("captcha") == 3 and client.calls.count("submit") == 3

    def test_invalid_request_a_dropped_connection_and_an_empty_reply_do_too(self):
        import httpx

        provider = EcourtsProvider()
        client = _fake_client([DistrictServerError("Invalid Request"), httpx.RemoteProtocolError("peer closed"), {"adv_data": ""}, OK])
        _search(provider, client)
        assert client.calls.count("init") == 4 and client.calls.count("setup:1010307") == 4

    def test_an_unreadable_captcha_image_refetches_in_a_fresh_session(self):
        provider = EcourtsProvider()
        client = _fake_client([OK])
        readings = iter(["", "abc123"])

        async def captcha():
            client.calls.append("captcha")
            return next(readings)

        client._solve_captcha = captcha
        _search(provider, client)
        assert client.calls == [
            "init", "setup:1010307", "captcha",
            "init", "setup:1010307", "captcha", "submit",
        ]

    def test_the_attempt_budget_is_unchanged(self):
        provider = EcourtsProvider()
        client = _fake_client([DistrictServerError("Invalid Captcha")] * ADVOCATE_SEARCH_MAX_ATTEMPTS)
        with pytest.raises(Exception):
            _search(provider, client)
        assert client.calls.count("submit") == ADVOCATE_SEARCH_MAX_ATTEMPTS


class TestPerStepTiming:
    def test_each_step_is_timed_and_attempts_counted(self):
        provider = EcourtsProvider()
        client = _fake_client([DistrictServerError("Invalid Captcha"), OK])
        _search(provider, client)
        timing = provider.last_search_timing
        assert timing["attempts"] == 2
        for step in ("init_s", "setup_s", "captcha_s", "submit_s"):
            assert timing[step] > 0, step
        assert set(timing) == {"init_s", "setup_s", "captcha_s", "submit_s", "attempts"}

    def test_a_failed_search_still_leaves_its_timing(self):
        provider = EcourtsProvider()
        client = _fake_client([DistrictServerError("Invalid Captcha")] * ADVOCATE_SEARCH_MAX_ATTEMPTS)
        with pytest.raises(Exception):
            _search(provider, client)
        assert provider.last_search_timing["attempts"] == ADVOCATE_SEARCH_MAX_ATTEMPTS

    def test_the_timing_holds_numbers_only(self):
        provider = EcourtsProvider()
        _search(provider, _fake_client([OK]))
        assert all(isinstance(v, (int, float)) for v in provider.last_search_timing.values())


class TestSessionReuse:
    def _session(self, client):
        with patch("core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", return_value=client):
            return EcourtsProvider().advocate_search_session()

    def _two_complexes(self, client, second=None):
        calls = []
        with self._session(client) as session:
            for code in ("1010307", "1010308"):
                with patch("core.services.court_data.ecourts_provider.asyncio.sleep", new=AsyncMock()):
                    session.search_by_advocate(
                        {**HIERARCHY, "court_complex_code": code}, advocate_name="Zebulon Quillfeather"
                    )
                calls.append(session.last_search_timing)
        return calls

    def test_init_runs_once_and_setup_once_per_complex(self):
        client = _fake_client([OK, OK])
        timings = self._two_complexes(client)
        assert client.calls == [
            "init", "setup:1010307", "captcha", "submit",
            "setup:1010308", "captcha", "submit",
        ]
        assert timings[0]["init_s"] > 0 and timings[1]["init_s"] == 0  # the second complex paid nothing for it

    def test_a_failure_makes_the_next_attempt_start_the_session_over(self):
        client = _fake_client([OK, DistrictServerError("Invalid Request"), OK])
        self._two_complexes(client)
        assert client.calls == [
            "init", "setup:1010307", "captcha", "submit",
            "setup:1010308", "captcha", "submit",       # second complex, first try fails
            "init", "setup:1010308", "captcha", "submit",  # retried from a fresh session start
        ]

    def test_a_wrong_captcha_inside_a_reused_session_restarts_it_too(self):
        client = _fake_client([OK, DistrictServerError("Invalid Captcha... "), OK])
        self._two_complexes(client)
        assert client.calls == [
            "init", "setup:1010307", "captcha", "submit",
            "setup:1010308", "captcha", "submit",
            "init", "setup:1010308", "captcha", "submit",
        ]

    def test_a_complex_that_ends_in_failure_leaves_the_session_to_be_restarted(self):
        client = _fake_client([DistrictServerError("Invalid Captcha")] * ADVOCATE_SEARCH_MAX_ATTEMPTS + [OK])
        with self._session(client) as session, \
                patch("core.services.court_data.ecourts_provider.asyncio.sleep", new=AsyncMock()):
            with pytest.raises(Exception):
                session.search_by_advocate(HIERARCHY, advocate_name="Zebulon Quillfeather")
            assert session.needs_init is True
            client.calls.clear()
            session.search_by_advocate({**HIERARCHY, "court_complex_code": "1010308"}, advocate_name="Zebulon Quillfeather")
        assert client.calls[0] == "init"

    def test_the_session_closes_its_client_and_its_loop(self):
        client = _fake_client([OK])
        session = self._session(client)
        with session:
            pass
        client.__aexit__.assert_awaited_once()
        assert session._loop.is_closed()

    def test_the_search_still_validates_its_arguments(self):
        client = _fake_client([])
        with self._session(client) as session:
            with pytest.raises(ValueError):
                session.search_by_advocate(HIERARCHY)
            with pytest.raises(ValueError):
                session.search_by_advocate(HIERARCHY, advocate_name="x", bar_code="MAH/1/2015")


@pytest.mark.django_db
class TestServiceUsesTheSessionOnlyWhenAsked:
    class _Session:
        def __init__(self, owner):
            self.owner = owner
            self.entered = self.exited = False
            self.last_search_timing = _timing()

        def __enter__(self):
            self.entered = True
            return self

        def __exit__(self, *exc):
            self.exited = True

        def search_by_advocate(self, hierarchy, **kwargs):
            self.owner.session_calls.append(hierarchy["court_complex_code"])
            return []

    class _P(_Provider):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.session_calls = []
            self.sessions = []

        def advocate_search_session(self):
            session = TestServiceUsesTheSessionOnlyWhenAsked._Session(self)
            self.sessions.append(session)
            return session

    def _provider(self):
        return self._P({"1": "Dist A", "2": "Dist B"},
                       {"1": {"c1@e1@N": "C1", "c2@e2@N": "C2"}, "2": {"c3@e3@N": "C3"}},
                       [([], _timing())] * 3)

    def test_off_by_default_the_provider_is_called_directly(self, user_a):
        provider = self._provider()
        _run(_search_job(user_a), provider)
        assert provider.sessions == [] and provider.calls == ["c1/e1", "c2/e2", "c3/e3"]

    @override_settings(ADVOCATE_SEARCH_REUSE_SESSION=True)
    def test_on_each_district_gets_one_session_that_is_closed_after_it(self, user_a):
        provider = self._provider()
        job = _search_job(user_a)
        _run(job, provider)
        assert len(provider.sessions) == 2  # one per district
        assert all(s.entered and s.exited for s in provider.sessions)
        assert provider.session_calls == ["c1", "c2", "c3"] and provider.calls == []
        assert job.payload["timing"]["reuse_session"] is True

    @override_settings(ADVOCATE_SEARCH_REUSE_SESSION=True)
    def test_the_session_is_closed_even_if_the_district_blows_up(self, user_a):
        provider = self._provider()
        provider.list_complexes = MagicMock(return_value={"c1@e1@N": "C1"})
        original = provider.advocate_search_session

        def boom():
            session = original()
            session.search_by_advocate = MagicMock(side_effect=KeyboardInterrupt)
            return session

        provider.advocate_search_session = boom
        with pytest.raises(KeyboardInterrupt):
            _run(_search_job(user_a), provider)
        assert provider.sessions[0].exited
