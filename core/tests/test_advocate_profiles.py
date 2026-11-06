"""Advocate search profiles, row labelling at read time, the keep-everything
parser mode, and the connection retry on court-structure calls."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.test import APIClient

from core.models import AdvocateSearchProfile, ProcessingJob
from core.services.advocate_results import annotate_rows
from core.services.court_data import CourtPortalError
from core.services.court_data.ecourts_parsing import parse_advocate_search_html
from core.services.court_data.ecourts_provider import EcourtsProvider
from core.tests.auth_helpers import token_for

FORMS = ["Rambabu", "Ram babu", "S Rambabu", "S Ram babu", "Rambabu S"]
NOT_ME = ["T Rambabu", "K Rambabu", "Rambabu Reddy"]


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
        owner=user_a,
        display_name="Rambabu Samalla",
        bar_codes=["TS/1234/2009"],
        name_forms=list(FORMS),
        excluded_names=list(NOT_ME),
    )


def _row(cnr, advocate, **extra):
    return {
        "cnr_number": cnr,
        "case_number": f"OS/{cnr[-3:]}/2020",
        "listed_advocate_name": advocate,
        "listed_advocates": [advocate],
        **extra,
    }


# ---------------------------------------------------------------------------
# CRUD, validation, tenancy
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestProfileCrud:
    def test_create_stamps_the_owner_and_computes_queries_and_suggestions(self, client_a, user_a):
        resp = client_a.post(
            "/api/advocate-profiles/",
            {"display_name": "Rambabu Samalla", "bar_codes": ["ts/1234/2009"], "name_forms": FORMS},
            format="json",
        )
        assert resp.status_code == 201, resp.data
        assert AdvocateSearchProfile.objects.get(id=resp.data["id"]).owner == user_a
        assert resp.data["bar_codes"] == ["TS/1234/2009"]  # normalised
        assert resp.data["queries"] == ["Rambabu", "Ram babu"]
        assert resp.data["query_count"] == 2
        assert resp.data["query_warning"] == ""
        assert resp.data["suggestions"] == ["Samalla Rambabu"]

    def test_more_than_three_queries_carries_a_warning(self, client_a):
        resp = client_a.post(
            "/api/advocate-profiles/",
            {"display_name": "A B", "name_forms": ["Anil", "Bhaskar", "Chandra", "Dinesh"]},
            format="json",
        )
        assert resp.status_code == 201
        assert resp.data["query_count"] == 4
        assert "4 different searches" in resp.data["query_warning"]

    def test_bar_code_must_be_state_number_year(self, client_a):
        resp = client_a.post(
            "/api/advocate-profiles/", {"display_name": "X Y", "bar_codes": ["1234"]}, format="json"
        )
        assert resp.status_code == 400
        assert "bar_codes" in resp.data

    def test_a_name_cannot_be_in_both_lists(self, client_a):
        resp = client_a.post(
            "/api/advocate-profiles/",
            {"display_name": "X Y", "name_forms": ["S Rambabu"], "excluded_names": ["s. rambabu"]},
            format="json",
        )
        assert resp.status_code == 400
        assert "name_forms" in resp.data

    def test_patch_cannot_create_the_overlap_either(self, client_a, profile_a):
        resp = client_a.patch(
            f"/api/advocate-profiles/{profile_a.id}/", {"excluded_names": [*NOT_ME, "S Rambabu"]}, format="json"
        )
        assert resp.status_code == 400
        profile_a.refresh_from_db()
        assert "S Rambabu" not in profile_a.excluded_names

    def test_patch_updates_and_dedupes(self, client_a, profile_a):
        resp = client_a.patch(
            f"/api/advocate-profiles/{profile_a.id}/",
            {"name_forms": ["Rambabu", "rambabu", "Ram  babu"]},
            format="json",
        )
        assert resp.status_code == 200
        # Exact repeats collapse; "Ram babu" stays: the portal searches it differently from "Rambabu".
        assert resp.data["name_forms"] == ["Rambabu", "Ram babu"]

    def test_empty_display_name_rejected(self, client_a):
        assert client_a.post("/api/advocate-profiles/", {"display_name": "  "}, format="json").status_code == 400

    def test_delete(self, client_a, profile_a):
        assert client_a.delete(f"/api/advocate-profiles/{profile_a.id}/").status_code == 204
        assert not AdvocateSearchProfile.objects.filter(id=profile_a.id).exists()

    def test_requires_authentication(self):
        assert APIClient().get("/api/advocate-profiles/").status_code == 401


@pytest.mark.django_db
class TestProfileTenancy:
    def test_list_shows_only_my_profiles(self, client_a, client_b, profile_a, user_b):
        AdvocateSearchProfile.objects.create(owner=user_b, display_name="Bob")
        assert [p["display_name"] for p in client_a.get("/api/advocate-profiles/").data] == ["Rambabu Samalla"]
        assert [p["display_name"] for p in client_b.get("/api/advocate-profiles/").data] == ["Bob"]

    def test_other_advocates_profile_is_a_404_on_every_verb_and_action(self, client_b, profile_a):
        base = f"/api/advocate-profiles/{profile_a.id}/"
        assert client_b.get(base).status_code == 404
        assert client_b.patch(base, {"display_name": "hijacked"}, format="json").status_code == 404
        assert client_b.delete(base).status_code == 404
        assert client_b.post(base + "exclude/", {"name": "S Rambabu"}, format="json").status_code == 404
        assert client_b.post(base + "add-name-form/", {"name": "X Y"}, format="json").status_code == 404
        profile_a.refresh_from_db()
        assert profile_a.display_name == "Rambabu Samalla"
        assert "S Rambabu" in profile_a.name_forms

    def test_create_ignores_a_client_supplied_owner(self, client_a, user_a, user_b):
        resp = client_a.post(
            "/api/advocate-profiles/", {"display_name": "X Y", "owner": user_b.id}, format="json"
        )
        assert resp.status_code == 201
        assert AdvocateSearchProfile.objects.get(id=resp.data["id"]).owner == user_a


# ---------------------------------------------------------------------------
# "Not me" / "That's me": quick actions that MOVE a name between the lists
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestQuickActions:
    def test_not_me_moves_the_name_off_the_forms(self, client_a, profile_a):
        resp = client_a.post(f"/api/advocate-profiles/{profile_a.id}/exclude/", {"name": "s rambabu"}, format="json")
        assert resp.status_code == 200
        # every spelling that is the same name leaves the forms, not just the typed one
        assert not {"S Rambabu", "Rambabu S", "S Ram babu"} & set(resp.data["name_forms"])
        assert {"Rambabu", "Ram babu"} <= set(resp.data["name_forms"])
        assert "s rambabu" in resp.data["excluded_names"]

    def test_thats_me_moves_the_name_off_the_not_me_list(self, client_a, profile_a):
        resp = client_a.post(
            f"/api/advocate-profiles/{profile_a.id}/add-name-form/", {"name": "T Rambabu"}, format="json"
        )
        assert resp.status_code == 200
        assert "T Rambabu" in resp.data["name_forms"]
        assert "T Rambabu" not in resp.data["excluded_names"]

    def test_repeating_an_action_does_not_duplicate(self, client_a, profile_a):
        url = f"/api/advocate-profiles/{profile_a.id}/exclude/"
        client_a.post(url, {"name": "G Rambabu"}, format="json")
        resp = client_a.post(url, {"name": "G. Rambabu"}, format="json")
        assert resp.data["excluded_names"].count("G Rambabu") == 1
        assert len(resp.data["excluded_names"]) == len(NOT_ME) + 1

    def test_name_is_required(self, client_a, profile_a):
        assert client_a.post(f"/api/advocate-profiles/{profile_a.id}/exclude/", {}, format="json").status_code == 400


# ---------------------------------------------------------------------------
# Labelling at read time: no new search, nothing deleted
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRowsAreLabelledWhenRead:
    ROWS = [
        _row("C001", "S Rambabu"),
        _row("C002", "Rambabu S"),
        _row("C003", "Rambabu"),
        _row("C004", "T Rambabu"),
        _row("C005", "Rambabu Reddy"),
        _row("C006", "G Rambabu"),
        _row("C007", "", listed_advocates=[]),
        _row("C008", "unused", listed_advocates=["APP", "S Ram babu"]),
        _row("C009", "Bar", match_source="bar_code", listed_advocates=["Someone Else"]),
    ]

    def test_acceptance_labels(self, profile_a):
        rows, counts = annotate_rows([dict(r) for r in self.ROWS], profile_a)
        status = {r["cnr_number"]: (r["match_status"], r["match_label"]) for r in rows}
        assert status["C001"] == ("matched", "Your name")
        assert status["C002"] == ("matched", "Your name")
        assert status["C003"] == ("check", "Check name")
        assert status["C004"][0] == "excluded"  # T Rambabu is hidden
        assert status["C005"][0] == "excluded"
        assert status["C006"][0] == "other"
        assert status["C007"][0] == "check"  # no advocate listed at all: cannot be verified
        assert status["C008"][0] == "matched"  # a designation beside the name
        assert status["C009"] == ("matched", "Your bar no.")
        assert counts == {"matched": 4, "check": 2, "excluded": 2, "other": 1}

    def test_best_matches_come_first_and_nothing_is_dropped(self, profile_a):
        rows, _ = annotate_rows([dict(r) for r in self.ROWS], profile_a)
        assert len(rows) == len(self.ROWS)
        order = [r["match_status"] for r in rows]
        assert order == sorted(order, key=["matched", "check", "other", "excluded"].index)

    def test_no_profile_leaves_rows_untouched(self):
        rows = [dict(r) for r in self.ROWS]
        out, counts = annotate_rows(rows, None)
        assert out is rows and counts == {}

    def test_an_old_row_with_only_matched_advocate_text_is_still_classified(self, profile_a):
        rows, _ = annotate_rows([{"cnr_number": "C1", "matched_advocate_text": "S Rambabu"}], profile_a)
        assert rows[0]["match_status"] == "matched"

    def _job(self, user, profile):
        return ProcessingJob.objects.create(
            owner=user,
            job_type="advocate_search",
            status="succeeded",
            payload={"results": [dict(r) for r in self.ROWS], "profile_id": profile.id},
        )

    def test_status_endpoint_labels_rows_from_the_job_profile(self, client_a, user_a, profile_a):
        job = self._job(user_a, profile_a)
        data = client_a.get(f"/api/cases/search-advocate/{job.id}/").data
        assert data["profile_id"] == profile_a.id
        assert data["match_counts"] == {"matched": 4, "check": 2, "excluded": 2, "other": 1}
        assert data["results_total"] == len(self.ROWS)
        assert data["results"][0]["match_status"] == "matched"

    def test_not_me_relabels_the_same_search_with_no_new_portal_call(self, client_a, user_a, profile_a):
        job = self._job(user_a, profile_a)
        url = f"/api/cases/search-advocate/{job.id}/"
        before = {r["cnr_number"]: r["match_status"] for r in client_a.get(url).data["results"]}
        assert before["C001"] == "matched"

        client_a.post(f"/api/advocate-profiles/{profile_a.id}/exclude/", {"name": "S Rambabu"}, format="json")
        after = {r["cnr_number"]: r["match_status"] for r in client_a.get(url).data["results"]}

        assert after["C001"] == "excluded"  # the row is hidden...
        # ...and so are the rows that list the same name another way: "Rambabu S"
        # and "S Ram babu" are "S Rambabu" once spaces and word order are ignored.
        assert after["C002"] == "excluded"
        assert after["C008"] == "excluded"
        assert after["C003"] == "check"  # a plain "Rambabu" is a different question
        assert len(after) == len(before)  # ...and nothing was deleted
        assert ProcessingJob.objects.filter(job_type="advocate_search").count() == 1  # no new search

        client_a.post(f"/api/advocate-profiles/{profile_a.id}/add-name-form/", {"name": "S Rambabu"}, format="json")
        restored = {r["cnr_number"]: r["match_status"] for r in client_a.get(url).data["results"]}
        assert restored["C001"] == "matched"

    def test_a_row_flips_from_other_to_matched_after_thats_me(self, client_a, user_a, profile_a):
        job = self._job(user_a, profile_a)
        url = f"/api/cases/search-advocate/{job.id}/"
        client_a.post(f"/api/advocate-profiles/{profile_a.id}/add-name-form/", {"name": "G Rambabu"}, format="json")
        after = {r["cnr_number"]: r["match_status"] for r in client_a.get(url).data["results"]}
        assert after["C006"] == "matched"

    def test_another_advocates_profile_id_is_ignored(self, client_b, user_b, profile_a):
        job = ProcessingJob.objects.create(
            owner=user_b, job_type="advocate_search", status="succeeded", payload={"results": [dict(self.ROWS[0])]}
        )
        data = client_b.get(f"/api/cases/search-advocate/{job.id}/", {"profile_id": profile_a.id}).data
        assert data["profile_id"] is None
        assert "match_status" not in data["results"][0]

    def test_a_job_without_a_profile_is_returned_as_before(self, client_a, user_a):
        job = ProcessingJob.objects.create(
            owner=user_a, job_type="advocate_search", status="succeeded", payload={"results": [dict(self.ROWS[0])]}
        )
        data = client_a.get(f"/api/cases/search-advocate/{job.id}/").data
        assert data["match_counts"] == {}
        assert "match_status" not in data["results"][0]


# ---------------------------------------------------------------------------
# Parser: keep_all stores every raw row with the Advocate cell as listed
# ---------------------------------------------------------------------------

_HEADER = (
    "<thead><tr><th>Sr No</th><th>Case Number</th><th>Parties</th>"
    "<th>Advocate Name</th><th>View</th></tr></thead>"
)


def _html(*rows):
    body = "".join(
        f"""<tr><td>{i}</td><td>OS/{i}/2020</td><td>A<br>Vs</br>B</td><td>{advocate}</td>
        <td><a onClick="viewHistory(1,'{cnr}',1,'','CScaseNumber',29,9,1,'CSAdvName')">View</a></td></tr>"""
        for i, (cnr, advocate) in enumerate(rows, start=1)
    )
    return f"<table id='dispTable'>{_HEADER}<tbody>{body}</tbody></table>"


class TestParserKeepAll:
    HTML = _html(
        ("TSRA110027752023", "S Rambabu"),
        ("TSRA110027752024", "Totally Unrelated Person"),
        ("TSRA110027752025", "APP<br>G.Ramesh kumar"),
    )

    def test_default_still_drops_rows_the_advocate_column_does_not_back_up(self):
        hits = parse_advocate_search_html(self.HTML, advocate_name="Rambabu")
        assert [h.cnr_number for h in hits] == ["TSRA110027752023"]

    def test_keep_all_keeps_every_row_with_the_cell_as_listed(self):
        hits = parse_advocate_search_html(self.HTML, advocate_name="Rambabu", keep_all=True)
        assert [h.listed_advocate_name for h in hits] == ["S Rambabu", "Totally Unrelated Person", "APP G.Ramesh kumar"]
        assert [h.advocate_match_verified for h in hits] == [True, False, False]

    def test_a_br_splits_a_designation_from_the_name(self):
        hits = parse_advocate_search_html(self.HTML, advocate_name="Rambabu", keep_all=True)
        assert hits[2].listed_advocates == ["APP", "G.Ramesh kumar"]
        assert hits[0].to_dict()["listed_advocates"] == ["S Rambabu"]

    def test_a_grid_with_no_advocate_column_keeps_rows_with_no_listed_name(self):
        html = (
            "<table><thead><tr><th>Sr No</th><th>Case Number</th><th>Parties</th><th>View</th></tr></thead><tbody>"
            "<tr><td>1</td><td>OS/1/2020</td><td>A<br>Vs</br>B</td>"
            "<td><a onClick=\"viewHistory(1,'TSRA110027752023',1)\">View</a></td></tr></tbody></table>"
        )
        hits = parse_advocate_search_html(html, advocate_name="Rambabu", keep_all=True)
        assert len(hits) == 1
        assert hits[0].listed_advocate_name == "" and hits[0].listed_advocates == []


# ---------------------------------------------------------------------------
# The first court-structure call that disconnects is retried
# ---------------------------------------------------------------------------


def _client_that(**methods):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    for name, effect in methods.items():
        setattr(client, name, AsyncMock(side_effect=effect))
    return client


@pytest.fixture(autouse=True)
def _clear_cache():
    cache.clear()
    yield
    cache.clear()


class TestHierarchyConnectionRetry:
    def test_two_disconnects_then_success_returns_the_list(self):
        client = _client_that(
            list_districts=[httpx.RemoteProtocolError("peer closed connection"), httpx.ConnectError("reset"), {"1": "Adilabad"}]
        )
        with patch("core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", return_value=client), \
                patch("core.services.court_data.ecourts_provider.time.sleep") as sleep:
            assert EcourtsProvider().list_districts("29") == {"1": "Adilabad"}
        assert [c.args[0] for c in sleep.call_args_list] == [0.5, 1.5]  # backoff between the tries
        assert client.list_districts.await_count == 3

    def test_gives_up_after_the_backoff_schedule_and_raises_a_typed_error(self):
        client = _client_that(list_districts=httpx.RemoteProtocolError("peer closed connection"))
        with patch("core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", return_value=client), \
                patch("core.services.court_data.ecourts_provider.time.sleep") as sleep:
            with pytest.raises(CourtPortalError):
                EcourtsProvider().list_districts("29")
        assert [c.args[0] for c in sleep.call_args_list] == [0.5, 1.5, 3.0]
        assert client.list_districts.await_count == 4  # first try + three retries

    def test_a_portal_error_answer_is_not_retried(self):
        from bharat_courts.districtcourts.parser import ServerError as DistrictServerError

        client = _client_that(list_districts=DistrictServerError("Invalid Request"))
        with patch("core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", return_value=client), \
                patch("core.services.court_data.ecourts_provider.time.sleep") as sleep:
            with pytest.raises(CourtPortalError):
                EcourtsProvider().list_districts("29")
        sleep.assert_not_called()
        assert client.list_districts.await_count == 1

    def test_a_failure_is_not_cached_so_the_retry_button_really_retries(self):
        bad = _client_that(list_districts=httpx.ConnectError("down"))
        good = _client_that(list_districts=[{"1": "Adilabad"}])
        with patch("core.services.court_data.ecourts_provider.time.sleep"):
            with patch("core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", return_value=bad):
                with pytest.raises(CourtPortalError):
                    EcourtsProvider().list_districts("29")
            with patch("core.services.court_data.ecourts_provider._TokenSeedingDistrictClient", return_value=good):
                assert EcourtsProvider().list_districts("29") == {"1": "Adilabad"}
