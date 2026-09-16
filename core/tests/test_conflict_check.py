"""Conflict of interest check at intake.

  - Name matching: the labelled fixture (core/tests/fixtures/party_names.json)
    plus party splitting and cleaning.
  - find_conflicts: which relationships count, role-unknown handling, the
    State stoplist, and tenant isolation.
  - The three intake paths: manual POST /api/cases/, Track-by-CNR preview and
    confirm, and the advocate import worker.
  - Party-name persistence and the backfill / report commands.
"""

import json
from io import StringIO
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth.models import User
from django.core.management import call_command
from rest_framework.test import APIClient

from core.models import ActivityLog, Case, ClientContact, ProcessingJob
from core.services.advocate_import import run_advocate_import
from core.services.conflict_check import (
    BAND_LIKELY,
    BAND_POSSIBLE,
    KIND_ADVERSE,
    KIND_ROLE_UNKNOWN,
    _band,
    find_conflicts,
    split_title,
)
from core.services.court_data.models import CourtCaseData
from core.services.name_matching import name_similarity, party_tokens, split_parties

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures" / "party_names.json").read_text(encoding="utf-8")
)


def _band_for(a: str, b: str):
    return _band(name_similarity(party_tokens(a), party_tokens(b)))


# ---------------------------------------------------------------------------
# Name matching
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("a, b", FIXTURE["likely"])
def test_likely_pairs(a, b):
    assert _band_for(a, b) == BAND_LIKELY
    assert _band_for(b, a) == BAND_LIKELY  # symmetric


@pytest.mark.parametrize("a, b", FIXTURE["possible"])
def test_possible_pairs(a, b):
    assert _band_for(a, b) == BAND_POSSIBLE


@pytest.mark.parametrize("a, b", FIXTURE["no_match"])
def test_near_misses_do_not_match(a, b):
    assert _band_for(a, b) is None


@pytest.mark.parametrize(
    "field, expected",
    [
        ("1) RAMESH KUMAR 2) SURESH BABU & 3 Ors", ["RAMESH KUMAR", "SURESH BABU"]),
        ("Ramesh Kumar, S/o Venkat Rao, aged 45", ["Ramesh Kumar, S/o Venkat Rao, aged 45"]),
        ("A. Rao\nB. Naidu", ["A. Rao", "B. Naidu"]),
        ("", []),
    ],
)
def test_split_parties(field, expected):
    assert split_parties(field) == expected


def test_state_parties_have_no_tokens():
    assert party_tokens("The State of Telangana, rep. by its Principal Secretary") == ()
    assert party_tokens("Union of India") == ()


def test_split_title():
    assert split_title("Ramesh Kumar vs State of Telangana") == ("Ramesh Kumar", "State of Telangana")
    assert split_title("A. Rao v. B. Naidu") == ("A. Rao", "B. Naidu")
    assert split_title("WP/123/2026") == ("", "")


# ---------------------------------------------------------------------------
# find_conflicts
# ---------------------------------------------------------------------------


@pytest.fixture
def advocate(db):
    return User.objects.create_user(username="conflict-advocate", password="pw-12345")


@pytest.fixture
def other_advocate(db):
    return User.objects.create_user(username="conflict-other", password="pw-12345")


def _case(owner, number, *, role="petitioner", petitioner="", respondent="", title=None, **extra):
    return Case.objects.create(
        owner=owner,
        case_number=number,
        title=title if title is not None else number,
        user_party_role=role,
        petitioner_name=petitioner,
        respondent_name=respondent,
        **extra,
    )


