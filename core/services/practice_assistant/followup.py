"""Follow-up questions: "that", "it", "the one on Friday", "the second one".

The previous turn of the same practice conversation is read from what was
stored for it (turns.py): its sources (References to the owner's own rows),
its case chooser and its action card. A follow-up resolves only to cases
named there, and every case id is re-checked against the owner before it is
used, so a stored turn can never widen what a question reaches.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from core.models import Case, Conversation, Message

from .turns import REQUEST_MARKER_KIND

_WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_ORDINALS = {"first": 0, "1st": 0, "second": 1, "2nd": 1, "third": 2, "3rd": 2, "fourth": 3, "4th": 3, "fifth": 4, "5th": 4}

_FOLLOWUP_RE = re.compile(
    r"\b(that|it|this|them|those|these|the same|same case|that case|this case|that matter|this matter|"
    r"that hearing|this hearing|the one|that one|this one|the (?:first|second|third|fourth|fifth|last|1st|2nd|3rd|4th|5th)(?: one)?|"
    r"(?:him|her))\b"
)
# Pronouns that are part of a request's own wording, not a pointer back.
_NOT_A_POINTER_RE = re.compile(r"\b(what is (?:it|that|this) about|is it|it is|that is|this week|this month|this year|that's all)\b")


def previous_turn(owner, conversation: Optional[Conversation]) -> Optional[dict]:
    """{"intent", "sources", "case_candidates", "action_card"} of the latest
    turn in the owner's practice conversation, or None."""
    if conversation is None:
        return None
    user_message = (
        Message.objects.filter(owner=owner, conversation=conversation, role="user").order_by("-id").first()
    )
    if user_message is None:
        return None
    marker = next(
        (item for item in user_message.references or [] if isinstance(item, dict) and item.get("kind") == REQUEST_MARKER_KIND),
        None,
    )
    stored = (marker or {}).get("turn") or {}
    assistant = Message.objects.filter(
        owner=owner, conversation=conversation, role="assistant", id=stored.get("assistant_message_id")
    ).first()
    return {
        "intent": stored.get("intent"),
        "sources": list(assistant.references or []) if assistant else [],
        "case_candidates": stored.get("case_candidates") or [],
        "action_card": stored.get("action_card"),
    }


def is_followup(text: str) -> bool:
    """`text` (normalised, lower case) points back at the previous answer."""
    stripped = _NOT_A_POINTER_RE.sub(" ", text)
    return bool(_FOLLOWUP_RE.search(stripped)) or bool(re.match(r"^(and|also|what about|how about)\b", text))


def _day_of(ref: dict) -> Optional[date]:
    raw = ref.get("recorded_at")
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _case_ids(refs: list[dict]) -> list[int]:
    ids: list[int] = []
    for ref in refs:
        case_id = ref.get("case_id") if ref.get("kind") != "case" else ref.get("id")
        if isinstance(case_id, int) and case_id not in ids:
            ids.append(case_id)
    return ids


def resolve(text: str, previous: dict, owner) -> Optional[dict]:
    """{"case_ids": [...], "described": "..."} when `text` points back at
    cases in the previous turn, else None. One id means that case."""
    refs = [ref for ref in previous.get("sources") or [] if isinstance(ref, dict)]
    card = previous.get("action_card") or {}
    if isinstance(card.get("case_id"), int):
        refs.append({"kind": "case", "id": card["case_id"], "case_id": card["case_id"]})
    for candidate in previous.get("case_candidates") or []:
        if isinstance(candidate, dict) and isinstance(candidate.get("id"), int):
            refs.append({"kind": "case", "id": candidate["id"], "case_id": candidate["id"]})
    if not refs:
        return None

    described = "your last question"
    dated = [ref for ref in refs if ref.get("kind") in ("hearing", "task", "event") and _day_of(ref)]
    weekday = next((day for day in _WEEKDAYS if re.search(rf"\b{day}\b", text)), None)
    ordinal = next((index for word, index in _ORDINALS.items() if re.search(rf"\b{word}\b", text)), None)
    if weekday and dated:
        picked = [ref for ref in dated if _day_of(ref).weekday() == _WEEKDAYS.index(weekday)]
        if not picked:
            return {"case_ids": [], "described": f"nothing on {weekday.capitalize()} in your last answer"}
        refs, described = picked, f"the {weekday.capitalize()} item in your last answer"
        hearings = [ref for ref in refs if ref.get("kind") == "hearing"]
        refs = hearings or refs
    elif ordinal is not None or re.search(r"\b(the )?last( one)?\b", text):
        ordered = [ref for ref in refs if ref.get("kind") in ("hearing", "case", "event", "task", "fee")]
        if not ordered:
            return None
        index = ordinal if ordinal is not None else len(ordered) - 1
        if index >= len(ordered):
            return {"case_ids": [], "described": "an item your last answer did not list"}
        refs, described = [ordered[index]], f"item {index + 1} of your last answer"

    ids = _case_ids(refs)
    owned = set(Case.objects.filter(owner=owner, id__in=ids).values_list("id", flat=True))
    return {"case_ids": [case_id for case_id in ids if case_id in owned], "described": described}


# Needles that are only pointers back, never a case's own name.
POINTER_WORDS = {"that", "it", "this", "them", "those", "these", "the one", "that one", "this one", "him", "her", "same"}
