"""
Unit tests for the LangGraph node functions.

Tests the pure-logic aspects of each node using mocked LLM and
search services, verifying state transformations.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from core.services.graph.nodes import (
    _build_context,
    _parse_json_safe,
    answer_generator,
    chunk_ranker,
    citation_extractor,
    handle_low_confidence,
    handle_no_results,
    query_analyzer,
    query_router,
    response_formatter,
)
from core.services.graph.state import AgentState


def _make_state(**overrides) -> AgentState:
    """Build a minimal valid AgentState with sensible defaults."""
    defaults: AgentState = {
        "user_query": "What is the motion about?",
        "case_id": 1,
        "conversation_id": 1,
        "conversation_history": [],
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
    defaults.update(overrides)
    return defaults


def _make_chunk(chunk_id=1, doc_id=1, text="Sample chunk text", score=0.9):
    return {
        "chunk_id": chunk_id,
        "document_id": doc_id,
        "chunk_index": 0,
        "text": text,
        "score": score,
        "rerank_score": 0.0,
        "metadata": {
            "filename": f"doc_{doc_id}.pdf",
            "document_type": "motion",
            "case_id": 1,
            "file_type": "pdf",
        },
    }


class TestParseJsonSafe(TestCase):
    """Tests for the JSON parsing helper."""

    def test_valid_json(self):
        result = _parse_json_safe('{"key": "value"}')
        self.assertEqual(result, {"key": "value"})

    def test_json_with_code_fences(self):
        result = _parse_json_safe('```json\n{"key": "value"}\n```')
        self.assertEqual(result, {"key": "value"})

    def test_invalid_json_returns_empty_dict(self):
        result = _parse_json_safe("not json at all")
        self.assertEqual(result, {})


class TestBuildContext(TestCase):
    """Tests for the context formatting helper."""

    def test_builds_numbered_context(self):
        chunks = [_make_chunk(chunk_id=1), _make_chunk(chunk_id=2, doc_id=2)]
        context = _build_context(chunks)
        self.assertIn("[Document 1:", context)
        self.assertIn("[Document 2:", context)

    def test_empty_chunks(self):
        self.assertEqual(_build_context([]), "")


class TestQueryRouter(TestCase):
    """Tests for the query_router node."""

    def test_classifies_query_type(self):
        mock_llm = MagicMock()
        mock_llm.generate_with_json.return_value = (
            '{"query_type": "simple_qa", "needs_clarification": false}'
        )

        state = _make_state()
        result = query_router(state, llm=mock_llm)

        self.assertEqual(result["query_type"], "simple_qa")
        self.assertFalse(result["requires_clarification"])
        mock_llm.generate_with_json.assert_called_once()

    def test_defaults_to_simple_qa_on_invalid_type(self):
        mock_llm = MagicMock()
        mock_llm.generate_with_json.return_value = (
            '{"query_type": "invalid_type", "needs_clarification": false}'
        )

        state = _make_state()
        result = query_router(state, llm=mock_llm)

        self.assertEqual(result["query_type"], "simple_qa")

    def test_marks_clarification_needed(self):
        mock_llm = MagicMock()
        mock_llm.generate_with_json.return_value = (
            '{"query_type": "unclear", "needs_clarification": true, '
            '"clarification_question": "Which case?"}'
        )

        state = _make_state()
        result = query_router(state, llm=mock_llm)

        self.assertTrue(result["requires_clarification"])
        self.assertEqual(result["clarification_question"], "Which case?")


class TestQueryAnalyzer(TestCase):
    """Tests for the query_analyzer node."""

    def test_extracts_filters(self):
        mock_llm = MagicMock()
        mock_llm.generate_with_json.return_value = (
            '{"document_types": ["motion"], "date_range": {}, '
            '"entities": ["Smith"], "specific_docs": []}'
        )

        state = _make_state()
        result = query_analyzer(state, llm=mock_llm)

        self.assertEqual(result["extracted_filters"]["document_types"], ["motion"])
        self.assertEqual(result["extracted_filters"]["entities"], ["Smith"])


class TestChunkRanker(TestCase):
    """Tests for the chunk_ranker node."""

    def test_reranks_by_llm_scores(self):
        mock_llm = MagicMock()
        mock_llm.generate_with_json.return_value = '{"scores": [3, 9, 7]}'

        chunks = [
            _make_chunk(chunk_id=1, score=0.9),
            _make_chunk(chunk_id=2, score=0.8),
            _make_chunk(chunk_id=3, score=0.7),
        ]
        state = _make_state(retrieved_chunks=chunks, chunk_count=3)
        result = chunk_ranker(state, llm=mock_llm)

        # Chunk 2 (score 9) should be first
        self.assertEqual(result["retrieved_chunks"][0]["chunk_id"], 2)

    def test_empty_chunks_returns_unchanged(self):
        mock_llm = MagicMock()
        state = _make_state(retrieved_chunks=[], chunk_count=0)
        result = chunk_ranker(state, llm=mock_llm)
        self.assertEqual(result["chunk_count"], 0)
        mock_llm.generate_with_json.assert_not_called()

    def test_deduplicates_by_document(self):
        mock_llm = MagicMock()
        mock_llm.generate_with_json.return_value = '{"scores": [9, 8, 7, 6]}'

        # 3 chunks from same document, 1 from another
        chunks = [
            _make_chunk(chunk_id=1, doc_id=1, score=0.9),
            _make_chunk(chunk_id=2, doc_id=1, score=0.8),
            _make_chunk(chunk_id=3, doc_id=1, score=0.7),
            _make_chunk(chunk_id=4, doc_id=2, score=0.6),
        ]
        state = _make_state(retrieved_chunks=chunks, chunk_count=4)
        result = chunk_ranker(state, llm=mock_llm)

        # Max 2 per document
        doc1_count = sum(
            1 for c in result["retrieved_chunks"] if c["document_id"] == 1
        )
        self.assertLessEqual(doc1_count, 2)


class TestAnswerGenerator(TestCase):
    """Tests for the answer_generator node."""

    def test_generates_answer_with_confidence(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "The motion argues for dismissal based on jurisdiction."

        chunks = [_make_chunk(chunk_id=1)]
        state = _make_state(
            retrieved_chunks=chunks,
            chunk_count=1,
            search_confidence=0.85,
            query_type="simple_qa",
        )
        result = answer_generator(state, llm=mock_llm)

        self.assertIn("motion", result["answer"])
        self.assertGreater(result["answer_confidence"], 0)
        mock_llm.generate.assert_called_once()


class TestCitationExtractor(TestCase):
    """Tests for the citation_extractor node."""

    def test_extracts_citations(self):
        mock_llm = MagicMock()
        mock_llm.generate_with_json.return_value = (
            '{"citations": [{"answer_text": "claim", "chunk_indices": [0], '
            '"quote": "relevant quote"}]}'
        )

        chunks = [_make_chunk(chunk_id=10, doc_id=5)]
        state = _make_state(
            answer="The claim is supported.",
            retrieved_chunks=chunks,
            chunk_count=1,
        )
        result = citation_extractor(state, llm=mock_llm)

        self.assertEqual(len(result["citations"]), 1)
        self.assertEqual(result["citations"][0]["chunk_id"], 10)
        self.assertEqual(result["citations"][0]["document_id"], 5)

    def test_no_chunks_returns_empty_citations(self):
        mock_llm = MagicMock()
        state = _make_state(answer="Some answer", retrieved_chunks=[], chunk_count=0)
        result = citation_extractor(state, llm=mock_llm)
        self.assertEqual(result["citations"], [])


class TestResponseFormatter(TestCase):
    """Tests for the response_formatter node."""

    def test_appends_sources_section(self):
        chunks = [_make_chunk(chunk_id=1, doc_id=1)]
        citations = [
            {"chunk_id": 1, "document_id": 1, "citation_text": "quote", "source_type": "chunk"}
        ]
        state = _make_state(
            answer="The motion was filed.",
            retrieved_chunks=chunks,
            citations=citations,
        )
        result = response_formatter(state)

        self.assertIn("**Sources:**", result["answer"])
        self.assertIn("doc_1.pdf", result["answer"])

    def test_no_citations_returns_answer_unchanged(self):
        state = _make_state(answer="The answer.", citations=[])
        result = response_formatter(state)
        self.assertEqual(result["answer"], "The answer.")


class TestHandleNoResults(TestCase):
    """Tests for the handle_no_results node."""

    def test_with_case_id(self):
        state = _make_state(case_id=1)
        result = handle_no_results(state)
        self.assertIn("couldn't find", result["answer"])
        self.assertEqual(result["answer_confidence"], 0.0)
        self.assertEqual(result["citations"], [])

    def test_without_case_id(self):
        state = _make_state(case_id=None)
        result = handle_no_results(state)
        self.assertIn("Selecting a specific case", result["answer"])


class TestHandleLowConfidence(TestCase):
    """Tests for the handle_low_confidence node."""

    def test_adds_disclaimer(self):
        mock_llm = MagicMock()
        mock_llm.generate.return_value = "Some answer content."

        chunks = [_make_chunk()]
        state = _make_state(
            retrieved_chunks=chunks,
            chunk_count=1,
            search_confidence=0.3,
            query_type="simple_qa",
        )
        result = handle_low_confidence(state, llm=mock_llm)

        self.assertIn("not highly confident", result["answer"])
        self.assertIn("Some answer content.", result["answer"])
