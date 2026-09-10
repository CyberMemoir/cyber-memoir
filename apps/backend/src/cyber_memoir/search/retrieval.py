import logging
from collections import defaultdict

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from cyber_memoir.adapters.inference import embed, rerank
from cyber_memoir.application.content import detail
from cyber_memoir.config import settings
from cyber_memoir.domain.models import Alias, Chunk, Evidence, EvidenceLink, Meme, Relation, Source
from cyber_memoir.domain.policy import publication_is_valid
from cyber_memoir.domain.schemas import SearchRequest, normalize
from cyber_memoir.search.indexing import client

log = logging.getLogger(__name__)


def rrf(rankings: list[tuple[list[str], float]], k=60) -> dict[str, float]:
    scores = defaultdict(float)
    for ranking, weight in rankings:
        for rank, identifier in enumerate(dict.fromkeys(ranking), 1):
            scores[identifier] += weight / (k + rank)
    return dict(scores)


def _source_filters(request: SearchRequest):
    filters = []
    if request.platform:
        filters.append(Source.platform == request.platform)
    if request.published_after:
        filters.append(Source.platform_published_at >= request.published_after)
    if request.published_before:
        filters.append(Source.platform_published_at <= request.published_before)
    return filters


def _base(request: SearchRequest):
    return (
        select(Chunk)
        .join(Meme, Chunk.meme_id == Meme.id)
        .join(Evidence, Chunk.evidence_id == Evidence.id)
        .join(Source)
        .where(
            publication_is_valid(),
            Meme.published_revision == Chunk.revision,
            Evidence.verified.is_(True),
            Evidence.retracted.is_(False),
            *_source_filters(request),
        )
    )


