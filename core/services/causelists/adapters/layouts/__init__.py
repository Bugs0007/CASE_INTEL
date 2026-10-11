"""PDF layout parsers for the hcservices High Courts.

One parser per layout FAMILY (see docs/causelists/COVERAGE.md); the family a
court uses is data in hc_config.py. A parser takes a RawDoc and returns a
ParsedDoc, or raises CauseListParseError -- never an empty ParsedDoc for a
non-empty document, and never a silently partial one.
"""

from __future__ import annotations

from typing import Callable

from ...base import ParsedDoc, RawDoc
from ...hc_config import PARSER_DELHI, PARSER_JK, PARSER_TABLE, PARSER_TELANGANA


def _telangana_family(doc: RawDoc) -> ParsedDoc:
    from ..telangana_hc import get_adapter

    return get_adapter().parse(doc)


def parser_for(family: str) -> Callable[[RawDoc], ParsedDoc] | None:
    if family == PARSER_TELANGANA:
        return _telangana_family
    if family in (PARSER_TABLE, PARSER_JK):
        from .table import parse_table_doc

        return parse_table_doc
    if family == PARSER_DELHI:
        from .delhi import parse_delhi_doc

        return parse_delhi_doc
    return None
