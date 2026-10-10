"use client";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import {
  ASSESSMENTS,
  decode,
  fileBytes,
  importReviews,
  loadQueue,
  pending,
  quoteFromSelection,
  reviewFile,
  sourceUrl,
  validateReview,
  type Assessment,
  type LoadedQueue,
  type Quote,
  type Review,
} from "@/lib/semantic-review";

const LABELS: Record<Assessment, string> = {
  supported: "支持",
  partial: "部分支持",
  unsupported: "未找到支持",
  contradicted: "存在相反表述",
  unverifiable: "当前材料无法核验",
};
const FIELDS: Record<string, string> = {
  definition: "定义",
  usage_context: "语境",
  origin: "起源",
};
function clone(row: Review): Review {
  return { ...row, quotes: row.quotes.map((quote) => ({ ...quote })) };
}

export default function SemanticReviewPage() {
  const [queue, setQueue] = useState<LoadedQueue | null>(null);
  const [saved, setSaved] = useState<Review[]>([]);
  const [selected, setSelected] = useState(0);
  const [draft, setDraft] = useState<Review | null>(null);
  const [dirty, setDirty] = useState(false);
  const [unexported, setUnexported] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [selection, setSelection] = useState<Quote | null>(null);
  const generation = useRef(0);
  const row = queue?.rows[selected];
  const reviewed = saved.filter((value) => value.assessment !== null).length;
  useEffect(() => {
    function leave(event: BeforeUnloadEvent) {
      if (dirty || unexported) {
        event.preventDefault();
        event.returnValue = "";
      }
    }
    function links(event: MouseEvent) {
      const anchor = (event.target as Element).closest?.("a");
      if (
        !anchor ||
        anchor.target === "_blank" ||
        anchor.hasAttribute("download") ||
        (!dirty && !unexported)
      )
        return;
      const url = new URL(anchor.href, location.href);
      if (url.pathname === location.pathname && url.search === location.search)
        return;
      if (
        !window.confirm("本地编辑尚未导出。确认离开并放弃本页未导出的记录？")
      ) {
        event.preventDefault();
        event.stopPropagation();
      }
    }
    window.addEventListener("beforeunload", leave);
    document.addEventListener("click", links, true);
    return () => {
      window.removeEventListener("beforeunload", leave);
      document.removeEventListener("click", links, true);
    };
  }, [dirty, unexported]);
  useEffect(
    () => () => {
      generation.current++;
    },
    [],
  );
  function replaceAllowed() {
    return (
      (!dirty && !unexported) ||
      window.confirm("导入新文件将替换本页记录。确认放弃未导出的编辑？")
    );
  }
  async function importFile(file: File | undefined, kind: "queue" | "reviews") {
    if (!file || !replaceAllowed()) return;
    const id = ++generation.current;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const bytes = await fileBytes(file);
      if (id !== generation.current) return;
      if (kind === "queue") {
        const next = await loadQueue(bytes);
        if (id !== generation.current) return;
        const reviews = next.rows.map((value) => pending(value.audit_id));
        setQueue(next);
        setSaved(reviews);
        setSelected(0);
        setDraft(clone(reviews[0]));
      } else {
        if (!queue) throw new Error("请先导入对应的审计队列");
        const next = importReviews(bytes, queue);
        setSaved(next.reviews);
        setDraft(clone(next.reviews[selected]));
      }
      setDirty(false);
      setUnexported(false);
      setSelection(null);
      setNotice("");
    } catch (e) {
      if (id === generation.current) setError((e as Error).message);
    } finally {
      if (id === generation.current) setBusy(false);
    }
  }
  function select(index: number) {
    if (dirty && !window.confirm("当前断言尚未保存。确认放弃当前编辑？"))
      return;
    setSelected(index);
    setDraft(clone(saved[index]));
    setDirty(false);
    setSelection(null);
    setError("");
    setNotice("");
  }
  function update(values: Partial<Review>) {
    if (draft) {
      setDraft({ ...draft, ...values });
      setDirty(true);
      setError("");
      setNotice("");
    }
  }
  function save() {
    if (!row || !draft) return;
    setError("");
    try {
      if (!draft.assessment)
        throw new Error("请选择结论；撤回评级请使用独立按钮");
      const next = validateReview(
        { ...draft, reviewed_at: new Date().toISOString() },
        row,
      );
      setSaved(
        saved.map((value) => (value.audit_id === next.audit_id ? next : value)),
      );
      setDraft(clone(next));
      setDirty(false);
      setUnexported(true);
      setNotice(
        "已保存到本页内存；请导出 JSON 以保留记录。保存时间来自本机时钟，不是身份或发布审批证明。",
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function withdraw() {
    if (!row || !window.confirm("仅撤回这一条本地评级，不影响文化记录。确认？"))
      return;
    const next = pending(row.audit_id);
    setSaved(
      saved.map((value) => (value.audit_id === row.audit_id ? next : value)),
    );
    setDraft(next);
    setDirty(false);
    setUnexported(true);
    setSelection(null);
    setError("");
    setNotice("本地评级已撤回；原审计队列和文化发布状态未改。");
  }
  function capture(element: HTMLPreElement, evidenceIndex: number) {
    try {
      const current = window.getSelection();
      if (!row || !current || current.rangeCount !== 1 || current.isCollapsed)
        return;
      const range = current.getRangeAt(0);
      const node = element.firstChild;
      if (
        !node ||
        node.nodeType !== Node.TEXT_NODE ||
        range.startContainer !== node ||
        range.endContainer !== node
      )
        throw new Error("请选择一份保存原文中的连续文字");
      setSelection(
        quoteFromSelection(
          row.evidence[evidenceIndex],
          range.startOffset,
          range.endOffset,
        ),
      );
      setError("");
    } catch (e) {
      setSelection(null);
      setError((e as Error).message);
    }
  }
  function addQuote() {
    if (!draft || !selection || !row) return;
    if (
      draft.quotes.some(
        (q) =>
          q.evidence_id === selection.evidence_id &&
          q.start === selection.start &&
          q.end === selection.end,
      )
    ) {
      setError("这段摘录已添加");
      return;
    }
    update({ quotes: [...draft.quotes, selection] });
    setSelection(null);
    window.getSelection()?.removeAllRanges();
  }
  function download() {
    if (!queue) return;
    setError("");
    if (dirty) {
      setError("请先保存当前复核或明确放弃编辑，再导出已保存记录");
      return;
    }
    try {
      const file = reviewFile(queue, saved);
      const blob = new Blob([JSON.stringify(file, null, 2) + "\n"], {
        type: "application/json;charset=utf-8",
      });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = `semantic-review-${queue.sha.slice(0, 8)}.json`;
      anchor.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      setUnexported(false);
      setNotice(
        "已发起本地下载；请确认浏览器已保存文件。仅结构化复核记录，不等于语义真值或发布审批。",
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <main id="main" className="semantic-workspace">
      <div className="semantic-breadcrumb">
        <Link href="/review">审核工作台</Link>
        <span>/</span>
        <span>本地语义复核</span>
      </div>
      <h1>本地语义复核</h1>
      <p className="semantic-intro">
        文件仅在本机浏览器处理，不自动上传或发布。
      </p>
      <div className="semantic-toolbar">
        <label className="button semantic-file">
          导入审计队列
          <input
            aria-label="导入审计队列"
            type="file"
            accept=".jsonl,.json"
            disabled={busy}
            onChange={(event) => {
              void importFile(event.target.files?.[0], "queue");
              event.target.value = "";
            }}
          />
        </label>
        <label className="button semantic-file">
          加载复核文件
          <input
            aria-label="加载复核文件"
            type="file"
            accept=".json"
            disabled={busy || !queue}
            onChange={(event) => {
              void importFile(event.target.files?.[0], "reviews");
              event.target.value = "";
            }}
          />
        </label>
        <span className="semantic-count" aria-live="polite">
          已复核 {reviewed} / 待复核 {(queue?.rows.length ?? 0) - reviewed}
        </span>
        <button
          className="button semantic-export"
          onClick={download}
          disabled={!queue || busy}
        >
          导出复核 JSON
        </button>
      </div>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <p className="semantic-notice" role="status">
          {notice}
        </p>
      )}
      {!queue ? (
        <div className="semantic-empty">
          <h2>导入固定队列开始复核</h2>
          <p>
            接受 citation_audit.py 的未评级
            JSONL。复核文件与整份队列摘要绑定；本页不连接业务数据库，不认证复核者或判断实际真值。
          </p>
          <p>文件仅在本页内存。请及时导出，刷新可能丢失未导出的工作。</p>
        </div>
      ) : (
        <div className="semantic-grid">
          <aside className="semantic-rail">
            <div className="semantic-rail-title">
              <h2>断言队列</h2>
              <span>{queue.rows.length} 条</span>
            </div>
            {queue.rows.map((value, index) => (
              <button
                className={`semantic-item ${selected === index ? "active" : ""}`}
                key={value.audit_id}
                onClick={() => select(index)}
                aria-pressed={selected === index}
              >
                <strong>{value.claim.meme_name || value.claim.key}</strong>
                <small>
                  {FIELDS[value.claim.key] || value.claim.key} · 修订{" "}
                  {value.claim.meme_revision} ·{" "}
                  {saved[index].assessment
                    ? LABELS[saved[index].assessment!]
                    : "待复核"}
                </small>
              </button>
            ))}
          </aside>
          {row && draft && (
            <>
              <section className="semantic-editor" aria-label="断言复核编辑">
                <h2>{row.claim.meme_name || row.claim.key}</h2>
                <label>
                  断言内容（只读）
                  <div className="semantic-statement">
                    {row.claim.statement}
                  </div>
                </label>
                <p className="semantic-stance">
                  主张类型
                  <br />
                  <span>
                    {row.claim.stance === "supports"
                      ? "支持性主张"
                      : row.claim.stance === "contradicts"
                        ? "反对性主张"
                        : row.claim.stance}
                  </span>
                </p>
                <label>
                  复核结论
                  <select
                    value={draft.assessment ?? ""}
                    onChange={(event) =>
                      update({
                        assessment: event.target.value
                          ? (event.target.value as Assessment)
                          : null,
                      })
                    }
                  >
                    <option value="">待复核</option>
                    {ASSESSMENTS.map((value) => (
                      <option key={value} value={value}>
                        {LABELS[value]}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  复核者
                  <input
                    value={draft.reviewer ?? ""}
                    onChange={(event) =>
                      update({ reviewer: event.target.value })
                    }
                    placeholder="请输入复核者姓名或代号"
                  />
                </label>
                <label>
                  复核理由
                  <textarea
                    value={draft.reason ?? ""}
                    onChange={(event) => update({ reason: event.target.value })}
                    placeholder="请填写复核理由（必填）"
                    rows={3}
                  />
                </label>
                <div className="semantic-quotes">
                  <h3>选中摘录</h3>
                  {!draft.quotes.length ? (
                    <p>尚未添加摘录</p>
                  ) : (
                    <ol>
                      {draft.quotes.map((quote, index) => (
                        <li
                          key={`${quote.evidence_id}:${quote.start}:${quote.end}`}
                        >
                          <blockquote>{quote.exact}</blockquote>
                          <small>
                            码点 {quote.start}–{quote.end} ·{" "}
                            {quote.evidence_id.slice(0, 8)}
                          </small>
                          <button
                            className="text-button"
                            onClick={() =>
                              update({
                                quotes: draft.quotes.filter(
                                  (_, i) => i !== index,
                                ),
                              })
                            }
                          >
                            移除摘录 {index + 1}
                          </button>
                        </li>
                      ))}
                    </ol>
                  )}
                </div>
                <div className="semantic-actions">
                  <button className="button primary" onClick={save}>
                    保存这条复核
                  </button>
                  <button className="button" onClick={withdraw}>
                    撤回本地评级
                  </button>
                </div>
              </section>
              <section className="semantic-evidence" aria-label="保存的证据">
                <h2>保存的证据</h2>
                {row.evidence.map((evidence, index) => {
                  const url = sourceUrl(evidence.source.canonical_url);
                  return (
                    <div className="semantic-source" key={evidence.id}>
                      {url ? (
                        <a href={url} target="_blank" rel="noreferrer">
                          {evidence.source.title || "来源链接"}
                        </a>
                      ) : (
                        <span>{evidence.source.title || "保存的来源"}</span>
                      )}
                      <p className="semantic-locator">
                        {String(evidence.locator?.note || evidence.id)} ·
                        文本哈希已绑定
                      </p>
                      <pre
                        tabIndex={0}
                        className="semantic-evidence-text"
                        onMouseUp={(event) =>
                          capture(event.currentTarget, index)
                        }
                        onKeyUp={(event) => capture(event.currentTarget, index)}
                      >
                        {evidence.text}
                      </pre>
                    </div>
                  );
                })}
                <p className="semantic-selection-help">选择原文后添加摘录</p>
                <button
                  className="button"
                  onClick={addQuote}
                  disabled={!selection}
                >
                  添加选中摘录
                </button>
              </section>
            </>
          )}
        </div>
      )}
    </main>
  );
}
