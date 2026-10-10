"""Timing-only tracing does not change outputs, swallow errors or persist query text."""

import importlib
import json
import threading
import time
from functools import lru_cache
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def tracer(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "evals"))
    return importlib.import_module("inference_trace")


def stub():
    module = SimpleNamespace(_EMBED=threading.Lock(), _RERANK=threading.Lock())

    class Model:
        def compute_score(self, pairs):
            return [0.5] * len(pairs)

        def encode(self, texts):
            return texts

    module._load_embedder = lru_cache(maxsize=1)(lambda: Model())
    module._load_reranker = lru_cache(maxsize=1)(lambda: Model())
    scores = {}

    def rerank(query):
        with module._RERANK:
            if query not in scores:
                scores[query] = module._load_reranker().compute_score([query])
            return scores[query]

    def embed_query(query):
        with module._EMBED:
            return module._load_embedder().encode([query])

    module.rerank = rerank
    module.embed_query = embed_query
    return module


def test_tracing_preserves_values_and_distinguishes_cache_hits(tracer, tmp_path):
    module = stub()
    original = module.rerank
    path = tmp_path / "trace.jsonl"
    trace = tracer.InferenceTrace(path, module)
    token = tracer.REQUEST_ID.set("a" * 32)
    try:
        assert module.rerank("private synthetic query") == [0.5]
        assert module.rerank("private synthetic query") == [0.5]
        assert module.embed_query("private synthetic query") == ["private synthetic query"]
    finally:
        tracer.REQUEST_ID.reset(token)
        trace.close()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert len([row for row in rows if row["stage"] == "reranker_compute"]) == 1
    assert len([row for row in rows if row["stage"] == "reranker_total"]) == 2
    assert all(row["request_id"] == "a" * 32 and row["ok"] and row["seconds"] >= 0 for row in rows)
    assert "private synthetic query" not in path.read_text()
    assert module.rerank is original
    assert module.rerank("new untraced query") == [0.5]


def test_loader_errors_are_recorded_and_rethrown(tracer, tmp_path):
    module = stub()

    @lru_cache(maxsize=1)
    def failing():
        raise RuntimeError("private error detail")

    module._load_reranker = failing
    path = tmp_path / "trace.jsonl"
    trace = tracer.InferenceTrace(path, module)
    try:
        with pytest.raises(RuntimeError, match="private"):
            module.rerank("private query")
    finally:
        trace.close()
    rows = [json.loads(line) for line in path.read_text().splitlines()]
    assert {row["stage"] for row in rows if not row["ok"]} == {"reranker_load", "reranker_total"}
    assert "private" not in path.read_text()


def test_lock_wait_is_measured_without_changing_lock_semantics(tracer):
    lock = threading.Lock()
    rows = []
    ready = threading.Event()

    def hold():
        with lock:
            ready.set()
            time.sleep(0.04)

    thread = threading.Thread(target=hold)
    thread.start()
    ready.wait(timeout=1)
    measured = tracer.TimedLock(lock, lambda *args: rows.append(args), "test_lock_wait")
    with measured:
        assert lock.locked()
    thread.join(timeout=1)
    assert not thread.is_alive() and not lock.locked()
    assert rows[0][1] > 0.01


def test_existing_trace_refused_before_monkey_patching(tracer, tmp_path):
    path = tmp_path / "trace.jsonl"
    path.write_text("original")
    module = stub()
    original = module.rerank
    with pytest.raises(FileExistsError):
        tracer.InferenceTrace(path, module)
    assert module.rerank is original and path.read_text() == "original"


def test_failed_trace_write_does_not_leave_lock_held(tracer):
    lock = threading.Lock()

    def fail(*args):
        raise OSError("synthetic I/O error")

    with pytest.raises(OSError):
        with tracer.TimedLock(lock, fail, "test_lock_wait"):
            pass
    assert not lock.locked()
