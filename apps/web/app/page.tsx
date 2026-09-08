"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { api, post, type SearchResult, type Answer } from "@/lib/api";
import { Principles } from "@/components/shell";
import { Icon } from "@/components/icons";

export default function ArchivePage() {
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState<string | null>(null);
  const [rag, setRag] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const serial = useRef(0);
  async function run(nextPlatform = platform, offset = 0) {
    const id = ++serial.current;
    setError("");
    setLoading(true);
    setAnswer(null);
    try {
      const body = { query, platform: nextPlatform, limit: 20, offset };
      const data = await api<SearchResult>("/v1/search", post(body));
      if (serial.current !== id) return;
      setResult(
        offset
          ? { ...data, items: [...(result?.items || []), ...data.items] }
          : data,
      );
      if (rag && query.trim()) {
        const response = await api<Answer>("/v1/answers", post(body));
        if (serial.current === id) setAnswer(response);
      }
    } catch (e) {
      if (serial.current === id) setError((e as Error).message);
    } finally {
      if (serial.current === id) setLoading(false);
    }
  }
  useEffect(() => {
    void run(); /* initial catalog */
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  return (
    <main id="main" className="archive-main">
      <section className="intro">
        <h1>
          记住一个梗，
          <br />
          <span>也记住它从哪里来。</span>
        </h1>
        <p>梗、语境与传播轨迹。每一个解释，都有证据可循。</p>
      </section>
      <form
        className="search-form"
        onSubmit={(e) => {
          e.preventDefault();
          void run();
        }}
      >
        <Icon name="search" size={22} />
        <input
          aria-label="搜索记忆"
          placeholder="搜索梗、别名、创作者或一句话…"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
        />
        <button type="submit" disabled={loading}>
          {loading ? "检索中…" : "搜索记忆"}
        </button>
      </form>
      <div className="filter-bar">
        <div className="tabs" aria-label="平台筛选">
          {[
            [null, "全部平台"],
            ["bilibili", "Bilibili"],
            ["douyin", "抖音"],
          ].map(([id, label]) => (
            <button
              key={label}
              aria-pressed={platform === id}
              className={platform === id ? "active" : ""}
              onClick={() => {
                setPlatform(id);
                void run(id);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <label className="check-label">
          <input
            type="checkbox"
            checked={rag}
            onChange={(e) => setRag(e.target.checked)}
          />
          基于证据回答
        </label>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
          <button className="text-button" onClick={() => void run()}>
            重试
          </button>
        </div>
      )}
      <div className="archive-columns">
        <section className="archive-panel" aria-busy={loading}>
          <div className="panel-heading">
            <h2>记忆索引</h2>
            <span>
              {result?.total ?? "—"} 条{query ? "相关" : "已审核"}记录
            </span>
          </div>
          {answer && (
            <section className="answer">
              <h3>基于证据的回答</h3>
              <p className="answer-text">{answer.answer}</p>
              {answer.uncertainties.map((t) => (
                <p className="uncertainty" key={t}>
                  <Icon name="info" size={17} />
                  {t}
                </p>
              ))}
              <ol className="citations">
                {answer.citations.map((c, i) => (
                  <li key={c.evidence_id}>
                    <a href={c.url} target="_blank" rel="noreferrer">
                      证据 {i + 1} · {c.evidence_id.slice(0, 8)}{" "}
                      <Icon name="arrow" size={15} />
                    </a>
                    <p>{c.text.slice(0, 200)}</p>
                  </li>
                ))}
              </ol>
            </section>
          )}
          {!loading && !result?.items.length && !error && (
            <div className="empty-state">
              <Icon name="archive" size={86} />
              <h3>
                {query ? "这段记忆，还缺少证据" : "第一条记忆，从一个链接开始"}
              </h3>
              <p>
                {query
                  ? "换一个别名试试，或提交你找到的原始来源。"
                  : "提交 Bilibili 或抖音来源，核对证据后进入公共索引。"}
              </p>
              <Link className="button outline" href="/submit">
                提交第一个来源 <Icon name="arrow" />
              </Link>
            </div>
          )}
          {loading && !result && (
            <div className="empty-state muted" role="status">
              正在连接记忆索引…
            </div>
          )}
          {result?.items.map((meme) => (
            <article className="meme-row" key={meme.id}>
              <div className="row-meta">
                <span>
                  {Array.from(
                    new Set(meme.evidence.map((e) => e.source?.platform)),
                  )
                    .map((p) => (p === "bilibili" ? "Bilibili" : "抖音"))
                    .join(" / ")}
                </span>
                <span>
                  {meme.evidence.length} 份证据 · 修订 {meme.published_revision}
                </span>
              </div>
              <Link href={`/memes/${meme.id}`}>
                <h3>
                  {meme.canonical_name}
                  <Icon name="arrow" />
                </h3>
              </Link>
              {meme.aliases.length > 0 && (
                <p className="aliases">也叫 {meme.aliases.join(" / ")}</p>
              )}
              <p>{meme.definition}</p>
              <div className="row-meta">
                <span>
                  {meme.origin_status === "unknown"
                    ? "起源尚未确认"
                    : meme.origin_status === "disputed"
                      ? "来源存在争议"
                      : "有证据支持的来源主张"}
                </span>
                <Link href={`/memes/${meme.id}`}>查看语境与证据</Link>
              </div>
            </article>
          ))}
          {result && result.items.length < result.total && (
            <button
              className="load-more"
              disabled={loading}
              onClick={() => void run(platform, result.items.length)}
            >
              加载更多
            </button>
          )}
        </section>
        <Principles />
      </div>
      {query && result && (
        <p className="retrieval-note">
          检索通道：{result.channels.join(" · ")}
          {result.degraded.length > 0 &&
            ` ｜ 未启用或降级：${result.degraded.join("、")}`}
        </p>
      )}
    </main>
  );
}
