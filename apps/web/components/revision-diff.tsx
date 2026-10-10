"use client";

import type { Draft } from "@/lib/api";
import { revisionChanges, showDiffValue } from "@/lib/revision-diff";

export function RevisionDiff({
  before,
  after,
  beforeLabel,
  afterLabel,
  title = "修订内容对照",
}: {
  before: Draft | null;
  after: Draft | null;
  beforeLabel: string;
  afterLabel: string;
  title?: string;
}) {
  let changes: ReturnType<typeof revisionChanges> = [];
  let valid = Boolean(after);
  try {
    if (after) changes = revisionChanges(before, after);
  } catch {
    valid = false;
  }
  return (
    <details className="revision-diff">
      <summary>
        {title} · {valid ? `${changes.length} 项变化` : "结构化内容尚未解析"}
      </summary>
      <p className="muted">
        只对照内容与引用变化，不判断材料真实性或语义支持；不会自动合并或发布。
      </p>
      {!valid ? (
        <p role="status">
          高级结构化内容尚不能作为候选解析，原文字保留；检查 JSON
          与数组/引用格式后可继续对照。
        </p>
      ) : changes.length === 0 ? (
        <p role="status">内容与证据绑定没有变化。</p>
      ) : (
        <div role="region" aria-label={title}>
          {changes.map(([field, label]) => (
            <section className="revision-diff-field" key={field}>
              <h4>{label}</h4>
              <div className="revision-diff-columns">
                <div>
                  <p className="row-meta">− {beforeLabel}</p>
                  <pre>{showDiffValue(before, field)}</pre>
                </div>
                <div>
                  <p className="row-meta">＋ {afterLabel}</p>
                  <pre>{showDiffValue(after, field)}</pre>
                </div>
              </div>
            </section>
          ))}
        </div>
      )}
    </details>
  );
}
