"""Cause-list ingestion for ONE court: the High Court for the State of
Telangana.

Deliberately not a universal parser. Every court publishes its cause list
in its own layout, and a parser that tries to cover several ends up
matching nothing reliably. `telangana_hc.py` targets the exact DOM the TS
High Court's daily list ships (a table#dataTable of per-item <tbody>
blocks) and will correctly refuse to parse anything else.

Adding a second court means adding a sibling module with its own parser
and registering it -- not generalising this one.
"""

from .exceptions import (
    CauseListError,
    CauseListNotConfiguredError,
    CauseListNotPublishedError,
    CauseListParseError,
)
from .telangana_hc import (
    CauseList,
    CauseListItem,
    normalize_case_token,
    parse_cause_list_html,
)

__all__ = [
    "CauseList",
    "CauseListError",
    "CauseListItem",
    "CauseListNotConfiguredError",
    "CauseListNotPublishedError",
    "CauseListParseError",
    "normalize_case_token",
    "parse_cause_list_html",
]
