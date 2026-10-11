"""Portal locks, the API surface, and the court-locator flow."""

import datetime
import json

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db import connection
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Case, CourtFetchLog, Hearing, ProcessingJob
from core.services.causelists import lock, registry, service
from core.services.causelists.adapters import district_ecourts as dc
from core.services.causelists.adapters.hcservices_generic import get_adapter as hc_adapter
from core.services.causelists.adapters.telangana_hc import get_adapter as telangana_adapter
from core.services.causelists.base import FetchResult
from core.tests.causelist_support import FIXTURES_ROOT, make_case, make_hearing

DAY = datetime.date(2026, 10, 12)
LOCATOR = {"kind": "district", "state_code": "29", "dist_code": "2", "est_code": "2", "complex_code": "1290019", "court_no": "1"}


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="lock-advocate", password="pw-123456")


def job(owner, job_type, *, status="running", age_minutes=0):
    j = ProcessingJob.objects.create(owner=owner, job_type=job_type, status=status, payload={})
    if age_minutes:
        ProcessingJob.objects.filter(pk=j.pk).update(updated_at=timezone.now() - datetime.timedelta(minutes=age_minutes))
    return j


# ---------------------------------------------------------------------------
# Who may talk to which portal
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBlockedReason:
    def test_nothing_running_means_go(self):
        assert lock.blocked_reason(None) is None
        for portal in ("district", "hcservices", "sci"):
            assert lock.blocked_reason(portal) is None

    @pytest.mark.parametrize("job_type", ["advocate_import", "advocate_search"])
    def test_an_advocate_job_blocks_every_portal(self, advocate, job_type):
        job(advocate, job_type)
        for portal in (None, "district", "hcservices", "sci"):
            assert job_type.replace("_", " ") in lock.blocked_reason(portal)

    def test_a_tracked_case_refresh_blocks_the_case_portals_but_not_sci(self, advocate):
        job(advocate, "tracking_refresh")
        assert lock.blocked_reason(None) is None
        assert "district" in lock.blocked_reason("district")
        assert "hcservices" in lock.blocked_reason("hcservices")
        assert lock.blocked_reason("sci") is None

    def test_other_jobs_do_not_block(self, advocate):
        for t in ("document", "order_sync", "case_briefing"):
            job(advocate, t)
        assert lock.blocked_reason("district") is None

    def test_a_queued_job_does_not_block_it_may_sit_behind_a_stopped_worker(self, advocate):
        job(advocate, "advocate_search", status="queued")
        assert lock.blocked_reason(None) is None

    def test_a_running_row_with_a_stale_heartbeat_belongs_to_a_crashed_worker(self, advocate):
        job(advocate, "advocate_import", age_minutes=45)
        assert lock.blocked_reason(None) is None

    def test_a_finished_job_does_not_block(self, advocate):
        job(advocate, "advocate_import", status="succeeded")
        assert lock.blocked_reason(None) is None


@pytest.mark.django_db(transaction=True)
class TestAdvisoryLock:
    def test_a_second_run_cannot_take_the_lock(self):
        import psycopg2

        settings_dict = connection.settings_dict
        other = psycopg2.connect(
            dbname=settings_dict["NAME"], user=settings_dict["USER"], password=settings_dict["PASSWORD"],
            host=settings_dict["HOST"], port=settings_dict["PORT"],
        )
        other.autocommit = True
        cur = other.cursor()
        cur.execute("SELECT pg_advisory_lock(%s)", [lock.ADVISORY_LOCK_KEY])
        try:
            with lock.run_lock() as acquired:
                assert acquired is False
        finally:
            cur.execute("SELECT pg_advisory_unlock(%s)", [lock.ADVISORY_LOCK_KEY])
            other.close()
        with lock.run_lock() as acquired:
            assert acquired is True

    def test_the_lock_is_released_after_the_run(self):
        with lock.run_lock() as first:
            assert first
        with lock.run_lock() as second:
            assert second

    def test_a_run_that_cannot_take_the_lock_does_nothing(self, monkeypatch, advocate):
        from contextlib import contextmanager

        @contextmanager
        def held():
            yield False

        hearing = make_hearing(advocate, make_case(advocate, "WP/1/2026", tracking_config={"hc_court_code": "telangana"}), DAY)
        monkeypatch.setattr(lock, "run_lock", held)
        report = service.run([DAY])
        assert report.not_run_reason and report.groups == []
        hearing.refresh_from_db()
        assert hearing.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED


# ---------------------------------------------------------------------------
# service.run() honouring them
# ---------------------------------------------------------------------------


@pytest.fixture
def two_courts(advocate, monkeypatch, settings):
    """A Telangana hearing (hcservices portal) and a located district hearing."""
    settings.CAUSE_LIST_LOCK_WAIT_SECONDS = 600
    settings.CAUSE_LIST_LOCK_POLL_SECONDS = 30
    tele = make_hearing(advocate, make_case(advocate, "WP/1/2026", tracking_config={"hc_court_code": "telangana"}), DAY)
    district = make_hearing(
        advocate,
        make_case(advocate, "OS/1/2026", court_type="district", cnr_number="TSHC010000012026", court_locator=LOCATOR),
        DAY,
    )
    order = []
    monkeypatch.setattr(type(telangana_adapter()), "fetch", lambda self, t, d, w: order.append("hc") or FetchResult(status="none_available"))
    monkeypatch.setattr(type(dc.get_adapter()), "fetch", lambda self, t, d, w: order.append("district") or FetchResult(status="none_available"))
    return tele, district, order


@pytest.mark.django_db
class TestRunHonoursTheLocks:
    def test_unblocked_both_run_hcservices_before_district(self, two_courts):
        tele, district, order = two_courts
        service.run([DAY])
        assert order == ["hc", "district"]

    def test_a_refresh_makes_only_the_case_portals_wait_and_they_run_once_it_ends(self, two_courts, advocate):
        tele, district, order = two_courts
        refresh = job(advocate, "tracking_refresh")
        sleeps = []

        def sleep(seconds):
            sleeps.append(seconds)
            ProcessingJob.objects.filter(pk=refresh.pk).update(status="succeeded")

        report = service.run([DAY], sleep=sleep)
        assert sleeps == [30]
        assert order == ["hc", "district"] and len(report.groups) == 2 and report.skipped == []

    def test_a_district_group_that_never_gets_the_portal_is_skipped_and_left_as_it_was(self, two_courts, advocate, settings):
        tele, district, order = two_courts
        settings.CAUSE_LIST_LOCK_WAIT_SECONDS = 0
        job(advocate, "tracking_refresh")
        report = service.run([DAY])
        assert order == []  # the refresh blocks both case portals
        assert len(report.skipped) == 2 and all("waiting on" in s for s in report.skipped)
        for h in (tele, district):
            h.refresh_from_db()
            assert h.cause_list_status == Hearing.CAUSE_LIST_NOT_CHECKED

    def test_an_advocate_import_stops_the_whole_run_whatever_the_portal(self, two_courts, advocate, settings):
        tele, district, order = two_courts
        settings.CAUSE_LIST_LOCK_WAIT_SECONDS = 0
        job(advocate, "advocate_import")
        report = service.run([DAY])
        assert order == [] and len(report.skipped) == 2
        assert all("advocate import" in s for s in report.skipped)

    def test_a_job_that_starts_mid_run_stops_the_rest(self, two_courts, advocate, settings):
        tele, district, order = two_courts
        settings.CAUSE_LIST_LOCK_WAIT_SECONDS = 0
        real = type(telangana_adapter()).fetch

        def fetch_then_import_starts(self, t, d, w):
            order.append("hc")
            job(advocate, "advocate_search")
            return FetchResult(status="none_available")

        type(telangana_adapter()).fetch = fetch_then_import_starts
        try:
            report = service.run([DAY])
        finally:
            type(telangana_adapter()).fetch = real
        assert order == ["hc"]
        assert len(report.skipped) == 1 and "district" in report.skipped[0]

    def test_sci_needs_no_lock_of_its_own(self):
        assert lock.REFRESH_BLOCKERS["sci"] == ()


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