@pytest.mark.django_db
class TestFindConflicts:
    def test_new_opponent_who_is_an_existing_client_is_adverse(self, advocate):
        existing = _case(
            advocate, "OS/1/2025", role="petitioner", petitioner="Ramesh Kumar", respondent="Lakshmi Textiles"
        )

        hits = find_conflicts(
            advocate, petitioner="Venkat Rao", respondent="K. Ramesh Kumar", user_party_role="petitioner"
        )

        assert len(hits) == 1
        hit = hits[0]
        assert (hit.kind, hit.band, hit.case_id) == (KIND_ADVERSE, BAND_LIKELY, existing.id)
        assert (hit.new_side, hit.existing_side) == ("other", "own")

    def test_new_client_who_is_an_existing_opponent_is_adverse(self, advocate):
        _case(advocate, "OS/1/2025", role="respondent", petitioner="Ramesh Kumar", respondent="Venkat Rao")

        hits = find_conflicts(advocate, petitioner="Ramesh Kumar", user_party_role="petitioner")

        assert [h.kind for h in hits] == [KIND_ADVERSE]

    def test_repeat_client_and_repeat_opponent_are_not_conflicts(self, advocate):
        _case(advocate, "OS/1/2025", role="petitioner", petitioner="Ramesh Kumar", respondent="Venkat Rao")

        assert find_conflicts(
            advocate, petitioner="Ramesh Kumar", respondent="Venkat Rao", user_party_role="petitioner"
        ) == []

    def test_role_unknown_reports_only_close_matches(self, advocate):
        _case(advocate, "OS/1/2025", role="unknown", petitioner="Ramesh Kumar", respondent="Sreenivas Rao")

        hits = find_conflicts(advocate, opposing_party="Ramesh Kumar")
        assert [(h.kind, h.band) for h in hits] == [(KIND_ROLE_UNKNOWN, BAND_LIKELY)]

        # "Srinivas Rao" is only a possible match -- not reported when the
        # side is unknown.
        assert find_conflicts(advocate, opposing_party="Srinivas Rao") == []

    def test_client_contacts_count_as_the_advocates_side(self, advocate):
        case = _case(advocate, "OS/1/2025", role="unknown")
        ClientContact.objects.create(owner=advocate, case=case, name="Priya Verma")

        hits = find_conflicts(advocate, opposing_party="Kumari Priya Verma")

        assert [(h.kind, h.existing_side) for h in hits] == [(KIND_ADVERSE, "own")]

    def test_manual_case_titles_supply_parties(self, advocate):
        _case(advocate, "OS/1/2025", role="petitioner", title="Ramesh Kumar vs Venkat Rao")

        hits = find_conflicts(advocate, title="Venkat Rao vs Ramesh Kumar", user_party_role="petitioner")

        assert {h.new_party for h in hits} == {"Ramesh Kumar", "Venkat Rao"}
        assert all(h.kind == KIND_ADVERSE for h in hits)

    def test_the_state_on_both_sides_is_not_a_conflict(self, advocate):
        _case(advocate, "WP/1/2025", role="petitioner", petitioner="A. Rao", respondent="State of Telangana")

        assert find_conflicts(
            advocate, petitioner="State of Telangana", respondent="B. Naidu", user_party_role="respondent"
        ) == []

    def test_never_matches_another_advocates_cases(self, advocate, other_advocate):
        _case(other_advocate, "OS/1/2025", role="petitioner", petitioner="Ramesh Kumar")

        assert find_conflicts(advocate, opposing_party="Ramesh Kumar") == []

    def test_exclude_case_id_skips_the_case_itself(self, advocate):
        case = _case(advocate, "OS/1/2025", role="petitioner", petitioner="Ramesh Kumar", respondent="Venkat Rao")

        assert find_conflicts(
            advocate,
            petitioner="Venkat Rao",
            respondent="Ramesh Kumar",
            user_party_role="petitioner",
            exclude_case_id=case.id,
        ) == []

    def test_adverse_hits_rank_first(self, advocate):
        _case(advocate, "OS/1/2025", role="unknown", petitioner="Ramesh Kumar")
        _case(advocate, "OS/2/2025", role="petitioner", petitioner="Venkat Rao")

        hits = find_conflicts(advocate, opposing_party="1) Ramesh Kumar 2) Venkat Rao")

        assert [h.kind for h in hits] == [KIND_ADVERSE, KIND_ROLE_UNKNOWN]


