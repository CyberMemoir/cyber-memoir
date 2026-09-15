"use client";
import { useEffect, useState } from "react";
import { api, type Evidence, type Star } from "@/lib/api";
import { STAGE_STYLE, type Stage } from "./universe-layout";

/** Every excerpt, kind, locator and hash below is the API's own text. */
export function StarPanel({
  star,
  onClose,
}: {
  star: Star;
  onClose: () => void;
}) {
  const style = STAGE_STYLE[star.stage as Stage];
  return (
    <aside
      className="star-panel"
      role="dialog"
      aria-modal="false"
      aria-label={`${style?.label ?? star.stage}：${star.label}`}
      data-star-id={star.id}
    >
      <div className="star-panel-head">
        <span className={`stage-chip stage-${star.stage}`}>
          {style?.label ?? star.stage}
          {style ? ` · ${style.shapeNote}` : ""}
        </span>
        <button
          type="button"
          className="text-button"
          onClick={onClose}
          aria-label="关闭星体面板"
        >
          关闭 (Esc)
        </button>
      </div>
      <h2 className="star-panel-title">{star.label}</h2>
      <div className="row-meta">
        {/* INV-1: the date field is already the Beijing calendar day. */}
        <span>{star.date ?? "无日期"}</span>
        <span>
          {star.tier ? `来源层级 ${star.tier}` : "无来源层级"}
          {star.milestone ? " · 里程碑" : ""}
        </span>
      </div>

      <section className="star-evidence" aria-labelledby="star-evidence-title">
        <h3 id="star-evidence-title">证据</h3>
        {star.evidence_ids.length === 0 ? (
          <p className="muted">这条星体没有关联证据编号。</p>
        ) : (
          <ul className="star-evidence-list">
            {star.evidence_ids.map((id) => (
              <EvidenceItem key={id} evidenceId={id} />
            ))}
          </ul>
        )}
      </section>

      <div className="star-actions">
        {star.url ? (
          <a
            className="button outline"
            href={star.url}
            target="_blank"
            rel="noreferrer"
          >
            打开原始链接
          </a>
        ) : star.kind === "meme" ? (
          <p className="muted">这是一个梗，打开它的星系即可看到它的证据。</p>
        ) : (
          <p className="muted">这条星体没有外部链接。</p>
        )}
      </div>

      {star.bvid && <EmbeddedPlayer bvid={star.bvid} />}
    </aside>
  );
}

function EvidenceItem({ evidenceId }: { evidenceId: string }) {
  const [evidence, setEvidence] = useState<Evidence | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<Evidence>(`/v1/evidence/${evidenceId}`)
      .then((data) => {
        if (active) setEvidence(data);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [evidenceId]);
  return (
    <li className="evidence-box star-evidence-item" data-evidence-id={evidenceId}>
      {error && <p className="error">证据读取失败：{error}</p>}
      {!evidence && !error && <p className="muted">正在读取证据…</p>}
      {evidence && (
        <>
          <div className="evidence-head">
            <span>{evidence.kind}</span>
            <span className="small-code">{evidence.id.slice(0, 8)}</span>
          </div>
          <blockquote>{evidence.text}</blockquote>
          <p className="small-code">定位：{JSON.stringify(evidence.locator)}</p>
          <p className="small-code">
            内容哈希：{evidence.content_hash.slice(0, 12)}
          </p>
        </>
      )}
    </li>
  );
}

/**
 * The official Bilibili player, created only after a click. No video is ever
 * downloaded, proxied or cached here, and the outbound link above stays usable
 * when the embed refuses to play.
 */
function EmbeddedPlayer({ bvid }: { bvid: string }) {
  const [open, setOpen] = useState(false);
  return (
    <details
      className="star-embed"
      onToggle={(event) => setOpen((event.target as HTMLDetailsElement).open)}
    >
      <summary>播放（Bilibili 官方播放器）</summary>
      {open && (
        <iframe
          src={`https://player.bilibili.com/player.html?bvid=${bvid}&autoplay=0`}
          title={`Bilibili 播放器 ${bvid}`}
          loading="lazy"
          allowFullScreen
          referrerPolicy="no-referrer"
        />
      )}
      <p className="muted star-embed-note">
        播放器来自 Bilibili。若不显示，请使用上方的原始链接。
      </p>
    </details>
  );
}
