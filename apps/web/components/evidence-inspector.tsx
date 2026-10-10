"use client";

import { useState } from "react";
import { date, type Meme } from "@/lib/api";
import { describeKind, describeLocator } from "@/lib/evidence";
import { platformLabel } from "@/lib/platforms";
import { referenceUrl, stanceLabel } from "@/lib/citations";
import type { useReferenceNavigation } from "@/lib/use-reference-navigation";
import { ReferenceLink } from "@/components/citation-links";
import { Icon } from "@/components/icons";

export function EvidenceInspector({
  meme,
  navigation,
}: {
  meme: Meme;
  navigation: ReturnType<typeof useReferenceNavigation>;
}) {
  const [copied, setCopied] = useState<Record<string, string>>({});
  const platforms = Array.from(
    new Set(
      meme.evidence
        .map((e) => e.source?.platform)
        .filter((p): p is string => !!p),
    ),
  );
  async function copy(id: string) {
    try {
      if (!navigator.clipboard) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(
        new URL(
          referenceUrl(meme.id, meme.published_revision, id),
          window.location.origin,
        ).href,
      );
      setCopied((old) => ({ ...old, [id]: "引用链接已复制。" }));
    } catch {
      setCopied((old) => ({
        ...old,
        [id]: "复制失败，可右键复制下方的引用直达链接。",
      }));
    }
  }
  return (
    <aside
      className="evidence-inspector"
      id="evidence"
      tabIndex={-1}
      aria-label="公开证据浏览器"
    >
      <h2 className="section-title" style={{ marginTop: 0 }}>
        回到证据本身
      </h2>
      {meme.evidence.length > 0 && (
        <div className="evidence-controls">
          <label className="field">
            <span>在证据中查找</span>
            <input
              type="search"
              value={navigation.query}
              onChange={(e) => navigation.setQuery(e.target.value)}
              placeholder="原文或来源标题"
            />
          </label>
          <label className="field">
            <span>证据平台</span>
            <select
              value={navigation.platform}
              onChange={(e) => navigation.setPlatform(e.target.value)}
            >
              <option value="">全部平台</option>
              {platforms.map((platform) => (
                <option key={platform} value={platform}>
                  {platformLabel(platform)}
                </option>
              ))}
            </select>
          </label>
          <div className="evidence-filter-status" role="status">
            显示 {navigation.visible.length} / {meme.evidence.length} 份证据
            {(navigation.query || navigation.platform) && (
              <button
                className="text-button"
                onClick={() => {
                  navigation.setQuery("");
                  navigation.setPlatform("");
                }}
              >
                清除证据筛选
              </button>
            )}
          </div>
        </div>
      )}
      {!navigation.visible.length && (
        <p className="muted">
          {meme.evidence.length
            ? "当前筛选没有匹配的证据。"
            : "当前公开修订没有可展示的证据材料。"}
        </p>
      )}
      {navigation.visible.map(({ evidence: e, number, uses }) => (
        <article
          key={e.id}
          id={`evidence-${e.id}`}
          className="evidence-box"
          tabIndex={-1}
          aria-label={`证据 ${number}`}
          aria-current={navigation.activeEvidence === e.id ? "true" : undefined}
        >
          <div className="evidence-head">
            <span>
              证据 {number} · {describeKind(e.kind)}
            </span>
            <span>已审核</span>
          </div>
          {navigation.activeEvidence === e.id &&
            navigation.messages.length > 0 && (
              <p className="notice reference-status" role="status">
                {navigation.messages.join(" ")}
              </p>
            )}
          <blockquote>{e.text}</blockquote>
          <p className="evidence-where">{describeLocator(e.locator)}</p>
          {e.source && (
            <>
              <p className="evidence-source-platform">
                {platformLabel(e.source.platform)}
              </p>
              <a href={e.source.canonical_url} target="_blank" rel="noreferrer">
                {e.source.title || "查看平台原始来源"}{" "}
                <Icon name="arrow" size={17} />
              </a>
              <p className="evidence-dates">
                平台发布时间：{date(e.source.platform_published_at)}
                <br />
                证据登记时间：{date(e.created_at)}
              </p>
              {e.source.metadata_note && (
                <p className="muted">来源备注：{e.source.metadata_note}</p>
              )}
            </>
          )}
          {uses.length > 0 && (
            <div className="evidence-backlinks" aria-label="返回引用位置">
              {uses.map((use, i) => (
                <div key={`${use.anchor}-${i}`}>
                  <ReferenceLink
                    anchor={use.anchor}
                    onNavigate={navigation.navigate}
                    title={use.statement}
                  >
                    {use.label}
                  </ReferenceLink>
                  <span>{stanceLabel(use.stance)}</span>
                </div>
              ))}
            </div>
          )}
          <details className="evidence-integrity">
            <summary>证据版本与摘要</summary>
            <p className="small-code">
              当前档案修订：{meme.published_revision}
            </p>
            <p className="small-code">记录 SHA-256：{e.content_hash}</p>
            <p className="small-code">工件 SHA-256：{e.artifact_hash}</p>
            <a href={`/api/v1/evidence/${encodeURIComponent(e.id)}/artifact`}>
              下载证据工件
            </a>
          </details>
          <div className="evidence-share">
            <button className="text-button" onClick={() => void copy(e.id)}>
              复制引用链接
            </button>
            <a href={referenceUrl(meme.id, meme.published_revision, e.id)}>
              引用直达链接
            </a>
          </div>
          {copied[e.id] && (
            <p className="retrieval-note" role="status">
              {copied[e.id]}
            </p>
          )}
        </article>
      ))}
    </aside>
  );
}