def search(db: Session, request: SearchRequest):
    query = normalize(request.query)
    warnings, channels = [], []
    eligible = (
        select(Meme.id)
        .join(EvidenceLink, EvidenceLink.meme_id == Meme.id)
        .join(Evidence)
        .join(Source)
        .where(
            publication_is_valid(),
            Meme.published_revision == EvidenceLink.revision,
            Evidence.verified.is_(True),
            Evidence.retracted.is_(False),
            *_source_filters(request),
        )
        .distinct()
    )
    if not query:
        total = db.scalar(select(func.count()).select_from(eligible.subquery()))
        ids = db.scalars(
            select(Meme.id)
            .where(Meme.id.in_(eligible))
            .order_by(Meme.created_at.desc(), Meme.id)
            .offset(request.offset)
            .limit(request.limit)
        ).all()
        return {
            "items": [detail(db, mid) for mid in ids],
            "total": total,
            "channels": ["catalog"],
            "degraded": [],
            "query": request.query,
        }
    exact_memes = set(
        db.scalars(select(Alias.meme_id).where(Alias.normalized == query, Alias.meme_id.in_(eligible)))
    )
    exact_memes.update(
        db.scalars(
            eligible.where(
                or_(
                    func.lower(Source.platform_item_id) == query,
                    func.lower(Source.canonical_url) == query,
                )
            )
        )
    )
    cfg = settings()
    rankings = []
    exact = (
        db.scalars(
            _base(request).where(Chunk.meme_id.in_(exact_memes)).limit(cfg.retrieval_channel_limit)
        ).all()
        if exact_memes
        else []
    )
    rankings.append(([x.id for x in exact], cfg.rrf_weight_exact_alias))
    channels.append("exact_alias")
    if settings().opensearch_url:
        try:
            filters = []
            if request.platform:
                filters.append({"term": {"platform": request.platform}})
            if request.published_after or request.published_before:
                bounds = {}
                if request.published_after:
                    bounds["gte"] = request.published_after.isoformat()
                if request.published_before:
                    bounds["lte"] = request.published_before.isoformat()
                filters.append({"range": {"published_at": bounds}})
            result = client().search(
                index=settings().search_index,
                body={
                    "size": cfg.retrieval_channel_limit,
                    "query": {
                        "bool": {
                            "must": [
                                {
                                    "multi_match": {
                                        "query": query,
                                        "fields": ["name^4", "text"],
                                        "type": "best_fields",
                                    }
                                }
                            ],
                            "filter": filters,
                        }
                    },
                },
            )
            rankings.append(([x["_id"] for x in result["hits"]["hits"]], cfg.rrf_weight_bm25))
            channels.append("bm25")
        except Exception as exc:
            warnings.append("bm25_unavailable")
            log.info("bm25 failed: %s", type(exc).__name__)
    else:
        warnings.append("bm25_disabled")
    if settings().embedding_backend == "local":
        try:
            vector = embed([query])[0]
            nearest = db.scalars(
                _base(request)
                .where(Chunk.embedding_model == settings().embedding_model, Chunk.embedding.is_not(None))
                .order_by(Chunk.embedding.cosine_distance(vector))
                .limit(cfg.retrieval_channel_limit)
            ).all()
            rankings.append(([x.id for x in nearest], cfg.rrf_weight_vector))
            channels.append("vector")
        except Exception as exc:
            warnings.append("vector_unavailable")
            log.info("vector failed: %s", type(exc).__name__)
    else:
        warnings.append("vector_disabled")
    if "bm25" not in channels:
        fallback = db.scalars(
            _base(request)
            .where(
                or_(
                    Chunk.text.contains(query, autoescape=True),
                    Meme.normalized_name.contains(query, autoescape=True),
                )
            )
            .limit(cfg.retrieval_channel_limit)
        ).all()
        # The fallback stands in for bm25, so it carries the bm25 weight rather than its own knob.
        rankings.append(([x.id for x in fallback], cfg.rrf_weight_bm25))
        channels.append("lexical_fallback")
    fused = rrf(rankings, k=cfg.rrf_k)
    # Untrusted/stale index documents cannot bypass current database visibility.
    chunks = db.scalars(_base(request).where(Chunk.id.in_(list(fused)))).all() if fused else []
    chunks.sort(key=lambda c: (-fused[c.id], c.id))
    seeds = list(dict.fromkeys([*sorted(exact_memes), *(x.meme_id for x in chunks[:30])]))[:10]
    relations = db.scalars(
        select(Relation)
        .join(Meme, Relation.meme_id == Meme.id)
        .where(
            publication_is_valid(),
            Relation.revision == Meme.published_revision,
            Relation.predicate.in_(["derived_from", "variant_of"]),
            Relation.assertion_status == "supported",
            or_(Relation.meme_id.in_(seeds), Relation.to_meme_id.in_(seeds)),
        )
        .limit(20)
    ).all()
    graph_ids = {r.to_meme_id if r.meme_id in seeds else r.meme_id for r in relations} - set(seeds)
    if graph_ids:
        expanded = db.scalars(_base(request).where(Chunk.meme_id.in_(graph_ids)).limit(20)).all()
        for chunk in expanded:
            if chunk.id not in fused:
                chunks.append(chunk)
                fused[chunk.id] = 0.001
    channels.append("graph_1hop")
    # One source cannot consume the entire cross-encoder budget.
    source_counts, candidates = defaultdict(int), []
    for chunk in chunks:
        source_id = db.get(Evidence, chunk.evidence_id).source_id
        if source_counts[source_id] < cfg.retrieval_per_source_cap:
            candidates.append(chunk)
            source_counts[source_id] += 1
        if len(candidates) >= cfg.retrieval_candidate_cap:
            break
    try:
        scores = rerank(query, [f"{db.get(Meme, x.meme_id).canonical_name}\n{x.text}" for x in candidates])
        if scores is not None:
            candidates = [x for _, x in sorted(zip(scores, candidates, strict=True), key=lambda x: -x[0])]
            channels.append("bge_reranker")
        else:
            warnings.append("reranker_disabled")
    except Exception as exc:
        warnings.append("reranker_unavailable")
        log.info("reranker failed: %s", type(exc).__name__)
    ordered = list(dict.fromkeys([*sorted(exact_memes), *(x.meme_id for x in candidates)]))
    items = []
    for mid in ordered[request.offset : request.offset + request.limit]:
        item = detail(db, mid)
        item["exact_match"] = mid in exact_memes
        item["matches"] = [
            {"evidence_id": x.evidence_id, "text": x.text, "offset": x.offset}
            for x in candidates
            if x.meme_id == mid
        ]
        items.append(item)
    return {
        "items": items,
        "total": len(ordered),
        "total_is_candidate_count": True,
        "channels": channels,
        "degraded": warnings,
        "query": request.query,
    }
