"""Cause-list ingestion for ONE court: the High Court for the State of
Telangana, via eCourts' hcservices portal.

Deliberately not a universal parser. Every court publishes its cause list
in its own way, and a parser that tries to cover several ends up matching
nothing reliably. `telangana_hc.py` targets the exact artifacts this court
serves -- a CAPTCHA-gated meta-table of per-bench PDF links, then the PDFs
themselves -- and will correctly refuse to parse anything else.

Adding a second court means adding a sibling module with its own fetcher
and parser and registering it, not generalising this one.
"""

from .exceptions import (
    CauseListError,
    CauseListNotConfiguredError,
    CauseListNotPublishedError,
    CauseListParseError,
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
    "CauseListDay",
    "CauseListDocument",
    "CauseListEntry",
    "CauseListError",
    "CauseListItem",
    "CauseListNotConfiguredError",
    "CauseListNotPublishedError",
    "CauseListParseError",
    "build_pdf_url",
    "fetch_cause_list_day",
    "normalize_case_token",
    "parse_cause_list_pdf",
    "parse_meta_table",
    "strip_pdf_bom",
]
