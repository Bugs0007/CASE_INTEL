"""
Exceptions raised by court data providers.

Views catch these to return actionable messages instead of 500s -- see
core/views/case_tracking.py.
"""


class CourtDataError(Exception):
    """Base class for all court-data-provider errors."""


class CaseNotFoundError(CourtDataError):
    """The portal returned no matching case for the given identifiers.

    Usually means the case_type/case_number/year (or court hierarchy)
    the user entered doesn't match a real case.
    """


class CourtPortalError(CourtDataError):
    """The court portal itself failed (connection error, ERROR_VAL, 5xx,
    unexpected response shape) after exhausting retries."""


class CaptchaSolveError(CourtDataError):
    """CAPTCHA solving failed on every retry attempt."""
