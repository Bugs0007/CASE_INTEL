"""The redesigned advocate search: the court-complex run state machine, the worker
that fills it, the per-court status endpoint and the retry of chosen courts.

The portal is never touched: a FakeProvider plays list_districts/list_complexes/
search_by_advocate and reports the attempts each court spent, like the real
provider's `last_search_timing`.
"""

from unittest.mock import MagicMock, patch

import httpx
import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import (
    AdvocateSearchComplexRun,
    AdvocateSearchProfile,
    InvalidComplexRunTransition,
    ProcessingJob,
)
from core.services.advocate_search import AdvocateSearchCancelled, run_advocate_search
from core.services.advocate_search_v2 import classify_run_error, run_retry, summarize_runs
from core.services.court_data import CaptchaSolveError, CourtPortalError
from core.services.court_data.models import AdvocateSearchHit
from core.tests.auth_helpers import token_for

Run = AdvocateSearchComplexRun

FORMS = ["Rambabu", "Ram babu", "S Rambabu", "S Ram babu", "Rambabu S"]
NOT_ME = ["T Rambabu", "K Rambabu", "Rambabu Reddy"]
TWO_COURTS = {"c1@e1@N": "Adilabad Court Complex", "c2@e1@N": "Khanapur Court Complex"}


@pytest.fixture
def user_a():
    return User.objects.create_user(username="alice", password="alice-pass-123")


@pytest.fixture
def user_b():
    return User.objects.create_user(username="bob", password="bob-pass-123")


def _client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token_for(user)}")
    return client


@pytest.fixture
def client_a(user_a):
    return _client(user_a)


@pytest.fixture
def client_b(user_b):
    return _client(user_b)


@pytest.fixture
def profile_a(user_a):
    return AdvocateSearchProfile.objects.create(
        owner=user_a, display_name="Rambabu Samalla", bar_codes=["TS/1234/2009"],
        name_forms=list(FORMS), excluded_names=list(NOT_ME),
    )


@pytest.fixture
def v2_on(settings):
    settings.ADVOCATE_SEARCH_V2 = True


def hit(cnr, advocate="S Rambabu", segments=None):
    return AdvocateSearchHit(
        case_number=f"OS/{cnr[-1]}/2020",
        cnr_number=cnr,
        petitioner="A",
        respondent="B",
        listed_advocate_name=advocate,
        listed_advocates=segments if segments is not None else [advocate],
    )


class FakeProvider:
    """list_districts/list_complexes/search_by_advocate from a script. Each
    search outcome is (hits or an Exception, attempts the court spent)."""

    def __init__(self, script, *, districts=None, complexes=None):
        self.districts = districts or {"1": "Adilabad"}
        self.complexes = TWO_COURTS if complexes is None else complexes
        self.script = list(script)
        self.calls: list[dict] = []
        self.last_search_timing: dict = {}

    def list_districts(self, state_code):
        return self.districts

    def list_complexes(self, state_code, dist_code):
        if isinstance(self.complexes, Exception):
            raise self.complexes
        return self.complexes

    def search_by_advocate(self, hierarchy, *, advocate_name="", bar_code="", status_filter="Both", keep_all=False):
        self.calls.append(
            {"complex": hierarchy["court_complex_code"], "advocate_name": advocate_name, "bar_code": bar_code,
             "status_filter": status_filter, "keep_all": keep_all}
        )
        outcome, attempts = self.script.pop(0)
        self.last_search_timing = {"attempts": attempts}
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _job(user, profile=None, **overrides):
    params = {
        "v2": True, "state_code": "29", "court_type": "district", "search_by": "names",
        "queries": ["Rambabu"], "advocate_name": "Rambabu", "bar_code": "", "status_filter": "Both",
        "profile_id": profile.id if profile else None, "mode": "state",
    }
    params.update(overrides)
    return ProcessingJob.enqueue_advocate_search(user, params)


def _run_worker(job, provider, **kwargs):
    with patch("core.services.advocate_search_v2.get_provider", return_value=provider), \
            patch("core.services.advocate_search_v2.time.sleep") as sleep:
        try:
            run_advocate_search(job, **kwargs)
        finally:
            run_worker.sleep = sleep
    job.refresh_from_db()


