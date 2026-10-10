"use client";

import { useRef, useState } from "react";
import {
  api,
  post,
  type ImportPlan,
  type ImportResult,
  type PublicationPackage,
} from "@/lib/api";

const actions = {
  create_draft: "新增待审稿",
  append_draft: "追加用法，保留原文",
  duplicate: "已导入，不重复创建",
  blocked: "需要先处理冲突",
};

export function PublicationImport({
  token,
  onImported,
}: {
  token: string;
  onImported: () => Promise<void>;
}) {
  const [manifest, setManifest] = useState<
    PublicationPackage["manifest"] | null
  >(null);
  const [entries, setEntries] = useState("");
  const [plan, setPlan] = useState<ImportPlan | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const versions = useRef({ manifest: 0, entries: 0 });

  async function readFile(kind: "manifest" | "entries", file?: File) {
    const version = ++versions.current[kind];
    setPlan(null);
    setError("");
    setNotice("");
    if (kind === "manifest") setManifest(null);
    else setEntries("");
    if (!file) return;
    try {
      if (file.size > (kind === "manifest" ? 100_000 : 8_000_000))
        throw new Error("文件过大：清单上限 100 KB，条目上限 8 MB。");
      const text = await file.text();
      if (versions.current[kind] !== version) return;
      if (kind === "manifest") {
        const parsed: unknown = JSON.parse(text);
        if (!parsed || typeof parsed !== "object" || Array.isArray(parsed))
          throw new Error("清单必须是 JSON 对象。");
        setManifest(parsed as PublicationPackage["manifest"]);
      } else setEntries(text);
    } catch (e) {
      if (versions.current[kind] === version) setError((e as Error).message);
    }
  }

  async function preview() {
    if (!manifest || !entries) return;
    setBusy(true);
    setError("");
    setNotice("");
    setPlan(null);
    try {
      const data = await api<ImportPlan>(
        "/v1/reviews/imports/validate",
        post({ manifest, entries_jsonl: entries }),
        token,
      );
      setPlan(data);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function stage() {
    if (!plan?.can_import || !manifest || !entries) return;
    setBusy(true);
    setError("");
    try {
      const result = await api<ImportResult>(
        `/v1/reviews/imports?expected_plan_hash=${encodeURIComponent(plan.plan_hash)}`,
        post({ manifest, entries_jsonl: entries }),
        token,
      );
      const created = result.items.filter((item) => !item.duplicate).length;
      setPlan(null);
      setNotice(
        `${created} 份待审稿已入队，${result.items.length - created} 份已导入记录保持不变。本次未发布任何条目。`,
      );
      await onImported();
    } catch (e) {
      setError((e as Error).message);
      setPlan(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <details className="import-workbench">
      <summary>导入已采集的数据</summary>
      <p className="muted">
        上传同一交付中的两个文件，先查看新增、追加和冲突，再生成待审稿。不会抓取平台、运行模型或自动发布。
      </p>
      <div className="import-files">
        <label className="field">
          <span>交付清单 manifest.json</span>
          <input
            type="file"
            accept=".json,application/json"
            disabled={busy}
            onChange={(e) => void readFile("manifest", e.target.files?.[0])}
          />
        </label>
        <label className="field">
          <span>条目文件 entries.jsonl</span>
          <input
            type="file"
            accept=".jsonl,application/jsonl,text/plain"
            disabled={busy}
            onChange={(e) => void readFile("entries", e.target.files?.[0])}
          />
        </label>
      </div>
      <button
        className="button outline"
        disabled={busy || !manifest || !entries}
        onClick={() => void preview()}
      >
        {busy ? "正在处理…" : "校验并预演"}
      </button>
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
      {plan && (
        <section className="import-preview" aria-label="导入预演结果">
          <h3 className="section-title">预演结果 · 尚未写入</h3>
          <p>
            {plan.groups} 组条目 · {plan.new_groups} 新增 /{" "}
            {plan.existing_groups} 追加 · {plan.unique_sources} 个独立来源 /{" "}
            {plan.meme_source_associations} 个来源关联
          </p>
          <ol className="import-plan">
            {plan.items.map((item) => (
              <li key={item.entry_hash} className="import-plan-row">
                <div>
                  <strong>{item.canonical_name}</strong>
                  {item.message && <p>{item.message}</p>}
                </div>
                <span>{actions[item.action]}</span>
              </li>
            ))}
          </ol>
          <details className="import-limitations">
            <summary>证据与导入边界</summary>
            <ul>
              {plan.warnings.map((warning) => (
                <li key={warning}>{warning}</li>
              ))}
            </ul>
          </details>
          <p className="small-code">SHA-256 · {plan.entries_sha256}</p>
          <button
            className="button primary"
            disabled={busy || !plan.can_import}
            onClick={() => void stage()}
          >
            确认生成待审稿
          </button>
          {!plan.can_import && (
            <p className="muted">存在冲突，整包暂不导入；处理后重新预演。</p>
          )}
        </section>
      )}
    </details>
  );
}
