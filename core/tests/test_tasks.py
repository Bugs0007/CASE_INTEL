"""Tasks: the API for manual tasks, and idempotent system-task generation.

Cross-tenant isolation for /api/tasks/ lives with the other isolation tests
in test_multi_tenancy.py (TestTaskIsolation).
"""

from datetime import date, timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Case, CourtOrder, Task
from core.services.tasks import (
    OUTCOME_CREATED,
    OUTCOME_SKIPPED,
    OUTCOME_UNCHANGED,
    OUTCOME_UPDATED,
    upsert_system_task,
)


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="task-advocate", password="pw-12345")


@pytest.fixture
def other_advocate(db):
    return User.objects.create_user(username="task-other", password="pw-12345")


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


@pytest.fixture
def case(advocate):
    return Case.objects.create(owner=advocate, case_number="WP/100/2026", title="Rao vs State")


@pytest.fixture
def order(advocate, case):
    return CourtOrder.objects.create(
        owner=advocate,
        case=case,
        order_number="1",
        order_date=date(2026, 9, 1),
        dedup_key="CNR:1:2026-09-01",
    )


def _system_task(owner, case, **overrides):
    values = {
        "owner": owner,
        "case": case,
        "kind": Task.KIND_ORDER_DIRECTION,
        "dedup_key": "order:1:respondent:abc",
        "title": "File counter affidavit",
        "due_date": date(2026, 9, 29),
        "due_date_basis": Task.BASIS_RELATIVE_TO_ORDER,
        "source_text": "Respondent to file counter within 4 weeks.",
    }
    values.update(overrides)
    return upsert_system_task(**values)


# ---------------------------------------------------------------------------
# API: manual tasks
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestTaskApi:
    def test_create_is_always_manual_and_owned_by_caller(self, api, advocate, case):
        resp = api.post(
            "/api/tasks/",
            {
                "title": "Collect vakalat",
                "case": case.id,
                "due_date": "2026-10-01",
                # Provenance fields are read-only -- a client can't forge a
                # system task.
                "kind": Task.KIND_LIMITATION,
                "rule_key": "art_116_a",
                "user_modified": True,
            },
            format="json",
        )

        assert resp.status_code == 201, resp.data
        task = Task.objects.get(id=resp.data["id"])
        assert task.owner == advocate
        assert task.kind == Task.KIND_MANUAL
        assert task.rule_key == ""
        assert task.user_modified is False
        assert task.due_date == date(2026, 10, 1)
        assert resp.data["case_number"] == "WP/100/2026"

    def test_title_is_required(self, api, case):
        resp = api.post("/api/tasks/", {"case": case.id}, format="json")
        assert resp.status_code == 400
        assert "title" in resp.data

    def test_task_without_a_case_is_allowed(self, api):
        resp = api.post("/api/tasks/", {"title": "Renew bar membership"}, format="json")
        assert resp.status_code == 201
        assert resp.data["case"] is None

    def test_completing_stamps_completed_at_and_reopening_clears_it(self, api, advocate):
        task = Task.objects.create(owner=advocate, title="Draft reply")

        resp = api.patch(f"/api/tasks/{task.id}/", {"status": "completed"}, format="json")
        assert resp.status_code == 200
        task.refresh_from_db()
        assert task.completed_at is not None

        resp = api.patch(f"/api/tasks/{task.id}/", {"status": "pending"}, format="json")
        task.refresh_from_db()
        assert task.completed_at is None

    def test_editing_a_system_task_marks_it_user_modified(self, api, advocate, case):
        task, _ = _system_task(advocate, case)

        resp = api.patch(f"/api/tasks/{task.id}/", {"due_date": "2026-10-05"}, format="json")

        assert resp.status_code == 200
        task.refresh_from_db()
        assert task.user_modified is True
        assert task.due_date == date(2026, 10, 5)

    def test_confirming_a_suggestion_is_not_a_user_edit(self, api, advocate, case):
        task, _ = _system_task(advocate, case, needs_review=True)

        resp = api.patch(f"/api/tasks/{task.id}/", {"needs_review": False}, format="json")

        assert resp.status_code == 200
        task.refresh_from_db()
        assert task.needs_review is False
        assert task.user_modified is False

    def test_patch_with_unchanged_values_is_not_a_user_edit(self, api, advocate, case):
        task, _ = _system_task(advocate, case)

        api.patch(f"/api/tasks/{task.id}/", {"title": task.title}, format="json")

        task.refresh_from_db()
        assert task.user_modified is False

    def test_manual_task_can_be_deleted(self, api, advocate):
        task = Task.objects.create(owner=advocate, title="Scratch")
        resp = api.delete(f"/api/tasks/{task.id}/")
        assert resp.status_code == 204
        assert not Task.objects.filter(id=task.id).exists()

    def test_system_task_cannot_be_deleted_only_dismissed(self, api, advocate, case):
        task, _ = _system_task(advocate, case)

        resp = api.delete(f"/api/tasks/{task.id}/")
        assert resp.status_code == 400
        assert resp.data["code"] == "system_task_not_deletable"
        assert Task.objects.filter(id=task.id).exists()

        resp = api.patch(f"/api/tasks/{task.id}/", {"status": "cancelled"}, format="json")
        assert resp.status_code == 200


