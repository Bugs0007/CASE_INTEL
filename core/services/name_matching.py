"""Normalising and comparing names of people and organisations.

Two users:
  - party_role.py compares ADVOCATE names (normalize_name + substring).
  - conflict_check.py compares PARTY names across an advocate's cases
    (party_tokens + name_similarity).

Why a token scorer rather than a generic fuzzy ratio: Indian party names
reorder freely ("K. Ramesh" / "Ramesh K"), abbreviate ("V. Ramana Reddy"),
transliterate ("Srinivas" / "Srinivasa"), and carry noise ("M/s", "Pvt
Ltd", "S/o Venkat Rao, aged 45 years"). But whole-string ratios also rate
"Ramesh Kumar" and "Ramesh Kumari" -- different people -- as near-identical.
Aligning token by token, scoring an exact token fully, an initial partly,
and a misspelling only when the token is long enough for one letter not to
change the name, separates those cases in a way that can be reasoned about
and tested.
"""

from __future__ import annotations

import re
from difflib import SequenceMatcher

# ---------------------------------------------------------------------------
# Basic name normalisation (shared with party_role.py)
# ---------------------------------------------------------------------------

_HONORIFIC_RE = re.compile(r"\b(adv|advocate|sr|jr|shri|smt|mr|mrs|ms|dr)\b\.?", re.I)
_PUNCT_RE = re.compile(r"[.,]")
_WS_RE = re.compile(r"\s+")


def normalize_name(name: str) -> str:
    """Lowercase, drop honorifics and full stops/commas, collapse spaces."""
    name = (name or "").lower()
    name = _HONORIFIC_RE.sub(" ", name)
    name = _PUNCT_RE.sub(" ", name)
    return _WS_RE.sub(" ", name).strip()


# ---------------------------------------------------------------------------
# Party names
# ---------------------------------------------------------------------------

# Clauses that describe a party rather than name it.
_PARTY_NOISE = [
    re.compile(r"\b(?:rep(?:resented)?|reptd)\s*\.?\s*by\b.*$", re.I),  # "rep. by its Secretary"
    re.compile(r"\b[sdwc]\s*/\s*o\b[^,;]*", re.I),  # "S/o Venkat Rao"
    re.compile(r"\bage[d]?\s*(?:about\s*)?:?\s*\d+\s*(?:years|yrs)?\b", re.I),
    re.compile(r"\br\s*/\s*o\b.*$", re.I),  # "R/o Hyderabad ..."
    re.compile(r"(?:\band\b|&)\s*(?:\d+\s*)?(?:ors|others|anr|another)\b\.?", re.I),
]
_PARTY_HONORIFIC_RE = re.compile(
    r"\b(?:adv|advocate|sr|jr|shri|sri|smt|mr|mrs|ms|dr|messrs|the)\b\.?|\bm\s*/\s*s\b\.?",
    re.I,
)
# "Kumari" is a title only in front of a name ("Kumari Priya"); after one
# it is part of the name ("Priya Kumari"), so it is stripped only when leading.
_LEADING_TITLE_RE = re.compile(r"^\s*(?:kumari|kum)\b\.?", re.I)
_ORG_SUFFIX_RE = re.compile(
    r"\b(?:private|pvt|limited|ltd|llp|inc|company|co|corporation|corp)\b\.?", re.I
)
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# Spellings of the same name, folded before comparison.
_CANONICAL_TOKENS = {
    "mohd": "mohammed",
    "md": "mohammed",
    "mohammad": "mohammed",
    "muhammad": "mohammed",
    "mohamed": "mohammed",
    "sk": "shaik",
    "shaikh": "shaik",
    "sheikh": "shaik",
}
_STOP_TOKENS = {"and", "of"}

# The State and its police appear in a huge share of matters, on whichever
# side; matching them would flag nearly every criminal case as a conflict.
_GENERIC_PARTY_RE = re.compile(
    r"^(?:state|union|government|govt)\s+of\b"
    r"|\bunion of india\b"
    r"|\bpublic prosecutor\b"
    r"|\bstation house officer\b"
    r"|\bpolice station\b"
    r"|\b(?:commissioner|superintendent|inspector|sub inspector|deputy superintendent) of police\b"
)

# Names so common that sharing only these says nothing.
COMMON_TOKENS = frozenset(
    {
        "kumar", "kumari", "reddy", "rao", "naidu", "sharma", "singh", "devi", "begum",
        "khan", "ali", "mohammed", "shaik", "syed", "goud", "yadav", "patel", "venkata",
        "lakshmi", "bai", "babu", "prasad", "raju", "chowdary", "gupta", "agarwal",
        "traders", "enterprises", "industries", "associates", "constructions", "agencies",
        "services", "group", "sons", "brothers", "india", "hyderabad", "telangana",
    }
)


