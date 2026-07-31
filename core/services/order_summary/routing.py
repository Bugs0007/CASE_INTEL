"""Decide, without calling the LLM, whether an order needs the LLM.

Every order goes through classify_order_text() first. Three of the four
outcomes cost nothing; only ROUTE_LLM spends money. On a free product
that gate is the feature, not an optimisation.

Routing is deliberately TWO-SIDED: an order may only take a free path
when there is positive evidence of routineness AND no evidence of
substance. A short order that says "adjourned to 12.08.2026" is routine;
a short order that says "adjourned to 12.08.2026. Respondent shall file
counter by then" is NOT, and must reach the LLM.

The substantive-marker veto therefore applies GLOBALLY, ahead of every
length shortcut -- including the "too short to carry directions" one.
Length alone is not evidence of emptiness: plenty of two-line orders do
real work. Getting this backwards would silently drop real directions,
which is far worse than paying for a call.
"""

from __future__ import annotations

import re

ROUTE_UNREADABLE = "unreadable"
ROUTE_SHORT = "short"
ROUTE_ROUTINE = "routine"
ROUTE_LLM = "llm"

# Below this there is effectively no text: a scanned PDF whose OCR never
# ran or produced nothing. Not "no directions" -- we genuinely cannot
# read the order, which the UI must say plainly.
MIN_READABLE_CHARS = 120

# Too short to carry directions at all (a one-line proceeding note).
SHORT_TEXT_CHARS = 400

# Ceiling for the routine-adjournment path. Beyond this an order is long
# enough to be doing something even if it also adjourns.
ROUTINE_MAX_CHARS = 1500

# Positive evidence of a routine listing/adjournment.
_ADJOURNMENT_MARKERS = [
    r"adjourn(?:ed|ment)?",
    r"\blist(?:ed)?\s+(?:on|for)\b",
    r"\bpost(?:ed)?\s+(?:on|to|for)\b",
    r"\bput\s+up\b",
    r"\bre-?notify\b",
    r"\bstand\s*over\b",
    r"\bcall\s+on\b",
    r"at\s+the\s+request\s+of\s+(?:the\s+)?(?:learned\s+)?counsel",
    r"\bpart\s*-?\s*heard\b",
    r"\bno\s+coram\b",
    r"\bnot\s+before\s+me\b",
    r"await(?:ing)?\s+counter",
    r"\bfor\s+orders\b",
]

# Evidence the order DOES something. Any of these vetoes the routine
# path outright, however short and however adjournment-like the text.
_SUBSTANTIVE_MARKERS = [
    r"\b(?:is|are)\s+directed\b",
    r"\bwe\s+direct\b",
    r"\bshall\s+(?:file|pay|produce|appear|comply|furnish|deposit|submit)\b",
    r"\bit\s+is\s+ordered\b",
    r"\bordered\s+accordingly\b",
    r"\ballowed\b",
    r"\bdismissed\b",
    r"\bset\s+aside\b",
    r"\bquash(?:ed)?\b",
    r"\binterim\b",
    r"\bstatus\s*quo\b",
    r"\bstay(?:ed)?\b",
    r"\binjunction\b",
    r"\bnotice\s+to\b",
    r"\bcosts\b",
    r"\bimpugned\s+order\b",
    r"\bdisposed\s+of\b",
]

_ADJOURNMENT_RE = re.compile("|".join(_ADJOURNMENT_MARKERS), re.IGNORECASE)
_SUBSTANTIVE_RE = re.compile("|".join(_SUBSTANTIVE_MARKERS), re.IGNORECASE)
_WS_RE = re.compile(r"\s+")


def normalize(text: str) -> str:
    """Collapse whitespace so markers spanning a PDF line break still
    match ('adjourned\\n   to' -> 'adjourned to')."""
    return _WS_RE.sub(" ", text or "").strip()


def has_adjournment_marker(text: str) -> bool:
    return bool(_ADJOURNMENT_RE.search(normalize(text)))


def has_substantive_marker(text: str) -> bool:
    return bool(_SUBSTANTIVE_RE.search(normalize(text)))


def classify_order_text(text: str) -> tuple[str, str]:
    """Return (route, reason). `reason` is logged, so it must read well.

    Pure and side-effect free -- the caller owns logging and persistence.
    """
    normalized = normalize(text)
    length = len(normalized)

    if length < MIN_READABLE_CHARS:
        return (
            ROUTE_UNREADABLE,
            f"only {length} characters of extractable text "
            f"(under {MIN_READABLE_CHARS}) -- treating as scanned/unreadable",
        )

    # The substantive-marker veto is GLOBAL, checked before any
    # length-based shortcut. Order matters: a 250-character order reading
    # "the respondents are directed to file their counter affidavit" is
    # short AND carries a real direction, and letting the length check
    # win would template it as "no directions issued" -- dropping the one
    # thing the advocate needed. Length may only route an order away from
    # the model once we know it says nothing operative.
    if has_substantive_marker(normalized):
        return (
            ROUTE_LLM,
            f"{length} characters carrying a substantive marker -- summarising "
            f"regardless of length",
        )

    if length < SHORT_TEXT_CHARS:
        return (
            ROUTE_SHORT,
            f"{length} characters (under {SHORT_TEXT_CHARS}) with no substantive "
            f"marker -- too short to carry directions",
        )

    if length < ROUTINE_MAX_CHARS and has_adjournment_marker(normalized):
        return (
            ROUTE_ROUTINE,
            f"{length} characters, matches a routine-adjournment pattern with "
            f"no substantive marker",
        )

    return ROUTE_LLM, f"{length} characters of substantive text"
