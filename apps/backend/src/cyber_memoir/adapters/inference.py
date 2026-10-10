import hashlib
import json
import math
import threading
import time
from collections import OrderedDict
from functools import lru_cache

import httpx

from cyber_memoir.config import settings


def embedder():
    cfg = settings()
    return _load_embedder(
        cfg.embedding_model, getattr(cfg, "embedding_device", ""), getattr(cfg, "embedding_threads", 0)
    )


@lru_cache(maxsize=1)
def _load_embedder(model: str, device: str, threads: int):
    from FlagEmbedding import BGEM3FlagModel

    if threads > 0:
        import torch

        torch.set_num_threads(threads)
    return BGEM3FlagModel(model, use_fp16=False, devices=device or None)


_EMBED = threading.Lock()


def embed(texts: list[str]) -> list[list[float]] | None:
    if settings().embedding_backend != "local":
        return None
    if not texts:
        return []
    with _EMBED:
        vectors = embedder().encode(texts, batch_size=8, max_length=1024)["dense_vecs"].tolist()
    if len(vectors) != len(texts) or any(
        len(vector) != 1024 or not all(math.isfinite(float(v)) for v in vector) for vector in vectors
    ):
        raise ValueError("Invalid BGE-M3 dense vectors")
    return [[float(value) for value in vector] for vector in vectors]


# One rerank at a time. The model is a 568M-parameter cross-encoder scoring on CPU,
# and a single call already spreads across every core: measured 2026-09-14 on the
# development box, one search took 1.2-3.5s warm, three at once finished none of them
# inside 30s while the container sat pegged and the proxy in front of it returned 500.
# The lock also covers building the model, because lru_cache does not hold anything
# while the wrapped function runs - two cold callers would each load 2.3GB of weights.
#
# Queueing makes the second caller wait. It does not make anyone answer without
# calibrated scores, which is the alternative worth refusing: an uncalibrated run
# cannot enforce the retrieval floor, so the archive would answer where it should
# abstain. If the queue is the bottleneck, the fix is more machine, not a looser answer.
_RERANK = threading.Lock()
_SCORES: OrderedDict[tuple[object, str], tuple[float, tuple[float, ...]]] = OrderedDict()
_SCORE_TTL = 300
_SCORE_LIMIT = 64


def reranker():
    cfg = settings()
    return _load_reranker(cfg.reranker_model, cfg.reranker_threads, getattr(cfg, "reranker_device", ""))


@lru_cache(maxsize=1)
def _load_reranker(model: str, threads: int, device: str):
    from FlagEmbedding import FlagReranker

    if threads > 0:
        import torch

        # Left alone by default: torch picks a sensible count per machine. Set it to
        # keep a shared box responsive while a rerank runs.
        torch.set_num_threads(threads)
    return FlagReranker(model, use_fp16=False, devices=device or None)


def rerank(query: str, texts: list[str]) -> list[float] | None:
    cfg = settings()
    if cfg.reranker_backend != "local" or not texts:
        return None
    # Adapted from PR #14. Reuse scores, never eligibility, facts or answers.
    # Hold the provider itself in the key so a replaced provider cannot inherit
    # stale scores through Python object-ID reuse. The cache is bounded below.
    provider = reranker
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                getattr(cfg, "reranker_model", ""),
                getattr(cfg, "reranker_threads", 0),
                getattr(cfg, "reranker_device", ""),
                query,
                texts,
            ],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    key = (provider, fingerprint)
    with _RERANK:
        cached = _SCORES.get(key)
        if cached and time.monotonic() - cached[0] < _SCORE_TTL:
            _SCORES.move_to_end(key)
            return list(cached[1])
        scores = provider().compute_score([[query, text] for text in texts], normalize=True)
        values = [float(scores)] if isinstance(scores, (float, int)) else [float(x) for x in scores]
        if len(values) != len(texts) or not all(math.isfinite(x) and 0 <= x <= 1 for x in values):
            raise ValueError("Invalid reranker scores")
        _SCORES[key] = (time.monotonic(), tuple(values))
        _SCORES.move_to_end(key)
        while len(_SCORES) > _SCORE_LIMIT:
            _SCORES.popitem(last=False)
        return values


def generate_json(system: str, payload: dict) -> dict | None:
    cfg = settings()
    if not cfg.llm_base_url or not cfg.llm_model:
        return None
    # Operator-configured inference endpoint, never taken from a submitted source.
    with httpx.Client(timeout=90) as client:
        response = client.post(
            f"{cfg.llm_base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {cfg.llm_api_key}"},
            json={
                "model": cfg.llm_model,
                "temperature": 0,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
            },
        )
        response.raise_for_status()
        return json.loads(response.json()["choices"][0]["message"]["content"])
