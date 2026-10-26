"""manage.py requeue_order_sync: dry run by default, throttled, idempotent."""

from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from core.models import Case, CourtOrder, Document, ProcessingJob

NOW = timezone.now()


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="requeue-advocate", password="pw-12345")


@pytest.fixture
def other(db):
    return User.objects.create_user(username="requeue-other", password="pw-12345")


def _case(owner, n, **extra):
    fields = dict(
        court_type="district", tracking_enabled=True,
        tracking_config={"court_type": "district", "cnr": f"TSHY01{n:010d}"},
    )
    fields.update(extra)
    return Case.objects.create(owner=owner, case_number=f"R/{n}", title=f"R{n}", client_name="C", **fields)


def _job(case, status, ago=timedelta(hours=1)):
    finished = status in ("succeeded", "partial", "failed")
    return ProcessingJob.objects.create(
        owner=case.owner, case=case, job_type="order_sync", status=status,
        finished_at=NOW - ago if finished else None,
    )


def run(*args):
    out = StringIO()
    call_command("requeue_order_sync", "--spacing", "0", *args, stdout=out)
    return out.getvalue()


def queued_case_ids():
    return set(
        ProcessingJob.objects.filter(job_type="order_sync", status="queued").values_list("case_id", flat=True)
    )


class TestSelection:
    def test_dry_run_is_the_default_and_writes_nothing(self, advocate):
        _case(advocate, 1)
        output = run()
        assert "DRY RUN" in output and "would enqueue case" in output
        assert ProcessingJob.objects.count() == 0

    def test_apply_enqueues_tracked_district_cases_only(self, advocate):
        district = _case(advocate, 1)
        _case(advocate, 2, court_type="high_court", tracking_config={"court_type": "high_court", "cnr": "HBHC010000000002"})
        _case(advocate, 3, tracking_enabled=False)
        _case(advocate, 4, tracking_config={"court_type": "district"})  # no CNR anywhere
        has_column_cnr = _case(advocate, 5, tracking_config={"court_type": "district"}, cnr_number="TSHY010000000005")
        run("--apply")
        assert queued_case_ids() == {district.id, has_column_cnr.id}

    def test_court_type_all_includes_high_courts(self, advocate):
        hc = _case(advocate, 2, court_type="high_court", tracking_config={"court_type": "high_court", "cnr": "HBHC010000000002"})
        district = _case(advocate, 1)
        run("--apply", "--court-type", "all")
        assert queued_case_ids() == {hc.id, district.id}

    def test_cases_with_a_downloaded_order_are_left_alone(self, advocate):
        done = _case(advocate, 1)
        doc = Document.objects.create(owner=advocate, case=done, filename="o.pdf", file_path="documents/o.pdf")
        CourtOrder.objects.create(owner=advocate, case=done, order_number="1", dedup_key="k", document=doc)
        # A pending (PDF-less) order does not count as downloaded.
        pending = _case(advocate, 2)
        CourtOrder.objects.create(
            owner=advocate, case=pending, order_number="1", dedup_key="k2", download_status="pending"
        )
        run("--apply")
        assert queued_case_ids() == {pending.id}

    def test_a_case_with_a_job_in_flight_is_skipped(self, advocate):
        busy = _case(advocate, 1)
        _job(busy, "running")
        free = _case(advocate, 2)
        run("--apply")
        assert queued_case_ids() == {free.id}

    def test_recently_clean_cases_are_skipped_but_failed_partial_and_old_ones_are_not(self, advocate):
        fresh = _case(advocate, 1)
        _job(fresh, "succeeded", ago=timedelta(hours=2))
        old = _case(advocate, 2)
        _job(old, "succeeded", ago=timedelta(days=3))
        failed = _case(advocate, 3)
        _job(failed, "failed", ago=timedelta(minutes=5))
        partial = _case(advocate, 4)
        _job(partial, "partial", ago=timedelta(minutes=5))
        run("--apply")
        assert queued_case_ids() == {old.id, failed.id, partial.id}

    def test_min_age_can_be_widened(self, advocate):
        recent = _case(advocate, 1)
        _job(recent, "succeeded", ago=timedelta(hours=30))
        run("--apply", "--min-age-hours", "48")
        assert queued_case_ids() == set()

    def test_owner_filter_scopes_to_one_advocate(self, advocate, other):
        mine = _case(advocate, 1)
        _case(other, 2)
        run("--apply", "--owner", advocate.username)
        assert queued_case_ids() == {mine.id}

    def test_unknown_owner_is_an_error(self, advocate):
        with pytest.raises(CommandError):
            run("--owner", "nobody")


