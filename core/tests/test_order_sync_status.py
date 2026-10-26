"""The order-check status on a case (`order_sync` on GET /api/cases/ and
/api/cases/<id>/): never / queued / running / ok / partial / failed, and a
later success clearing an earlier failure.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import AppearanceFee, Case, Client, CourtOrder, Document, Hearing, ProcessingJob
from core.services import bulk_refresh

NOW = timezone.now()
RAW = "Invalid Captcha after 3 attempts for Ramesh Kumar vs State"  # must never be echoed


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="status-advocate", password="pw-12345")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="status-other", password="pw-12345")


def _api(user):
    client = APIClient()
    client.force_authenticate(user=user)
    return client


def _case(owner, number="A/1", **extra):
    return Case.objects.create(owner=owner, case_number=number, title=number, client_name="C", **extra)


def _job(case, status, *, ago=timedelta(hours=1), error="", payload=None, owner=None):
    finished = status in ("succeeded", "partial", "failed")
    return ProcessingJob.objects.create(
        owner=owner or case.owner, case=case, job_type="order_sync", status=status, error=error,
        payload=payload or {}, finished_at=NOW - ago if finished else None,
    )


def _summary(user, case, detail=False):
    if detail:
        return _api(user).get(f"/api/cases/{case.id}/").json()["order_sync"]
    rows = _api(user).get("/api/cases/").json()
    return next(r for r in rows if r["id"] == case.id)["order_sync"]


@pytest.fixture(params=["list", "detail"])
def read(request, advocate):
    """Both endpoints must tell the same story."""
    return lambda case: _summary(advocate, case, detail=request.param == "detail")


class TestStates:
    def test_never_when_no_sync_has_run(self, advocate, read):
        assert read(_case(advocate)) == {
            "state": "never", "last_checked_at": None, "last_success_at": None,
            "found": 0, "downloaded": 0, "reason": None,
        }

    def test_queued_and_running(self, advocate, read):
        queued = _case(advocate, "Q/1")
        _job(queued, "queued")
        running = _case(advocate, "R/1")
        _job(running, "running")
        assert read(queued)["state"] == "queued"
        assert read(running)["state"] == "running"

    def test_ok_with_zero_orders_found(self, advocate, read):
        case = _case(advocate)
        _job(case, "succeeded", payload={"result": {"listed": 0}})
        summary = read(case)
        assert (summary["state"], summary["found"], summary["downloaded"], summary["reason"]) == ("ok", 0, 0, None)
        assert summary["last_checked_at"] and summary["last_success_at"]

    def test_ok_counts_found_and_downloaded_orders(self, advocate, read):
        case = _case(advocate)
        _job(case, "succeeded")
        doc = Document.objects.create(owner=advocate, case=case, filename="o.pdf", file_path="documents/o.pdf")
        CourtOrder.objects.create(owner=advocate, case=case, order_number="1", dedup_key="k1", document=doc)
        CourtOrder.objects.create(
            owner=advocate, case=case, order_number="2", dedup_key="k2", download_status="pending"
        )
        summary = read(case)
        assert (summary["found"], summary["downloaded"]) == (2, 1)

    def test_partial_carries_the_stored_reason_label(self, advocate, read):
        case = _case(advocate)
        _job(case, "partial", error="1 order PDF(s) could not be downloaded", payload={"result": {"reason": "captcha"}})
        summary = read(case)
        assert (summary["state"], summary["reason"]) == ("partial", "CAPTCHA not read")
        assert summary["last_success_at"]  # the listing itself worked

    def test_failed_maps_the_error_to_a_label_and_never_echoes_it(self, advocate, read):
        case = _case(advocate)
        _job(case, "failed", error=RAW)
        summary = read(case)
        assert (summary["state"], summary["reason"]) == ("failed", "CAPTCHA not read")
        assert summary["last_checked_at"] and summary["last_success_at"] is None
        assert "Ramesh" not in str(summary)

    @pytest.mark.parametrize(
        "error, label",
        [
            ("OCR failed to read the CAPTCHA image.", "CAPTCHA not read"),
            ("Server disconnected without sending a response", "court portal didn't answer"),
            ("unrecognized portal response", "court portal didn't answer"),
            ("KeyError: 'x'", "other"),
            ("", "other"),
        ],
    )
    def test_reason_labels(self, advocate, read, error, label):
        case = _case(advocate)
        _job(case, "failed", error=error)
        assert read(case)["reason"] == label

    def test_a_later_success_clears_an_earlier_failure(self, advocate, read):
        case = _case(advocate)
        _job(case, "failed", error=RAW, ago=timedelta(days=2))
        _job(case, "succeeded", ago=timedelta(hours=1))
        summary = read(case)
        assert (summary["state"], summary["reason"]) == ("ok", None)

    def test_a_later_failure_replaces_an_earlier_success_but_keeps_last_success(self, advocate, read):
        case = _case(advocate)
        _job(case, "succeeded", ago=timedelta(days=3))
        _job(case, "failed", error=RAW, ago=timedelta(hours=1))
        summary = read(case)
        assert summary["state"] == "failed"
        assert summary["last_success_at"] is not None
        assert summary["last_success_at"] < summary["last_checked_at"]

    def test_a_queued_retry_after_a_failure_reads_queued(self, advocate, read):
        case = _case(advocate)
        _job(case, "failed", error=RAW, ago=timedelta(hours=3))
        _job(case, "queued")
        summary = read(case)
        assert (summary["state"], summary["reason"]) == ("queued", None)
        assert summary["last_checked_at"] is not None

    def test_cancelled_jobs_are_ignored(self, advocate, read):
        case = _case(advocate)
        _job(case, "succeeded", ago=timedelta(days=1))
        ProcessingJob.objects.create(owner=advocate, case=case, job_type="order_sync", status="cancelled")
        assert read(case)["state"] == "ok"

    def test_other_job_types_do_not_count(self, advocate, read):
        case = _case(advocate)
        ProcessingJob.objects.create(
            owner=advocate, case=case, job_type="case_briefing", status="succeeded", finished_at=NOW
        )
        assert read(case)["state"] == "never"


class TestIsolation:
    def test_another_advocates_jobs_and_orders_never_show(self, advocate, other):
        mine = _case(advocate, "M/1")
        theirs = _case(other, "T/1")
        _job(theirs, "failed", error=RAW, owner=other)
        CourtOrder.objects.create(owner=other, case=theirs, order_number="1", dedup_key="k")
        assert _summary(advocate, mine)["state"] == "never"
        listed = _api(advocate).get("/api/cases/").json()
        assert [c["case_number"] for c in listed] == ["M/1"]
        assert _api(advocate).get(f"/api/cases/{theirs.id}/").status_code == 404
        assert _summary(other, theirs)["state"] == "failed"


class TestOtherEndpointsKeepWorking:
    def test_a_freshly_created_case_serializes_with_a_never_status(self, advocate):
        response = _api(advocate).post(
            "/api/cases/", {"case_number": "N/1", "title": "N", "client_name": "C"}, format="json"
        )
        assert response.status_code == 201, response.content
        assert response.json()["order_sync"]["state"] == "never"
        assert response.json()["document_count"] == 0


class TestRefreshThenFreshRequest:
    """Refresh runs, the order-sync job it queues finishes, and a brand-new
    request tells the truth: document_count counts saved documents only and
    order_sync says what the check found."""

    def test_district_case_after_refresh_and_sync(self, advocate):
        case = _case(
            advocate, "T/1", court_type="district",
            tracking_config={"court_type": "district", "cnr": "TSHY010000000001"}, tracking_enabled=True,
        )
        ok = {"rate_limited": False, "new_hearing_dates": [], "client_update_drafts": 0}
        with patch("core.services.court_tracking.refresh_case_tracking", return_value=ok):
            bulk_refresh.run_tracking_refresh(bulk_refresh.start_bulk_refresh(advocate))
        assert _summary(advocate, case)["state"] == "never"  # refresh alone checks nothing

        _job(case, "succeeded", payload={"result": {"listed": 0}})
        row = next(r for r in _api(advocate).get("/api/cases/").json() if r["id"] == case.id)
        assert row["document_count"] == 0
        assert (row["order_sync"]["state"], row["order_sync"]["found"]) == ("ok", 0)

        doc = Document.objects.create(owner=advocate, case=case, filename="o.pdf", file_path="documents/o.pdf")
        CourtOrder.objects.create(owner=advocate, case=case, order_number="1", dedup_key="k", document=doc)
        row = next(r for r in _api(advocate).get("/api/cases/").json() if r["id"] == case.id)
        assert row["document_count"] == 1
        assert (row["order_sync"]["found"], row["order_sync"]["downloaded"]) == (1, 1)


class TestQueryCount:
    def _populate(self, advocate, start, count):
        client = Client.objects.create(owner=advocate, name=f"Client {start}")
        for i in range(start, start + count):
            case = _case(advocate, f"Q/{i}", client=client)
            Document.objects.create(owner=advocate, case=case, filename=f"{i}.pdf", file_path=f"documents/{i}.pdf")
            hearing = Hearing.objects.create(
                owner=advocate, case=case, hearing_date=NOW + timedelta(days=i + 1), hearing_type="other"
            )
            AppearanceFee.objects.create(owner=advocate, hearing=hearing, amount=Decimal("500.00"))
            _job(case, "failed", error=RAW)
            CourtOrder.objects.create(owner=advocate, case=case, order_number="1", dedup_key=f"k{i}")

    def test_list_runs_the_same_number_of_queries_for_3_cases_and_for_9(self, advocate):
        self._populate(advocate, 0, 3)
        client = _api(advocate)
        with CaptureQueriesContext(connection) as few:
            assert len(client.get("/api/cases/").json()) == 3
        self._populate(advocate, 3, 6)
        with CaptureQueriesContext(connection) as many:
            body = client.get("/api/cases/").json()
        assert len(body) == 9
        assert len(many) == len(few), "\n".join(q["sql"][:200] for q in many.captured_queries)
        row = body[0]
        assert row["document_count"] == 1 and row["hearing_count"] == 1
        assert row["fee_summary"]["pending_amount"] == "500.00"
        assert row["order_sync"]["state"] == "failed" and row["order_sync"]["found"] == 1
