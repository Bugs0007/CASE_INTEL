"""
AI Workflow orchestrator for the Case Intel application.

Unchanged in structure from the original — this module owns all Django ORM
interactions and keeps the graph nodes free of database concerns.

The main changes are the updated initial_state dict, which now includes
`hyde_passage` (populated by the hyde_expand node), and compatibility
defaults for `requires_clarification` / `clarification_question` while the
dedicated clarification route remains removed.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from core.models import Citation, Conversation, DocumentChunk, Message
from core.services.conversation_utils import generate_conversation_title
from core.services.graph.builder import build_legal_ai_graph
from core.services.graph.state import AgentState
from core.services.ai_service_factory import get_llm_client, get_embedding_service
from core.services.vector_search_service import VectorSearchService

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AIResponse:
    """Immutable result returned from the AI workflow."""

    answer: str
    confidence: float
    citations: list[dict]
    query_type: str
    requires_clarification: bool
    clarification_question: Optional[str]
    message_id: Optional[int]


class AIWorkflowService:
    """Orchestrates the LangGraph pipeline and persists results."""

    def __init__(
        self,
        llm=None,
        embedding_service=None,
        search_service: Optional[VectorSearchService] = None,
    ) -> None:
        self._llm = llm
        self._embedding_service = embedding_service
        self._search_service = search_service
        self._graph = None

    # ------------------------------------------------------------------
    # Lazy initialisation
    # ------------------------------------------------------------------

    def _get_llm(self):
        if self._llm is None:
            self._llm = get_llm_client()
        return self._llm

    def _get_embedding_service(self):
        if self._embedding_service is None:
            self._embedding_service = get_embedding_service()
        return self._embedding_service

    def _get_search_service(self) -> VectorSearchService:
        if self._search_service is None:
            self._search_service = VectorSearchService(
                embedding_service=self._get_embedding_service()
            )
        return self._search_service

    def _get_graph(self):
        if self._graph is None:
            self._graph = build_legal_ai_graph(
                llm=self._get_llm(),
                search_service=self._get_search_service(),
            )
        return self._graph

    # ------------------------------------------------------------------
    # Conversation history
    # ------------------------------------------------------------------

    @staticmethod
    def _load_conversation_history(conversation_id: int, limit: int = 5) -> list[dict]:
        messages = (
            Message.objects.filter(conversation_id=conversation_id)
            .order_by("-created_at")[:limit]
        )
        return [
            {"role": msg.role, "content": msg.content}
            for msg in reversed(messages)
        ]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _save_user_message(conversation: Conversation, content: str) -> Message:
        return Message.objects.create(
            conversation=conversation,
            role="user",
            content=content,
        )

    @staticmethod
    def _save_assistant_message(
        conversation: Conversation,
        content: str,
        citations_data: list[dict],
    ) -> Message:
        message = Message.objects.create(
            conversation=conversation,
            role="assistant",
            content=content,
        )
        citation_objects = [
            Citation(
                message=message,
                source_type=cit.get("source_type", "chunk"),
                document_id=cit.get("document_id"),
                chunk_id=cit.get("chunk_id"),
                citation_text=cit.get("citation_text", ""),
            )
            for cit in citations_data
        ]
        if citation_objects:
            Citation.objects.bulk_create(citation_objects)
            logger.info(
                "Saved %d citations for message %d",
                len(citation_objects),
                message.id,
            )
        return message

    @staticmethod
    def _get_or_create_conversation(
        conversation_id: Optional[int],
        case_id: Optional[int],
        query: str,
    ) -> Conversation:
        if conversation_id:
            return Conversation.objects.get(id=conversation_id)
        return Conversation.objects.create(
            case_id=case_id,
            title=generate_conversation_title(query),
            last_message_at=timezone.now(),
        )

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    @transaction.atomic
    def process_query(
        self,
        user_query: str,
        case_id: Optional[int] = None,
        conversation_id: Optional[int] = None,
    ) -> AIResponse:
        """Process a user query through the lean 3-node LangGraph pipeline."""
        conversation = self._get_or_create_conversation(
            conversation_id, case_id, user_query
        )
        self._save_user_message(conversation, user_query)
        if not conversation.title:
            conversation.title = generate_conversation_title(user_query)
            conversation.save(update_fields=["title"])
        history = self._load_conversation_history(conversation.id)

        # AgentState for the new 3-node pipeline
        initial_state: AgentState = {
            "user_query": user_query,
            "case_id": case_id,
            "conversation_id": conversation.id,
            "conversation_history": history,
            # Populated by hyde_expand
            "hyde_passage": "",
            "query_type": "",
            "requires_clarification": False,
            "clarification_question": None,
            # Populated by hybrid_search
            "retrieved_chunks": [],
            "chunk_count": 0,
            "search_confidence": 0.0,
            # Populated by generate_answer
            "answer": "",
            "answer_confidence": 0.0,
            "citations": [],
            "error": None,
        }

        logger.info(
            "Processing query: conversation=%d, case=%s, query='%s...'",
            conversation.id,
            case_id,
            user_query[:50],
        )

        try:
            result = self._get_graph().invoke(initial_state)
        except Exception:
            logger.exception(
                "Graph execution failed for conversation %d", conversation.id
            )
            result = {
                **initial_state,
                "answer": (
                    "I encountered an error while processing your question. "
                    "Please try again or rephrase your query."
                ),
                "answer_confidence": 0.0,
                "citations": [],
                "requires_clarification": False,
                "clarification_question": None,
                "error": "graph_execution_failed",
            }

        message = self._save_assistant_message(
            conversation,
            result["answer"],
            result.get("citations", []),
        )

        conversation.last_message_at = timezone.now()
        conversation.save(update_fields=["last_message_at"])

        return AIResponse(
            answer=result["answer"],
            confidence=result.get("answer_confidence", 0.0),
            citations=result.get("citations", []),
            query_type=result.get("query_type", ""),
            requires_clarification=result.get("requires_clarification", False),
            clarification_question=result.get("clarification_question"),
            message_id=message.id,
        )