class TestThrottling:
    def test_limit_caps_one_run_and_never_checked_cases_go_first(self, advocate):
        checked = [_case(advocate, n) for n in range(1, 4)]
        for case in checked:
            _job(case, "failed", ago=timedelta(days=5))
        never = [_case(advocate, n) for n in range(10, 13)]
        output = run("--apply", "--limit", "3")
        assert queued_case_ids() == {c.id for c in never}
        assert "3 more eligible case(s) left for a later run" in output

    def test_max_in_flight_counts_jobs_already_queued_anywhere(self, advocate, other):
        _job(_case(other, 50), "queued")
        _job(_case(other, 51), "running")
        cases = [_case(advocate, n) for n in range(1, 6)]
        run("--apply", "--max-in-flight", "3", "--limit", "10")
        new = queued_case_ids() - {c.id for c in Case.objects.filter(owner=other)}
        assert len(new) == 1 and new <= {c.id for c in cases}

    def test_full_pipeline_enqueues_nothing(self, advocate):
        _case(advocate, 1)
        for n in range(5):
            _job(_case(advocate, 100 + n), "queued")
        before = ProcessingJob.objects.count()
        run("--apply", "--max-in-flight", "5")
        assert ProcessingJob.objects.count() == before

    def test_bad_limits_are_rejected(self, advocate):
        with pytest.raises(CommandError):
            run("--limit", "0")


class TestIdempotence:
    def test_running_apply_twice_queues_each_case_once(self, advocate):
        cases = [_case(advocate, n) for n in range(1, 4)]
        run("--apply")
        run("--apply")
        jobs = ProcessingJob.objects.filter(job_type="order_sync")
        assert jobs.count() == 3 and {j.case_id for j in jobs} == {c.id for c in cases}

    def test_a_case_whose_job_succeeded_drops_out(self, advocate):
        case = _case(advocate, 1)
        run("--apply")
        ProcessingJob.objects.filter(case=case).update(status="succeeded", finished_at=timezone.now())
        run("--apply")
        assert ProcessingJob.objects.filter(case=case).count() == 1


class TestRetryFailed:
    def test_apply_with_retry_failed_resets_given_up_orders(self, advocate):
        case = _case(advocate, 1)
        row = CourtOrder.objects.create(
            owner=advocate, case=case, order_number="1", dedup_key="k", download_status="failed",
            download_attempts=6, last_download_error="x",
        )
        run("--apply", "--retry-failed")
        row.refresh_from_db()
        assert (row.download_status, row.download_attempts, row.last_download_error) == ("pending", 0, "")

    def test_dry_run_with_retry_failed_resets_nothing(self, advocate):
        case = _case(advocate, 1)
        row = CourtOrder.objects.create(
            owner=advocate, case=case, order_number="1", dedup_key="k", download_status="failed", download_attempts=6
        )
        output = run("--retry-failed")
        row.refresh_from_db()
        assert row.download_status == "failed" and "1 failed order(s) to retry" in output

    def test_without_the_flag_failed_orders_are_untouched(self, advocate):
        case = _case(advocate, 1)
        row = CourtOrder.objects.create(
            owner=advocate, case=case, order_number="1", dedup_key="k", download_status="failed"
        )
        run("--apply")
        row.refresh_from_db()
        assert row.download_status == "failed"
