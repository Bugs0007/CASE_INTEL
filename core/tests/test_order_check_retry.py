"""POST /api/cases/<id>/orders/check/ -- the "Retry" on a failed order check.

It only enqueues the same `order_sync` job a tracking refresh enqueues; these
tests pin the three bounds: the caller's own tracked case, never a second
active job, and a cooldown after the previous one.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Case, ProcessingJob
from core.tests.auth_helpers import token_for

CNR = "TSHC010030082026"


def _client(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token_for(user)}")
    return client


@pytest.fixture
def alice(db):
    return User.objects.create_user(username="alice-retry", password="alice-pass-123")


@pytest.fixture
def bob(db):
    return User.objects.create_user(username="bob-retry", password="bob-pass-123")


@pytest.fixture
def case(alice):
    return Case.objects.create(
        owner=alice, case_number="OS/336/2026", title="A vs B", client_name="A",
        cnr_number=CNR, court_type="district", tracking_enabled=True,
        tracking_config={"court_type": "district", "cnr": CNR},
    )


def _url(case):
    return f"/api/cases/{case.id}/orders/check/"


def _finished_job(case, *, status="failed", minutes_ago=30):
    job = ProcessingJob.objects.create(owner=case.owner, case=case, job_type="order_sync")
    when = timezone.now() - timedelta(minutes=minutes_ago)
    ProcessingJob.objects.filter(pk=job.pk).update(status=status, created_at=when, finished_at=when)
    return job


@pytest.mark.django_db
class TestOrderCheckRetry:
    def test_queues_one_order_sync_and_says_so(self, alice, case):
        resp = _client(alice).post(_url(case))
        assert resp.status_code == 202
        assert resp.data["order_sync"]["state"] == "queued"
        jobs = ProcessingJob.objects.filter(case=case, job_type="order_sync")
        assert jobs.count() == 1
        assert jobs.get().owner == alice

    def test_a_failed_check_older_than_the_cooldown_can_be_retried(self, alice, case):
        _finished_job(case, status="failed", minutes_ago=30)
        resp = _client(alice).post(_url(case))
        assert resp.status_code == 202
        assert ProcessingJob.objects.filter(case=case, job_type="order_sync", status="queued").count() == 1

    def test_a_check_already_queued_or_running_is_not_doubled(self, alice, case):
        first = _client(alice).post(_url(case))
        second = _client(alice).post(_url(case))
        assert first.status_code == 202
        assert second.status_code == 200
        assert second.data["order_sync"]["state"] == "queued"
        assert ProcessingJob.objects.filter(case=case, job_type="order_sync").count() == 1

    def test_a_running_check_is_reported_as_running(self, alice, case):
        job, _ = ProcessingJob.enqueue_order_sync(case)
        ProcessingJob.objects.filter(pk=job.pk).update(status="running")
        resp = _client(alice).post(_url(case))
        assert resp.status_code == 200
        assert resp.data["order_sync"]["state"] == "running"
        assert ProcessingJob.objects.filter(case=case, job_type="order_sync").count() == 1

    def test_a_check_that_just_finished_is_refused_with_retry_after(self, alice, case):
        _finished_job(case, status="failed", minutes_ago=1)
        resp = _client(alice).post(_url(case))
        assert resp.status_code == 429
        assert 0 < resp.data["retry_after"] <= 5 * 60
        assert resp["Retry-After"] == str(resp.data["retry_after"])
        assert ProcessingJob.objects.filter(case=case, job_type="order_sync").count() == 1

    def test_a_cancelled_job_does_not_start_the_cooldown(self, alice, case):
        _finished_job(case, status="cancelled", minutes_ago=1)
        assert _client(alice).post(_url(case)).status_code == 202

    def test_an_untracked_case_is_refused(self, alice, case):
        Case.objects.filter(pk=case.pk).update(tracking_enabled=False)
        resp = _client(alice).post(_url(case))
        assert resp.status_code == 400
        assert not ProcessingJob.objects.filter(case=case).exists()

    def test_another_advocates_case_is_a_404_and_queues_nothing(self, bob, case):
        resp = _client(bob).post(_url(case))
        assert resp.status_code == 404
        assert not ProcessingJob.objects.filter(case=case).exists()

    def test_it_needs_a_login(self, case):
        assert APIClient().post(_url(case)).status_code == 401

    def test_get_is_not_allowed(self, alice, case):
        assert _client(alice).get(_url(case)).status_code == 405