class run_worker:  # noqa: N801 -- a tiny holder so tests can read what the patched sleep saw
    sleep = None


def _disconnect():
    exc = CourtPortalError("District Courts advocate search failed after 6 attempts: peer closed connection")
    exc.__cause__ = httpx.RemoteProtocolError("peer closed connection")
    return exc


# ---------------------------------------------------------------------------
# The state machine
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestComplexRunStateMachine:
    def _run(self, user):
        job = _job(user)
        return Run.objects.create(job=job, owner=user, dist_code="1", complex_code="c1", complex_name="Court")

    def test_pending_running_done(self, user_a):
        run = self._run(user_a)
        assert run.status == Run.PENDING
        run.mark_running()
        assert run.status == Run.RUNNING and run.started_at is not None
        run.mark_done(attempts=2, raw_count=7, matched_count=3)
        run.refresh_from_db()
        assert (run.status, run.attempts, run.raw_count, run.matched_count) == (Run.DONE, 2, 7, 3)
        assert run.finished_at is not None and run.last_error_code == ""

    def test_running_to_failed_carries_the_reason(self, user_a):
        run = self._run(user_a)
        run.mark_running()
        run.mark_failed(attempts=6, error_code=Run.CAPTCHA_FAILED, error_message="Captcha not solved.")
        run.refresh_from_db()
        assert run.status == Run.FAILED
        assert (run.attempts, run.last_error_code, run.last_error_message) == (6, "captcha_failed", "Captcha not solved.")

    def test_failed_can_go_back_to_pending_for_a_retry(self, user_a):
        run = self._run(user_a)
        run.mark_running()
        run.mark_failed(attempts=3, error_code=Run.TIMEOUT, error_message="x")
        run.reset_for_retry()
        run.refresh_from_db()
        assert (run.status, run.attempts, run.last_error_code, run.finished_at) == (Run.PENDING, 0, "", None)

    def test_done_can_be_searched_again_on_request(self, user_a):
        run = self._run(user_a)
        run.mark_running()
        run.mark_done(attempts=1, raw_count=0, matched_count=0)
        run.reset_for_retry()
        assert run.status == Run.PENDING

    @pytest.mark.parametrize("bad", ["mark_done", "mark_failed", "reset_for_retry"])
    def test_a_pending_run_cannot_finish_without_running(self, user_a, bad):
        run = self._run(user_a)
        with pytest.raises(InvalidComplexRunTransition):
            if bad == "mark_done":
                run.mark_done(attempts=1, raw_count=0, matched_count=0)
            elif bad == "mark_failed":
                run.mark_failed(attempts=1, error_code=Run.PORTAL_ERROR, error_message="x")
            else:
                run.reset_for_retry()
        assert run.status == Run.PENDING

    def test_a_running_run_cannot_be_reset_or_started_twice(self, user_a):
        run = self._run(user_a)
        run.mark_running()
        with pytest.raises(InvalidComplexRunTransition):
            run.mark_running()
        with pytest.raises(InvalidComplexRunTransition):
            run.reset_for_retry()

    def test_a_finished_run_cannot_finish_again(self, user_a):
        run = self._run(user_a)
        run.mark_running()
        run.mark_done(attempts=1, raw_count=0, matched_count=0)
        with pytest.raises(InvalidComplexRunTransition):
            run.mark_failed(attempts=1, error_code=Run.PORTAL_ERROR, error_message="x")

    def test_one_row_per_court_per_job(self, user_a):
        from django.db import IntegrityError, transaction

        run = self._run(user_a)
        with pytest.raises(IntegrityError), transaction.atomic():
            Run.objects.create(job=run.job, owner=user_a, dist_code="1", complex_code="c1")


