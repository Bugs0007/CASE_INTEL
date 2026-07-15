"""
Provider abstraction for court data lookups.

CourtDataProvider is the ONLY interface the rest of Case Intel talks to.
Swapping the free eCourts scraping approach for a paid API later means
writing one new class here and changing get_provider() -- nothing in
core/services/court_tracking.py, the views, or the frontend needs to
change, since they only ever see CourtCaseData/HearingRecord.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from functools import lru_cache

from core.services.court_data.models import CourtCaseData


class CourtDataProvider(ABC):
    """Fetches case data from a court records source.

    All methods are SYNCHRONOUS by design (see case_tracking implementation
    report, "Architecture Decisions" -- v1 fetches happen inline in a
    request/response cycle, no Celery/background tasks). Implementations
    that wrap an async SDK (like bharat-courts) are responsible for
    bridging that internally.
    """

    @abstractmethod
    def fetch_case(self, tracking_config: dict) -> CourtCaseData:
        """Look up a case and its hearing history.

        Args:
            tracking_config: Court hierarchy + case_type/case_number/year.
                Shape depends on tracking_config["court_type"]:
                  "district": state_code, dist_code, court_complex_code,
                      est_code, case_type, case_number, year
                  "high_court": hc_court_code, state_code, bench_code,
                      case_type, case_number, year

        Raises:
            CaseNotFoundError: No matching case for these identifiers.
            CourtPortalError: The portal failed after retries.
            CaptchaSolveError: CAPTCHA solving failed after retries.
        """

    @abstractmethod
    def list_court_options(self, court_type: str) -> dict[str, str]:
        """Top-level choice for the tracking setup form.

        For "district": dict of numeric state code -> state name.
        For "high_court": dict of bharat_courts court code -> court name
            (e.g. {"telangana": "Telangana High Court"}).
        """

    @abstractmethod
    def list_districts(self, state_code: str) -> dict[str, str]:
        """District Courts only: districts within a state."""

    @abstractmethod
    def list_complexes(self, state_code: str, dist_code: str) -> dict[str, str]:
        """District Courts only: court complexes within a district.

        Returned values are the raw "code@est_codes@flag" portal format --
        callers needing the parsed complex code should use
        core.services.court_data.ecourts_provider.parse_complex_code.
        """

    @abstractmethod
    def list_benches(self, hc_court_code: str) -> dict[str, str]:
        """High Court only: benches for a given High Court."""

    @abstractmethod
    def list_case_types(self, court_type: str, **hierarchy) -> dict[str, str]:
        """Case type options for the final dropdown.

        For "district": pass state_code, dist_code, court_complex_code,
            est_code. Returned codes are the compound "<code>^<est>" form
            bharat-courts requires -- pass them straight back as case_type.
        For "high_court": pass hc_court_code, bench_code.
        """


@lru_cache(maxsize=1)
def get_provider() -> CourtDataProvider:
    """Return the active court data provider (singleton).

    This is the one place that decides which provider implementation is
    live. Swapping providers is changing this function, not any caller.
    """
    from core.services.court_data.ecourts_provider import EcourtsProvider

    return EcourtsProvider()