def authed(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.mark.django_db
class TestHearingApi:
    def test_the_new_fields_and_a_verify_link_are_returned(self, advocate):
        case = make_case(advocate, "WA/102/2026", tracking_config={"hc_court_code": "andhra"})
        hearing = make_hearing(advocate, case, DAY)
        Hearing.objects.filter(pk=hearing.pk).update(
            cause_list_status="listed", cause_list_item_number="3", cause_list_court_hall="1",
            cause_list_bench="LISA GILL, CHALLA GUNARANJAN", cause_list_list_type="FRESH MOTION HEARING",
        )
        from core.models import CauseListMatch

        CauseListMatch.objects.create(
            owner=advocate, hearing=hearing, item_number="3", court_hall="1", bench="LISA GILL",
            list_type="FRESH MOTION HEARING", is_primary=True,
        )
        body = authed(advocate).get(f"/api/hearings/{hearing.pk}/").json()
        assert body["cause_list_status"] == "listed"
        assert body["cause_list_bench"] == "LISA GILL, CHALLA GUNARANJAN"
        assert body["cause_list_list_type"] == "FRESH MOTION HEARING"
        assert body["cause_list_matches"][0]["item_number"] == "3"
        assert body["cause_list_verify_url"].startswith("https://hcservices.ecourts.gov.in/")
        assert body["cause_list_source_url"] == ""

    def test_clients_cannot_write_cause_list_fields(self, advocate):
        hearing = make_hearing(advocate, make_case(advocate, "WA/1/2026", tracking_config={"hc_court_code": "andhra"}), DAY)
        resp = authed(advocate).patch(
            f"/api/hearings/{hearing.pk}/",
            {"cause_list_status": "listed", "cause_list_bench": "x", "cause_list_note": "y", "cause_list_source_url": "http://z"},
            format="json",
        )
        assert resp.status_code == 200
        hearing.refresh_from_db()
        assert hearing.cause_list_status == "not_checked" and hearing.cause_list_bench == ""
        assert hearing.cause_list_note == "" and hearing.cause_list_source_url == ""

    def test_another_advocate_cannot_see_the_hearing_or_its_matches(self, advocate):
        from core.models import CauseListMatch

        hearing = make_hearing(advocate, make_case(advocate, "WA/1/2026", tracking_config={"hc_court_code": "andhra"}), DAY)
        CauseListMatch.objects.create(owner=advocate, hearing=hearing, item_number="9", is_primary=True)
        other = User.objects.create_user(username="someone-else", password="pw-123456")
        assert authed(other).get(f"/api/hearings/{hearing.pk}/").status_code == 404
        listing = authed(other).get("/api/hearings/").json()
        rows = listing["results"] if isinstance(listing, dict) else listing
        assert rows == []

    def test_the_hearing_list_costs_no_query_per_hearing_for_matches(self, advocate, django_assert_max_num_queries):
        from core.models import CauseListMatch

        case = make_case(advocate, "WA/1/2026", tracking_config={"hc_court_code": "andhra"})
        for n in range(8):
            h = Hearing.objects.create(
                owner=advocate, case=case, hearing_type="other", status="scheduled", source="manual",
                hearing_date=datetime.datetime(2026, 10, 12 + n, 5, 0, tzinfo=datetime.timezone.utc),
            )
            CauseListMatch.objects.create(owner=advocate, hearing=h, item_number=str(n), is_primary=True)
        client = authed(advocate)
        with django_assert_max_num_queries(20):
            resp = client.get("/api/hearings/")
        assert resp.status_code == 200


@pytest.mark.django_db
class TestCaseCoverage:
    def get(self, owner, case):
        return authed(owner).get(f"/api/cases/{case.pk}/").json()["cause_list_coverage"]

    def test_a_covered_high_court(self, advocate):
        cov = self.get(advocate, make_case(advocate, "WA/1/2026", tracking_config={"hc_court_code": "andhra"}))
        assert cov["status"] == "supported" and "Andhra" in cov["label"] and cov["url"]

    @pytest.mark.parametrize("hc,word", [("kerala", "Kerala"), ("mp", "Madhya Pradesh"), ("punjab", "Punjab")])
    def test_a_court_the_portal_cannot_serve_says_why(self, advocate, hc, word):
        cov = self.get(advocate, make_case(advocate, "WA/1/2026", tracking_config={"hc_court_code": hc}))
        assert cov["status"] == "unsupported" and word in cov["reason"] and cov["url"]

    def test_a_district_case_not_yet_located_is_pending(self, advocate):
        case = make_case(advocate, "OS/1/2026", court_type="district", cnr_number="TSHC010000012026")
        assert self.get(advocate, case)["status"] == "pending"

    def test_a_located_district_case_is_covered(self, advocate):
        case = make_case(advocate, "OS/1/2026", court_type="district", cnr_number="TSHC010000012026", court_locator=LOCATOR)
        assert self.get(advocate, case)["status"] == "supported"

    def test_coverage_makes_no_network_call(self, advocate, monkeypatch):
        import socket

        monkeypatch.setattr(socket.socket, "connect", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network!")))
        cov = self.get(advocate, make_case(advocate, "WA/1/2026", tracking_config={"hc_court_code": "bombay"}))
        assert cov["status"] == "supported"


# ---------------------------------------------------------------------------
# The locator flow
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestLocatorWrittenByTheRefresh:
    def data(self, **hints):
        from core.services.court_data.models import CourtCaseData

        return CourtCaseData(cnr="TSHC010030082026", locator_hints=hints)

    def test_a_fetch_with_hints_stores_the_locator(self, advocate):
        from core.services.court_tracking import _apply_case_data

        case = make_case(advocate, "OS/336/2026", court_type="district", cnr_number="TSHC010030082026")
        _apply_case_data(case, self.data(state_code="29", dist_code="2", est_code="2", court_no="1"))
        case.refresh_from_db()
        assert case.court_locator == {**LOCATOR, "complex_code": ""}

    def test_a_cascade_case_gets_its_complex_from_its_own_tracking_config(self, advocate):
        from core.services.court_tracking import _apply_case_data

        case = make_case(
            advocate, "OS/336/2026", court_type="district", cnr_number="TSHC010030082026",
            tracking_config={"state_code": "29", "dist_code": "2", "court_complex_code": "1290019", "est_code": "2"},
        )
        _apply_case_data(case, self.data(state_code="29", dist_code="2", est_code="2", court_no="1"))
        case.refresh_from_db()
        assert case.court_locator["complex_code"] == "1290019"

    def test_a_fetch_without_hints_leaves_the_locator_alone(self, advocate):
        from core.services.court_tracking import _apply_case_data

        case = make_case(advocate, "OS/336/2026", court_type="district", cnr_number="TSHC010030082026", court_locator=LOCATOR)
        _apply_case_data(case, self.data())
        case.refresh_from_db()
        assert case.court_locator == LOCATOR

    def test_the_case_moving_courts_updates_the_court_number_and_keeps_the_complex(self, advocate):
        from core.services.court_tracking import _apply_case_data

        case = make_case(advocate, "OS/336/2026", court_type="district", cnr_number="TSHC010030082026", court_locator=LOCATOR)
        _apply_case_data(case, self.data(state_code="29", dist_code="2", est_code="2", court_no="9"))
        case.refresh_from_db()
        assert case.court_locator["court_no"] == "9" and case.court_locator["complex_code"] == "1290019"


@pytest.mark.django_db
class TestBackfillCommand:
    def upcoming(self, owner, case):
        return Hearing.objects.create(
            owner=owner, case=case, hearing_type="other", status="scheduled", source="manual",
            hearing_date=timezone.now() + datetime.timedelta(days=3),
        )

    def cases(self, owner):
        complete = make_case(owner, "OS/1/2026", court_type="district", cnr_number="TSHC010000012026", court_locator=LOCATOR)
        cascade = make_case(
            owner, "OS/2/2026", court_type="district", cnr_number="TSHC010000022026",
            tracking_config={"state_code": "29", "dist_code": "2", "court_complex_code": "1290019", "est_code": "2"},
        )
        CourtFetchLog.objects.create(
            owner=owner, case=cascade, success=True, fields_changed={"snapshot": {"court_and_judge": "4-SOMEONE"}}
        )
        bare = make_case(owner, "OS/3/2026", court_type="district", cnr_number="TSHC010000032026")
        quiet = make_case(owner, "OS/4/2026", court_type="district", cnr_number="TSHC010000042026")  # no upcoming hearing
        for c in (complete, cascade, bare):
            self.upcoming(owner, c)
        return complete, cascade, bare, quiet

    def test_dry_run_reports_and_changes_nothing(self, advocate, capsys):
        complete, cascade, bare, quiet = self.cases(advocate)
        call_command("backfill_court_locators", "--dry-run")
        out = capsys.readouterr().out
        assert "already complete: 1" in out and "filled from stored data: 1" in out and "need a portal lookup: 1" in out
        cascade.refresh_from_db()
        assert cascade.court_locator is None

    def test_stored_data_is_used_first_with_no_portal_call(self, advocate, monkeypatch, capsys):
        complete, cascade, bare, quiet = self.cases(advocate)
        monkeypatch.setattr(
            "core.services.court_data.ecourts_provider.EcourtsProvider.fetch_case_by_cnr",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("no portal call expected for the cascade case")),
        )
        call_command("backfill_court_locators", "--limit", "0")
        cascade.refresh_from_db()
        assert cascade.court_locator == {**LOCATOR, "court_no": "4"}

    def test_remaining_cases_cost_one_throttled_lookup_each_up_to_the_limit(self, advocate, monkeypatch, capsys):
        from core.services.court_data.models import CourtCaseData

        complete, cascade, bare, quiet = self.cases(advocate)
        second = make_case(advocate, "OS/5/2026", court_type="district", cnr_number="TSHC010000052026")
        self.upcoming(advocate, second)
        lookups, sleeps = [], []
        hints = {"state_code": "29", "dist_code": "2", "est_code": "2", "court_no": "3"}

        def fetch(self, cnr, court_type):
            lookups.append(cnr)
            return CourtCaseData(cnr=cnr, locator_hints=hints)

        monkeypatch.setattr("core.services.court_data.ecourts_provider.EcourtsProvider.fetch_case_by_cnr", fetch)
        monkeypatch.setattr("core.management.commands.backfill_court_locators.complete_complex", lambda loc, provider=None: {**loc, "complex_code": "1290019"})
        monkeypatch.setattr("time.sleep", lambda s: sleeps.append(s))
        call_command("backfill_court_locators", "--limit", "1", "--sleep", "7")

        assert len(lookups) == 1 and sleeps == [7.0]
        located = Case.objects.filter(cnr_number=lookups[0]).get()
        assert located.court_locator["court_no"] == "3" and located.court_locator["complex_code"] == "1290019"
        assert "1 left for the next run" in capsys.readouterr().out

    def test_it_stops_when_an_advocate_search_is_running(self, advocate, monkeypatch, capsys):
        complete, cascade, bare, quiet = self.cases(advocate)
        job(advocate, "advocate_search")
        calls = []
        monkeypatch.setattr("core.services.court_data.ecourts_provider.EcourtsProvider.fetch_case_by_cnr", lambda *a, **k: calls.append(1))
        call_command("backfill_court_locators")
        assert calls == [] and "Stopping" in capsys.readouterr().out