class TestClassifyRunError:
    def test_captcha(self):
        assert classify_run_error(CaptchaSolveError("CAPTCHA solving failed after 6 attempts.")) == Run.CAPTCHA_FAILED

    def test_dropped_connection_even_when_wrapped_by_the_provider(self):
        assert classify_run_error(_disconnect()) == Run.PORTAL_DISCONNECT

    def test_timeout_cause(self):
        exc = CourtPortalError("failed after 6 attempts: ")
        exc.__cause__ = httpx.ReadTimeout("slow")
        assert classify_run_error(exc) == Run.TIMEOUT

    def test_our_own_wall_clock_budget(self):
        assert classify_run_error(CourtPortalError("The court portal did not answer within 90 seconds")) == Run.TIMEOUT

    def test_plain_portal_refusal(self):
        assert classify_run_error(CourtPortalError("Invalid Request")) == Run.PORTAL_ERROR

    def test_something_our_code_choked_on_is_a_parse_error(self):
        assert classify_run_error(AttributeError("'NoneType' object has no attribute 'find_all'")) == Run.PARSE_ERROR


# ---------------------------------------------------------------------------
# The worker
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestWorkerV2:
    def test_every_court_is_recorded_and_a_failure_is_isolated(self, user_a, profile_a):
        job = _job(user_a, profile_a)
        provider = FakeProvider(
            [
                ([hit("CNR1"), hit("CNR2", "T Rambabu"), hit("CNR3", "G Rambabu")], 1),
                (_disconnect(), 6),
            ]
        )
        _run_worker(job, provider)

        a, b = Run.objects.filter(job=job).order_by("id")
        assert (a.complex_name, a.status, a.attempts, a.raw_count) == ("Adilabad Court Complex", Run.DONE, 1, 3)
        # Of the three rows only the advocate's own counts: T Rambabu is Not me, G Rambabu is someone else.
        assert a.matched_count == 1
        assert (b.complex_name, b.status, b.attempts) == ("Khanapur Court Complex", Run.FAILED, 6)
        assert (b.last_error_code, b.last_error_message) == ("portal_disconnect", "Portal disconnected.")
        assert a.query == "Rambabu" and b.finished_at is not None

        payload = job.payload
        assert sorted(r["cnr_number"] for r in payload["results"]) == ["CNR1", "CNR2", "CNR3"]  # nothing dropped
        assert payload["districts_status"]["1"]["status"] == "partial"
        assert payload["complexes_searched"] == 1 and payload["complexes_done"] == 2
        assert [f["court_complex"] for f in payload["failures"]] == ["Khanapur Court Complex"]

    def test_stored_rows_carry_the_cell_as_listed_and_where_it_came_from(self, user_a, profile_a):
        job = _job(user_a, profile_a)
        _run_worker(job, FakeProvider([([hit("CNR1", segments=["APP", "S Rambabu"])], 1), ([], 1)]))
        row = job.payload["results"][0]
        assert row["listed_advocates"] == ["APP", "S Rambabu"]
        assert (row["dist_name"], row["complex_name"], row["complex_code"]) == ("Adilabad", "Adilabad Court Complex", "c1")

    def test_courts_get_their_rows_before_the_search_reaches_them(self, user_a, profile_a):
        """A court is `running` while searched; an observer sees the later ones `pending`."""
        job = _job(user_a, profile_a)
        seen = []

        class Watching(FakeProvider):
            def search_by_advocate(self, hierarchy, **kw):
                seen.append(sorted(Run.objects.filter(job=job).values_list("complex_name", "status")))
                return super().search_by_advocate(hierarchy, **kw)

        _run_worker(job, Watching([([], 1), ([], 1)]))
        assert seen[0] == [("Adilabad Court Complex", "running"), ("Khanapur Court Complex", "pending")]

    def test_two_queries_cost_two_requests_per_court_merged_by_cnr(self, user_a, profile_a):
        job = _job(user_a, profile_a, queries=["Rambabu", "Ram babu"])
        provider = FakeProvider(
            [
                ([hit("CNR1"), hit("CNR2")], 1),  # court 1, "Rambabu"
                ([hit("CNR2"), hit("CNR3")], 2),  # court 1, "Ram babu"
                ([], 1),  # court 2, "Rambabu"
                ([], 1),  # court 2, "Ram babu"
            ]
        )
        _run_worker(job, provider)
        assert [(c["complex"], c["advocate_name"]) for c in provider.calls] == [
            ("c1", "Rambabu"), ("c1", "Ram babu"), ("c2", "Rambabu"), ("c2", "Ram babu"),
        ]
        assert all(c["keep_all"] and c["bar_code"] == "" for c in provider.calls)
        first = Run.objects.filter(job=job).order_by("id").first()
        assert (first.raw_count, first.attempts, first.query) == (3, 3, "Rambabu | Ram babu")
        assert sorted(r["cnr_number"] for r in job.payload["results"]) == ["CNR1", "CNR2", "CNR3"]

    def test_a_court_whose_first_query_fails_is_not_tried_with_the_second(self, user_a, profile_a):
        job = _job(user_a, profile_a, queries=["Rambabu", "Ram babu"], districts_filter=["1"])
        provider = FakeProvider([(_disconnect(), 6), ([], 1), ([], 1)], complexes={"c1@e1@N": "Only Court"})
        _run_worker(job, provider)
        assert len(provider.calls) == 1  # the portal that just dropped us is not hammered
        run = Run.objects.get(job=job)
        assert run.status == Run.FAILED and run.attempts == 6

    def test_rows_read_before_a_failure_are_kept(self, user_a, profile_a):
        job = _job(user_a, profile_a, queries=["Rambabu", "Ram babu"])
        provider = FakeProvider([([hit("CNR1")], 1), (_disconnect(), 6), ([], 1), ([], 1)])
        _run_worker(job, provider)
        first = Run.objects.filter(job=job).order_by("id").first()
        assert first.status == Run.FAILED and first.raw_count == 1
        assert [r["cnr_number"] for r in job.payload["results"]] == ["CNR1"]

    def test_bar_code_search_asks_by_bar_code_and_tags_the_rows(self, user_a, profile_a):
        job = _job(user_a, profile_a, search_by="bar_code", queries=[], bar_code="TS/1234/2009", advocate_name="")
        provider = FakeProvider([([hit("CNR1", "Someone Else Entirely")], 1), ([], 1)])
        _run_worker(job, provider)
        assert provider.calls[0]["bar_code"] == "TS/1234/2009" and provider.calls[0]["advocate_name"] == ""
        row = job.payload["results"][0]
        assert row["match_source"] == "bar_code"
        # whatever name the court lists, the portal matched the bar code itself
        from core.services.advocate_results import annotate_rows

        labelled, _ = annotate_rows([row], profile_a)
        assert (labelled[0]["match_status"], labelled[0]["match_label"]) == ("matched", "Your bar no.")

    def test_a_district_whose_courts_cannot_be_listed_is_one_failed_row(self, user_a, profile_a):
        job = _job(user_a, profile_a)
        provider = FakeProvider([], complexes=CourtPortalError("The court portal could not be reached"))
        _run_worker(job, provider)
        run = Run.objects.get(job=job)
        assert (run.complex_code, run.status, run.dist_name) == ("", Run.FAILED, "Adilabad")
        assert run.complex_name == "All courts in Adilabad"
        assert job.payload["districts_status"]["1"]["status"] == "failed"

    def test_every_court_refused_reads_the_district_once_more_and_then_stops(self, user_a, profile_a):
        job = _job(user_a, profile_a)
        refused = CourtPortalError("Invalid Request")
        provider = FakeProvider([(refused, 6)] * 4)
        _run_worker(job, provider)
        assert len(provider.calls) == 4  # two courts, read twice, never a third time
        assert {r.status for r in Run.objects.filter(job=job)} == {Run.FAILED}
        assert 20 in [c.args[0] for c in run_worker.sleep.call_args_list]  # the cooldown between the two reads

    def test_progress_is_reported_per_district(self, user_a, profile_a):
        job = _job(user_a, profile_a)
        cb = MagicMock()
        _run_worker(job, FakeProvider([([], 1), ([], 1)]), progress_callback=cb)
        cb.assert_any_call(0, 1)
        cb.assert_any_call(1, 1)

    def test_cancelling_stops_after_the_court_in_progress_and_keeps_what_was_found(self, user_a, profile_a):
        job = _job(user_a, profile_a)
        ProcessingJob.objects.filter(pk=job.pk).update(cancel_requested=True)
        provider = FakeProvider([([hit("CNR1")], 1), ([hit("CNR2")], 1)])
        with patch("core.services.advocate_search_v2.get_provider", return_value=provider), \
                patch("core.services.advocate_search_v2.time.sleep"), pytest.raises(AdvocateSearchCancelled):
            run_advocate_search(job)
        job.refresh_from_db()
        statuses = [r.status for r in Run.objects.filter(job=job).order_by("id")]
        assert statuses == [Run.DONE, Run.PENDING]
        assert [r["cnr_number"] for r in job.payload["results"]] == ["CNR1"]

    def test_a_reclaimed_job_starts_with_a_clean_list_of_courts(self, user_a, profile_a):
        job = _job(user_a, profile_a)
        Run.objects.create(job=job, owner=user_a, dist_code="1", complex_code="ghost", status=Run.RUNNING)
        _run_worker(job, FakeProvider([([], 1), ([], 1)]))
        assert not Run.objects.filter(job=job, complex_code="ghost").exists()

    def test_the_old_request_shape_still_runs_the_old_path(self, user_a):
        job = ProcessingJob.enqueue_advocate_search(
            user_a, {"state_code": "1", "court_type": "district", "advocate_name": "Suresh", "bar_code": "", "status_filter": "Both"}
        )
        provider = MagicMock()
        provider.list_districts.return_value = {"1": "Dist A"}
        provider.list_complexes.return_value = {"cx1@e@N": "Complex 1"}
        provider.search_by_advocate.return_value = []
        with patch("core.services.advocate_search.get_provider", return_value=provider), \
                patch("core.services.advocate_search.time.sleep"):
            run_advocate_search(job)
        job.refresh_from_db()
        assert not Run.objects.filter(job=job).exists()  # the old flow writes no court rows
        assert "keep_all" not in provider.search_by_advocate.call_args.kwargs  # and calls the provider as before
        assert job.payload["complexes_searched"] == 1


