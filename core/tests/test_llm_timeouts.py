"""A hung provider must not hold a web worker.

Before: the OpenAI SDK's default timeout is 10 minutes (and it retries
twice), Gemini's query embedding could sleep 30 s per rate-limit hit, and
gunicorn's 120 s arbiter timeout was the only thing that ever ended the
request -- killing the worker and 502-ing whatever else it was serving.
"""

import socket
import threading
import time
from unittest.mock import MagicMock, patch

import httpx
import openai
import pytest
from django.test import override_settings

from core.services.llm_client import LLMClient


@pytest.fixture
def silent_server():
    """Accepts connections and never answers -- a provider that hangs."""
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(5)
    held = []
    stop = threading.Event()

    def accept_loop():
        server.settimeout(0.2)
        while not stop.is_set():
            try:
                held.append(server.accept()[0])
            except OSError:
                continue

    thread = threading.Thread(target=accept_loop, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.getsockname()[1]}/v1"
    stop.set()
    thread.join(timeout=2)
    for conn in held:
        conn.close()
    server.close()


class TestLLMClientTimeout:
    def test_a_hung_provider_raises_instead_of_waiting(self, silent_server):
        client = LLMClient(api_key="k", base_url=silent_server, timeout=0.5, max_retries=0)

        start = time.monotonic()
        with pytest.raises(openai.APITimeoutError):
            client.generate([{"role": "user", "content": "hi"}])

        assert time.monotonic() - start < 5

    def test_a_per_call_timeout_is_one_attempt_even_when_retries_are_configured(self, silent_server):
        client = LLMClient(api_key="k", base_url=silent_server, timeout=30, max_retries=3)

        start = time.monotonic()
        with pytest.raises(openai.APITimeoutError):
            client.generate([{"role": "user", "content": "hi"}], timeout=0.4)

        # One 0.4 s attempt -- not 30 s x 4.
        assert time.monotonic() - start < 4

    @override_settings(LLM_REQUEST_TIMEOUT_SECONDS=17, LLM_MAX_RETRIES=2)
    def test_defaults_come_from_settings(self):
        with patch("core.services.llm_client.OpenAI") as sdk:
            LLMClient(api_key="k")

        kwargs = sdk.call_args.kwargs
        assert isinstance(kwargs["timeout"], httpx.Timeout)
        assert kwargs["timeout"].read == 17
        assert kwargs["timeout"].connect <= 5
        assert kwargs["max_retries"] == 2

    def test_worst_case_for_one_chat_request_fits_inside_the_gunicorn_timeout(self):
        """HyDE (single short attempt) + the answer call (full budget with
        its retries) + the query embedding, all in one request."""
        from django.conf import settings

        answer = settings.LLM_REQUEST_TIMEOUT_SECONDS * (1 + settings.LLM_MAX_RETRIES)
        hyde = settings.AI_HYDE_TIMEOUT_SECONDS
        embedding = 8 * 2  # GeminiEmbeddingService.QUERY_TIMEOUT_SECONDS x QUERY_RETRY_ATTEMPTS
        assert hyde + answer + embedding < 120


class TestHydeIsBounded:
    def test_hyde_asks_for_a_short_single_attempt(self):
        from core.services.graph.nodes import hyde_expand

        llm = MagicMock()
        llm.generate.return_value = "A passage."
        state = {"user_query": "what is the next date"}

        with override_settings(AI_HYDE_TIMEOUT_SECONDS=7):
            hyde_expand(state, llm)

        assert llm.generate.call_args.kwargs["timeout"] == 7

    def test_a_hyde_timeout_degrades_to_the_raw_query(self):
        from core.services.graph.nodes import hyde_expand

        llm = MagicMock()
        llm.generate.side_effect = openai.APITimeoutError(request=httpx.Request("POST", "http://x"))
        state = {"user_query": "what is the next date"}

        result = hyde_expand(state, llm)

        assert result["hyde_passage"] == "what is the next date"


class TestGeminiQueryEmbeddingIsBounded:
    def _service(self):
        from core.services.gemini_embedding_service import GeminiEmbeddingService

        with patch("core.services.gemini_embedding_service.genai.Client"):
            return GeminiEmbeddingService(api_key="k")

    def test_a_rate_limited_query_fails_fast_without_the_30s_sleep(self):
        from google.genai import errors

        service = self._service()
        service._client.models.embed_content.side_effect = errors.APIError(429, {"error": {}})

        with patch("core.services.gemini_embedding_service.time.sleep") as sleep, \
                pytest.raises(errors.APIError):
            service.embed_text("when is the hearing")

        assert service._client.models.embed_content.call_count == service.QUERY_RETRY_ATTEMPTS
        assert all(call.args[0] < service.RATE_LIMIT_RETRY_DELAY for call in sleep.call_args_list)

    def test_the_query_carries_a_request_timeout_in_milliseconds(self):
        service = self._service()
        response = MagicMock()
        response.embeddings = [MagicMock(values=[0.0] * 768)]
        service._client.models.embed_content.return_value = response

        service.embed_text("when is the hearing")

        config = service._client.models.embed_content.call_args.kwargs["config"]
        assert config.http_options.timeout == int(service.QUERY_TIMEOUT_SECONDS * 1000)

    def test_ingestion_keeps_its_patient_retries(self):
        from google.genai import errors

        service = self._service()
        service._client.models.embed_content.side_effect = errors.APIError(429, {"error": {}})

        with patch("core.services.gemini_embedding_service.time.sleep") as sleep, \
                pytest.raises(errors.APIError):
            service.embed_texts(["clause one", "clause two"])

        assert service._client.models.embed_content.call_count == service.DEFAULT_RETRY_ATTEMPTS
        assert any(call.args[0] >= service.RATE_LIMIT_RETRY_DELAY for call in sleep.call_args_list)


class TestPortalCallBudget:
    """Under gthread, gunicorn's --timeout no longer ends a stuck request, so
    the web-facing portal paths carry their own wall-clock budget."""

    @override_settings(COURT_PORTAL_CALL_TIMEOUT_SECONDS=0.3)
    def test_a_portal_that_never_answers_becomes_a_portal_error(self):
        import asyncio

        from core.services.court_data.ecourts_provider import _run_bounded
        from core.services.court_data.exceptions import CourtPortalError

        async def hangs():
            await asyncio.sleep(30)

        start = time.monotonic()
        with pytest.raises(CourtPortalError, match="did not answer within"):
            _run_bounded(hangs(), label="fetch by CNR")

        assert time.monotonic() - start < 5

    @override_settings(COURT_PORTAL_CALL_TIMEOUT_SECONDS=5)
    def test_a_normal_call_returns_its_result_untouched(self):
        from core.services.court_data.ecourts_provider import _run_bounded

        async def answers():
            return {"cnr": "ABCD010000012026"}

        assert _run_bounded(answers(), label="fetch case") == {"cnr": "ABCD010000012026"}

    def test_the_budget_fits_inside_the_gunicorn_timeout(self):
        from django.conf import settings

        assert settings.COURT_PORTAL_CALL_TIMEOUT_SECONDS < 120