# ---------------------------------------------------------------------------
# Intake: manual create
# ---------------------------------------------------------------------------


@pytest.fixture
def api(advocate):
    client = APIClient()
    client.force_authenticate(user=advocate)
    return client


@pytest.mark.django_db
class TestManualCreate:
    def test_conflict_needs_acknowledging_then_is_logged(self, api, advocate):
        _case(advocate, "OS/1/2025", role="petitioner", petitioner="Ramesh Kumar")
        body = {
            "case_number": "OS/9/2026",
            "title": "Venkat Rao vs Ramesh Kumar",
            "opposing_party": "Ramesh Kumar",
            "user_party_role": "petitioner",
        }

        blocked = api.post("/api/cases/", body, format="json")
        assert blocked.status_code == 409
        assert blocked.data["code"] == "conflict_check"
        assert blocked.data["conflicts"][0]["case_number"] == "OS/1/2025"
        assert not Case.objects.filter(case_number="OS/9/2026").exists()

        created = api.post("/api/cases/", {**body, "acknowledge_conflicts": True}, format="json")
        assert created.status_code == 201
        log = ActivityLog.objects.get(activity_type="conflict_acknowledged")
        assert log.case_id == created.data["id"]
        assert "OS/1/2025" in log.description

    def test_no_conflict_creates_without_a_log(self, api, advocate):
        _case(advocate, "OS/1/2025", role="petitioner", petitioner="Ramesh Kumar")

        resp = api.post(
            "/api/cases/",
            {"case_number": "OS/9/2026", "title": "Venkat Rao vs Suresh Babu", "user_party_role": "petitioner"},
            format="json",
        )

        assert resp.status_code == 201
        assert not ActivityLog.objects.filter(activity_type="conflict_acknowledged").exists()


# ---------------------------------------------------------------------------
# Intake: Track by CNR
# ---------------------------------------------------------------------------

CNR = "TSHC010051622026"


def _case_data(**overrides):
    values = dict(
        cnr=CNR,
        case_status="CASE PENDING",
        registration_number="WP/23998/2026",
        petitioner="Venkat Rao",
        respondent="Ramesh Kumar",
        court_name="High Court for the State of Telangana",
    )
    values.update(overrides)
    return CourtCaseData(**values)


@pytest.mark.django_db
class TestTrackByCnr:
    @pytest.fixture
    def existing_client(self, advocate):
        return _case(advocate, "OS/1/2025", role="petitioner", petitioner="Ramesh Kumar")

    @patch("core.services.court_tracking.get_provider")
    def test_preview_warns_and_create_needs_acknowledgement(
        self, get_provider, api, advocate, existing_client
    ):
        provider = MagicMock()
        provider.fetch_case_by_cnr.return_value = _case_data()
        get_provider.return_value = provider

        lookup = api.post("/api/cases/cnr-lookup/", {"cnr": CNR, "court_type": "high_court"}, format="json")
        assert lookup.status_code == 200
        # Role unknown at preview (no advocate profile): a close match is
        # still surfaced, as role-unknown.
        assert [c["case_number"] for c in lookup.data["conflicts"]] == ["OS/1/2025"]

        body = {
            "preview_token": lookup.data["preview_token"],
            "case_number": "WP/23998/2026",
            "title": "Venkat Rao vs Ramesh Kumar",
            "user_party_role": "petitioner",
        }
        blocked = api.post("/api/cases/cnr-lookup/create/", body, format="json")
        assert blocked.status_code == 409
        assert blocked.data["conflicts"][0]["kind"] == KIND_ADVERSE
        assert not Case.objects.filter(cnr_number=CNR).exists()

        created = api.post(
            "/api/cases/cnr-lookup/create/", {**body, "acknowledge_conflicts": True}, format="json"
        )
        assert created.status_code == 201
        case = Case.objects.get(cnr_number=CNR)
        # The fetched parties are persisted for future checks.
        assert (case.petitioner_name, case.respondent_name) == ("Venkat Rao", "Ramesh Kumar")
        assert ActivityLog.objects.filter(case=case, activity_type="conflict_acknowledged").exists()