# ---------------------------------------------------------------------------
# Starting a v2 search
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestStartV2:
    def _start(self, client, profile, **body):
        return client.post(
            "/api/cases/search-advocate/",
            {"profile_id": profile.id, "state_code": "29", **body},
            format="json",
        )

    def test_off_by_default(self, client_a, profile_a):
        resp = self._start(client_a, profile_a)
        assert resp.status_code == 400 and resp.data["code"] == "v2_disabled"
        assert not ProcessingJob.objects.filter(job_type="advocate_search").exists()

    def test_names_search_sends_the_minimised_queries(self, v2_on, client_a, profile_a):
        # The profile has a bar code, so ask for names explicitly.
        resp = self._start(client_a, profile_a, search_by="names", dist_codes=["1", "3"], status_filter="Pending")
        assert resp.status_code == 202, resp.data
        assert resp.data["queries"] == ["Rambabu", "Ram babu"] and resp.data["portal_calls_per_court"] == 2
        params = ProcessingJob.objects.get(id=resp.data["job_id"]).payload
        assert params["v2"] is True and params["profile_id"] == profile_a.id
        assert params["queries"] == ["Rambabu", "Ram babu"] and params["bar_code"] == ""
        assert params["districts_filter"] == ["1", "3"] and params["status_filter"] == "Pending"
        assert params["advocate_name"] == "Rambabu"

    def test_defaults_to_the_bar_code_when_the_profile_has_one(self, v2_on, client_a, profile_a):
        resp = self._start(client_a, profile_a)
        params = ProcessingJob.objects.get(id=resp.data["job_id"]).payload
        assert params["search_by"] == "bar_code" and params["bar_code"] == "TS/1234/2009" and params["queries"] == []

    def test_a_bar_code_not_on_the_profile_is_refused(self, v2_on, client_a, profile_a):
        assert self._start(client_a, profile_a, bar_code="MH/9/2001").status_code == 400

    def test_names_search_needs_a_searchable_name(self, v2_on, client_a, user_a):
        empty = AdvocateSearchProfile.objects.create(owner=user_a, display_name="X Y", name_forms=["S R"])
        resp = self._start(client_a, empty, search_by="names")
        assert resp.status_code == 400 and "name form" in resp.data["detail"]

    def test_another_advocates_profile_is_refused(self, v2_on, client_b, profile_a):
        assert self._start(client_b, profile_a).status_code == 400

    def test_one_search_at_a_time_is_still_enforced(self, v2_on, client_a, profile_a):
        assert self._start(client_a, profile_a).status_code == 202
        second = self._start(client_a, profile_a)
        assert second.status_code == 409 and second.data["code"] == "search_already_running"

    def test_state_is_required(self, v2_on, client_a, profile_a):
        resp = client_a.post("/api/cases/search-advocate/", {"profile_id": profile_a.id}, format="json")
        assert resp.status_code == 400

    def test_the_old_request_shape_is_untouched(self, client_a):
        resp = client_a.post(
            "/api/cases/search-advocate/",
            {"name_or_bar_code": "Suresh", "court_type": "district", "state_code": "1"},
            format="json",
        )
        assert resp.status_code == 202
        assert "v2" not in ProcessingJob.objects.get(id=resp.data["job_id"]).payload

    def test_features(self, client_a, settings):
        settings.ADVOCATE_SEARCH_V2 = False
        assert client_a.get("/api/advocate-search/features/").data["v2"] is False
        settings.ADVOCATE_SEARCH_V2 = True
        data = client_a.get("/api/advocate-search/features/").data
        assert data["v2"] is True and data["seconds_per_call"] > 0


