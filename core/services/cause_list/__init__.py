"""Cause-list ingestion. One court is wired up today -- the High Court for
the State of Telangana, via eCourts' hcservices portal (`telangana_hc.py`)
-- but the command and the systemd timer that drive it are parameterised
by court KEY (see `registry.py`), so adding a second court is a sibling
fetcher module + a registry entry + a settings key, never a change to the
deploy units.

Deliberately not a universal parser. Every court publishes its cause list
in its own way, and a parser that tries to cover several ends up matching
nothing reliably. `telangana_hc.py` targets the exact artifacts this court
serves -- a CAPTCHA-gated meta-table of per-bench PDF links, then the PDFs
themselves -- and will correctly refuse to parse anything else.
"""

from .exceptions import (
    CauseListError,
    CauseListNotConfiguredError,
    CauseListNotPublishedError,
    CauseListParseError,
)
from .registry import (
    CauseListCourt,
    all_registered_courts,
    configured_cause_list_courts,
    configured_court_keys,
    get_cause_list_court,
)
from .telangana_hc import (
    CauseListDay,
    CauseListDocument,
    CauseListEntry,
    CauseListItem,
    build_pdf_url,
    fetch_cause_list_day,
    normalize_case_token,
    parse_cause_list_pdf,
    parse_meta_table,
    strip_pdf_bom,
)

__all__ = [
    "CauseListCourt",
    "CauseListDay",
    "CauseListDocument",
    "CauseListEntry",
    "CauseListError",
    "CauseListItem",
    "CauseListNotConfiguredError",
    "CauseListNotPublishedError",
    "CauseListParseError",
    "all_registered_courts",
    "build_pdf_url",
    "configured_cause_list_courts",
    "configured_court_keys",
    "fetch_cause_list_day",
    "get_cause_list_court",
    "normalize_case_token",
    "parse_cause_list_pdf",
    "parse_meta_table",
    "strip_pdf_bom",
]
