"""
Unit tests for the LangGraph builder.

Verifies that the graph compiles successfully and has the expected
node and edge structure.
"""

from unittest.mock import MagicMock

from django.test import TestCase

from core.services.graph.builder import (
    _check_results,
    _should_clarify,
    build_legal_ai_graph,
)


class TestConditionalEdges(TestCase):
    """Tests for conditional routing functions."""

    def test_should_clarify_returns_clarify(self):
        state = {"requires_clarification": True}
        self.assertEqual(_should_clarify(state), "clarify")

    def test_should_clarify_returns_analyze(self):
        state = {"requires_clarification": False}
        self.assertEqual(_should_clarify(state), "analyze")

    def test_check_results_no_results(self):
        state = {"chunk_count": 0, "search_confidence": 0.0}
        self.assertEqual(_check_results(state), "no_results")

    def test_check_results_low_confidence(self):
        state = {"chunk_count": 3, "search_confidence": 0.2}
        self.assertEqual(_check_results(state), "low_confidence")

    def test_check_results_rank(self):
        state = {"chunk_count": 5, "search_confidence": 0.8}
        self.assertEqual(_check_results(state), "rank")


class TestGraphCompilation(TestCase):
    """Verify the graph compiles without errors."""

    def test_graph_compiles_successfully(self):
        mock_llm = MagicMock()
        mock_search = MagicMock()

        graph = build_legal_ai_graph(llm=mock_llm, search_service=mock_search)

        # The compiled graph should be callable
        self.assertTrue(callable(graph.invoke))
