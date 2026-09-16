"""Hearing prep sheet: what an advocate needs for one upcoming hearing.

Composition over data already held (assemble.py), plus one cached LLM
paragraph on the state of the matter (briefing.py). Deliberately NOT the
Case Bot pipeline -- the inputs are already structured, and a chat run
would create Conversation rows nobody asked for.
"""

from .assemble import HearingDigest, assemble_hearing_digest
from .briefing import (
    BriefingError,
    generate_case_briefing,
    get_briefing_state,
    request_briefing,
)

__all__ = [
    "BriefingError",
    "HearingDigest",
    "assemble_hearing_digest",
    "generate_case_briefing",
    "get_briefing_state",
    "request_briefing",
]
