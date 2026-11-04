"""Case events: the advocate's own appointments on a case's calendar.

Cross-tenant isolation for /api/case-events/ lives with the other isolation
tests in test_multi_tenancy.py (TestCaseEventIsolation).
"""

from datetime import date

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from core.models import Case, CaseEvent


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="event-advocate", password="pw-12345")


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


@pytest.fixture
def case(advocate):
    return Case.objects.create(owner=advocate, case_number="OS/9/2026", title="Rao vs State")


@pytest.fixture
def other_case(advocate):
    return Case.objects.create(owner=advocate, case_number="OS/10/2026", title="Iyer vs Iyer")


def _event(owner, case, **overrides):
    values = {"owner": owner, "case": case, "title": "Mediation sitting", "date": date(2026, 11, 10)}
    values.update(overrides)
    return CaseEvent.objects.create(**values)


class TestCrud:
    def test_create_defaults_and_derived_fields(self, api, case):
        resp = api.post(
            "/api/case-events/",
            {"case": case.id, "title": "Call with client", "date": "2026-11-10"},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["event_type"] == "other"
        assert resp.data["event_type_display"] == "Other"
        assert resp.data["status"] == "scheduled"
        assert resp.data["start_time"] is None  # all-day
        assert resp.data["case_title"] == "Rao vs State"
        assert resp.data["case_number"] == "OS/9/2026"

    def test_create_stamps_owner_and_timed_event(self, api, advocate, case):
        resp = api.post(
            "/api/case-events/",
            {
                "case": case.id,
                "title": "Arbitration",
                "event_type": "arbitration",
                "date": "2026-11-10",
                "start_time": "10:30:00",
                "end_time": "12:00:00",
                "location": "Chamber 4",
                "notes": "Bring the bundle",
            },
            format="json",
        )
        assert resp.status_code == 201
        event = CaseEvent.objects.get(id=resp.data["id"])
        assert event.owner == advocate
        assert event.event_type == "arbitration"
        assert str(event.start_time) == "10:30:00"
        assert str(event.end_time) == "12:00:00"

    def test_title_is_required(self, api, case):
        resp = api.post(
            "/api/case-events/", {"case": case.id, "date": "2026-11-10"}, format="json"
        )
        assert resp.status_code == 400
        assert "title" in resp.data

    def test_unknown_event_type_is_rejected(self, api, case):
        resp = api.post(
            "/api/case-events/",
            {"case": case.id, "title": "x", "date": "2026-11-10", "event_type": "hearing"},
            format="json",
        )
        assert resp.status_code == 400
        assert "event_type" in resp.data

    def test_retrieve_update_delete(self, api, advocate, case):
        event = _event(advocate, case)

        assert api.get(f"/api/case-events/{event.id}/").status_code == 200

        resp = api.patch(
            f"/api/case-events/{event.id}/",
            {"status": "completed", "notes": "Settled the schedule"},
            format="json",
        )
        assert resp.status_code == 200
        event.refresh_from_db()
        assert event.status == "completed"
        assert event.notes == "Settled the schedule"

        assert api.delete(f"/api/case-events/{event.id}/").status_code == 204
        assert not CaseEvent.objects.filter(id=event.id).exists()

    def test_event_is_removed_with_its_case(self, advocate, case):
        event = _event(advocate, case)
        case.delete()
        assert not CaseEvent.objects.filter(id=event.id).exists()


class TestTimeValidation:
    def test_end_before_start_is_rejected(self, api, case):
        resp = api.post(
            "/api/case-events/",
            {
                "case": case.id, "title": "x", "date": "2026-11-10",
                "start_time": "11:00:00", "end_time": "10:00:00",
            },
            format="json",
        )
        assert resp.status_code == 400
        assert "end_time" in resp.data

    def test_end_equal_to_start_is_rejected(self, api, case):
        resp = api.post(
            "/api/case-events/",
            {
                "case": case.id, "title": "x", "date": "2026-11-10",
                "start_time": "10:00:00", "end_time": "10:00:00",
            },
            format="json",
        )
        assert resp.status_code == 400

    def test_end_without_start_is_rejected(self, api, case):
        resp = api.post(
            "/api/case-events/",
            {"case": case.id, "title": "x", "date": "2026-11-10", "end_time": "10:00:00"},
            format="json",
        )
        assert resp.status_code == 400
        assert "end_time" in resp.data

    def test_patch_is_judged_against_the_stored_times(self, api, advocate, case):
        event = _event(advocate, case, start_time="10:00", end_time="11:00")

        # Moving only the end before the stored start is still invalid.
        resp = api.patch(
            f"/api/case-events/{event.id}/", {"end_time": "09:00:00"}, format="json"
        )
        assert resp.status_code == 400

        # Clearing the start while an end remains is invalid too.
        resp = api.patch(
            f"/api/case-events/{event.id}/", {"start_time": None}, format="json"
        )
        assert resp.status_code == 400

        # Clearing both turns it back into an all-day event.
        resp = api.patch(
            f"/api/case-events/{event.id}/",
            {"start_time": None, "end_time": None},
            format="json",
        )
        assert resp.status_code == 200
        assert resp.data["start_time"] is None

    def test_start_without_end_is_fine(self, api, case):
        resp = api.post(
            "/api/case-events/",
            {"case": case.id, "title": "x", "date": "2026-11-10", "start_time": "15:00:00"},
            format="json",
        )
        assert resp.status_code == 201


class TestFilters:
    @pytest.fixture
    def events(self, advocate, case, other_case):
        return {
            "early": _event(advocate, case, title="early", date=date(2026, 11, 1)),
            "mid": _event(advocate, case, title="mid", date=date(2026, 11, 15)),
            "late": _event(advocate, other_case, title="late", date=date(2026, 12, 1)),
            "done": _event(
                advocate, case, title="done", date=date(2026, 11, 15), status="completed"
            ),
        }

    def _titles(self, api, **params):
        resp = api.get("/api/case-events/", params)
        assert resp.status_code == 200
        return {e["title"] for e in resp.data}

    def test_unfiltered_lists_everything_ordered_by_date(self, api, events):
        resp = api.get("/api/case-events/")
        assert [e["title"] for e in resp.data][0] == "early"
        assert len(resp.data) == 4

    def test_case_id(self, api, events, other_case):
        assert self._titles(api, case_id=other_case.id) == {"late"}

    def test_date_range_is_inclusive_on_both_ends(self, api, events):
        assert self._titles(api, date_from="2026-11-01", date_to="2026-11-15") == {
            "early", "mid", "done",
        }
        assert self._titles(api, date_from="2026-11-15", date_to="2026-11-15") == {"mid", "done"}

    def test_date_from_only_and_date_to_only(self, api, events):
        assert self._titles(api, date_from="2026-11-16") == {"late"}
        assert self._titles(api, date_to="2026-11-01") == {"early"}

    def test_status(self, api, events):
        assert self._titles(api, status="completed") == {"done"}
        assert self._titles(api, status="scheduled") == {"early", "mid", "late"}

    def test_bad_dates_are_a_400(self, api, events):
        for name in ("date_from", "date_to"):
            resp = api.get("/api/case-events/", {name: "04-11-2026"})
            assert resp.status_code == 400
            assert name in resp.data
