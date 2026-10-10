"use client";

import { useEffect, useState } from "react";
import { date, type Revision } from "@/lib/api";
import { RevisionDiff } from "./revision-diff";

function label(item: Revision) {
  const version =
    item.status === "published"
      ? `已批准修订 ${item.based_on_revision + 1}`
      : `基于修订 ${item.based_on_revision} 的${item.status === "rejected" ? "已拒绝" : "待审"}稿`;
  return `${version} · 编辑版 ${item.edit_version} · ${date(item.created_at)} · ${item.id.slice(0, 8)}`;
}

export function RevisionHistory({
  items,
  onRevise,
}: {
  items: Revision[];
  onRevise: (revision: Revision) => void;
}) {
  const [beforeId, setBeforeId] = useState("");
  const [afterId, setAfterId] = useState("");
  useEffect(() => {
    setAfterId(items[0]?.id || "");
    setBeforeId(items[1]?.id || items[0]?.id || "");
  }, [items]);
  const before = items.find((item) => item.id === beforeId);
  const after = items.find((item) => item.id === afterId);
  if (!items.length) return null;
  return (
    <section aria-label="历史修订对照">
      <h3 className="section-title">历史修订</h3>
      <p className="muted">
        仅审核者可见，包括被拒绝与已撤回条目的记录；历史内容不因此恢复公开资格。
      </p>
      <div className="revision-diff-columns">
        <label className="field">
          <span>对照基准修订</span>
          <select
            value={beforeId}
            onChange={(e) => setBeforeId(e.target.value)}
          >
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {label(item)}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>对照目标修订</span>
          <select value={afterId} onChange={(e) => setAfterId(e.target.value)}>
            {items.map((item) => (
              <option key={item.id} value={item.id}>
                {label(item)}
              </option>
            ))}
          </select>
        </label>
      </div>
      {before && after && (
        <RevisionDiff
          before={before.payload}
          after={after.payload}
          beforeLabel={label(before)}
          afterLabel={label(after)}
          title="历史内容对照"
        />
      )}
      {items.map((item) => (
        <article className="evidence-box" key={item.id}>
          <p className="row-meta">{label(item)}</p>
          <p>{item.review_reason || "尚无审核决定"}</p>
          <p className="muted">
            {item.reviewer ? `审核者：${item.reviewer}` : "未审核"}
            {item.reviewed_at ? ` · ${date(item.reviewed_at)}` : ""}
          </p>
          <button className="text-button" onClick={() => onRevise(item)}>
            基于此内容创建新修订
          </button>
        </article>
      ))}
    </section>
  );
}
