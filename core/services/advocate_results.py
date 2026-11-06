"""Which advocate-search rows are the advocate's own, decided when read.

A search stores every raw row the court returned, each with the Advocate cell as
the court listed it (`listed_advocate_name`, `listed_advocates`). Nothing is
dropped and no verdict is stored. The verdict -- `match_status` -- is computed
here, from the CURRENT search profile, every time results are read:

    matched   -- a spelling the advocate listed as theirs ("Your name")
    check     -- could be them (a plain "Kiranmai", or no advocate listed at all)
    excluded  -- a spelling on the Not me list (hidden by default)
    other     -- the portal's loose matching returned someone else (hidden)

So "Not me" and "That's me" change the labels of an already-finished search the
moment the profile changes, with no new portal search. A row found by a bar-code
search is the exception: the portal matched it on the bar code itself, so it is
`matched` and labelled "Your bar no." whatever name is listed.
"""

from __future__ import annotations

from core.services.name_matching import (
    CHECK,
    EXCLUDED,
    MATCHED,
    OTHER,
    classify_listed_advocates,
)

LABELS = {
    MATCHED: "Your name",
    CHECK: "Check name",
    EXCLUDED: "Hidden (Not me)",
    OTHER: "Other name",
}
BAR_CODE_LABEL = "Your bar no."
BAR_CODE_SOURCE = "bar_code"

_RANK = {MATCHED: 0, CHECK: 1, OTHER: 2, EXCLUDED: 3}


def listed_segments(row: dict) -> list[str]:
    """The advocate names a stored row lists, oldest row shapes included (a row
    saved before `listed_advocates` existed only has `matched_advocate_text`)."""
    segments = [s for s in (row.get("listed_advocates") or []) if s]
    if segments:
        return segments
    text = row.get("listed_advocate_name") or row.get("matched_advocate_text") or ""
    return [text] if text else []


def classify_row(row: dict, profile) -> tuple[str, str]:
    """(match_status, match_label) for one stored row."""
    if row.get("match_source") == BAR_CODE_SOURCE:
        return MATCHED, BAR_CODE_LABEL
    segments = listed_segments(row)
    if not segments:
        # A court grid with no Advocate column: nothing to check the row against.
        return CHECK, LABELS[CHECK]
    status = classify_listed_advocates(segments, profile)
    return status, LABELS[status]


def annotate_rows(rows: list[dict], profile) -> tuple[list[dict], dict[str, int]]:
    """Copies of `rows` with `match_status` / `match_label`, best first, and the
    count of each status over ALL of them. Without a profile the rows come back
    unchanged and uncounted (the old, name-only flow)."""
    if profile is None:
        return rows, {}
    counts = {MATCHED: 0, CHECK: 0, EXCLUDED: 0, OTHER: 0}
    out: list[dict] = []
    for row in rows:
        status, label = classify_row(row, profile)
        counts[status] += 1
        out.append({**row, "match_status": status, "match_label": label})
    out.sort(key=lambda r: _RANK[r["match_status"]])  # stable: keeps court order within a status
    return out, counts


def count_visible(found: list[dict], profile) -> int:
    """Rows the advocate would see by default (matched or worth checking)."""
    if profile is None:
        return len(found)
    return sum(1 for row in found if classify_row(row, profile)[0] in (MATCHED, CHECK))
