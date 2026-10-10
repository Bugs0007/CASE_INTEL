"""The Case Bot cross-encoder reranker, without torch in the web process.

The reranker is cross-encoder/ms-marco-MiniLM-L-6-v2 (22M parameters). Run
through sentence-transformers it drags torch into every gunicorn worker:
measured, a worker goes from ~128 MB to ~559 MB resident on its first chat
(+431 MB each, on a 2 GB box shared with the job worker). The model itself
is only ~90 MB; the rest is the framework.

The same weights are published as an ONNX graph by the model's authors
(onnx/model.onnx at the revision pinned below). onnxruntime -- already
installed for the CAPTCHA solver -- and the `tokenizers` library run it
without importing torch or transformers. Scores are the model's raw logits,
exactly what CrossEncoder.predict returns for this model (its config sets an
Identity activation), and agree with the torch scorer to ~1e-5 on a
96-pair legal-text check with identical rankings -- see
core/tests/test_reranker.py, which re-checks this when the model is cached.

That score scale matters beyond ordering: graph/nodes.py compares the top
result's score to CONFIDENCE_THRESHOLD and folds it into the answer's
confidence. A plain-RRF fallback (scores ~0.02) would flag every answer as
low-confidence, so "just drop the reranker" is a product change, not a
free saving. RERANKER_BACKEND=none exists for emergencies and says so.

Backends (settings.RERANKER_BACKEND):
    onnx   (default) onnxruntime + tokenizers, no torch.
    torch  the original sentence-transformers CrossEncoder (needs torch).
    none   no reranking; results stay in RRF order.

Loading is lazy, once per process, and thread-safe (gunicorn gthread runs
several request threads in one process). A failed load -- say the first
download can't reach the Hub -- is NOT remembered forever: the next attempt
is allowed after RERANKER_RETRY_SECONDS, and every skipped rerank is logged.
`manage.py warm_reranker` fetches the files ahead of time so the first chat
after a deploy doesn't download 90 MB inside a request.
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, Sequence

from django.conf import settings

logger = logging.getLogger(__name__)

RERANKER_REPO = "cross-encoder/ms-marco-MiniLM-L-6-v2"
# Pinned: the revision whose onnx/model.onnx was checked against the torch
# scorer. Bumping it means re-running that check.
RERANKER_REVISION = "233902d25c440f23af6f7d6e94d2946bac0bee0a"
ONNX_FILE = "onnx/model.onnx"
TOKENIZER_FILE = "tokenizer.json"
MAX_SEQUENCE_LENGTH = 512
# Pairs scored per forward pass. Padding is to the longest pair in the batch,
# so small batches keep short chunks from being padded to a long one.
BATCH_SIZE = 16


class OnnxCrossEncoder:
    """predict(pairs) -> raw logits, like CrossEncoder.predict, minus torch."""

    def __init__(self, model_path: str, tokenizer_path: str, threads: int = 1) -> None:
        import onnxruntime as ort
        from tokenizers import Tokenizer

        tokenizer = Tokenizer.from_file(tokenizer_path)
        tokenizer.enable_truncation(max_length=MAX_SEQUENCE_LENGTH, strategy="longest_first")
        tokenizer.enable_padding(pad_id=0, pad_token="[PAD]")
        self._tokenizer = tokenizer

        options = ort.SessionOptions()
        options.intra_op_num_threads = max(1, threads)
        options.inter_op_num_threads = 1
        # Input lengths vary per request. With the memory-pattern planner on,
        # onnxruntime caches a plan per distinct shape (growing without
        # bound); the CPU arena keeps freed blocks instead of returning them.
        options.enable_mem_pattern = False
        options.enable_cpu_mem_arena = False
        self._session = ort.InferenceSession(
            model_path, options, providers=["CPUExecutionProvider"]
        )
        self._input_names = {i.name for i in self._session.get_inputs()}

    def predict(self, pairs: Sequence[tuple[str, str]], **_ignored) -> list[float]:
        import numpy as np

        scores: list[float] = []
        for start in range(0, len(pairs), BATCH_SIZE):
            encodings = self._tokenizer.encode_batch(list(pairs[start:start + BATCH_SIZE]))
            feed = {
                "input_ids": np.array([e.ids for e in encodings], dtype=np.int64),
                "attention_mask": np.array([e.attention_mask for e in encodings], dtype=np.int64),
                "token_type_ids": np.array([e.type_ids for e in encodings], dtype=np.int64),
            }
            feed = {name: value for name, value in feed.items() if name in self._input_names}
            logits = self._session.run(None, feed)[0]
            scores.extend(float(x) for x in logits.reshape(-1))
        return scores


class _TorchCrossEncoder:
    """The original backend, behind the same predict() the rest of the code uses."""

    def __init__(self) -> None:
        from sentence_transformers import CrossEncoder

        self._model = CrossEncoder(RERANKER_REPO, revision=RERANKER_REVISION)

    def predict(self, pairs: Sequence[tuple[str, str]], **_ignored) -> list[float]:
        return [float(s) for s in self._model.predict(list(pairs), show_progress_bar=False)]


def fetch_onnx_files() -> tuple[str, str]:
    """Paths to the pinned ONNX model and tokenizer, downloading on a miss.

    With a commit-hash revision huggingface_hub serves a cached file without
    contacting the Hub, so after `manage.py warm_reranker` this is offline.
    """
    from huggingface_hub import hf_hub_download

    model = hf_hub_download(RERANKER_REPO, ONNX_FILE, revision=RERANKER_REVISION)
    tokenizer = hf_hub_download(RERANKER_REPO, TOKENIZER_FILE, revision=RERANKER_REVISION)
    return model, tokenizer


def _load(backend: str):
    if backend == "torch":
        return _TorchCrossEncoder()
    model, tokenizer = fetch_onnx_files()
    return OnnxCrossEncoder(
        model, tokenizer, threads=getattr(settings, "RERANKER_ONNX_THREADS", 1)
    )


_lock = threading.Lock()
_reranker = None
_retry_after = 0.0


def get_reranker() -> Optional[object]:
    """The process-wide reranker, or None when disabled or unavailable.

    None never means "unconfigured and quiet": a failed load logs at ERROR and
    callers log each skipped rerank, because results fall back to RRF order
    and lose the cross-encoder's precision.
    """
    global _reranker, _retry_after

    backend = getattr(settings, "RERANKER_BACKEND", "onnx")
    if backend == "none":
        return None
    if _reranker is not None:
        return _reranker

    with _lock:
        if _reranker is not None:  # another thread finished loading while we waited
            return _reranker
        if time.monotonic() < _retry_after:
            return None
        started = time.monotonic()
        try:
            _reranker = _load(backend)
        except Exception:  # noqa: BLE001 -- a bad load must degrade, not 500 a chat
            _retry_after = time.monotonic() + getattr(settings, "RERANKER_RETRY_SECONDS", 300)
            logger.error(
                "Reranker (%s) could not be loaded; Case Bot results fall back to "
                "unreranked RRF order until it can. Retrying in %ss.",
                backend,
                getattr(settings, "RERANKER_RETRY_SECONDS", 300),
                exc_info=True,
            )
            return None
        logger.info("Reranker (%s) loaded in %.1fs.", backend, time.monotonic() - started)
        return _reranker


def reset_for_tests() -> None:
    global _reranker, _retry_after
    with _lock:
        _reranker = None
        _retry_after = 0.0
