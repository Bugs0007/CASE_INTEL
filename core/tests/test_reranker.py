"""The Case Bot reranker without torch (core/services/reranker.py).

The parity tests need the model files in the Hugging Face cache (run
`manage.py warm_reranker`); they are skipped, not failed, when absent so a
machine that has never fetched the model can still run the suite.
"""

import os
import subprocess
import sys
import textwrap
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.test import override_settings

from core.services import reranker
from core.services.vector_search_service import VectorSearchService

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _onnx_files_cached():
    from huggingface_hub import try_to_load_from_cache

    paths = [
        try_to_load_from_cache(reranker.RERANKER_REPO, name, revision=reranker.RERANKER_REVISION)
        for name in (reranker.ONNX_FILE, reranker.TOKENIZER_FILE)
    ]
    return paths if all(isinstance(p, str) for p in paths) else None


needs_model = pytest.mark.skipif(
    _onnx_files_cached() is None, reason="reranker files not cached (python manage.py warm_reranker)"
)

QUERIES = [
    "when is the counter affidavit due",
    "what interim relief was granted to the petitioner",
    "which section of the Negotiable Instruments Act applies",
]
PASSAGES = [
    "The respondent is directed to file a counter affidavit within four weeks from today. List on 12.11.2026.",
    "Interim stay of the impugned order dated 04.03.2026 is granted till the next date of hearing.",
    "The complaint is under Section 138 of the Negotiable Instruments Act, 1881 for dishonour of cheque no. 004512.",
    "Sri K. Rao, learned Standing Counsel, appears for the respondent State. None appears for the petitioner.",
    "The lease deed dated 14.02.2019 stipulates monthly rent of Rs. 45,000 with a lock-in period of 11 months.",
    "The delay of 112 days in filing the appeal is condoned subject to payment of costs of Rs. 5,000.",
]
PAIRS = [(q, p) for q in QUERIES for p in PASSAGES]


@pytest.fixture(autouse=True)
def fresh_reranker_state():
    reranker.reset_for_tests()
    yield
    reranker.reset_for_tests()


@needs_model
class TestOnnxMatchesTorch:
    """Dropping torch must not change what the reranker says. Same weights,
    same tokenizer: scores agree to float rounding and rankings are identical."""

    def test_scores_and_rankings_agree_with_the_torch_scorer(self):
        from sentence_transformers import CrossEncoder

        model_path, tokenizer_path = _onnx_files_cached()
        onnx_scores = reranker.OnnxCrossEncoder(model_path, tokenizer_path, threads=1).predict(PAIRS)
        torch_scores = [float(s) for s in CrossEncoder(
            reranker.RERANKER_REPO, revision=reranker.RERANKER_REVISION
        ).predict(PAIRS, show_progress_bar=False)]

        assert max(abs(a - b) for a, b in zip(onnx_scores, torch_scores)) < 1e-3
        for i in range(len(QUERIES)):
            row = slice(i * len(PASSAGES), (i + 1) * len(PASSAGES))
            by_onnx = sorted(range(len(PASSAGES)), key=lambda j: -onnx_scores[row][j])
            by_torch = sorted(range(len(PASSAGES)), key=lambda j: -torch_scores[row][j])
            assert by_onnx == by_torch

    def test_scores_are_raw_logits_on_the_scale_the_confidence_threshold_assumes(self):
        model_path, tokenizer_path = _onnx_files_cached()
        relevant, unrelated = reranker.OnnxCrossEncoder(model_path, tokenizer_path, threads=1).predict([
            (QUERIES[0], PASSAGES[0]),
            (QUERIES[0], PASSAGES[4]),
        ])
        # graph/nodes.py compares the top score with CONFIDENCE_THRESHOLD (0.35):
        # a relevant chunk is clearly above it, an unrelated one clearly below.
        assert relevant > 0.35 > unrelated

    def test_long_pairs_are_truncated_not_rejected(self):
        model_path, tokenizer_path = _onnx_files_cached()
        scorer = reranker.OnnxCrossEncoder(model_path, tokenizer_path, threads=1)
        assert len(scorer.predict([(QUERIES[0], "counter affidavit " * 2000)])) == 1

    def test_more_pairs_than_one_batch(self):
        model_path, tokenizer_path = _onnx_files_cached()
        scorer = reranker.OnnxCrossEncoder(model_path, tokenizer_path, threads=1)
        pairs = PAIRS * 2  # 36 > BATCH_SIZE
        scores = scorer.predict(pairs)
        assert len(scores) == len(pairs)
        assert scores[: len(PAIRS)] == pytest.approx(scores[len(PAIRS):])


