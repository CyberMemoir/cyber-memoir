import json
import threading
from functools import lru_cache

import httpx

from cyber_memoir.config import settings


@lru_cache
def embedder():
    from FlagEmbedding import BGEM3FlagModel

    return BGEM3FlagModel(settings().embedding_model, use_fp16=False)


def embed(texts: list[str]) -> list[list[float]] | None:
    if settings().embedding_backend != "local":
        return None
    return embedder().encode(texts, batch_size=8, max_length=1024)["dense_vecs"].tolist()


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


@lru_cache
def reranker():
    from FlagEmbedding import FlagReranker

    threads = settings().reranker_threads
    if threads > 0:
        import torch

        # Left alone by default: torch picks a sensible count per machine. Set it to
        # keep a shared box responsive while a rerank runs.
        torch.set_num_threads(threads)
    return FlagReranker(settings().reranker_model, use_fp16=False)


def rerank(query: str, texts: list[str]) -> list[float] | None:
    if settings().reranker_backend != "local" or not texts:
        return None
    with _RERANK:
        scores = reranker().compute_score([[query, text] for text in texts], normalize=True)
    return [float(scores)] if isinstance(scores, (float, int)) else [float(x) for x in scores]


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
