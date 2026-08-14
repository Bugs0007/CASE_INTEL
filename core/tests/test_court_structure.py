"""Court hierarchy discovery (list_districts/list_complexes/
list_court_options/list_benches/list_case_types) -- regression tests for
the missing exception-taxonomy wrapping that let a bharat_courts
ServerError (or any other portal/transport failure) propagate as an
unhandled 500 out of GET /api/court-structure/, and as an untyped,
unclassified job failure out of advocate_search.run_advocate_search()'s
very first call.

Root cause, confirmed by reading the code (not assumed): the client
wiring itself was already correct -- list_districts/list_complexes/
list_court_options all already construct _TokenSeedingDistrictClient,
exactly like search_by_advocate does. The actual gap was that these 5
methods had NO try/except at all, unlike every other portal-calling
method in ecourts_provider.py. See EcourtsProvider._run_hierarchy_call's
docstring for the full account.

Mocks at the same boundary test_advocate_search.py already treats as
authoritative for this exact client (_TokenSeedingDistrictClient /
HCServicesClient), so these tests exercise the REAL EcourtsProvider (and,
for the view tests, the REAL CourtStructureView) end-to-end -- only the
bharat_courts network layer is faked.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bharat_courts.districtcourts.parser import ServerError as DistrictServerError
from bharat_courts.hcservices.parser import ServerError as HCServerError
from django.contrib.auth.models import User
from django.core.cache import cache
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from core.models import ProcessingJob
from core.services.advocate_search import run_advocate_search
from core.services.court_data import CourtPortalError
from core.services.court_data.ecourts_provider import EcourtsProvider


@pytest.fixture(autouse=True)
def _clear_hierarchy_cache():
    """list_districts/list_complexes/list_court_options/etc. cache
    successful results for 30 days (see HIERARCHY_CACHE_TTL) -- clear
    Django's cache around every test here so one test's cached result
    can't leak into another's assertions."""
    cache.clear()
    yield
    cache.clear()


def _mock_district_client(**method_results):
    """A MagicMock standing in for _TokenSeedingDistrictClient, used as
    an async context manager -- same pattern as
    test_advocate_search.py's _mock_district_client, but for the plain
    (non-retry-loop) hierarchy methods this file covers, which call
    client.list_states()/list_districts()/list_complexes()/
    list_case_types() directly rather than client._post_ajax()."""
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    for name, result in method_results.items():
        setattr(client, name, AsyncMock(return_value=result))
    return client


def _mock_hc_client(**method_results):
    client = MagicMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    for name, result in method_results.items():
        setattr(client, name, AsyncMock(return_value=result))
    return client


@pytest.fixture
def user_a():
    return User.objects.create_user(username="alice", password="alice-pass-123")


@pytest.fixture
def client_a(user_a):
    client = APIClient()
    token, _ = Token.objects.get_or_create(user=user_a)
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


# ---------------------------------------------------------------------------
# 1. Client wiring -- confirmed by reading the code, not assumed
# ---------------------------------------------------------------------------


class TestHierarchyMethodsUseTheFixedClient:
    """Every District Courts hierarchy call already constructs
    _TokenSeedingDistrictClient -- the same fixed client search_by_advocate
    uses -- BEFORE this change too. Verified here (rather than assumed)
    by patching the class and asserting it's what actually gets
    constructed and awaited."""

    def test_list_districts_uses_token_seeding_client(self):
        client = _mock_district_client(list_districts={"1": "Mumbai City"})
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ) as ctor:
            result = EcourtsProvider().list_districts("27")
        ctor.assert_called_once_with()
        client.list_districts.assert_awaited_once_with("27")
        assert result == {"1": "Mumbai City"}

    def test_list_complexes_uses_token_seeding_client(self):
        client = _mock_district_client(list_complexes={"c1@e@N": "Complex 1"})
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ) as ctor:
            EcourtsProvider().list_complexes("27", "1")
        ctor.assert_called_once_with()

    def test_list_court_options_district_branch_uses_token_seeding_client(self):
        client = _mock_district_client(list_states={"1": "Maharashtra"})
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ) as ctor:
            EcourtsProvider().list_court_options("district")
        ctor.assert_called_once_with()

    def test_list_district_case_types_uses_token_seeding_client(self):
        client = _mock_district_client(list_case_types={"1^2": "Civil Suit"})
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ) as ctor:
            EcourtsProvider().list_case_types(
                "district", state_code="27", dist_code="1",
                court_complex_code="1290019", est_code="2",
            )
        ctor.assert_called_once_with()


# ---------------------------------------------------------------------------
# 2. Reproduces the exact crash: parse_ajax_response raises ServerError
#    (bharat_courts' shape for a portal-side "Invalid Request"/errormsg
#    response) from inside client.list_districts()/list_complexes()/etc.
#    Before this fix that propagated straight out of EcourtsProvider as a
#    raw, untyped exception.
# ---------------------------------------------------------------------------


class TestServerErrorIsWrappedNotUnhandled:
    def test_list_districts_server_error_becomes_court_portal_error(self):
        client = _mock_district_client()
        client.list_districts = AsyncMock(side_effect=DistrictServerError("Invalid Request"))
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ):
            with pytest.raises(CourtPortalError) as exc_info:
                EcourtsProvider().list_districts("27")
        assert "Invalid Request" in str(exc_info.value)

    def test_list_complexes_server_error_becomes_court_portal_error(self):
        client = _mock_district_client()
        client.list_complexes = AsyncMock(side_effect=DistrictServerError("Invalid Request"))
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ):
            with pytest.raises(CourtPortalError):
                EcourtsProvider().list_complexes("27", "1")

    def test_list_court_options_district_server_error_becomes_court_portal_error(self):
        client = _mock_district_client()
        client.list_states = AsyncMock(side_effect=DistrictServerError("Invalid Request"))
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ):
            with pytest.raises(CourtPortalError):
                EcourtsProvider().list_court_options("district")

    def test_list_district_case_types_server_error_becomes_court_portal_error(self):
        client = _mock_district_client()
        client.list_case_types = AsyncMock(side_effect=DistrictServerError("Invalid Request"))
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ):
            with pytest.raises(CourtPortalError):
                EcourtsProvider().list_case_types(
                    "district", state_code="27", dist_code="1",
                    court_complex_code="1290019", est_code="2",
                )

    def test_list_benches_hc_server_error_becomes_court_portal_error(self):
        client = _mock_hc_client()
        client.list_benches = AsyncMock(side_effect=HCServerError("THERE IS AN SQL ERROR"))
        with patch(
            "core.services.court_data.ecourts_provider.HCServicesClient",
            return_value=client,
        ):
            with pytest.raises(CourtPortalError):
                EcourtsProvider().list_benches("telangana")

    def test_list_hc_case_types_server_error_becomes_court_portal_error(self):
        client = _mock_hc_client()
        client.list_case_types = AsyncMock(side_effect=HCServerError("THERE IS AN SQL ERROR"))
        with patch(
            "core.services.court_data.ecourts_provider.HCServicesClient",
            return_value=client,
        ):
            with pytest.raises(CourtPortalError):
                EcourtsProvider().list_case_types(
                    "high_court", hc_court_code="telangana", bench_code="1",
                )


# ---------------------------------------------------------------------------
# 3. An invalid hc_court_code is a caller mistake (a 400 at the view
#    layer via CourtStructureView's own `except ValueError`), not a portal
#    failure -- must not be re-wrapped into CourtPortalError.
# ---------------------------------------------------------------------------


class TestValueErrorPassesThroughUnwrapped:
    def test_list_benches_unknown_hc_court_code_raises_value_error_not_court_portal_error(self):
        with pytest.raises(ValueError):
            EcourtsProvider().list_benches("not-a-real-court")

    def test_list_case_types_unknown_hc_court_code_raises_value_error_not_court_portal_error(self):
        with pytest.raises(ValueError):
            EcourtsProvider().list_case_types(
                "high_court", hc_court_code="not-a-real-court", bench_code="1",
            )


# ---------------------------------------------------------------------------
# 4. The literal bug report: GET /api/court-structure/ 500'd. Goes through
#    the REAL view + REAL EcourtsProvider (only the bharat_courts client
#    construction is faked), to prove the fix holds end-to-end and not
#    just at the provider's own boundary.
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestCourtStructureViewNoLongerCrashes:
    def test_state_list_failure_is_a_clean_502_not_a_500(self, client_a):
        client = _mock_district_client()
        client.list_states = AsyncMock(side_effect=DistrictServerError("Invalid Request"))
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ):
            response = client_a.get("/api/court-structure/", {"court_type": "district"})
        assert response.status_code == 502
        assert response.data["code"] == "portal_error"

    def test_district_listing_failure_is_a_clean_502_not_a_500(self, client_a):
        client = _mock_district_client()
        client.list_districts = AsyncMock(side_effect=DistrictServerError("Invalid Request"))
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ):
            response = client_a.get(
                "/api/court-structure/", {"court_type": "district", "state_code": "27"}
            )
        assert response.status_code == 502
        assert response.data["code"] == "portal_error"

    def test_complex_listing_failure_is_a_clean_502_not_a_500(self, client_a):
        client = _mock_district_client()
        client.list_complexes = AsyncMock(side_effect=DistrictServerError("Invalid Request"))
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ):
            response = client_a.get(
                "/api/court-structure/",
                {"court_type": "district", "state_code": "27", "dist_code": "1"},
            )
        assert response.status_code == 502
        assert response.data["code"] == "portal_error"

    def test_successful_district_listing_still_returns_real_data(self, client_a):
        """Confirms the fix doesn't accidentally swallow the happy path
        along with the error path."""
        client = _mock_district_client(list_districts={"1": "Mumbai City", "2": "Pune"})
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ):
            response = client_a.get(
                "/api/court-structure/", {"court_type": "district", "state_code": "27"}
            )
        assert response.status_code == 200
        assert response.data["options"] == {"1": "Mumbai City", "2": "Pune"}


# ---------------------------------------------------------------------------
# 5. advocate_search.run_advocate_search()'s very first call is
#    provider.list_districts(state_code) -- deliberately unguarded there
#    (a failure listing the state's districts leaves nothing to fan out
#    over), but it still deserves the same typed, clearly-worded error
#    every per-district/per-complex failure downstream already gets,
#    instead of a raw bharat_courts exception with no context.
# ---------------------------------------------------------------------------


def _search_job(user, **overrides):
    params = {
        "state_code": "27", "court_type": "district",
        "advocate_name": "Suresh", "bar_code": "", "status_filter": "Both",
    }
    params.update(overrides)
    return ProcessingJob.enqueue_advocate_search(user, params)


@pytest.mark.django_db
class TestAdvocateSearchListDistrictsFailureIsTyped:
    def test_real_provider_server_error_surfaces_as_court_portal_error(self, user_a):
        """Through the REAL EcourtsProvider (not a mocked one) -- proves
        the fix threads all the way from the bharat_courts client up
        through run_advocate_search, not just at EcourtsProvider's own
        boundary."""
        job = _search_job(user_a)
        client = _mock_district_client()
        client.list_districts = AsyncMock(side_effect=DistrictServerError("Invalid Request"))
        with patch(
            "core.services.court_data.ecourts_provider._TokenSeedingDistrictClient",
            return_value=client,
        ), patch(
            "core.services.advocate_search.get_provider", return_value=EcourtsProvider()
        ), patch("core.services.advocate_search.time.sleep"):
            with pytest.raises(CourtPortalError) as exc_info:
                run_advocate_search(job)
        assert "Invalid Request" in str(exc_info.value)
