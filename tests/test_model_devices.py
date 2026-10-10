"""Explicit device selection, cache separation and bounded embedding concurrency."""

import sys
import threading
import time
from types import SimpleNamespace

import pytest

from cyber_memoir.adapters import inference
from cyber_memoir.config import settings


def test_device_change_does_not_reuse_another_reranker(monkeypatch, env):
    constructors = []

    class Model:
        def __init__(self, path, **kwargs):
            constructors.append((path, kwargs.get("devices")))
            self.value = 0.6 if kwargs.get("devices") == "mps" else 0.5

        def compute_score(self, pairs, **kwargs):
            return [self.value] * len(pairs)

    monkeypatch.setitem(sys.modules, "FlagEmbedding", SimpleNamespace(FlagReranker=Model))
    monkeypatch.setenv("RERANKER_BACKEND", "local")
    monkeypatch.setenv("RERANKER_MODEL", "synthetic-model-path")
    inference._load_reranker.cache_clear()
    try:
        monkeypatch.setenv("RERANKER_DEVICE", "cpu")
        settings.cache_clear()
        assert inference.rerank("synthetic query", ["synthetic passage"]) == [0.5]
        monkeypatch.setenv("RERANKER_DEVICE", "mps")
        settings.cache_clear()
        assert inference.rerank("synthetic query", ["synthetic passage"]) == [0.6]
        assert constructors == [("synthetic-model-path", "cpu"), ("synthetic-model-path", "mps")]
    finally:
        inference._load_reranker.cache_clear()
        inference._SCORES.clear()
        settings.cache_clear()


def test_embedding_cold_load_and_encode_are_serialized(monkeypatch, env):
    constructors, peak = [], [0]
    active = [0]
    guard = threading.Lock()

    class Dense:
        def tolist(self):
            return [[1.0] + [0.0] * 1023]

    class Model:
        def __init__(self, path, **kwargs):
            constructors.append((path, kwargs.get("devices")))
            time.sleep(0.02)

        def encode(self, texts, **kwargs):
            with guard:
                active[0] += 1
                peak[0] = max(peak[0], active[0])
            time.sleep(0.02)
            with guard:
                active[0] -= 1
            return {"dense_vecs": Dense()}

    monkeypatch.setitem(sys.modules, "FlagEmbedding", SimpleNamespace(BGEM3FlagModel=Model))
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
    monkeypatch.setenv("EMBEDDING_MODEL", "synthetic-embedding-path")
    monkeypatch.setenv("EMBEDDING_DEVICE", "cpu")
    settings.cache_clear()
    inference.embedder.cache_clear() if hasattr(
        inference.embedder, "cache_clear"
    ) else inference._load_embedder.cache_clear()
    try:
        outputs = [None] * 4
        threads = [
            threading.Thread(target=lambda i=i: outputs.__setitem__(i, inference.embed(["synthetic text"])))
            for i in range(4)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        assert not any(thread.is_alive() for thread in threads)
        assert all(output and len(output[0]) == 1024 for output in outputs)
        assert constructors == [("synthetic-embedding-path", "cpu")]
        assert peak[0] == 1
    finally:
        inference.embedder.cache_clear() if hasattr(
            inference.embedder, "cache_clear"
        ) else inference._load_embedder.cache_clear()
        settings.cache_clear()


@pytest.mark.parametrize(
    "vectors", [[], [[1.0] * 1023], [[1.0] * 1024] * 2, [[float("nan")] * 1024], [[float("inf")] * 1024]]
)
def test_embedding_shape_and_finite_values_are_required(monkeypatch, env, vectors):
    class Dense:
        def tolist(self):
            return vectors

    class Model:
        def encode(self, *args, **kwargs):
            return {"dense_vecs": Dense()}

    monkeypatch.setattr(inference, "embedder", lambda: Model())
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
    settings.cache_clear()
    with pytest.raises(ValueError, match="Invalid BGE-M3"):
        inference.embed(["synthetic validation text"])
