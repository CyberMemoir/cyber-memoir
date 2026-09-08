"use client";
import { useEffect, useState } from "react";
import {
  api,
  post,
  type Draft,
  type Evidence,
  type Revision,
  type Source,
} from "@/lib/api";

export function ReviewEditor({
  revision,
  token,
  onDone,
}: {
  revision: Revision;
  token: string;
  onDone: () => void;
}) {
  const [name, setName] = useState(revision.payload.canonical_name);
  const [aliases, setAliases] = useState(revision.payload.aliases.join(" / "));
  const [definition, setDefinition] = useState(revision.payload.definition);
  const [context, setContext] = useState(revision.payload.usage_context);
  const [origin, setOrigin] = useState(revision.payload.origin_status);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [selected, setSelected] = useState<string[]>(
    Array.from(new Set(revision.payload.claims.flatMap((c) => c.evidence_ids))),
  );
  const [reason, setReason] = useState("");
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(
    JSON.stringify(
      {
        events: revision.payload.events,
        relations: revision.payload.relations,
        claims: revision.payload.claims.filter(
          (c) => !["definition", "usage_context"].includes(c.key),
        ),
      },
      null,
      2,
    ),
  );
  useEffect(() => {
    let active = true;
    async function load() {
      try {
        if (revision.payload._source_id) {
          const data = await api<{ evidence: Evidence[]; source: Source }>(
            `/v1/reviews/sources/${revision.payload._source_id}`,
            undefined,
            token,
          );
          if (active)
            setEvidence(
              data.evidence.map((item) => ({ ...item, source: data.source })),
            );
        } else {
          const ids = Array.from(
            new Set(revision.payload.claims.flatMap((c) => c.evidence_ids)),
          );
          const data = await Promise.all(
            ids.map((id) =>
              api<Evidence>(`/v1/reviews/evidence/${id}`, undefined, token),
            ),
          );
          if (active) setEvidence(data);
        }
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    }
    void load();
    return () => {
      active = false;
    };
  }, [revision.id, token]);
  function payload(): Draft {
    const extra = JSON.parse(advanced);
    return {
      canonical_name: name,
      aliases: aliases
        .split("/")
        .map((s) => s.trim())
        .filter(Boolean),
      definition,
      usage_context: context,
      origin_status: origin,
      claims: [
        ...(extra.claims || []),
        ...(definition
          ? [
              {
                key: "definition",
                statement: definition,
                evidence_ids: selected,
                stance: "supports",
              },
            ]
          : []),
        ...(context
          ? [
              {
                key: "usage_context",
                statement: context,
                evidence_ids: selected,
                stance: "supports",
              },
            ]
          : []),
      ],
      events: extra.events || [],
      relations: extra.relations || [],
    };
  }
  async function save() {
    const body = payload();
    await api(
      `/v1/reviews/${revision.id}`,
      { method: "PUT", body: JSON.stringify(body) },
      token,
    );
    return body;
  }
  async function act(decision?: "approve" | "reject") {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (decision && reason.trim().length < 3)
        throw new Error("请填写至少 3 字的审核理由。");
      if (decision === "approve" && !verified)
        throw new Error("发布前请确认已核对证据及定位。");
      const body = decision === "reject" ? revision.payload : await save();
      if (decision) {
        const ids = Array.from(
          new Set([
            ...body.claims.flatMap((c) => c.evidence_ids),
            ...body.events.flatMap(
              (e) => (e as { evidence_ids?: string[] }).evidence_ids || [],
            ),
            ...body.relations.flatMap(
              (r) => (r as { evidence_ids?: string[] }).evidence_ids || [],
            ),
          ]),
        );
        await api(
          `/v1/reviews/${revision.id}/decision`,
          post({
            decision,
            reason,
            verified_evidence_ids: verified ? ids : [],
          }),
          token,
        );
        onDone();
      } else setNotice("草稿已保存，尚未发布。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function addEvidence() {
    const id = window.prompt("输入另一份证据的 ID");
    if (!id) return;
    try {
      const item = await api<Evidence>(
        `/v1/reviews/evidence/${id}`,
        undefined,
        token,
      );
      setEvidence((old) =>
        old.some((e) => e.id === id) ? old : [...old, item],
      );
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <section>
      <h2 className="section-title" style={{ marginTop: 0 }}>
        核对语境，再发布结论。
      </h2>
      <p className="small-code">
        Meme: {revision.meme_id} · 基于修订 {revision.based_on_revision}
      </p>
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
      <div className="form-stack">
        <label className="field">
          <span>梗名称</span>
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={200}
          />
        </label>
        <label className="field">
          <span>别名（用 / 分隔）</span>
          <input value={aliases} onChange={(e) => setAliases(e.target.value)} />
        </label>
        <label className="field">
          <span>定义 · 必须由下方选中的证据完整支持</span>
          <textarea
            value={definition}
            onChange={(e) => setDefinition(e.target.value)}
          />
        </label>
        <label className="field">
          <span>使用语境</span>
          <textarea
            value={context}
            onChange={(e) => setContext(e.target.value)}
          />
        </label>
        <label className="field">
          <span>起源状态</span>
          <select value={origin} onChange={(e) => setOrigin(e.target.value)}>
            <option value="unknown">未知：不作起源判断</option>
            <option value="disputed">有争议：需要 origin 引用</option>
            <option value="supported">
              有证据支持：需要 origin 引用及 Source 关系
            </option>
          </select>
        </label>
      </div>
      <h3 className="section-title">逐条核对证据</h3>
      <p className="muted">
        选中支持定义与使用语境的材料。仅有一个链接不足以支持事实断言。
      </p>
      {evidence.map((item) => (
        <article key={item.id} className="evidence-box">
          <label className="check-label">
            <input
              type="checkbox"
              disabled={item.retracted}
              checked={selected.includes(item.id)}
              onChange={(e) => {
                setVerified(false);
                setSelected((old) =>
                  e.target.checked
                    ? [...old, item.id]
                    : old.filter((x) => x !== item.id),
                );
              }}
            />
            <span>
              {item.kind} · {item.id.slice(0, 8)}
              {item.retracted ? " · 已撤回" : ""}
            </span>
          </label>
          <blockquote>{item.text}</blockquote>
          <div className="small-code">定位：{JSON.stringify(item.locator)}</div>
          {item.source && (
            <p>
              <a
                href={item.source.canonical_url}
                target="_blank"
                rel="noreferrer"
              >
                核对平台原始来源：{item.source.title || item.source.platform}
              </a>
            </p>
          )}
        </article>
      ))}
      <button
        className="text-button"
        style={{ marginLeft: 0 }}
        onClick={() => void addEvidence()}
      >
        补充其他证据 ID
      </button>
      <details>
        <summary>传播事件、衍生关系与来源主张（结构化编辑）</summary>
        <p className="muted">
          事件与关系都必须有 evidence_ids。起源不能由最早收录时间推断。
        </p>
        <label className="field">
          <span>events / relations / claims</span>
          <textarea
            aria-label="高级结构化编辑"
            value={advanced}
            onChange={(e) => setAdvanced(e.target.value)}
          />
        </label>
      </details>
      <hr className="divider" />
      <label className="field">
        <span>审核理由</span>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="说明证据怎样支持这些断言，哪些内容仍不确定。"
        />
      </label>
      <label className="check-label" style={{ margin: "20px 0" }}>
        <input
          type="checkbox"
          checked={verified}
          onChange={(e) => setVerified(e.target.checked)}
        />
        我已人工核对所有引用材料、时间定位及其对断言的支持关系
      </label>
      <div className="action-row">
        <button
          className="button primary"
          disabled={busy}
          onClick={() => void act("approve")}
        >
          审核通过并发布
        </button>
        <button
          className="button outline"
          disabled={busy}
          onClick={() => void act()}
        >
          保存草稿
        </button>
        <button
          className="button danger"
          disabled={busy}
          onClick={() => void act("reject")}
        >
          拒绝此修订
        </button>
      </div>
    </section>
  );
}
