"""
AI Workflow orchestrator for the Case Intel application.

This module is the primary entry point for Django code to invoke the
LangGraph AI pipeline. It handles:
    - Graph lifecycle (lazy initialization)
    - Conversation persistence (load history, save response)
    - Citation persistence

All Django ORM interactions are confined to this module, keeping the
graph nodes free of database concerns.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from django.db import transaction
from django.utils import timezone

from core.models import Citation, Conversation, DocumentChunk, Message
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
    """Orchestrates the LangGraph pipeline and persists results.

    This service is designed to be instantiated once and reused across
    requests. The compiled graph and underlying services are created
    lazily on first use.

    Usage::

        service = AIWorkflowService()
        response = service.process_query(
            user_query="What were the key arguments in the motion to dismiss?",
            case_id=1,
            conversation_id=5,
        )
    """

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
    # Lazy initialization
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
    def _load_conversation_history(
        conversation_id: int, limit: int = 5
    ) -> list[dict]:
        """Load recent messages from the database for context."""
        messages = (
            Message.objects.filter(conversation_id=conversation_id)
            .order_by("-created_at")[:limit]
        )
        # Reverse so oldest is first
        return [
            {"role": msg.role, "content": msg.content}
            for msg in reversed(messages)
        ]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    @staticmethod
    def _save_user_message(conversation: Conversation, content: str) -> Message:
        """Persist the user's message."""
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
        """Persist the assistant's response and its citations."""
        message = Message.objects.create(
            conversation=conversation,
            role="assistant",
            content=content,
        )

        citation_objects = []
        for cit in citations_data:
            citation_objects.append(
                Citation(
                    message=message,
                    source_type=cit.get("source_type", "chunk"),
                    document_id=cit.get("document_id"),
                    chunk_id=cit.get("chunk_id"),
                    citation_text=cit.get("citation_text", ""),
                )
            )

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
        """Retrieve an existing conversation or create a new one."""
        if conversation_id:
            try:
                return Conversation.objects.get(id=conversation_id)
            except Conversation.DoesNotExist:
                logger.warning(
                    "Conversation %d not found, creating new one.",
                    conversation_id,
                )

        title = query[:100] if query else "New Conversation"
        return Conversation.objects.create(
            case_id=case_id,
            title=title,
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
        """Process a user query through the LangGraph pipeline.

        This is the primary entry point for the Django application.
        It loads conversation context, runs the graph, and persists
        the results atomically.

        Args:
            user_query: The user's natural-language question.
            case_id: Optional case to scope the search.
            conversation_id: Optional existing conversation to continue.

        Returns:
            An AIResponse with the answer, confidence, and citations.
        """
        # 1. Conversation setup
        conversation = self._get_or_create_conversation(
            conversation_id, case_id, user_query
        )

        # 2. Save user message
        self._save_user_message(conversation, user_query)

        # 3. Load conversation history
        history = self._load_conversation_history(conversation.id)

        # 4. Build initial state
        initial_state: AgentState = {
            "user_query": user_query,
            "case_id": case_id,
            "conversation_id": conversation.id,
            "conversation_history": history,
            "query_type": "",
            "requires_clarification": False,
            "clarification_question": None,
            "extracted_filters": {},
            "retrieved_chunks": [],
            "chunk_count": 0,
            "search_confidence": 0.0,
            "answer": "",
            "answer_confidence": 0.0,
            "citations": [],
            "error": None,
        }

        # 5. Run the graph
        logger.info(
            "Processing query: conversation=%d, case=%s, query='%s...'",
            conversation.id,
            case_id,
            user_query[:50],
        )

        try:
            result = self._get_graph().invoke(initial_state)
        except Exception:
            logger.exception("Graph execution failed for conversation %d", conversation.id)
            result = {
                **initial_state,
                "answer": (
                    "I encountered an error while processing your question. "
                    "Please try again or rephrase your query."
                ),
                "answer_confidence": 0.0,
                "citations": [],
                "error": "graph_execution_failed",
            }

        # 6. Persist assistant response
        message = self._save_assistant_message(
            conversation,
            result["answer"],
            result.get("citations", []),
        )

        # 7. Update conversation timestamp
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
