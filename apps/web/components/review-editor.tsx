"use client";
import { useEffect, useRef, useState } from "react";
import {
  api,
  ApiError,
  post,
  type Draft,
  type Evidence,
  type Revision,
  type ReviewComparison,
  type Source,
} from "@/lib/api";
import {
  fieldClaims,
  initialFieldEvidence,
  missingFieldSupport,
  reviewedFields,
  supplementalClaims,
} from "@/lib/review-claims";
import { RevisionDiff } from "@/components/revision-diff";

export function ReviewEditor({
  revision,
  token,
  onDone,
  remoteEtag,
}: {
  revision: Revision;
  token: string;
  onDone: () => void;
  remoteEtag?: string;
}) {
  const [snapshot, setSnapshot] = useState(revision);
  const [expected, setExpected] = useState(revision.etag || "");
  const expectedRef = useRef(expected);
  const [comparison, setComparison] = useState<ReviewComparison | null>(null);
  const [comparisonError, setComparisonError] = useState("");
  const [conflict, setConflict] = useState<Revision | null>(null);
  const [copyNotice, setCopyNotice] = useState("");
  const isAppend = snapshot.payload._import?.operation === "append_derivatives";
  const readOnly = snapshot.status !== "pending_review";
  const [name, setName] = useState(revision.payload.canonical_name);
  const [aliases, setAliases] = useState(revision.payload.aliases.join(" / "));
  const [definition, setDefinition] = useState(revision.payload.definition);
  const [context, setContext] = useState(revision.payload.usage_context);
  const [origin, setOrigin] = useState(revision.payload.origin_status);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [selected, setSelected] = useState(() =>
    initialFieldEvidence(revision.payload),
  );
  const [reason, setReason] = useState("");
  const [verified, setVerified] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [advanced, setAdvanced] = useState(() =>
    JSON.stringify(
      {
        events: revision.payload.events,
        relations: revision.payload.relations,
        claims: supplementalClaims(revision.payload, isAppend),
      },
      null,
      2,
    ),
  );
  async function readComparison(signal?: AbortSignal) {
    const data = await api<ReviewComparison>(
      `/v1/reviews/${revision.id}/comparison`,
      { signal },
      token,
    );
    if (signal?.aborted) return;
    setComparison(data);
    setComparisonError("");
    if (data.draft.etag !== expectedRef.current) {
      setConflict(data.draft);
      setVerified(false);
    }
    return data;
  }
  useEffect(() => {
    const controller = new AbortController();
    void readComparison(controller.signal).catch((e) => {
      if (!controller.signal.aborted) setComparisonError((e as Error).message);
    });
    return () => controller.abort();
    // Queue hints trigger a read, but never replace the local editor.
  }, [revision.id, token, remoteEtag]);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    async function load() {
      try {
        const ids = Array.from(
          new Set([
            ...evidence.map((item) => item.id),
            ...snapshot.payload.claims.flatMap((c) => c.evidence_ids),
            ...(snapshot.payload._import?.evidence_ids || []),
            ...snapshot.payload.events.flatMap(
              (event) =>
                (event as { evidence_ids?: string[] }).evidence_ids || [],
            ),
            ...snapshot.payload.relations.flatMap(
              (relation) =>
                (relation as { evidence_ids?: string[] }).evidence_ids || [],
            ),
          ]),
        );
        let materials: Evidence[] = [];
        if (snapshot.payload._source_id) {
          const data = await api<{ evidence: Evidence[]; source: Source }>(
            `/v1/reviews/sources/${snapshot.payload._source_id}`,
            { signal: controller.signal },
            token,
          );
          materials = data.evidence.map((item) => ({
            ...item,
            source: data.source,
          }));
        }
        const loaded = new Set(materials.map((item) => item.id));
        const referenced = await Promise.all(
          ids
            .filter((id) => !loaded.has(id))
            .map((id) =>
              api<Evidence>(
                `/v1/reviews/evidence/${id}`,
                { signal: controller.signal },
                token,
              ),
            ),
        );
        if (active) setEvidence([...materials, ...referenced]);
      } catch (e) {
        if (active) setError((e as Error).message);
      }
    }
    void load();
    return () => {
      active = false;
      controller.abort();
    };
  }, [snapshot, token]);
  function payload(): Draft {
    const extra = JSON.parse(advanced);
    if (
      !extra ||
      typeof extra !== "object" ||
      ![extra.claims || [], extra.events || [], extra.relations || []].every(
        Array.isArray,
      )
    )
      throw new Error(
        "高级结构化编辑中的 claims、events、relations 必须为数组。",
      );
    return {
      canonical_name: name,
      aliases: isAppend
        ? snapshot.payload.aliases
        : aliases
            .split("/")
            .map((s) => s.trim())
            .filter(Boolean),
      definition,
      usage_context: context,
      origin_status: origin,
      claims: [
        ...(extra.claims || []),
        ...fieldClaims(
          snapshot.payload,
          { definition, usage_context: context },
          selected,
          isAppend,
        ),
      ],
      events: extra.events || [],
      relations: extra.relations || [],
    };
  }
  async function save(body: Draft) {
    if (!expected)
      throw new Error("服务端未提供审核版本；升级服务后重新读取工作台。");
    const saved = await api<Revision>(
      `/v1/reviews/${revision.id}`,
      {
        method: "PUT",
        body: JSON.stringify(body),
        headers: { "If-Match": expected },
      },
      token,
    );
    expectedRef.current = saved.etag;
    setExpected(saved.etag);
    setSnapshot(saved);
    return saved;
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
      if (
        decision === "approve" &&
        comparison?.meme_status === "retracted" &&
        !window.confirm("该条目已撤回。确认重新发布你刚核查的这一版内容？")
      )
        return;
      if (!expected)
        throw new Error("服务端未提供审核版本；升级服务后重新读取工作台。");
      const body = decision === "reject" ? snapshot.payload : payload();
      if (decision === "approve") {
        if (!body.definition.trim())
          throw new Error("发布前请填写有证据支持的定义。");
        const missing = missingFieldSupport(body);
        if (missing)
          throw new Error(
            `${missing === "definition" ? "定义" : "使用语境"}尚未选择完整字段的支持证据。请分别勾选，或在高级编辑中提供对应断言。`,
          );
      }
      const saved = decision === "reject" ? snapshot : await save(body);
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
          {
            ...post({
              decision,
              reason,
              verified_evidence_ids: verified ? ids : [],
            }),
            headers: { "If-Match": saved.etag },
          },
          token,
        );
        onDone();
      } else setNotice("草稿已保存，尚未发布。");
    } catch (e) {
      setError((e as Error).message);
      if (e instanceof ApiError && [409, 412].includes(e.status)) {
        setVerified(false);
        try {
          await readComparison();
        } catch (readError) {
          setComparisonError((readError as Error).message);
        }
      }
    } finally {
      setBusy(false);
    }
  }
  function useLatest(replaceLocal: boolean) {
    if (!conflict) return;
    if (
      replaceLocal &&
      !window.confirm(
        "读取最新服务器稿会替换本地未提交文字。已复制需要保留的内容吗？",
      )
    )
      return;
    const latest = conflict;
    if (replaceLocal) {
      setName(latest.payload.canonical_name);
      setAliases(latest.payload.aliases.join(" / "));
      setDefinition(latest.payload.definition);
      setContext(latest.payload.usage_context);
      setOrigin(latest.payload.origin_status);
      setSelected(initialFieldEvidence(latest.payload));
      setAdvanced(
        JSON.stringify(
          {
            events: latest.payload.events,
            relations: latest.payload.relations,
            claims: supplementalClaims(latest.payload, isAppend),
          },
          null,
          2,
        ),
      );
    }
    setSnapshot(latest);
    expectedRef.current = latest.etag;
    setExpected(latest.etag);
    setVerified(false);
    setConflict(null);
    setError("");
    setNotice(
      replaceLocal
        ? "已读取服务器稿；尚未保存或发布。"
        : "已采用服务器最新版本作为写入基准，本地文字保留；请对照、重新核查后再提交。",
    );
  }
  async function copyLocal() {
    try {
      await navigator.clipboard.writeText(
        JSON.stringify(
          {
            revision_id: revision.id,
            expected_etag: expected,
            local_editor: {
              name,
              aliases,
              definition,
              usage_context: context,
              origin_status: origin,
              selected,
              advanced_text: advanced,
              reason,
            },
          },
          null,
          2,
        ),
      );
      setCopyNotice("本地编辑副本已复制，未提交服务器。");
    } catch {
      setCopyNotice(
        "复制失败；请先手工保存需要保留的文字，不要直接读取服务器稿。",
      );
    }
  }
  let proposal: Draft | null = null;
  try {
    proposal = payload();
  } catch {
    /* Keep malformed JSON editable. */
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
    <section data-revision-id={revision.id}>
      <h2 className="section-title" style={{ marginTop: 0 }}>
        核对语境，再发布结论。
      </h2>
      <p className="small-code">
        Meme: {revision.meme_id} · 基于修订 {snapshot.based_on_revision} ·
        稿件编辑版 {snapshot.edit_version}
      </p>
      {comparison &&
        ["retracted", "merged"].includes(comparison.meme_status) && (
          <p className="notice">
            条目当前
            {comparison.meme_status === "retracted"
              ? "已撤回。读取历史内容不会恢复公开资格；再次审核通过会明确确认重新发布。"
              : "已合并，不能在原条目发布。"}
          </p>
        )}
      {comparisonError && (
        <p className="error">内容对照暂不可用：{comparisonError}</p>
      )}
      {comparison && snapshot.based_on_revision > 0 && !comparison.base && <p className="notice">基准修订的已批准快照不可用，不能计算差异；不会把它当成空白版本。</p>}
      {comparison?.base_changed && (
        <p className="notice">
          公开版本已从修订 {snapshot.based_on_revision} 变为{" "}
          {comparison.current_published_revision}
          。本地文字保留；此稿不能自动变基发布，请基于当前内容创建新修订。
        </p>
      )}
      {comparison &&
        !comparison.base_changed &&
        (snapshot.based_on_revision === 0 || comparison.base) && (
          <RevisionDiff
            before={comparison.base?.payload || null}
            after={proposal}
            beforeLabel={
              comparison.base
                ? `已批准修订 ${snapshot.based_on_revision}`
                : "新条目：尚无公开内容"
            }
            afterLabel="本地编辑（尚未提交）"
          />
        )}
      {conflict && (
        <section className="review-conflict" aria-label="审核编辑冲突">
          <h3>服务器稿件已变化，本地文字已保留。</h3>
          <p>
            服务器编辑版 {conflict.edit_version} · {conflict.status}
            。不会自动覆盖、自动合并或批准另一位编辑者的内容。
          </p>
          <RevisionDiff
            before={conflict.payload}
            after={proposal}
            beforeLabel="服务器最新稿"
            afterLabel="你的本地文字"
            title="冲突内容对照"
          />
          <div className="action-row">
            <button
              className="button outline"
              disabled={busy}
              onClick={() => void copyLocal()}
            >
              复制本地编辑副本
            </button>
            <button
              className="button outline"
              disabled={busy || conflict.status !== "pending_review"}
              onClick={() => useLatest(false)}
            >
              以最新服务器版继续核对本地稿
            </button>
            <button
              className="text-button"
              disabled={busy}
              onClick={() => useLatest(true)}
            >
              读取服务器稿，放弃本地改动
            </button>
          </div>
          {copyNotice && <p role="status">{copyNotice}</p>}
        </section>
      )}
      {revision.payload._import && (
        <div className="task-state">
          <p>
            {revision.payload._import.operation === "append_derivatives"
              ? "此修订仅追加用法：原有定义、别名、出处和证据绑定受到保护。"
              : "数据包导入的待审稿：请选择真正支持定义与使用语境的证据。"}
          </p>
          <p>原始附件仅有引用；当前可核查材料是随包保存的文本摘录。</p>
        </div>
      )}
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
            disabled={isAppend || busy || readOnly}
            onChange={(e) => {
              setName(e.target.value);
              setVerified(false);
            }}
            required
            maxLength={200}
          />
        </label>
        <label className="field">
          <span>别名（用 / 分隔）</span>
          <input
            value={aliases}
            disabled={isAppend || busy || readOnly}
            onChange={(e) => {
              setAliases(e.target.value);
              setVerified(false);
            }}
          />
        </label>
        <label className="field">
          <span>定义 · 必须由下方选中的证据完整支持</span>
          <textarea
            value={definition}
            disabled={isAppend || busy || readOnly}
            onChange={(e) => {
              setDefinition(e.target.value);
              setSelected((old) => ({ ...old, definition: [] }));
              setVerified(false);
            }}
          />
        </label>
        <label className="field">
          <span>使用语境</span>
          <textarea
            aria-label="使用语境"
            value={context}
            disabled={isAppend || busy || readOnly}
            onChange={(e) => {
              setContext(e.target.value);
              setSelected((old) => ({ ...old, usage_context: [] }));
              setVerified(false);
            }}
          />
        </label>
        <label className="field">
          <span>起源状态</span>
          <select
            value={origin}
            disabled={isAppend || busy || readOnly}
            onChange={(e) => {
              setOrigin(e.target.value);
              setVerified(false);
            }}
          >
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
        {isAppend
          ? "已有字段引用保持不变。请逐条核对新增用法材料及事件绑定，再确认审核。"
          : "分别选择支持定义、支持使用语境的材料；同一材料确实支持两者时才勾选两项。修改字段文字后需重新选择该字段的证据。反对意见、起源与补充断言保留在结构化编辑中，不自动变成字段支持。"}
      </p>
      {evidence.map((item) => (
        <article key={item.id} className="evidence-box">
          <div className="row-meta">
            <span>
              {item.kind} · {item.id.slice(0, 8)}
              {item.retracted ? " · 已撤回" : ""}
            </span>
          </div>
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
          {!isAppend && (
            <div
              className="review-evidence-fields"
              role="group"
              aria-label="这份证据的字段支持关系"
            >
              {reviewedFields.map((field) => (
                <label className="check-label" key={field}>
                  <input
                    type="checkbox"
                    disabled={item.retracted || busy || readOnly}
                    checked={selected[field].includes(item.id)}
                    onChange={(e) => {
                      const checked = e.target.checked;
                      setVerified(false);
                      setSelected((old) => ({
                        ...old,
                        [field]: checked
                          ? Array.from(new Set([...old[field], item.id]))
                          : old[field].filter((id) => id !== item.id),
                      }));
                    }}
                  />
                  <span>
                    {field === "definition" ? "支持定义" : "支持使用语境"}
                  </span>
                </label>
              ))}
            </div>
          )}
        </article>
      ))}
      <button
        className="text-button"
        style={{ marginLeft: 0 }}
        disabled={busy}
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
            disabled={busy || readOnly}
            value={advanced}
            onChange={(e) => {
              setAdvanced(e.target.value);
              setVerified(false);
            }}
          />
        </label>
      </details>
      <hr className="divider" />
      <label className="field">
        <span>审核理由</span>
        <textarea
          disabled={busy || readOnly}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="说明证据怎样支持这些断言，哪些内容仍不确定。"
        />
      </label>
      <label className="check-label" style={{ margin: "20px 0" }}>
        <input
          type="checkbox"
          disabled={busy || readOnly}
          checked={verified}
          onChange={(e) => setVerified(e.target.checked)}
        />
        我已人工核对所有引用材料、时间定位及其对断言的支持关系
      </label>
      <div className="action-row">
        <button
          className="button primary"
          disabled={
            busy ||
            readOnly ||
            Boolean(conflict) ||
            Boolean(comparison?.base_changed) ||
            comparison?.meme_status === "merged"
          }
          onClick={() => void act("approve")}
        >
          审核通过并发布
        </button>
        <button
          className="button outline"
          disabled={busy || readOnly || Boolean(conflict)}
          onClick={() => void act()}
        >
          保存草稿
        </button>
        <button
          className="button danger"
          disabled={busy || readOnly || Boolean(conflict)}
          onClick={() => void act("reject")}
        >
          拒绝此修订
        </button>
      </div>
    </section>
  );
}
