from uuid import NAMESPACE_URL, uuid5

from opensearchpy import OpenSearch
from sqlalchemy import select
from sqlalchemy.orm import Session

from cyber_memoir.adapters.inference import embed
from cyber_memoir.config import settings
from cyber_memoir.domain.models import Chunk, Evidence, EvidenceLink, Meme, Source


def client():
    return OpenSearch(settings().opensearch_url, timeout=8, max_retries=0)


def ensure_index():
    search = client()
    name = settings().search_index
    if not search.indices.exists(index=name):
        search.indices.create(
            index=name,
            body={
                "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                "mappings": {
                    "properties": {
                        "meme_id": {"type": "keyword"},
                        "evidence_id": {"type": "keyword"},
                        "revision": {"type": "integer"},
                        "name": {"type": "text", "analyzer": "cjk"},
                        "aliases": {"type": "keyword"},
                        "text": {"type": "text", "analyzer": "cjk"},
                        "platform": {"type": "keyword"},
                        "published_at": {"type": "date"},
                    }
                },
            },
        )
    return search


def index_meme(db: Session, meme_id: str):
    # Serialize indexing with publication/retraction. Every job indexes current truth.
    meme = db.scalar(select(Meme).where(Meme.id == meme_id).with_for_update())
    if not meme:
        return
    search = ensure_index() if settings().opensearch_url else None
    if search:
        search.delete_by_query(
            index=settings().search_index,
            body={"query": {"term": {"meme_id": meme.id}}},
            conflicts="proceed",
            refresh=True,
        )
    if meme.status != "published":
        return
    evidence = (
        db.scalars(
            select(Evidence)
            .join(EvidenceLink)
            .where(
                EvidenceLink.meme_id == meme.id,
                EvidenceLink.revision == meme.published_revision,
                Evidence.verified.is_(True),
                Evidence.retracted.is_(False),
            )
        )
        .unique()
        .all()
    )
    chunks = []
    for item in evidence:
        for offset in range(0, len(item.text), 700):
            identifier = str(
                uuid5(NAMESPACE_URL, f"memoir:{meme.id}:{meme.published_revision}:{item.id}:{offset}")
            )
            chunk = db.get(Chunk, identifier)
            if not chunk:
                chunk = Chunk(
                    id=identifier,
                    meme_id=meme.id,
                    revision=meme.published_revision,
                    evidence_id=item.id,
                    offset=offset,
                    text=item.text[offset : offset + 800],
                )
                db.add(chunk)
            chunks.append(chunk)
    vectors = (
        embed([f"{meme.canonical_name}\n{meme.definition}\n{x.text}" for x in chunks]) if chunks else None
    )
    for i, chunk in enumerate(chunks):
        if vectors is not None:
            chunk.embedding, chunk.embedding_model = vectors[i], settings().embedding_model
        if search:
            source = db.get(Source, db.get(Evidence, chunk.evidence_id).source_id)
            search.index(
                index=settings().search_index,
                id=chunk.id,
                body={
                    "meme_id": meme.id,
                    "evidence_id": chunk.evidence_id,
                    "revision": chunk.revision,
                    "name": meme.canonical_name,
                    "aliases": meme.aliases,
                    "text": f"{meme.definition}\n{meme.usage_context}\n{chunk.text}",
                    "platform": source.platform,
                    "published_at": source.platform_published_at.isoformat()
                    if source.platform_published_at
                    else None,
                },
            )
    if search:
        search.indices.refresh(index=settings().search_index)
    db.flush()