@pytest.mark.django_db
class TestTaskListFilters:
    @pytest.fixture
    def tasks(self, advocate, case):
        today = timezone.localdate()
        other_case = Case.objects.create(owner=advocate, case_number="OS/7/2025", title="Other")
        return {
            "overdue": Task.objects.create(
                owner=advocate, case=case, title="overdue", due_date=today - timedelta(days=2)
            ),
            "soon": Task.objects.create(
                owner=advocate, case=case, title="soon", due_date=today + timedelta(days=3)
            ),
            "later": Task.objects.create(
                owner=advocate, case=other_case, title="later", due_date=today + timedelta(days=40)
            ),
            "undated": Task.objects.create(owner=advocate, case=case, title="undated"),
            "done": Task.objects.create(
                owner=advocate,
                case=case,
                title="done",
                status=Task.STATUS_COMPLETED,
                due_date=today - timedelta(days=5),
            ),
            "review": Task.objects.create(
                owner=advocate,
                case=case,
                title="review",
                kind=Task.KIND_LIMITATION,
                dedup_key="limitation:1",
                needs_review=True,
                due_date=today + timedelta(days=20),
            ),
        }

    @staticmethod
    def _titles(resp):
        assert resp.status_code == 200, resp.data
        return [t["title"] for t in resp.data]

    def test_default_order_is_by_due_date_with_undated_last(self, api, tasks):
        titles = self._titles(api.get("/api/tasks/"))
        assert titles[0] == "done"
        assert titles[-1] == "undated"

    def test_open_excludes_completed_and_cancelled(self, api, tasks):
        titles = self._titles(api.get("/api/tasks/", {"status": "open"}))
        assert "done" not in titles
        assert {"overdue", "soon", "later", "undated", "review"} <= set(titles)

    def test_overdue_is_open_and_past_due(self, api, tasks):
        assert self._titles(api.get("/api/tasks/", {"overdue": "true"})) == ["overdue"]

    def test_due_before_is_inclusive_and_skips_undated(self, api, tasks):
        cutoff = (timezone.localdate() + timedelta(days=3)).isoformat()
        titles = self._titles(api.get("/api/tasks/", {"status": "open", "due_before": cutoff}))
        assert titles == ["overdue", "soon"]

    def test_invalid_due_before_is_a_400(self, api, tasks):
        resp = api.get("/api/tasks/", {"due_before": "next week"})
        assert resp.status_code == 400
        assert "due_before" in resp.data

    def test_case_kind_and_needs_review_filters(self, api, case, tasks):
        case_titles = set(self._titles(api.get("/api/tasks/", {"case_id": case.id})))
        assert "later" not in case_titles
        assert self._titles(api.get("/api/tasks/", {"kind": "limitation"})) == ["review"]
        assert self._titles(api.get("/api/tasks/", {"needs_review": "true"})) == ["review"]


# ---------------------------------------------------------------------------
# upsert_system_task
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestUpsertSystemTask:
    def test_creates_then_is_idempotent(self, advocate, case, order):
        task, outcome = _system_task(advocate, case, source_order=order)
        assert outcome == OUTCOME_CREATED
        assert task.kind == Task.KIND_ORDER_DIRECTION
        assert task.source_order == order

        again, outcome = _system_task(advocate, case, source_order=order)
        assert outcome == OUTCOME_UNCHANGED
        assert again.id == task.id
        assert Task.objects.count() == 1

    def test_refreshes_an_untouched_task(self, advocate, case):
        task, _ = _system_task(advocate, case)

        updated, outcome = _system_task(advocate, case, due_date=date(2026, 10, 6))

        assert outcome == OUTCOME_UPDATED
        assert updated.id == task.id
        task.refresh_from_db()
        assert task.due_date == date(2026, 10, 6)

    @pytest.mark.parametrize(
        "change",
        [
            {"user_modified": True},
            {"status": Task.STATUS_COMPLETED},
            {"status": Task.STATUS_CANCELLED},
        ],
    )
    def test_never_touches_a_task_the_advocate_owns_now(self, advocate, case, change):
        task, _ = _system_task(advocate, case)
        Task.objects.filter(id=task.id).update(**change)

        _, outcome = _system_task(advocate, case, due_date=date(2027, 1, 1), title="Rewritten")

        assert outcome == OUTCOME_SKIPPED
        task.refresh_from_db()
        assert task.due_date == date(2026, 9, 29)
        assert task.title == "File counter affidavit"

    def test_needs_review_applies_only_on_creation(self, advocate, case):
        task, _ = _system_task(advocate, case, needs_review=True)
        Task.objects.filter(id=task.id).update(needs_review=False)

        _system_task(advocate, case, needs_review=True, due_date=date(2026, 10, 1))

        task.refresh_from_db()
        assert task.needs_review is False

    def test_same_dedup_key_is_independent_per_owner(self, advocate, other_advocate, case):
        other_case = Case.objects.create(owner=other_advocate, case_number="WP/100/2026", title="x")

        _, first = _system_task(advocate, case)
        _, second = _system_task(other_advocate, other_case)

        assert (first, second) == (OUTCOME_CREATED, OUTCOME_CREATED)
        assert Task.objects.count() == 2

    def test_rejects_a_case_owned_by_someone_else(self, advocate, other_advocate):
        foreign_case = Case.objects.create(owner=other_advocate, case_number="X/1/2026", title="x")
        with pytest.raises(ValueError):
            _system_task(advocate, foreign_case)

    @pytest.mark.parametrize(
        "overrides", [{"kind": Task.KIND_MANUAL}, {"dedup_key": ""}]
    )
    def test_rejects_manual_or_unkeyed_tasks(self, advocate, case, overrides):
        with pytest.raises(ValueError):
            _system_task(advocate, case, **overrides)
