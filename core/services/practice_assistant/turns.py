"""Persistence and replay for practice-assistant turns.

How a turn is stored (no schema beyond Conversation.scope and
Message.references exists for it yet):

  - the user Message: `content` = the question; `references` = ONE marker
    entry `{"kind": "practice_request", "v": 1, "client_request_id": ...,
    "turn": {...}}` whose `turn` holds everything of the PracticeTurn that is
    not on the assistant row (ids, intent, status, summary, case_candidates,
    action_card, report, as_of). A replay rebuilds the cards from it and
    writes nothing; a turn stored before `report` existed replays with
    report null;
  - the assistant Message: `content` = the answer; `references` = the
    turn's sources, a plain list of contract `Reference`s.

So an assistant row's `references` stay a clean Reference list for the
history endpoint, and the marker rides on the user row (the only entry there
whose kind is not a RefKind).

Idempotency: a repeat of (owner, practice scope, client_request_id) returns
the stored turn and writes nothing. Both the lookup and the write happen
inside the caller's transaction after `lock_owner`, a per-owner Postgres
advisory transaction lock, so two concurrent sends of the same request id by
one owner run one after the other and the second sees the first's rows.
What is left: uniqueness is enforced by that lock, not by the database, so a
writer that skips `lock_owner` (or a non-Postgres database, where it is a
no-op) could store a duplicate; and the lookup is a JSON containment scan
over the owner's practice messages, not an index hit. A real
`client_request_id` column with a unique constraint per (owner, scope) would
close both.

A turn that raises is rolled back with the caller's transaction: nothing is
stored, and the same client_request_id can be sent again.
"""
from __future__ import annotations

from typing import Optional

from django.db import connection
from django.utils import timezone

from core.models import Conversation, Message
from core.services.conversation_utils import generate_conversation_title

from .contracts import PracticeTurn

REQUEST_MARKER_KIND = "practice_request"
ENVELOPE_VERSION = 1

# 'PRAC': first key of the two-key advisory lock; the second is the owner id.
# Distinct from the single-key locks in causelists/lock.py ('CAUS') and
# notifications/hearing_reminders.py ('HREM').
ADVISORY_LOCK_NAMESPACE = 0x50524143


def lock_owner(owner_id: int) -> None:
    """Serialise this owner's practice turns until the transaction ends.
    Must be called inside transaction.atomic()."""
    if connection.vendor != "postgresql":
        return
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT pg_advisory_xact_lock(%s, %s)", [ADVISORY_LOCK_NAMESPACE, int(owner_id) % 2**31]
        )


def find_practice_conversation(owner, conversation_id: int) -> Optional[Conversation]:
    """The owner's practice conversation, or None for anything else: another
    owner's, a case / legacy conversation, or an id that does not exist."""
    return Conversation.objects.filter(
        id=conversation_id, owner=owner, scope=Conversation.SCOPE_PRACTICE
    ).first()


def find_replay(owner, client_request_id: str) -> Optional[PracticeTurn]:
    """The stored turn for this request id, if the owner already sent it."""
    user_message = (
        Message.objects.filter(
            owner=owner,
            role="user",
            conversation__owner=owner,
            conversation__scope=Conversation.SCOPE_PRACTICE,
            references__contains=[
                {"kind": REQUEST_MARKER_KIND, "client_request_id": client_request_id}
            ],
        )
        .order_by("id")
        .first()
    )
    if user_message is None:
        return None
    marker = next(
        (
            item
            for item in user_message.references
            if isinstance(item, dict)
            and item.get("kind") == REQUEST_MARKER_KIND
            and item.get("client_request_id") == client_request_id
        ),
        None,
    )
    stored = (marker or {}).get("turn") or {}
    assistant = Message.objects.filter(
        owner=owner,
        id=stored.get("assistant_message_id"),
        conversation_id=user_message.conversation_id,
        role="assistant",
    ).first()
    if assistant is None:
        return None
    return {
        "conversation_id": user_message.conversation_id,
        "user_message_id": user_message.id,
        "assistant_message_id": assistant.id,
        "answer": assistant.content,
        "intent": stored.get("intent"),
        "status": stored.get("status"),
        "sources": assistant.references,
        "summary": stored.get("summary"),
        "case_candidates": stored.get("case_candidates") or [],
        "action_card": stored.get("action_card"),
        "report": stored.get("report"),
        "as_of": stored.get("as_of"),
    }


def store_turn(
    *,
    owner,
    conversation: Optional[Conversation],
    query: str,
    client_request_id: str,
    result: dict,
) -> PracticeTurn:
    """Write the user and assistant messages for a finished turn. A new
    conversation is created with scope practice and no case. `result` is the
    final state of the practice graph."""
    stamp = timezone.now()
    if conversation is None:
        conversation = Conversation.objects.create(
            owner=owner,
            case=None,
            scope=Conversation.SCOPE_PRACTICE,
            title=generate_conversation_title(query),
            last_message_at=stamp,
        )
    else:
        if not conversation.title:
            conversation.title = generate_conversation_title(query)
        conversation.last_message_at = stamp
        conversation.save(update_fields=["title", "last_message_at"])

    user_message = Message.objects.create(
        owner=owner, conversation=conversation, role="user", content=query
    )
    assistant = Message.objects.create(
        owner=owner,
        conversation=conversation,
        role="assistant",
        content=result["answer"],
        references=result["sources"],
    )
    stored = {
        "assistant_message_id": assistant.id,
        "intent": result["intent"],
        "status": result["status"],
        "summary": result["summary"],
        "case_candidates": result["case_candidates"],
        "action_card": result["action_card"],
        "report": result.get("report"),
        "as_of": result["now"].isoformat(),
    }
    user_message.references = [
        {
            "kind": REQUEST_MARKER_KIND,
            "v": ENVELOPE_VERSION,
            "client_request_id": client_request_id,
            "turn": stored,
        }
    ]
    user_message.save(update_fields=["references"])
    return {
        "conversation_id": conversation.id,
        "user_message_id": user_message.id,
        "assistant_message_id": assistant.id,
        "answer": assistant.content,
        "intent": stored["intent"],
        "status": stored["status"],
        "sources": assistant.references,
        "summary": stored["summary"],
        "case_candidates": stored["case_candidates"],
        "action_card": stored["action_card"],
        "report": stored["report"],
        "as_of": stored["as_of"],
    }