# ---------------------------------------------------------------------------
# Intake: advocate import (never blocks)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestAdvocateImport:
    def test_conflicts_are_recorded_not_blocking(self, advocate):
        _case(advocate, "OS/1/2025", role="respondent", respondent="Ramesh Kumar")
        job = ProcessingJob.enqueue_advocate_import(
            advocate, [{"cnr_number": CNR, "case_number": "WP/23998/2026", "court_type": "high_court"}]
        )

        with patch("core.services.court_tracking.get_provider") as get_provider, patch(
            "core.services.advocate_import.time.sleep"
        ):
            get_provider.return_value.fetch_case.return_value = _case_data()
            run_advocate_import(job)

        job.refresh_from_db()
        assert len(job.payload["created"]) == 1
        assert [c["case_number"] for c in job.payload["conflicts"][CNR]] == ["OS/1/2025"]
        imported = Case.objects.get(cnr_number=CNR)
        assert ActivityLog.objects.filter(case=imported, activity_type="conflict_flagged").exists()

    def test_status_endpoint_returns_conflicts(self, api, advocate):
        job = ProcessingJob.objects.create(
            owner=advocate,
            job_type="advocate_import",
            status="succeeded",
            payload={"created": [], "conflicts": {CNR: [{"case_number": "OS/1/2025"}]}},
        )

        resp = api.get(f"/api/cases/search-advocate/import/{job.id}/")

        assert resp.status_code == 200
        assert resp.data["conflicts"] == {CNR: [{"case_number": "OS/1/2025"}]}


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestBackfillPartyNames:
    def test_fills_blanks_from_stored_search_results(self, advocate, other_advocate):
        case = _case(advocate, "WP/1/2026", cnr_number=CNR)
        named = _case(advocate, "WP/2/2026", cnr_number="TSHC010000012026", petitioner="From a fetch")
        foreign = _case(other_advocate, "WP/1/2026", cnr_number="TSHC010000022026")
        ProcessingJob.objects.create(
            owner=advocate,
            job_type="advocate_search",
            payload={
                "results": [
                    {"cnr_number": CNR, "petitioner": "Venkat Rao", "respondent": "Ramesh Kumar"},
                    {"cnr_number": "TSHC010000012026", "petitioner": "Stale", "respondent": "X"},
                    # Another advocate's CNR in this advocate's search: not theirs to fill.
                    {"cnr_number": "TSHC010000022026", "petitioner": "Nope", "respondent": "Nope"},
                ]
            },
        )

        out = StringIO()
        call_command("backfill_party_names", "--dry-run", stdout=out)
        case.refresh_from_db()
        assert case.petitioner_name == ""
        assert "would update 2" in out.getvalue()

        call_command("backfill_party_names", stdout=StringIO())
        case.refresh_from_db()
        named.refresh_from_db()
        foreign.refresh_from_db()
        assert (case.petitioner_name, case.respondent_name) == ("Venkat Rao", "Ramesh Kumar")
        assert (named.petitioner_name, named.respondent_name) == ("From a fetch", "X")
        assert foreign.petitioner_name == ""


@pytest.mark.django_db
def test_conflict_check_report_lists_each_pair_once(advocate):
    _case(advocate, "OS/1/2025", role="petitioner", petitioner="Ramesh Kumar", respondent="Venkat Rao")
    _case(advocate, "OS/2/2025", role="petitioner", petitioner="Venkat Rao", respondent="Ramesh Kumar")
    out = StringIO()

    call_command("conflict_check_report", "--owner", advocate.username, stdout=out)

    output = out.getvalue()
    assert "2 possible conflict pair(s)" in output
    # Each case sees the other, but the pair is reported once.
    assert sum("Ramesh Kumar" in line for line in output.splitlines()) == 1
