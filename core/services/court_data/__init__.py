"""
Court data provider abstraction for eCourts case tracking.

Nothing outside this package should import bharat_courts (or any other
vendor SDK) directly -- go through get_provider() / CourtDataProvider so
swapping to a paid API later is a one-class change.
"""

from core.services.court_data.base import CourtDataProvider, get_provider
from core.services.court_data.exceptions import (
    CaptchaSolveError,
    CaseNotFoundError,
    CourtDataError,
    CourtPortalError,
)
from core.services.court_data.models import CourtCaseData, HearingRecord

__all__ = [
    "CourtDataProvider",
    "get_provider",
    "CourtCaseData",
    "HearingRecord",
    "CourtDataError",
    "CaseNotFoundError",
    "CourtPortalError",
    "CaptchaSolveError",
]
