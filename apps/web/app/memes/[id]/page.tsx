"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { api, type Galaxy, type Meme, type Universe } from "@/lib/api";
import { Icon } from "@/components/icons";
import { GalaxyGraph } from "@/components/universe-graphs";
import { GALAXY_VIEW } from "@/components/universe-layout";
import { TimeStrip } from "@/components/time-strip";
import { EventTime } from "@/components/event-time";
import { claimAnchor } from "@/lib/citations";
import { useReferenceNavigation } from "@/lib/use-reference-navigation";
import { CitationLinks, ReferenceLink } from "@/components/citation-links";
import { EvidenceInspector } from "@/components/evidence-inspector";

/** How precisely an event's date is known, in the reader's words. */
const PRECISION: Record<string, string> = {
  second: "精确到秒",
  day: "精确到日",
  month: "精确到月",
  year: "精确到年",
  unknown: "日期未知",
};
const predicates: Record<string, string> = {
  derived_from: "衍生自",
  variant_of: "变体关系",
  claimed_origin: "起源主张",
  documented_in: "记录于",
  mentions: "涉及实体",
  popularized_by: "走红于",
};
export default function MemePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [loadedMeme, setMeme] = useState<Meme | null>(null);
  const [loadError, setError] = useState<{
    id: string;
    message: string;
  } | null>(null);
  const [loadedGalaxy, setGalaxy] = useState<Galaxy | null>(null);
  // A reused client route must never show the previous record while the new
  // request is loading or has failed (especially when the new record is withdrawn).
  const meme = loadedMeme?.id === id ? loadedMeme : null;
  const galaxy = loadedGalaxy?.meme_id === id ? loadedGalaxy : null;
  const error = loadError?.id === id ? loadError.message : "";
  const navigation = useReferenceNavigation(meme);
  const originHasSupport =
    !!meme &&
    meme.claims.some(
      (claim) =>
        claim.key === "origin" &&
        claim.stance === "supports" &&
        claim.evidence_ids.length > 0 &&
        claim.evidence_ids.every((eid) => navigation.index.has(eid)),
    ) &&
    meme.relations.some(
      (relation) =>
        relation.predicate === "claimed_origin" &&
        relation.assertion_status === "supported" &&
        relation.to_source_id &&
        relation.evidence_ids?.length &&
        relation.evidence_ids.every((eid) => navigation.index.has(eid)),
    );
  const fieldClaims = (key: string, statement: string, stance = "supports") =>
    meme?.claims
      .filter(
        (c) =>
          c.key === key && c.statement === statement && c.stance === stance,
      )
      .flatMap((c) => c.evidence_ids) || [];
  /* The page opens on this meme's own galaxy. It is a picture of the same evidence
     listed below, so if it cannot load the page simply goes without it. */
  useEffect(() => {
    let active = true;
    api<Universe>("/v1/universe")
      .then((data) => {
        if (active)
          setGalaxy(data.galaxies.find((g) => g.meme_id === id) ?? null);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, [id]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    setMeme(null);
    setError(null);
    api<Meme>(`/v1/memes/${id}`, { signal: controller.signal })
      .then((data) => {
        if (data.id !== id) throw new Error("档案标识与请求不一致。");
        if (active) setMeme(data);
      })
      .catch((e) => {
        if (active) setError({ id, message: e.message });
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, [id]);
  return (
    <main id="main" className="page-main">
      <Link href="/" className="back-link">
        返回记忆索引
      </Link>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {!meme && !error && <p role="status">正在读取证据…</p>}
      {meme && (
        <>
          <header className={`detail-header${galaxy ? " has-galaxy" : ""}`}>
            <div className="detail-heading">
              <p className="eyebrow">CULTURAL RECORD / 文化记忆档案</p>
              <h1 className="page-title">{meme.canonical_name}</h1>
              {meme.aliases.length > 0 && (
                <p className="aliases">也叫：{meme.aliases.join(" / ")}</p>
              )}
              <div className="row-meta">
                <span>
                  {meme.evidence.length} 份可核查证据 · 修订{" "}
                  {meme.published_revision}
                </span>
                <span>
                  {meme.origin_status === "unknown"
                    ? "起源尚未确认"
                    : meme.origin_status === "disputed"
                      ? "来源存在争议"
                      : originHasSupport
                        ? "有证据支持的来源主张"
                        : "起源支持材料待核查"}
                </span>
              </div>
              <Link
                className="button outline small galaxy-link-button"
                href={`/universe?meme=${encodeURIComponent(meme.id)}`}
              >
                在星图中查看它的星系 →
              </Link>
            </div>
            {galaxy && (
              <Link
                href={`/universe?meme=${encodeURIComponent(meme.id)}`}
                className="detail-galaxy"
                aria-label={`${meme.canonical_name} 的星系：${galaxy.stars.length} 颗证据星。进入星图。`}
              >
                <svg
                  viewBox={`0 0 ${GALAXY_VIEW.width} ${GALAXY_VIEW.height}`}
                  className="universe-svg detail-galaxy-svg"
                  aria-hidden="true"
                  style={{ "--label-scale": 1.5 } as React.CSSProperties}
                >
                  <GalaxyGraph
                    galaxy={galaxy}
                    activeStarId={null}
                    onSelectStar={() => {}}
                    onHoverStar={() => {}}
                    labelScale={1.5}
                    still
                  />
                </svg>
              </Link>
            )}
          </header>
          {navigation.messages.length > 0 &&
            !navigation.index.has(navigation.activeEvidence || "") && (
              <p className="notice reference-status" role="status">
                {navigation.messages.join(" ")}
              </p>
            )}
          <nav className="record-navigation" aria-label="档案阅读导航">
            {[
              ["claim-definition", "含义"],
              ...(meme.usage_context ? [["claim-usage_context", "语境"]] : []),
              ["origin", "起源"],
              ["timeline", "传播"],
              ["relations", "关联"],
              ["evidence", "证据"],
            ].map(([anchor, label]) => (
              <ReferenceLink
                key={anchor}
                anchor={anchor}
                onNavigate={navigation.navigate}
              >
                {label}
              </ReferenceLink>
            ))}
          </nav>
          <div className="detail-columns">
            <div>
              <section
                className="detail-section reference-target"
                id="claim-definition"
                tabIndex={-1}
              >
                <h2>它是什么意思</h2>
                <p className="detail-copy">{meme.definition}</p>
                <div className="citations">
                  <CitationLinks
                    ids={fieldClaims("definition", meme.definition)}
                    index={navigation.index}
                    onNavigate={navigation.navigate}
                  />
                  {fieldClaims("definition", meme.definition, "contradicts")
                    .length > 0 && (
                    <p className="claim-counter-note">
                      另有相矛盾材料：
                      <CitationLinks
                        ids={fieldClaims(
                          "definition",
                          meme.definition,
                          "contradicts",
                        )}
                        index={navigation.index}
                        onNavigate={navigation.navigate}
                      />
                    </p>
                  )}
                </div>
              </section>
              {meme.usage_context && (
                <section
                  className="detail-section reference-target"
                  id="claim-usage_context"
                  tabIndex={-1}
                >
                  <h2>在什么语境下使用</h2>
                  <p className="detail-copy">{meme.usage_context}</p>
                  <CitationLinks
                    ids={fieldClaims("usage_context", meme.usage_context)}
                    index={navigation.index}
                    onNavigate={navigation.navigate}
                  />
                  {fieldClaims(
                    "usage_context",
                    meme.usage_context,
                    "contradicts",
                  ).length > 0 && (
                    <p className="claim-counter-note">
                      另有相矛盾材料：
                      <CitationLinks
                        ids={fieldClaims(
                          "usage_context",
                          meme.usage_context,
                          "contradicts",
                        )}
                        index={navigation.index}
                        onNavigate={navigation.navigate}
                      />
                    </p>
                  )}
                </section>
              )}
              <section
                className="detail-section reference-target"
                id="origin"
                tabIndex={-1}
              >
                <h2>它从哪里来</h2>
                <p className="muted">
                  {meme.origin_status === "unknown"
                    ? "起源尚未确认。普通使用记录不能代替起源证明。"
                    : meme.origin_status === "disputed"
                      ? "现有来源主张存在争议，以下材料不能作为已确认起源。"
                      : originHasSupport
                        ? "以下是经审核的来源主张；本库最早可验证记录仍不等于全网首创。"
                        : "当前支持性起源引用或来源关联不足，不能在本页确认该主张。"}
                </p>
                {meme.claims.map(
                  (claim, i) =>
                    claim.key === "origin" && (
                      <div
                        key={i}
                        className="claim-block reference-target"
                        id={claimAnchor(meme, claim, i)}
                        tabIndex={-1}
                      >
                        <p className="claim-stance">
                          {claim.stance === "contradicts"
                            ? "相矛盾材料所涉主张，不构成确认"
                            : meme.origin_status === "unknown"
                              ? "材料中的说法，尚未确认"
                              : "支持材料所涉来源主张"}
                        </p>
                        <p>{claim.statement}</p>
                        <CitationLinks
                          ids={claim.evidence_ids}
                          index={navigation.index}
                          onNavigate={navigation.navigate}
                        />
                      </div>
                    ),
                )}
                {!meme.claims.some((claim) => claim.key === "origin") && (
                  <p className="muted">尚无可引用的专门起源断言。</p>
                )}
              </section>
              <section
                className="detail-section reference-target"
                id="timeline"
                tabIndex={-1}
              >
                <h2>传播时间线</h2>
                <p className="muted">
                  事件时间与采集时间分开记录，起止按保存精度显示；时间未知时不补写日期。
                </p>
                {galaxy && <TimeStrip galaxy={galaxy} />}
                {galaxy?.stars.some((star) => star.t !== null) &&
                  meme.events.some((event) => event.occurred_at_end) && (
                    <p className="retrieval-note">
                      图示为证据日期概览；区间事件以下方起止标签为准。
                    </p>
                  )}
                {meme.events.length ? (
                  <ol className="timeline">
                    {meme.events.map((event) => (
                      <li
                        key={event.id}
                        id={`event-${event.id}`}
                        className="reference-target"
                        tabIndex={-1}
                      >
                        <EventTime
                          start={event.occurred_at_start}
                          end={event.occurred_at_end}
                          precision={event.time_precision}
                        />
                        <p>{event.description}</p>
                        <small className="muted">
                          {PRECISION[event.time_precision] ??
                            event.time_precision}{" "}
                          · 时间依据：
                          {event.time_basis}
                        </small>
                        <div>
                          <CitationLinks
                            ids={event.evidence_ids || []}
                            index={navigation.index}
                            onNavigate={navigation.navigate}
                          />
                        </div>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="notice">尚未收录经审核的传播事件。</p>
                )}
              </section>
              <section
                className="detail-section reference-target"
                id="relations"
                tabIndex={-1}
              >
                <h2>衍生与关联</h2>
                {meme.relations.length ? (
                  meme.relations.map((r) => (
                    <div
                      className="relation-row reference-target"
                      key={r.id}
                      id={`relation-${r.id}`}
                      tabIndex={-1}
                    >
                      <div>
                        <span>
                          {predicates[r.predicate] || r.predicate} ·{" "}
                          {r.assertion_status === "disputed"
                            ? "有争议"
                            : "有证据支持"}
                        </span>
                        <CitationLinks
                          ids={r.evidence_ids || []}
                          index={navigation.index}
                          onNavigate={navigation.navigate}
                        />
                      </div>
                      {/* The far end of a relation arrives named and linked. A
                          withdrawn meme comes back with no label and is named only
                          as withdrawn, so a retraction cannot stay readable here.
                          Dates are left out on purpose: the universe page is where
                          dates live, and published_at is UTC. */}
                      {r.target?.availability === "withdrawn" ? (
                        <span className="muted">已撤回</span>
                      ) : r.target?.url ? (
                        <a href={r.target.url} target="_blank" rel="noreferrer">
                          {r.target.label} <Icon name="arrow" size={16} />
                        </a>
                      ) : r.target?.type === "meme" &&
                        r.target.label &&
                        r.to_meme_id ? (
                        <Link href={`/memes/${r.to_meme_id}`}>
                          {r.target.label} <Icon name="arrow" size={16} />
                        </Link>
                      ) : r.target?.label ? (
                        <span>{r.target.label}</span>
                      ) : (
                        <span className="small-code">
                          {r.to_source_id || r.to_entity_id}
                        </span>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="muted">尚无经审核的关联关系。</p>
                )}
              </section>
              {meme.claims.some(
                (claim, i) =>
                  !["event", "relation"].includes(claim.key) &&
                  claimAnchor(meme, claim, i).startsWith("claim-extra-"),
              ) && (
                <section className="detail-section">
                  <h2>补充断言</h2>
                  {meme.claims.map(
                    (claim, i) =>
                      !["event", "relation"].includes(claim.key) &&
                      claimAnchor(meme, claim, i).startsWith(
                        "claim-extra-",
                      ) && (
                        <div
                          key={i}
                          id={claimAnchor(meme, claim, i)}
                          tabIndex={-1}
                          className="claim-block reference-target"
                        >
                          <p className="claim-stance">
                            {claim.stance === "contradicts"
                              ? "相矛盾材料所涉主张"
                              : "支持材料所涉断言"}
                          </p>
                          <p>{claim.statement}</p>
                          <CitationLinks
                            ids={claim.evidence_ids}
                            index={navigation.index}
                            onNavigate={navigation.navigate}
                          />
                        </div>
                      ),
                  )}
                </section>
              )}
              <p className="notice">目前可验证的最早记录，不等于互联网起源。</p>
            </div>
            <EvidenceInspector
              key={meme.id}
              meme={meme}
              navigation={navigation}
            />
          </div>
        </>
      )}
    </main>
  );
}
