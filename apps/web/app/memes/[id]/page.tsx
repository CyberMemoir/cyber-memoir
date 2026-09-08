"use client";
import { use, useEffect, useState } from "react";
import Link from "next/link";
import { api, date, type Meme } from "@/lib/api";
import { Icon } from "@/components/icons";

const predicates: Record<string, string> = {
  derived_from: "衍生自",
  variant_of: "变体关系",
  claimed_origin: "起源主张",
  documented_in: "记录于",
  mentions: "涉及实体",
};
export default function MemePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = use(params);
  const [meme, setMeme] = useState<Meme | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<Meme>(`/v1/memes/${id}`)
      .then((data) => {
        if (active) setMeme(data);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
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
          <header className="detail-header">
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
                    : "有证据支持的来源主张"}
              </span>
            </div>
          </header>
          <div className="detail-columns">
            <div>
              <section className="detail-section">
                <h2>它是什么意思</h2>
                <p className="detail-copy">{meme.definition}</p>
                <div className="citations">
                  {meme.claims
                    .filter((c) => c.key === "definition")
                    .flatMap((c) => c.evidence_ids)
                    .map((eid) => (
                      <a key={eid} href={`#evidence-${eid}`}>
                        [证据 {eid.slice(0, 8)}]{" "}
                      </a>
                    ))}
                </div>
              </section>
              {meme.usage_context && (
                <section className="detail-section">
                  <h2>在什么语境下使用</h2>
                  <p className="detail-copy">{meme.usage_context}</p>
                </section>
              )}
              <section className="detail-section">
                <h2>传播时间线</h2>
                <p className="muted">
                  事件时间与采集时间分开记录，时间未知时不补写日期。
                </p>
                {meme.events.length ? (
                  <ol className="timeline">
                    {meme.events.map((event) => (
                      <li key={event.id}>
                        <time>{date(event.occurred_at_start)}</time>
                        <p>{event.description}</p>
                        <small className="muted">
                          精度：{event.time_precision} · 时间依据：
                          {event.time_basis}
                        </small>
                      </li>
                    ))}
                  </ol>
                ) : (
                  <p className="notice">尚未收录经审核的传播事件。</p>
                )}
              </section>
              <section className="detail-section">
                <h2>衍生与关联</h2>
                {meme.relations.length ? (
                  meme.relations.map((r) => (
                    <div className="relation-row" key={r.id}>
                      <span>
                        {predicates[r.predicate] || r.predicate} ·{" "}
                        {r.assertion_status === "disputed"
                          ? "有争议"
                          : "有证据支持"}
                      </span>
                      {r.to_meme_id ? (
                        <Link href={`/memes/${r.to_meme_id}`}>
                          查看关联梗 <Icon name="arrow" size={16} />
                        </Link>
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
              <p className="notice">目前可验证的最早记录，不等于互联网起源。</p>
            </div>
            <aside>
              <h2 className="section-title" style={{ marginTop: 0 }}>
                回到证据本身
              </h2>
              {meme.evidence.map((e, i) => (
                <article
                  id={`evidence-${e.id}`}
                  className="evidence-box"
                  key={e.id}
                >
                  <div className="evidence-head">
                    <span>
                      证据 {i + 1} · {e.kind}
                    </span>
                    <span>已人工核对</span>
                  </div>
                  <blockquote>{e.text}</blockquote>
                  <p className="small-code">
                    定位：{JSON.stringify(e.locator)}
                  </p>
                  <p className="small-code">SHA-256: {e.content_hash}</p>
                  <a
                    href={e.source?.canonical_url}
                    target="_blank"
                    rel="noreferrer"
                  >
                    {e.source?.title || "查看平台原始来源"}{" "}
                    <Icon name="arrow" size={17} />
                  </a>
                  <p
                    className="muted"
                    style={{ fontSize: 12, margin: "7px 0" }}
                  >
                    平台发布时间：
                    {date(e.source?.platform_published_at || null)}
                  </p>
                  <a
                    style={{ fontSize: 12 }}
                    href={`/api/v1/evidence/${e.id}/artifact`}
                  >
                    下载证据工件
                  </a>
                </article>
              ))}
            </aside>
          </div>
        </>
      )}
    </main>
  );
}
