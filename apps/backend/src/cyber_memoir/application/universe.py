"""Everything the universe and galaxy views draw, in one response.

A galaxy is one meme's lineage in the four stages, read from that meme's side:

    source          derived_from -> a source, or a meme it was built on
    popularized_by  popularized_by -> a source
    derivative      remix events
    derived_meme    another published meme that is derived_from this one

Stars are positioned by date and nothing else; stage decides only how a star is
styled. The stages are a causal model and the evidence does not always run in their
order - 才是王道, a derived meme, was spreading four days before the work that
popularized its parent - so drawing stages in sequence would assert an order the
dates contradict.

Dates leave here already read in Beijing, so no client has to get the UTC shift right.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from cyber_memoir.application import timescale
from cyber_memoir.domain.models import Event, EvidenceLink, Meme, Relation, Source
from cyber_memoir.domain.policy import publication_is_valid

STAGES = ("source", "popularized_by", "derivative", "derived_meme")
# Which of a meme's own stars date the moment it became a meme, best first. Its
# sources are last because they are upstream material, often years older.
EMERGENCE_ORDER = ("derivative", "popularized_by", "source")


def _bvid(source: Source) -> str | None:
    if source.platform == "bilibili" and source.platform_item_id.startswith("BV"):
        return source.platform_item_id
    return None


def _star(stage, kind, key, at, *, target_id, label, url=None, bvid=None, tier=None, evidence_ids=()):
    return {
        "id": "%s:%s" % (stage, key),
        "stage": stage,
        "kind": kind,
        "target_id": target_id,
        "label": label,
        "url": url,
        "bvid": bvid,
        "tier": tier,
        "at": at,
        "evidence_ids": sorted(evidence_ids),
    }


def _source_star(stage, key, source: Source, evidence_ids):
    return _star(
        stage,
        "source",
        key,
        source.platform_published_at,
        target_id=source.id,
        label=source.title or source.platform_item_id,
        url=source.canonical_url,
        bvid=_bvid(source),
        tier=source.source_tier,
        evidence_ids=evidence_ids,
    )


def _emergence(stars: list[dict]) -> tuple[datetime | None, str]:
    for stage in EMERGENCE_ORDER:
        dated = [s["at"] for s in stars if s["stage"] == stage and s["kind"] == "source" and s["at"]]
        if dated:
            return min(dated, key=timescale.as_utc), stage
    return None, "none"


def build(db: Session) -> dict:
    memes = {m.id: m for m in db.scalars(select(Meme).where(publication_is_valid()))}
    ids = list(memes)
    current = lambda row: memes[row.meme_id].published_revision == row.revision  # noqa: E731

    relations = [r for r in db.scalars(select(Relation).where(Relation.meme_id.in_(ids))) if current(r)]
    events = [e for e in db.scalars(select(Event).where(Event.meme_id.in_(ids))) if current(e)]
    evidence = defaultdict(set)
    for link in db.scalars(select(EvidenceLink).where(EvidenceLink.meme_id.in_(ids))):
        if current(link):
            if link.relation_id:
                evidence[("relation", link.relation_id)].add(link.evidence_id)
            if link.event_id:
                evidence[("event", link.event_id)].add(link.evidence_id)
    wanted = {r.to_source_id for r in relations if r.to_source_id} | {
        e.to_source_id for e in events if e.to_source_id
    }
    sources = {s.id: s for s in db.scalars(select(Source).where(Source.id.in_(wanted)))} if wanted else {}

    stars: dict[str, list[dict]] = {mid: [] for mid in ids}
    meme_edges: list[tuple[str, str]] = []  # (child, parent): child derived_from parent
    for r in relations:
        refs = evidence[("relation", r.id)]
        if r.predicate in ("derived_from", "popularized_by") and r.to_source_id in sources:
            stage = "source" if r.predicate == "derived_from" else "popularized_by"
            stars[r.meme_id].append(_source_star(stage, r.id, sources[r.to_source_id], refs))
        elif r.predicate == "derived_from" and r.to_meme_id in memes and r.to_meme_id != r.meme_id:
            meme_edges.append((r.meme_id, r.to_meme_id))
    for e in events:
        if e.event_type != "remix":
            continue
        refs = evidence[("event", e.id)]
        if e.to_source_id in sources:
            star = _source_star("derivative", e.id, sources[e.to_source_id], refs)
            # The event's own date is the reviewed one; the source's is its fallback.
            star["at"] = e.occurred_at_start or star["at"]
        else:
            star = _star(
                "derivative",
                "source",
                e.id,
                e.occurred_at_start,
                target_id=None,
                label=e.description,
                evidence_ids=refs,
            )
        stars[e.meme_id].append(star)

    # Emergence reads only a meme's own source-kind stars, so it is settled before any
    # meme-to-meme star is added and cannot chase itself round a cycle.
    emergence = {mid: _emergence(stars[mid]) for mid in ids}
    for child, parent in meme_edges:
        for owner, other, stage in ((child, parent, "source"), (parent, child, "derived_meme")):
            refs = {
                i
                for r in relations
                if r.meme_id == child and r.to_meme_id == parent
                for i in evidence[("relation", r.id)]
            }
            stars[owner].append(
                _star(
                    stage,
                    "meme",
                    "%s>%s" % (child, parent),
                    emergence[other][0],
                    target_id=other,
                    label=memes[other].canonical_name,
                    evidence_ids=refs,
                )
            )

    universe_scale = timescale.build([emergence[mid][0] for mid in ids])
    galaxies = []
    for mid in sorted(
        ids,
        key=lambda m: (
            emergence[m][0] is None,
            emergence[m][0] and timescale.as_utc(emergence[m][0]),
            memes[m].canonical_name,
        ),
    ):
        own = stars[mid]
        scale = timescale.build([s["at"] for s in own])
        for s in own:
            s["t"] = scale.at(s["at"])
            s["date"] = timescale.china_date(s["at"])
        milestones = {}
        for stage in STAGES:
            members = [s for s in own if s["stage"] == stage]
            dated = sorted(
                (s for s in members if s["at"]), key=lambda s: (timescale.as_utc(s["at"]), s["id"])
            )
            first = dated[0] if dated else (sorted(members, key=lambda s: s["id"])[0] if members else None)
            milestones[stage] = first["id"] if first else None
        for s in own:
            s["milestone"] = s["id"] in milestones.values()
        at, basis = emergence[mid]
        galaxies.append(
            {
                "meme_id": mid,
                "name": memes[mid].canonical_name,
                "definition": memes[mid].definition,
                "emergence": {"at": at, "date": timescale.china_date(at), "basis": basis},
                "u": universe_scale.at(at),
                "stars": sorted(own, key=lambda s: (s["t"] is None, s["t"] or 0.0, s["id"])),
                "milestones": milestones,
                "bands": [vars(b) for b in scale.bands],
                "ticks": [vars(t) for t in scale.ticks],
            }
        )

    return {
        "timezone": timescale.CHINA.tzname(None),
        "quiet_gap_days": timescale.QUIET_GAP_DAYS,
        "axis": {
            "bands": [vars(b) for b in universe_scale.bands],
            "ticks": [vars(t) for t in universe_scale.ticks],
        },
        "galaxies": galaxies,
        "links": [
            {"from_meme_id": c, "to_meme_id": p, "predicate": "derived_from"}
            for c, p in sorted(set(meme_edges))
        ],
    }