class TestLoading:
    @override_settings(RERANKER_BACKEND="none")
    def test_none_disables_reranking_without_loading_anything(self):
        with patch.object(reranker, "_load") as load:
            assert reranker.get_reranker() is None
        load.assert_not_called()

    def test_loaded_once_and_shared_across_threads(self):
        calls = []

        def slow_load(backend):
            calls.append(backend)
            time.sleep(0.2)
            return SimpleNamespace(predict=lambda pairs, **kw: [0.0] * len(pairs))

        results = []
        with patch.object(reranker, "_load", side_effect=slow_load):
            threads = [threading.Thread(target=lambda: results.append(reranker.get_reranker())) for _ in range(8)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        assert len(calls) == 1
        assert len({id(r) for r in results}) == 1 and results[0] is not None

    @override_settings(RERANKER_RETRY_SECONDS=300)
    def test_a_failed_load_degrades_loudly_and_is_retried_later_not_forever(self):
        good = SimpleNamespace(predict=lambda pairs, **kw: [1.0] * len(pairs))
        attempts = iter([OSError("hub unreachable"), good])

        def load(backend):
            outcome = next(attempts)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        with patch.object(reranker, "_load", side_effect=load) as patched,                 patch.object(reranker, "logger") as log:
            assert reranker.get_reranker() is None
            assert "could not be loaded" in log.error.call_args.args[0]
            assert reranker.get_reranker() is None  # inside the cool-down: not retried yet
            assert patched.call_count == 1

            with patch.object(reranker.time, "monotonic", return_value=time.monotonic() + 301):
                assert reranker.get_reranker() is good  # cool-down over: recovers

    def test_importing_the_chat_stack_does_not_import_torch(self):
        script = textwrap.dedent(
            """
            import os, sys
            sys.path.insert(0, r"%s")
            os.environ.setdefault("DJANGO_SETTINGS_MODULE", "case_intel_project.settings")
            import django
            django.setup()
            import core.views.chat
            from core.services import reranker
            from core.services.vector_search_service import VectorSearchService
            print("torch", "torch" in sys.modules, "st", "sentence_transformers" in sys.modules)
            """
            % REPO
        )
        out = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, timeout=180).stdout
        assert "torch False st False" in out


class TestRerankStep:
    def _service(self, **kwargs):
        return VectorSearchService(embedding_service=SimpleNamespace(), **kwargs)

    def _candidates(self, n=4):
        return [(SimpleNamespace(chunk_text=f"chunk {i}"), 0.02 - i * 0.001) for i in range(n)]

    def test_orders_by_reranker_score_and_reports_those_scores(self):
        fake = SimpleNamespace(predict=lambda pairs, **kw: [0.1, 5.0, -3.0, 2.0])
        with patch("core.services.vector_search_service.get_reranker", return_value=fake):
            out = self._service()._rerank("q", self._candidates(), 3)

        assert [c.chunk_text for c, _ in out] == ["chunk 1", "chunk 3", "chunk 0"]
        assert [s for _, s in out] == [5.0, 2.0, 0.1]

    def test_unavailable_reranker_keeps_rrf_order_and_says_so(self):
        with patch("core.services.vector_search_service.get_reranker", return_value=None),                 patch("core.services.vector_search_service.logger") as log:
            out = self._service()._rerank("q", self._candidates(), 2)

        assert [c.chunk_text for c, _ in out] == ["chunk 0", "chunk 1"]
        assert "Reranking skipped" in log.warning.call_args.args[0]

    def test_opting_out_of_the_reranker_is_quiet(self):
        with patch("core.services.vector_search_service.logger") as log:
            out = self._service(use_reranker=False)._rerank("q", self._candidates(), 2)

        assert [c.chunk_text for c, _ in out] == ["chunk 0", "chunk 1"]
        log.warning.assert_not_called()
