"use client";
import { PLATFORMS, platformLabel } from "@/lib/platforms";
import { memoryUrl, referenceUrl } from "@/lib/citations";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  api,
  ApiError,
  post,
  type SearchResult,
  type Answer,
  type Universe,
} from "@/lib/api";
import { Principles } from "@/components/shell";
import { Icon } from "@/components/icons";
import { SkyBand } from "@/components/sky-band";
import { useReducedMotion } from "@/lib/motion";

type ConsoleState = "idle" | "searching" | "answered" | "abstained" | "error";
const ABSTENTION_LABELS = {
  no_public_matches: "暂无可用公开匹配",
  low_relevance: "相关性不足，未作为证据回答",
  no_approved_claims: "暂无可用于回答的已核查断言",
  selection_empty: "未选出足以回答本次提问的断言",
  corpus_changed: "公开档案已变化，请刷新",
};
type SearchRequest = {
  query: string;
  platform: string | null;
  offset: number;
  answer: boolean;
  reveal: boolean;
};

function useRetryRemaining(deadline: number) {
  const [, refresh] = useState(0);
  useEffect(() => {
    if (!deadline) return;
    const timer = window.setInterval(() => {
      refresh((n) => n + 1);
      if (Date.now() >= deadline) window.clearInterval(timer);
    }, 250);
    return () => window.clearInterval(timer);
  }, [deadline]);
  return Math.max(0, Math.ceil((deadline - Date.now()) / 1000));
}

function busyDeadline(error: unknown) {
  return error instanceof ApiError &&
    error.status === 503 &&
    error.code === "inference_busy"
    ? Date.now() + (error.retryAfterSeconds ?? 2) * 1000
    : 0;
}