def split_parties(text: str) -> list[str]:
    """One eCourts party field -> individual party names.

    eCourts lists several parties as "1) A 2) B" or one per line; commas are
    NOT separators here, since they routinely sit inside one party's
    description ("Ramesh, S/o Venkat Rao, aged 45").
    """
    if not text:
        return []
    text = _PARTY_NOISE[4].sub(" ", text)  # "& Ors" before splitting
    parts = re.split(r"(?:^|\s)\(?\d{1,2}\s*[.)]\s+|;|\n", text)
    return [part.strip(" ,.-") for part in parts if part and part.strip(" ,.-")]


def clean_party_name(name: str) -> str:
    """A party name with descriptions and honorifics stripped, lowercase."""
    text = name or ""
    for pattern in _PARTY_NOISE:
        text = pattern.sub(" ", text)
    text = _LEADING_TITLE_RE.sub(" ", text)
    text = _PARTY_HONORIFIC_RE.sub(" ", text)
    text = _NON_ALNUM_RE.sub(" ", text.lower())
    return _WS_RE.sub(" ", text).strip()


def is_generic_party(cleaned: str) -> bool:
    return bool(_GENERIC_PARTY_RE.search(cleaned))


def party_tokens(name: str) -> tuple[str, ...]:
    """Comparable tokens for a party name; empty for generic State parties."""
    cleaned = clean_party_name(name)
    if not cleaned or is_generic_party(cleaned):
        return ()
    cleaned = _ORG_SUFFIX_RE.sub(" ", cleaned)
    tokens = []
    for token in cleaned.split():
        token = _CANONICAL_TOKENS.get(token, token)
        if token not in _STOP_TOKENS and not token.isdigit():
            tokens.append(token)
    return tuple(tokens)


# ---------------------------------------------------------------------------
# Similarity
# ---------------------------------------------------------------------------

INITIAL_SCORE = 0.8  # "K" against "Kumar": consistent, not confirming
FUZZY_PENALTY = 0.9  # a misspelt token counts for less than an exact one
FUZZY_MIN_RATIO_LONG = 0.8  # tokens of 6+ letters
FUZZY_MIN_RATIO_SHORT = 0.92  # shorter tokens: one letter changes the name (Anil/Sunil)
SHORT_TOKEN_LEN = 6


def _token_score(a: str, b: str) -> float:
    if a == b:
        return 1.0
    if len(a) == 1 or len(b) == 1:
        return INITIAL_SCORE if a[0] == b[0] else 0.0
    shortest = min(len(a), len(b))
    if shortest < 4:
        return 0.0
    ratio = SequenceMatcher(None, a, b).ratio()
    threshold = FUZZY_MIN_RATIO_SHORT if shortest < SHORT_TOKEN_LEN else FUZZY_MIN_RATIO_LONG
    return ratio * FUZZY_PENALTY if ratio >= threshold else 0.0


def name_similarity(a: tuple[str, ...], b: tuple[str, ...]) -> int:
    """0-100. Every token of the shorter name is aligned with its best
    unused partner in the longer one; the average is discounted when the
    longer name has tokens the shorter lacks. A match resting only on
    common tokens (a shared surname) scores 0."""
    if not a or not b:
        return 0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    remaining = list(longer)
    total = 0.0
    distinctive = False
    for token in shorter:
        best, best_index = 0.0, None
        for index, other in enumerate(remaining):
            score = _token_score(token, other)
            if score > best:
                best, best_index = score, index
        if best_index is not None:
            partner = remaining.pop(best_index)
            if (
                len(token) > 1
                and len(partner) > 1
                and token not in COMMON_TOKENS
                and partner not in COMMON_TOKENS
            ):
                distinctive = True
        total += best
    if not distinctive:
        return 0
    coverage = len(shorter) / len(longer)
    return round(100 * (total / len(shorter)) * (0.75 + 0.25 * coverage))


def advocate_tokens(name: str) -> tuple[str, ...]:
    """Tokens for a free-text advocate-of-record string (e.g. "APP G.
    Ramesh Kumar" from a District Courts "Search by Advocate" results
    grid), for use with name_similarity.

    Deliberately built on normalize_name (already used for advocate-name
    comparison in party_role.py's substring check) rather than
    party_tokens: party_tokens strips PARTY-shaped noise ("S/o Venkat
    Rao", "aged 45 years", "rep. by its Secretary") that doesn't occur in
    an advocate field and isn't needed here."""
    return tuple(normalize_name(name).split())


def could_match(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Cheap pre-filter before name_similarity: do the names share the
    first two letters of any distinctive token? Two letters, not three, so
    transliterations ("Sreenivas" / "Srinivas") still get compared."""
    def prefixes(tokens):
        return {t[:2] for t in tokens if len(t) >= 4 and t not in COMMON_TOKENS}

    return bool(prefixes(a) & prefixes(b))
