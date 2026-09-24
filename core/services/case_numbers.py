"""Case-number tidying, shared by the eCourts parsers and the Case model.

Pure (re only) so core/models/case.py can import it without pulling in the
portal parsers.
"""

from __future__ import annotations

import re

_CASE_NUMBER_PREFIX_SPACE_RE = re.compile(r"^([A-Za-z]+)\s+(?=/)")


def normalize_case_number(value: str | None) -> str:
    """Collapse a stray space between a case-type prefix and the slash that
    follows it (e.g. "WP /26147/2026" -> "WP/26147/2026") -- a formatting
    quirk of the source portal HTML cell -- plus leading/trailing space and
    whitespace runs. Any other internal spacing in the value is left
    untouched ("OS 138 / 2008" is how some courts write it)."""
    cleaned = re.sub(r"\s+", " ", (value or "").strip())
    if not cleaned:
        return cleaned
    return _CASE_NUMBER_PREFIX_SPACE_RE.sub(r"\1", cleaned)
