import json
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


@lru_cache
def reranker():
    from FlagEmbedding import FlagReranker

    return FlagReranker(settings().reranker_model, use_fp16=False)


def rerank(query: str, texts: list[str]) -> list[float] | None:
    if settings().reranker_backend != "local" or not texts:
        return None
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
