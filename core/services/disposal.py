"""Has the case been disposed of? Two independent signals, neither guessed.

  1. eCourts: the latest successful fetch's case-status block says so
     ("Case disposed", or a Nature of Disposal is recorded).
  2. The order itself: the latest order's text finally disposes of the
     MAIN case -- "this Writ Petition is disposed of", "miscellaneous
     petitions, pending if any, stand closed", "DISPOSING OF THE WRIT
     PETITION". A pattern match on the extracted text, no LLM, so it works
     on every order the worker has read, summarised or not.

Nothing here closes a case. The case page shows a banner offering to, and
the client update says the matter was disposed of instead of "the next
date has not been fixed yet" -- the advocate decides.

The patterns are written against real Telangana HC order text, which is
the court's own OCR and noisy ("miscelianeous petitions, pending if any,
stand closed"), so they key on the operative verbs and tolerate spelling
damage in the nouns. Interim disposals ("I.A. No.1 of 2026 is disposed
of") must NOT match: the main-case nouns below exclude I.A./interlocutory/
miscellaneous applications, which get disposed of all the time while the
case itself goes on.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

# The main-case nouns an order disposes of. Deliberately NOT bare
# "petition"/"application": those are what interim applications are
# called too.
_MAIN_CASE = (
    r"(?:writ\s+petition|writ\s+appeal|w\.?\s?p\.?(?:\s*no\.?\s*[\d/ of]+)?|w\.?\s?a\.?"
    r"|civil\s+revision\s+petition|c\.?\s?r\.?\s?p\.?|criminal\s+(?:petition|appeal|revision\s+case)"
    r"|original\s+petition|original\s+suit|o\.?\s?s\.?|o\.?\s?p\.?"
    r"|appeal|suit|revision|case|matter|lis)"
)
_VERDICT = r"(?:disposed\s+of|dismissed|allowed|partly\s+allowed|closed|decreed|withdrawn|abated)"

_PATTERNS = [
    # "this Writ Petition is disposed of", "the appeal is accordingly allowed",
    # "the suit is decreed", "the matter stands closed"
    re.compile(
        rf"\b(?:this|the|said|present|instant)\s+{_MAIN_CASE}\s+"
        rf"(?:is|are|stands?|shall\s+stand|be|is\s+hereby|are\s+hereby)\s+"
        rf"(?:accordingly\s+|also\s+|hereby\s+)?{_VERDICT}\b",
        re.I,
    ),
    # The High Court's closing formula, only ever used in a final order:
    # "Miscellaneous petitions, if any pending, shall stand closed."
    re.compile(
        r"\bmisc\w*\s+(?:petitions?|applications?)\b[^.]{0,60}?\b(?:shall\s+)?(?:also\s+)?stand\s+closed\b",
        re.I,
    ),
    # The docket slip on HC orders: "ORDER ... DISPOSING OF THE WRIT PETITION".
    re.compile(r"\bdisposing\s+of\s+the\s+" + _MAIN_CASE + r"\b", re.I),
]


def order_text_disposes_case(text: str) -> bool:
    """True when an order's text finally disposes of the main case."""
    text = re.sub(r"\s+", " ", text or "")
    return any(pattern.search(text) for pattern in _PATTERNS)


def mark_order_disposal(order) -> bool:
    """Set order.disposes_case from its document's extracted text (worker,
    after extraction/OCR). Returns the value."""
    document = getattr(order, "document", None)
    disposes = order_text_disposes_case(document.extracted_text if document else "")
    if disposes != order.disposes_case:
        order.disposes_case = disposes
        order.save(update_fields=["disposes_case"])
    return disposes


def snapshot_says_disposed(snapshot: dict | None) -> bool:
    """The eCourts case-status block reports the case as disposed."""
    if not snapshot:
        return False
    status = (snapshot.get("case_status") or "").lower()
    nature = (snapshot.get("nature_of_disposal") or "").strip(" -").lower()
    return "dispos" in status or bool(nature)


@dataclass(frozen=True)
class Disposal:
    source: str  # "ecourts" or "order"
    detail: str  # the portal's nature of disposal, or the order's description
    order_id: int | None = None
    order_date: date | None = None

    def as_dict(self) -> dict:
        return {
            "source": self.source,
            "detail": self.detail,
            "order_id": self.order_id,
            "order_date": self.order_date.isoformat() if self.order_date else None,
        }


def case_disposal(case, *, snapshot: dict | None = None) -> Disposal | None:
    """The disposal signal for `case`, or None while it's still running.

    The ORDER wins when both exist: it carries a date and a document the
    advocate can open. Only the case's latest dated order counts -- an old
    final order on a case later restored/remanded is not the current state.
    """
    from core.models import CourtOrder

    latest = (
        CourtOrder.objects.filter(case=case, order_date__isnull=False)
        .order_by("-order_date", "-id")
        .only("id", "order_date", "order_number", "disposes_case")
        .first()
    )
    if latest is not None and latest.disposes_case:
        return Disposal(
            source="order",
            detail=f"Order {latest.order_number} disposes of the case.",
            order_id=latest.id,
            order_date=latest.order_date,
        )

    if snapshot is None:
        from core.services.court_tracking import latest_snapshot

        snapshot = latest_snapshot(case)
    if snapshot_says_disposed(snapshot):
        nature = (snapshot.get("nature_of_disposal") or "").strip()
        return Disposal(source="ecourts", detail=nature or snapshot.get("case_status") or "Disposed")
    return None
