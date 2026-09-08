"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { api, post, type Job, type Source } from "@/lib/api";
import { Principles } from "@/components/shell";
import { Icon } from "@/components/icons";

const statusNames: Record<string, string> = {
  pending: "排队中",
  running: "处理中",
  succeeded: "处理任务结束",
  failed: "任务失败",
  needs_material: "需要人工补充材料",
  material_available: "已有可核查材料",
};
export default function SubmitPage() {
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [token, setToken] = useState("");
  const [source, setSource] = useState<Source | null>(null);
  const [jobId, setJobId] = useState("");
  const [job, setJob] = useState<Job | null>(null);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [kind, setKind] = useState("manual");
  const [startMs, setStartMs] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  useEffect(() => {
    if (!jobId) return;
    let active = true;
    const poll = async () => {
      try {
        const data = await api<Job>(`/v1/jobs/${jobId}`);
        if (!active) return;
        setJob(data);
        if (source && ["succeeded", "failed"].includes(data.status)) {
          const next = await api<Source>(`/v1/sources/${source.id}`);
          if (active) setSource(next);
          clearInterval(timer);
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    };
    const timer = setInterval(() => void poll(), 2500);
    void poll();
    return () => {
      active = false;
      clearInterval(timer);
    };
  }, [jobId, source?.id]);
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const data = await api<{
        source: Source;
        job_id: string;
        duplicate: boolean;
      }>("/v1/submissions", post({ url, title }), token);
      setSource(data.source);
      setJobId(data.job_id);
      setNotice(
        data.duplicate
          ? "这个来源已存在，已关联到原有记录。"
          : "链接已登记。你也可以直接补充有定位信息的文字材料。",
      );
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function material(e: React.FormEvent) {
    e.preventDefault();
    if (!source) return;
    setBusy(true);
    setError("");
    try {
      const locator = {
        ...(startMs ? { start_ms: Number(startMs) } : {}),
        note,
      };
      await api(
        `/v1/sources/${source.id}/materials`,
        post({ text, kind, locator }),
        token,
      );
      setText("");
      setNotice("材料已保存，正在准备待审候选。未经审核不会出现在公共索引。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function upload(file: File | undefined) {
    if (!file || !source) return;
    setBusy(true);
    setError("");
    try {
      const form = new FormData();
      form.append("file", file);
      const data = await api<{ job_id: string }>(
        `/v1/sources/${source.id}/media`,
        { method: "POST", body: form },
        token,
      );
      setJobId(data.job_id);
      setNotice("识别任务已排队。音视频只作临时处理，不进入视频托管库。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="page-main" id="main">
      <h1 className="page-title">
        <span style={{ whiteSpace: "nowrap" }}>让一段记忆，</span>
        <span style={{ whiteSpace: "nowrap" }}>有据可查。</span>
      </h1>
      <p className="page-subtitle">
        从一条原始平台链接开始。保存语境与证据，不搬运视频。
      </p>
      <div className="form-columns">
        <section>
          {error && (
            <div role="alert" className="error">
              {error}
            </div>
          )}
          {notice && (
            <div role="status" className="notice">
              {notice}
            </div>
          )}
          <form className="form-stack" onSubmit={submit}>
            <label className="field">
              <span>
                <span className="step-label">01</span>Bilibili / 抖音视频链接
              </span>
              <input
                type="url"
                required
                placeholder="https://www.bilibili.com/video/…"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
              />
              <small>支持具体视频与平台短链接；不支持用户主页。</small>
            </label>
            <label className="field">
              <span>来源标题（可选）</span>
              <input
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                maxLength={500}
              />
            </label>
            <details>
              <summary>提交者令牌（部署要求时填写）</summary>
              <label className="field">
                <span>访问令牌</span>
                <input
                  type="password"
                  autoComplete="off"
                  value={token}
                  onChange={(e) => setToken(e.target.value)}
                />
              </label>
            </details>
            <button className="button primary" disabled={busy}>
              {busy ? "处理中…" : "登记原始来源"}
              <Icon name="arrow" />
            </button>
          </form>
          {source && (
            <>
              <h2 className="section-title">
                <span className="step-label">02</span>补充可核查材料
              </h2>
              <div className="task-state">
                <strong>
                  {statusNames[source.availability] ||
                    statusNames[job?.status || ""] ||
                    "来源已登记"}
                </strong>
                <p>{source.title || source.canonical_url}</p>
                <p>
                  任务：{job ? statusNames[job.status] : "正在获取进度…"}
                  {job?.error && ` · ${job.error}`}
                </p>
                <p className="small-code">Source ID: {source.id}</p>
              </div>
              <form className="form-stack" onSubmit={material}>
                <label className="field">
                  <span>材料类型</span>
                  <select
                    value={kind}
                    onChange={(e) => setKind(e.target.value)}
                  >
                    <option value="manual">人工摘录</option>
                    <option value="subtitle">字幕</option>
                    <option value="asr">转写文本</option>
                    <option value="ocr">画面文字</option>
                  </select>
                </label>
                <label className="field">
                  <span>原文摘录</span>
                  <textarea
                    value={text}
                    onChange={(e) => setText(e.target.value)}
                    required
                    placeholder="保留原文，不把个人解释当成原始材料。"
                  />
                </label>
                <label className="field">
                  <span>定位与核查说明</span>
                  <input
                    value={note}
                    onChange={(e) => setNote(e.target.value)}
                    required
                    placeholder="例如：视频 00:12–00:18，画面中央字幕"
                  />
                </label>
                <label className="field">
                  <span>起始时间（毫秒，可选）</span>
                  <input
                    type="number"
                    min={0}
                    value={startMs}
                    onChange={(e) => setStartMs(e.target.value)}
                  />
                </label>
                <button className="button primary" disabled={busy}>
                  保存证据材料
                  <Icon name="arrow" />
                </button>
              </form>
              <h2 className="section-title">图片 / 音视频识别</h2>
              <p className="muted">
                单文件上限 16 MiB。需要服务端安装 OCR / ASR
                模型；无法识别时可改用人工摘录。
              </p>
              <label className="field">
                <span>上传材料</span>
                <input
                  type="file"
                  disabled={busy}
                  accept="image/png,image/jpeg,image/webp,audio/mpeg,audio/wav,audio/mp4,video/mp4"
                  onChange={(e) => {
                    void upload(e.target.files?.[0]);
                    e.target.value = "";
                  }}
                />
              </label>
              <p style={{ marginTop: 24 }}>
                <Link href="/review" className="back-link">
                  前往审核工作台 <Icon name="arrow" size={16} />
                </Link>
              </p>
            </>
          )}
        </section>
        <Principles />
      </div>
    </main>
  );
}
