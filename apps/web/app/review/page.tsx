"use client";
import { useState } from "react";
import { api, post, date, type Revision, type Draft } from "@/lib/api";
import { ReviewEditor } from "@/components/review-editor";

export default function ReviewPage() {
  const [token, setToken] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [items, setItems] = useState<Revision[]>([]);
  const [selected, setSelected] = useState<Revision | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [memeId, setMemeId] = useState("");
  const [target, setTarget] = useState("");
  const [reason, setReason] = useState("");
  const [history, setHistory] = useState<
    (Revision & { review_reason?: string })[]
  >([]);
  async function load() {
    setBusy(true);
    setError("");
    try {
      const data = await api<Revision[]>("/v1/reviews", undefined, token);
      setAuthorized(true);
      setItems(data);
      setSelected(data[0] || null);
    } catch (e) {
      setError((e as Error).message);
      setAuthorized(false);
    } finally {
      setBusy(false);
    }
  }
  async function manage(action: string) {
    setError("");
    setNotice("");
    setBusy(true);
    try {
      if (action === "history") {
        setHistory(
          await api(`/v1/reviews/memes/${memeId}/history`, undefined, token),
        );
      } else if (action === "reindex") {
        const data = await api<{ queued: number }>(
          "/v1/reviews/reindex",
          post({}),
          token,
        );
        setNotice(`已排队 ${data.queued} 个索引重建任务。`);
      } else {
        if (
          !window.confirm(
            action === "merge"
              ? "确认合并？原条目的事实不会自动迁移。"
              : "确认撤回？条目将立即退出公共检索。",
          )
        )
          return;
        await api(
          `/v1/reviews/memes/${memeId}/${action}`,
          post({ reason, target_id: target }),
          token,
        );
        setNotice(
          action === "merge" ? "条目已合并。" : "条目已撤回，索引清理已排队。",
        );
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revise(payload: Draft) {
    setBusy(true);
    setError("");
    try {
      await api(
        `/v1/reviews/drafts?meme_id=${encodeURIComponent(memeId)}`,
        post(payload),
        token,
      );
      await load();
      setNotice("已创建新修订，旧公开版本保持不变。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main id="main" className="page-main">
      <h1 className="page-title">审核工作台</h1>
      <p className="page-subtitle">
        机器提出候选，人核查证据。审核通过，才成为公共记忆。
      </p>
      <form
        className="inline-form"
        onSubmit={(e) => {
          e.preventDefault();
          void load();
        }}
      >
        <label className="field">
          <span>审核者令牌</span>
          <input
            type="password"
            autoComplete="off"
            value={token}
            onChange={(e) => {
              setToken(e.target.value);
              setAuthorized(false);
            }}
            placeholder="由部署管理员提供，仅保存在本页内存"
            required
          />
        </label>
        <button className="button primary" disabled={busy}>
          连接工作台
        </button>
      </form>
      {error && (
        <div className="error" role="alert">
          {error}
        </div>
      )}
      {notice && (
        <div className="notice" role="status">
          {notice}
        </div>
      )}
      {authorized && (
        <>
          <div className="review-columns">
            <aside className="review-list">
              <h2 style={{ fontSize: 18, fontWeight: 500 }}>
                待审修订 · {items.length}
              </h2>
              <button
                className="text-button"
                style={{ margin: "0 0 15px" }}
                onClick={() => void load()}
              >
                刷新队列
              </button>
              {items.map((item) => (
                <button
                  className={`review-item ${selected?.id === item.id ? "active" : ""}`}
                  key={item.id}
                  onClick={() => setSelected(item)}
                >
                  <strong>{item.payload.canonical_name}</strong>
                  <small>{date(item.created_at)} · 待审核</small>
                </button>
              ))}
            </aside>
            {selected ? (
              <ReviewEditor
                key={selected.id}
                revision={selected}
                token={token}
                onDone={() => {
                  setNotice("审核决定已保存。索引异步更新，公开状态即时生效。");
                  void load();
                }}
              />
            ) : (
              <div className="empty-state">
                <h3>所有待审记忆，已处理完毕。</h3>
                <p>提交来源并补充材料后，新的候选会出现在这里。</p>
              </div>
            )}
          </div>
          <section className="management">
            <h2 className="section-title">版本与索引管理</h2>
            <div className="form-stack">
              <label className="field">
                <span>Meme ID</span>
                <input
                  value={memeId}
                  onChange={(e) => setMemeId(e.target.value)}
                />
              </label>
              <label className="field">
                <span>操作理由（撤回 / 合并必填）</span>
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                />
              </label>
              <label className="field">
                <span>合并目标 Meme ID（仅合并时填写）</span>
                <input
                  value={target}
                  onChange={(e) => setTarget(e.target.value)}
                />
              </label>
              <div className="action-row">
                <button
                  className="button outline"
                  disabled={busy || !memeId}
                  onClick={() => void manage("history")}
                >
                  查看历史修订
                </button>
                <button
                  className="button danger"
                  disabled={busy || !memeId || reason.length < 3}
                  onClick={() => void manage("retract")}
                >
                  撤回条目
                </button>
                <button
                  className="button outline"
                  disabled={busy || !memeId || !target || reason.length < 3}
                  onClick={() => void manage("merge")}
                >
                  合并到目标
                </button>
                <button
                  className="button outline"
                  disabled={busy}
                  onClick={() => void manage("reindex")}
                >
                  重建搜索索引
                </button>
              </div>
            </div>
            {history.map((item) => (
              <article className="evidence-box" key={item.id}>
                <div className="row-meta">
                  <span>
                    {date(item.created_at)} · {item.status}
                  </span>
                  <span>基于版本 {item.based_on_revision}</span>
                </div>
                <p>{item.review_reason}</p>
                {item.payload.canonical_name && (
                  <button
                    className="text-button"
                    onClick={() => void revise(item.payload)}
                  >
                    基于此内容创建新修订
                  </button>
                )}
              </article>
            ))}
          </section>
        </>
      )}
    </main>
  );
}