export default function ArchivePage() {
  const [query, setQuery] = useState("");
  const [platform, setPlatform] = useState<string | null>(null);
  const [rag, setRag] = useState(false);
  const [result, setResult] = useState<SearchResult | null>(null);
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [submittedPlatform, setSubmittedPlatform] = useState<string | null>(
    null,
  );
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [universe, setUniverse] = useState<Universe | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [answerLoading, setAnswerLoading] = useState(false);
  const [answerError, setAnswerError] = useState("");
  const [searchRetryAt, setSearchRetryAt] = useState(0);
  const [answerRetryAt, setAnswerRetryAt] = useState(0);
  const searchRetryRemaining = useRetryRemaining(searchRetryAt);
  const answerRetryRemaining = useRetryRemaining(answerRetryAt);
  const activeRequest = useRef<AbortController | null>(null);
  const answerRequest = useRef<{
    query: string;
    platform: string | null;
  } | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const serial = useRef(0);
  const lastRequest = useRef<SearchRequest | null>(null);
  const index = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();

  function cancel() {
    setSearchRetryAt(0);
    setAnswerRetryAt(0);
    ++serial.current;
    activeRequest.current?.abort();
    if (answerLoading) setAnswerError("已取消回答等待，检索结果已保留。");
    if (loading) setError("已取消检索等待。");
    setLoading(false);
    setAnswerLoading(false);
  }

  async function fetchAnswer(
    body: { query: string; platform: string | null },
    id: number,
  ) {
    answerRequest.current = body;
    const controller = new AbortController();
    activeRequest.current = controller;
    setAnswerLoading(true);
    setAnswerError("");
    setAnswerRetryAt(0);
    const timer = window.setTimeout(() => controller.abort(), 300000);
    try {
      const response = await api<Answer>("/v1/answers", {
        ...post(body),
        signal: controller.signal,
      });
      if (serial.current === id) setAnswer(response);
    } catch (e) {
      if (serial.current === id) {
        setAnswerRetryAt(busyDeadline(e));
        setAnswerError(
          controller.signal.aborted
            ? "回答等待超时。检索结果已保留，可以重试回答。"
            : (e as Error).message,
        );
      }
    } finally {
      window.clearTimeout(timer);
      if (serial.current === id) setAnswerLoading(false);
    }
  }

  async function run(
    nextPlatform = platform,
    offset = 0,
    reveal = false,
    retry?: SearchRequest,
  ) {
    const request = retry ?? {
      query: offset ? submittedQuery : query,
      platform: offset ? submittedPlatform : nextPlatform,
      offset,
      answer: rag,
      reveal,
    };
    lastRequest.current = request;
    const searchQuery = request.query;
    offset = request.offset;
    const id = ++serial.current;
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setAnswerLoading(false);
    setAnswerError("");
    setSearchRetryAt(0);
    setAnswerRetryAt(0);
    setError("");
    setLoading(true);
    setElapsed(0);
    if (!offset) setAnswer(null);
    const timer = window.setTimeout(() => controller.abort(), 300000);
    try {
      const body = {
        query: searchQuery,
        platform: request.platform,
        limit: 20,
        offset,
      };
      const data = await api<SearchResult>("/v1/search", {
        ...post(body),
        signal: controller.signal,
      });
      if (serial.current !== id) return;
      setSubmittedQuery(searchQuery);
      setSubmittedPlatform(body.platform);
      setResult(
        offset
          ? { ...data, items: [...(result?.items || []), ...data.items] }
          : data,
      );
      window.clearTimeout(timer);
      setLoading(false);
      /* A search asked from the console should land where its results are; the
         initial catalogue load should not move the page at all. */
      if (request.reveal && serial.current === id) {
        index.current?.scrollIntoView({
          behavior: reduced ? "auto" : "smooth",
          block: "start",
        });
      }
      if (!offset && request.answer && searchQuery.trim())
        await fetchAnswer(body, id);
    } catch (e) {
      if (serial.current === id) {
        setSearchRetryAt(busyDeadline(e));
        setError(
          controller.signal.aborted
            ? "检索等待超时，请重试或换一个更具体的描述。"
            : (e as Error).message,
        );
      }
    } finally {
      window.clearTimeout(timer);
      if (serial.current === id) setLoading(false);
    }
  }
  useEffect(() => {
    void run(); /* initial catalog */
    return () => {
      ++serial.current;
      activeRequest.current?.abort();
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps
  /* The sky is decoration and a way in; if it fails the page still works, so a
     failure here is silent rather than an error beside the search. */
  useEffect(() => {
    api<Universe>("/v1/universe")
      .then(setUniverse)
      .catch(() => setUniverse(null));
  }, []);
  /* An answer is not instant, so the wait has to look like work rather than a hang,
     without promising a duration this deployment cannot keep. Nothing here fires on
     a keystroke: the run is submitted with the form. */
  useEffect(() => {
    if (!loading && !answerLoading) return;
    const timer = window.setInterval(() => setElapsed((n) => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [loading, answerLoading]);

  const state: ConsoleState = error
    ? "error"
    : loading
      ? "searching"
      : answer
        ? answer.claims.length
          ? "answered"
          : "abstained"
        : "idle";

  return (
    <main id="main" className="archive-main">
      <section className="dome" aria-labelledby="dome-title">
        <div className="dome-console">
          <p className="eyebrow hero-eyebrow">
            <span className="signal-dot" />
            中文互联网文化档案 <span>/ OPEN ARCHIVE</span>
          </p>
          <h1 id="dome-title" className="dome-title">
            记住一个梗。
            <br />
            <span>也记住它的来处。</span>
          </h1>
          <p className="dome-sub">
            从一句话，到一段共同记忆。
            <br />
            收录梗的语境与传播轨迹，让每一个解释都有证据可循。
          </p>
          <form
            className="search-form"
            data-state={state}
            onSubmit={(e) => {
              e.preventDefault();
              void run(platform, 0, true);
            }}
          >
            <Icon name="search" size={21} />
            <input
              aria-label="搜索记忆"
              placeholder="一个梗、一个别名，或一句话…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
            <button type="submit" disabled={loading}>
              {loading && elapsed > 0 ? `检索中… ${elapsed}s` : "搜索记忆"}
            </button>
            <span className="scan-line" aria-hidden="true" />
          </form>
          <div className="filter-bar">
            <div className="tabs" aria-label="平台筛选">
              {[[null, "全部平台"], ...PLATFORMS].map(([id, label]) => (
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
          <div className="hero-paths">
            <a href="#memory-index">
              浏览记忆索引 <span aria-hidden="true">↓</span>
            </a>
            <Link href="/submit">
              留下一份来源 <Icon name="arrow" size={14} />
            </Link>
          </div>
          {(loading || answerLoading) && (
            <p className="retrieval-note console-status" role="status">
              {answerLoading
                ? "检索完成，正在整理证据回答。"
                : "正在检索记忆。"}
              {elapsed > 30 && " 本次处理较慢，你可以取消等待。"}
              <button type="button" className="text-button" onClick={cancel}>
                取消等待
              </button>
            </p>
          )}
        </div>
        <SkyBand universe={universe} />
      </section>

      <div className="archive-intro">
        <span className="eyebrow">A LIVING CULTURAL ARCHIVE</span>
        <p>流行会过去，语境值得留下。</p>
        <span>
          {universe
            ? `${universe.galaxies.length} 条已发布记忆`
            : "可追溯 · 可修订"}
        </span>
      </div>

      {error && (
        <div className="error" role="alert">
          {error}
          <button
            className="text-button"
            disabled={loading || answerLoading || searchRetryRemaining > 0}
            onClick={() => {
              if (lastRequest.current)
                void run(platform, 0, false, lastRequest.current);
            }}
          >
            {searchRetryRemaining > 0
              ? `重试（${searchRetryRemaining}s）`
              : "重试"}
          </button>
        </div>
      )}
      <div className="archive-columns" ref={index} id="memory-index">
        <section className="archive-panel" aria-busy={loading}>
          <div className="panel-heading">
            <h2>
              <span className="eyebrow">01 / INDEX</span>记忆索引
            </h2>
            <span>
              {result?.total ?? "—"} 条{submittedQuery ? "相关" : "已审核"}记录
            </span>
          </div>
          {answerError && (
            <div className="error" role="alert">
              回答暂不可用：{answerError}
              <button
                className="text-button"
                disabled={answerLoading || answerRetryRemaining > 0}
                onClick={() => {
                  if (answerRequest.current)
                    void fetchAnswer(answerRequest.current, ++serial.current);
                }}
              >
                {answerRetryRemaining > 0
                  ? `重试回答（${answerRetryRemaining}s）`
                  : "重试回答"}
              </button>
            </div>
          )}
          {result?.degraded.includes("corpus_changed_during_search") && (
            <div className="notice" role="status">
              检索期间公开档案发生变化，受影响的旧版本候选已排除。
              <button
                className="text-button"
                disabled={loading || answerLoading}
                onClick={() => {
                  const request = lastRequest.current;
                  if (request)
                    void run(request.platform, 0, true, {
                      ...request,
                      offset: 0,
                      reveal: true,
                    });
                }}
              >
                刷新当前检索
              </button>
            </div>
          )}
          {/* An abstention is a result. When `claims` is empty the answer text and
              the uncertainties are still the API's own, so they are rendered in the
              same place and the same style as any other answer - never as an error. */}
          {answer && (
            <section
              className={`answer${answer.claims.length ? "" : " is-abstained"}`}
            >
              <h3>基于证据的回答</h3>
              <p className="answer-text">{answer.answer}</p>
              {answer.claims.length === 0 && (
                <p className="retrieval-note">
                  {answer.abstention_reason
                    ? ABSTENTION_LABELS[answer.abstention_reason]
                    : "本次回答没有可引用的证据断言。"}
                </p>
              )}
              {answer.uncertainties.map((t) => (
                <p className="uncertainty" key={t}>
                  <Icon name="info" size={17} />
                  {t}
                </p>
              ))}
              {answer.claims.length === 0 &&
                !!answer.related_memories?.length && (
                  <div className="answer-candidates">
                    <p className="retrieval-note">
                      候选记忆仅供浏览，不是本次提问的证据回答：
                    </p>
                    <nav
                      className="answer-reference-links"
                      aria-label="仅供浏览的候选记忆"
                    >
                      {answer.related_memories.map((candidate) => (
                        <Link
                          key={candidate.id}
                          href={memoryUrl(
                            candidate.id,
                            candidate.published_revision,
                          )}
                        >
                          浏览{candidate.canonical_name}
                          <Icon name="arrow" size={15} />
                        </Link>
                      ))}
                    </nav>
                  </div>
                )}
              <ol className="citations">
                {answer.citations.map((c, i) => (
                  <li key={c.evidence_id}>
                    <a href={c.url} target="_blank" rel="noreferrer">
                      证据 {i + 1} · {c.evidence_id.slice(0, 8)}{" "}
                      <Icon name="arrow" size={15} />
                    </a>
                    <p>{c.text.slice(0, 200)}</p>
                    <div className="answer-reference-links">
                      {Array.from(
                        new Map(
                          answer.claims
                            .filter((claim) =>
                              claim.evidence_ids.includes(c.evidence_id),
                            )
                            .map((claim) => [claim.meme_id, claim]),
                        ).values(),
                      ).map((claim) => (
                        <Link
                          key={claim.meme_id}
                          href={referenceUrl(
                            claim.meme_id,
                            claim.meme_revision,
                            c.evidence_id,
                          )}
                        >
                          查看{claim.meme_name}的引用
                        </Link>
                      ))}
                    </div>
                  </li>
                ))}
              </ol>
              {/* How the answer was produced is our plumbing, not the reader's
                  question, so it is folded away. The degraded-channel line stays
                  where it always was, below the whole page. */}
              <details className="answer-details">
                <summary>检索细节</summary>
                <p className="retrieval-note">
                  回答模式：{answer.mode}
                  {answer.channels.length > 0 &&
                    ` ｜ 检索通道：${answer.channels.join(" · ")}`}
                </p>
              </details>
            </section>
          )}
          {!loading && !result?.items.length && !error && (
            <div className="empty-state">
              <Icon name="archive" size={86} />
              <h3>
                {result?.degraded.includes("corpus_changed_during_search")
                  ? "公开档案在检索期间发生变化"
                  : submittedQuery
                    ? "这段记忆，还缺少证据"
                    : "第一条记忆，从一个链接开始"}
              </h3>
              <p>
                {result?.degraded.includes("corpus_changed_during_search")
                  ? "刷新后会重新检查当前公开条目，不把版本变化当作证据缺失。"
                  : submittedQuery
                    ? "换一个别名试试，或提交你找到的原始来源。"
                    : "提交 Bilibili 或抖音来源，核对证据后进入公共索引。"}
              </p>
              {!result?.degraded.includes("corpus_changed_during_search") && (
                <Link className="button outline" href="/submit">
                  {submittedQuery ? "补充一份来源" : "提交第一个来源"}{" "}
                  <Icon name="arrow" />
                </Link>
              )}
            </div>
          )}
          {loading && !result && (
            <div className="empty-state muted" role="status">
              正在连接记忆索引…
            </div>
          )}
          <div
            className="meme-rows"
            key={`${submittedQuery}|${submittedPlatform}|${result?.total ?? ""}`}
          >
            {result?.items.map((meme, position) => (
              <article
                className="meme-row"
                key={meme.id}
                style={
                  { "--row": Math.min(position, 8) } as React.CSSProperties
                }
              >
                <span className="row-number" aria-hidden="true">
                  {String(position + 1).padStart(2, "0")}
                </span>
                <div className="row-content">
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
                      {Array.from(
                        new Set(meme.evidence.map((e) => e.source?.platform)),
                      )
                        .map(platformLabel)
                        .join(" / ")}
                      {" · "}
                      {meme.evidence.length} 份证据 · 修订{" "}
                      {meme.published_revision}
                      {" · "}
                      {meme.origin_status === "unknown"
                        ? "起源尚未确认"
                        : meme.origin_status === "disputed"
                          ? "来源存在争议"
                          : "有证据支持的来源主张"}
                      {/* A retrieval score is only a score when the pipeline says its
                        scores are calibrated; otherwise the number would be noise. */}
                      {result.scores_calibrated &&
                      typeof meme.retrieval_score === "number"
                        ? ` · 检索分 ${meme.retrieval_score.toFixed(3)}`
                        : ""}
                    </span>
                    <span className="row-links">
                      <Link href={`/universe?meme=${meme.id}`}>
                        在星图中查看
                      </Link>
                      <Link href={`/memes/${meme.id}`}>查看语境与证据</Link>
                    </span>
                  </div>
                </div>
              </article>
            ))}
          </div>
          {result && result.items.length < result.total && (
            <button
              className="load-more"
              disabled={loading || answerLoading}
              onClick={() => void run(platform, result.items.length)}
            >
              加载更多
            </button>
          )}
        </section>
        <Principles />
      </div>
      {submittedQuery && result && (
        <p className="retrieval-note">
          检索通道：{result.channels.join(" · ")}
          {result.degraded.length > 0 &&
            ` ｜ 未启用或降级：${result.degraded.join("、")}`}
        </p>
      )}
    </main>
  );
}