# ---------------------------------------------------------------------------
# The per-court status endpoint
# ---------------------------------------------------------------------------


def _finished_search(user, profile):
    job = _job(user, profile)
    provider = FakeProvider([([hit("CNR1"), hit("CNR2", "T Rambabu")], 1), (_disconnect(), 3)])
    _run_worker(job, provider)
    ProcessingJob.objects.filter(pk=job.pk).update(status="succeeded")
    job.refresh_from_db()
    return job


@pytest.mark.django_db
class TestCourtsEndpoint:
    def test_groups_courts_under_districts_with_plain_reasons(self, client_a, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        data = client_a.get(f"/api/cases/search-advocate/{job.id}/courts/").data
        assert data["counts"] == {"total": 2, "done": 1, "failed": 1, "running": 0, "pending": 0, "raw": 2, "matched": 1}
        (group,) = data["groups"]
        assert (group["name"], group["total"], group["done"], group["failed"]) == ("Adilabad", 2, 1, 1)
        done, failed = group["runs"]
        assert done["status"] == "done" and done["matched_count"] == 1 and done["reason"] == ""
        assert failed["reason"] == "Portal disconnected. 3 attempts."
        assert failed["error_code"] == "portal_disconnect"
        assert [r["complex_name"] for r in data["needs_attention"]] == ["Khanapur Court Complex"]
        assert data["job"]["can_retry"] is True and data["job"]["is_retrying"] is False
        assert data["court_site_url"].startswith("https://")

    def test_nothing_finished_yet_means_no_time_left_estimate(self, client_a, user_a, profile_a):
        job = _job(user_a, profile_a)
        Run.objects.create(job=job, owner=user_a, dist_code="1", dist_name="Adilabad", complex_code="c1")
        data = client_a.get(f"/api/cases/search-advocate/{job.id}/courts/").data
        assert data["seconds_left"] is None
        assert data["groups"][0]["runs"][0]["reason"] == "Waiting"

    def test_a_running_search_cannot_be_retried_yet(self, client_a, user_a, profile_a):
        job = _job(user_a, profile_a)
        assert client_a.get(f"/api/cases/search-advocate/{job.id}/courts/").data["job"]["can_retry"] is False

    def test_another_advocates_search_is_a_404(self, client_b, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        assert client_b.get(f"/api/cases/search-advocate/{job.id}/courts/").status_code == 404

    def test_requires_authentication(self, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        assert APIClient().get(f"/api/cases/search-advocate/{job.id}/courts/").status_code == 401


# ---------------------------------------------------------------------------
# Retrying chosen courts, with the provider mocked
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRetry:
    def _retry(self, client, job, **body):
        return client.post(f"/api/cases/search-advocate/{job.id}/retry/", body, format="json")

    def test_off_by_default(self, client_a, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        assert self._retry(client_a, job, only_failed=True).data["code"] == "v2_disabled"

    def test_only_failed_creates_a_child_for_just_those_courts(self, v2_on, client_a, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        failed = Run.objects.get(job=job, status=Run.FAILED)
        done = Run.objects.get(job=job, status=Run.DONE)

        resp = self._retry(client_a, job, only_failed=True)
        assert resp.status_code == 202, resp.data
        assert resp.data["courts"] == 1 and resp.data["parent_job_id"] == job.id
        child = ProcessingJob.objects.get(id=resp.data["job_id"])
        assert child.payload["parent_job_id"] == job.id and child.payload["run_ids"] == [failed.id]
        assert child.payload["queries"] == ["Rambabu"] and child.payload["profile_id"] == profile_a.id
        failed.refresh_from_db(), done.refresh_from_db()
        assert failed.status == Run.PENDING and failed.last_error_code == "" and failed.attempts == 0
        assert done.status == Run.DONE  # the courts that worked are left alone

    def test_the_child_runs_only_that_court_and_merges_into_the_same_list(self, v2_on, client_a, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        before = sorted(r["cnr_number"] for r in job.payload["results"])
        child = ProcessingJob.objects.get(id=self._retry(client_a, job, only_failed=True).data["job_id"])

        provider = FakeProvider([([hit("CNR9"), hit("CNR1", "Rambabu S")], 2)])
        with patch("core.services.advocate_search_v2.get_provider", return_value=provider), \
                patch("core.services.advocate_search_v2.time.sleep"):
            run_advocate_search(child)

        assert [c["complex"] for c in provider.calls] == ["c2"]  # one portal request: only the failed court
        job.refresh_from_db()
        after = sorted(r["cnr_number"] for r in job.payload["results"])
        assert after == sorted(set(before) | {"CNR9"})  # merged, no duplicates
        assert {r["cnr_number"]: r["listed_advocate_name"] for r in job.payload["results"]}["CNR1"] == "Rambabu S"
        assert {r.status for r in Run.objects.filter(job=job)} == {Run.DONE}
        assert job.payload["districts_status"]["1"]["status"] == "success"
        assert job.payload["failures"] == [] and job.payload["complexes_searched"] == 2

        data = client_a.get(f"/api/cases/search-advocate/{job.id}/").data  # one list, labelled as before
        assert data["match_counts"]["matched"] == 2 and data["results_total"] == 3

    def test_a_court_that_fails_again_stays_failed_with_its_new_reason(self, v2_on, client_a, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        child = ProcessingJob.objects.get(id=self._retry(client_a, job, only_failed=True).data["job_id"])
        provider = FakeProvider([(CaptchaSolveError("CAPTCHA solving failed after 6 attempts."), 6)])
        with patch("core.services.advocate_search_v2.get_provider", return_value=provider), \
                patch("core.services.advocate_search_v2.time.sleep"):
            run_advocate_search(child)
        run = Run.objects.get(job=job, complex_code="c2")
        assert (run.status, run.last_error_code, run.attempts) == (Run.FAILED, "captcha_failed", 6)

    def test_complex_ids_retry_chosen_courts_including_one_that_worked(self, v2_on, client_a, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        done = Run.objects.get(job=job, status=Run.DONE)
        resp = self._retry(client_a, job, complex_ids=[done.id])
        assert resp.status_code == 202 and resp.data["courts"] == 1
        done.refresh_from_db()
        assert done.status == Run.PENDING

    def test_nothing_failed_means_nothing_to_retry(self, v2_on, client_a, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        Run.objects.filter(job=job, status=Run.FAILED).update(status=Run.DONE)
        resp = self._retry(client_a, job, only_failed=True)
        assert resp.status_code == 400 and not ProcessingJob.objects.filter(payload__parent_job_id=job.id).exists()

    def test_body_must_say_one_thing(self, v2_on, client_a, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        assert self._retry(client_a, job).status_code == 400
        assert self._retry(client_a, job, only_failed=True, complex_ids=[1]).status_code == 400
        assert self._retry(client_a, job, complex_ids=["x"]).status_code == 400

    def test_a_running_search_cannot_be_retried(self, v2_on, client_a, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        ProcessingJob.objects.filter(pk=job.pk).update(status="running")
        assert self._retry(client_a, job, only_failed=True).status_code == 400

    def test_the_one_search_at_a_time_cap_applies_to_a_retry(self, v2_on, client_a, user_a, user_b, profile_a):
        job = _finished_search(user_a, profile_a)
        ProcessingJob.enqueue_advocate_search(user_b, {"v2": True, "state_code": "1"})  # someone else's search is running
        resp = self._retry(client_a, job, only_failed=True)
        assert resp.status_code == 409 and resp.data["code"] == "search_already_running"
        assert Run.objects.get(job=job, complex_code="c2").status == Run.FAILED  # nothing was reset

    def test_a_second_retry_while_one_is_running_is_refused(self, v2_on, client_a, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        assert self._retry(client_a, job, only_failed=True).status_code == 202
        again = self._retry(client_a, job, only_failed=True)
        assert again.status_code == 409 and again.data["code"] == "retry_in_progress"
        courts = client_a.get(f"/api/cases/search-advocate/{job.id}/courts/").data["job"]
        assert courts["is_retrying"] is True and courts["can_retry"] is False

    def test_another_advocates_search_cannot_be_retried(self, v2_on, client_b, user_a, profile_a):
        job = _finished_search(user_a, profile_a)
        assert self._retry(client_b, job, only_failed=True).status_code == 404

    def test_another_advocates_court_ids_are_ignored(self, v2_on, client_b, user_a, user_b):
        other_profile = AdvocateSearchProfile.objects.create(owner=user_b, display_name="B B", name_forms=["Bhaskar"])
        mine = _finished_search(user_b, other_profile)
        foreign = Run.objects.filter(job__owner=user_a).first()
        if foreign is None:  # nothing of Alice's exists in this test: make one
            alice_job = _job(user_a)
            foreign = Run.objects.create(job=alice_job, owner=user_a, dist_code="1", complex_code="z")
            ProcessingJob.objects.filter(pk=alice_job.pk).update(status="succeeded")
        resp = self._retry(client_b, mine, complex_ids=[foreign.id])
        assert resp.status_code == 400  # not one of the caller's courts: nothing to search again
        foreign.refresh_from_db()
        assert foreign.status == Run.PENDING

    def test_old_searches_keep_their_own_retry_failed(self, v2_on, client_a, user_a):
        old = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="succeeded", payload={"state_code": "1", "results": []}
        )
        assert self._retry(client_a, old, only_failed=True).status_code == 400

    def test_a_district_whose_courts_could_not_be_listed_is_expanded_on_retry(self, v2_on, client_a, user_a, profile_a):
        job = _job(user_a, profile_a)
        bad = FakeProvider([], complexes=CourtPortalError("The court portal could not be reached"))
        _run_worker(job, bad)
        ProcessingJob.objects.filter(pk=job.pk).update(status="succeeded")
        assert Run.objects.get(job=job).complex_code == ""

        child = ProcessingJob.objects.get(id=self._retry(client_a, job, only_failed=True).data["job_id"])
        good = FakeProvider([([hit("CNR1")], 1), ([], 1)])
        with patch("core.services.advocate_search_v2.get_provider", return_value=good), \
                patch("core.services.advocate_search_v2.time.sleep"):
            run_retry(child)
        runs = list(Run.objects.filter(job=job).order_by("id"))
        assert [r.complex_name for r in runs] == list(TWO_COURTS.values())  # the placeholder is gone
        assert {r.status for r in runs} == {Run.DONE}
        job.refresh_from_db()
        assert [r["cnr_number"] for r in job.payload["results"]] == ["CNR1"]


@pytest.mark.django_db
def test_summarize_runs_only_gives_a_verdict_to_a_district_whose_courts_all_finished(user_a):
    job = _job(user_a)
    Run.objects.create(job=job, owner=user_a, dist_code="1", dist_name="A", complex_code="c1", status=Run.DONE)
    Run.objects.create(job=job, owner=user_a, dist_code="1", dist_name="A", complex_code="c2", status=Run.PENDING)
    Run.objects.create(job=job, owner=user_a, dist_code="2", dist_name="B", complex_code="c1", status=Run.FAILED,
                       last_error_code="timeout", last_error_message="x")
    summary = summarize_runs(job)
    assert list(summary["districts_status"]) == ["2"]  # district 1 still has a court to go
    assert summary["districts_status"]["2"]["status"] == "failed"
    assert (summary["complexes_searched"], summary["complexes_done"], summary["complexes_total_known"]) == (1, 2, 3)
