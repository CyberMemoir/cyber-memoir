"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { api, post, date, type Revision, type ReviewQueue } from "@/lib/api";
import { ReviewEditor } from "@/components/review-editor";
import { PublicationImport } from "@/components/publication-import";
import { RevisionHistory } from "@/components/revision-history";
import Link from "next/link";

export default function ReviewPage() {
  const [token, setToken] = useState("");
  const [authorized, setAuthorized] = useState(false);
  const [queue, setQueue] = useState<ReviewQueue | null>(null);
  const latestQueue = useRef<ReviewQueue | null>(null);
  const [queueError, setQueueError] = useState("");
  const queueRequest = useRef<{
    controller: AbortController;
    background: boolean;
  } | null>(null);
  const queueSequence = useRef(0);
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
  const load = useCallback(
    async (manual = true) => {
      const sequence = ++queueSequence.current;
      queueRequest.current?.controller.abort();
      const controller = new AbortController();
      queueRequest.current = { controller, background: !manual };
      if (manual) {
        setBusy(true);
        setQueueError("");
      }
      try {
        const data = await api<ReviewQueue>(
          "/v1/reviews/queue",
          { signal: controller.signal },
          token,
        );
        if (sequence !== queueSequence.current || controller.signal.aborted)
          return;
        setAuthorized(true);
        setQueueError("");
        setQueue(data);
        latestQueue.current = data;
        setItems(data.items);
        // A peer may process this draft while the local editor is dirty. Keep
        // its local working copy until the user resolves it or our own action succeeds.
        setSelected((old) => old || data.items[0] || null);
        return data;
      } catch (e) {
        if (controller.signal.aborted || sequence !== queueSequence.current)
          return;
        const message = (e as Error).message;
        setQueueError(message);
        if (manual || message.includes("需要审核者令牌")) {
          setAuthorized(false);
          setItems([]);
          setSelected(null);
        }
      } finally {
        if (queueRequest.current?.controller === controller)
          queueRequest.current = null;
        if (manual) setBusy(false);
      }
    },
    [token],
  );
  useEffect(() => {
    if (!authorized) return;
    let active = true;
    let timeout: ReturnType<typeof setTimeout>;
    const interval = (data: ReviewQueue | null | undefined) =>
      data && data.pending_jobs + data.running_jobs > 0 ? 2000 : 15000;
    async function poll() {
      // Never abort a manually requested refresh or overlap two queue reads.
      if (queueRequest.current) {
        timeout = setTimeout(poll, 2000);
        return;
      }
      const data = await load(false);
      if (active) timeout = setTimeout(poll, interval(data));
    }
    timeout = setTimeout(poll, interval(latestQueue.current));
    return () => {
      active = false;
      clearTimeout(timeout);
      if (queueRequest.current?.background)
        queueRequest.current.controller.abort();
    };
    // Queue changes do not restart an in-flight polling cycle or overwrite edits.
  }, [authorized, load]);
  useEffect(
    () => () => {
      ++queueSequence.current;
      queueRequest.current?.controller.abort();
    },
    [],
  );
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
  async function revise(item: Revision) {
    setBusy(true);
    setError("");
    try {
      await api(
        `/v1/reviews/drafts?meme_id=${encodeURIComponent(item.meme_id)}`,
        post(item.payload),
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
      <p className="eyebrow">EVIDENCE BEFORE PUBLICATION / 核查与修订</p>
      <h1 className="page-title">审核工作台</h1>
      <p className="page-subtitle">
        机器提出候选，人核查证据。审核通过，才成为公共记忆。
      </p>
      <p className="retrieval-note">
        <Link href="/review/semantic">打开本地语义复核</Link> ·
        使用固定文件，不连接发布审批。
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
              ++queueSequence.current;
              queueRequest.current?.controller.abort();
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
      {queueError && (
        <div className="error" role="alert">
          队列更新失败：{queueError}
        </div>
      )}
      {notice && (
        <div className="notice" role="status">
          {notice}
        </div>
      )}
      {authorized && (
        <>
          <PublicationImport
            token={token}
            onImported={async () => {
              await load();
            }}
          />
          {queue && queue.pending_jobs + queue.running_jobs > 0 && (
            <p className="retrieval-note queue-processing" aria-live="polite">
              材料任务：{queue.pending_jobs} 个待处理，{queue.running_jobs}{" "}
              个执行中。待审队列将自动更新，不会重置正在编辑的草稿。
            </p>
          )}
          {!!queue?.failed_jobs && (
            <p className="retrieval-note">
              有 {queue.failed_jobs}{" "}
              条材料任务失败记录，可核对提交状态与运行日志；这不等于当前公开证据失效。
            </p>
          )}
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
                remoteEtag={items.find((item) => item.id === selected.id)?.etag}
                onDone={() => {
                  setNotice("审核决定已保存。索引异步更新，公开状态即时生效。");
                  setSelected(null);
                  void load();
                }}
              />
            ) : (
              <div className="empty-state">
                <h3>
                  {queue && queue.pending_jobs + queue.running_jobs > 0
                    ? "材料任务尚未结束"
                    : "队列暂时没有待审修订。"}
                </h3>
                <p>
                  目前暂无待审修订。新候选生成后会自动出现在这里；也可以刷新队列。
                </p>
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
            <RevisionHistory
              items={history}
              onRevise={(item) => void revise(item)}
            />
          </section>
        </>
      )}
    </main>
  );
}
