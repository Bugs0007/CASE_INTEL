"""The court's name on each case in GET /api/cases/ -- what the Cases page
groups by. court_names_for_cases is the batch twin of case_court_name (documents
use that one), so the two must always agree."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from core.models import Case, CourtFetchLog, Hearing
from core.services.parties import case_court_name, court_names_for_cases


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="court-name-advocate", password="pw-12345")


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


def _case(owner, number, **fields):
    return Case.objects.create(owner=owner, case_number=number, title=f"Matter {number}", **fields)


def _fetch(owner, case, snapshot, success=True):
    return CourtFetchLog.objects.create(owner=owner, case=case, success=success, fields_changed=snapshot)


def _hearing(owner, case, location, days=1):
    return Hearing.objects.create(
        owner=owner,
        case=case,
        hearing_date=timezone.now() + timedelta(days=days),
        hearing_type="other",
        source="ecourts",
        location=location,
    )


class TestCourtNamesForCases:
    def test_snapshot_beats_hearing_location_beats_cnr(self, advocate):
        from_snapshot = _case(advocate, "A/1/2026", cnr_number="HBHC010536082026")
        _fetch(advocate, from_snapshot, {"snapshot": {"court_name": "  Telangana High Court "}})
        _hearing(advocate, from_snapshot, "Some Hall")

        from_hearing = _case(advocate, "A/2/2026", cnr_number="HBHC010536082027")
        _hearing(advocate, from_hearing, "Family Court, Secunderabad")

        from_cnr = _case(advocate, "A/3/2026", cnr_number="HBHC010536082028")
        nothing = _case(advocate, "A/4/2026")

        names = court_names_for_cases([from_snapshot, from_hearing, from_cnr, nothing])
        assert names == {
            from_snapshot.id: "Telangana High Court",
            from_hearing.id: "Family Court, Secunderabad",
            from_cnr.id: "High Court for the State of Telangana at Hyderabad",
            nothing.id: "",
        }

    def test_agrees_with_case_court_name_for_every_combination(self, advocate):
        cases = []
        # snapshot only / snapshot + hearing / hearing only / CNR only / nothing /
        # a failed fetch only / a blank snapshot name falling through to the hearing
        c = _case(advocate, "B/1/2026")
        _fetch(advocate, c, {"snapshot": {"court_name": "XII Addl. Chief Metropolitan Magistrate, Hyderabad"}})
        cases.append(c)
        c = _case(advocate, "B/2/2026")
        _fetch(advocate, c, {"snapshot": {"court_name": "Sessions Court"}})
        _hearing(advocate, c, "Court Hall 3")
        cases.append(c)
        c = _case(advocate, "B/3/2026")
        _hearing(advocate, c, "Court Hall 3", days=1)
        _hearing(advocate, c, "Court Hall 9", days=5)  # the later hearing wins, as in case_court_name
        cases.append(c)
        cases.append(_case(advocate, "B/4/2026", cnr_number="DLHC010000012026"))
        cases.append(_case(advocate, "B/5/2026"))
        c = _case(advocate, "B/6/2026")
        _fetch(advocate, c, {"snapshot": {"court_name": "Ignored: the fetch failed"}}, success=False)
        cases.append(c)
        c = _case(advocate, "B/7/2026")
        _fetch(advocate, c, {"snapshot": {"court_name": "   "}})
        _hearing(advocate, c, "Court Hall 3")
        cases.append(c)

        batch = court_names_for_cases(cases)
        for case in cases:
            assert batch[case.id] == case_court_name(case), case.case_number

    def test_only_the_latest_successful_fetch_counts(self, advocate):
        case = _case(advocate, "C/1/2026")
        new = _fetch(advocate, case, {"snapshot": {"court_name": "New Court Name"}})
        old = _fetch(advocate, case, {"snapshot": {"court_name": "Old Court Name"}})
        # The older fetch has the higher id, so only the timestamp can pick the right one.
        CourtFetchLog.objects.filter(pk=old.pk).update(timestamp=new.timestamp - timedelta(days=3))
        failed = _fetch(advocate, case, None, success=False)  # a later failure does not hide it
        CourtFetchLog.objects.filter(pk=failed.pk).update(timestamp=new.timestamp + timedelta(days=1))
        assert court_names_for_cases([case]) == {case.id: "New Court Name"}

    def test_runs_two_queries_however_many_cases(self, advocate, django_assert_num_queries):
        cases = [_case(advocate, f"D/{i}/2026", cnr_number=f"HBHC01053608{2000 + i}") for i in range(12)]
        for case in cases[:6]:
            _fetch(advocate, case, {"snapshot": {"court_name": "Telangana High Court"}})
        for case in cases[6:]:
            _hearing(advocate, case, "Family Court, Secunderabad")
        with django_assert_num_queries(2):
            names = court_names_for_cases(cases)
        assert len(names) == 12

    def test_no_cases_no_queries(self, db, django_assert_num_queries):
        with django_assert_num_queries(0):
            assert court_names_for_cases([]) == {}


class TestCaseListApi:
    def test_list_and_detail_carry_court_name(self, api, advocate):
        tracked = _case(advocate, "E/1/2026")
        _fetch(advocate, tracked, {"snapshot": {"court_name": "Telangana High Court"}})
        unknown = _case(advocate, "E/2/2026")

        listing = {c["id"]: c for c in api.get("/api/cases/").data}
        assert listing[tracked.id]["court_name"] == "Telangana High Court"
        assert listing[unknown.id]["court_name"] is None

        assert api.get(f"/api/cases/{tracked.id}/").data["court_name"] == "Telangana High Court"
        assert api.get(f"/api/cases/{unknown.id}/").data["court_name"] is None

    def test_court_name_is_read_only(self, api, advocate):
        case = _case(advocate, "E/3/2026")
        api.patch(f"/api/cases/{case.id}/", {"court_name": "Made Up Court"}, format="json")
        assert api.get(f"/api/cases/{case.id}/").data["court_name"] is None

    def test_one_advocates_list_never_reads_anothers_courts(self, api, advocate):
        other = User.objects.create_user(username="someone-else", password="pw-12345")
        theirs = _case(other, "F/1/2026")
        _fetch(other, theirs, {"snapshot": {"court_name": "Their Private Court"}})
        mine = _case(advocate, "F/2/2026")

        rows = api.get("/api/cases/").data
        assert [r["id"] for r in rows] == [mine.id]
        assert rows[0]["court_name"] is None

    def test_list_looks_up_every_cases_court_in_two_queries(self, api, advocate):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        for i in range(10):
            case = _case(advocate, f"G/{i}/2026")
            _fetch(advocate, case, {"snapshot": {"court_name": "Telangana High Court"}})
        with CaptureQueriesContext(connection) as ctx:
            assert api.get("/api/cases/").status_code == 200
        # One DISTINCT ON over the fetch logs, one over the hearings -- not one per case.
        assert len([q for q in ctx.captured_queries if "DISTINCT ON" in q["sql"]]) == 2
