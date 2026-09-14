"use client";
import type { Galaxy, Star, Universe } from "@/lib/api";
import {
  STAGES,
  milestoneStar,
  orderedStars,
  stageLabel,
} from "./universe-layout";

/**
 * The same galaxies as the map, as text: ordered by date, keeping the two kinds
 * of missing distinct. It is the fallback for a screen reader and the honest
 * version of the picture when the picture cannot be read.
 */
export function UniverseList({
  universe,
  onOpenGalaxy,
}: {
  universe: Universe;
  onOpenGalaxy: (galaxy: Galaxy) => void;
}) {
  const dated = universe.galaxies.filter((g) => g.u !== null);
  const undated = universe.galaxies.filter((g) => g.u === null);
  return (
    <div className="universe-list">
      <h2>星图列表</h2>
      <p className="muted">
        按出现时间排列。无日期表示有证据但未定日，与无证据不同。
      </p>
      <ol>
        {dated.map((galaxy) => (
          <li key={galaxy.meme_id}>
            <button
              type="button"
              className="list-row"
              onClick={() => onOpenGalaxy(galaxy)}
            >
              <span className="list-date">
                {galaxy.emergence.date ?? "无日期"}
              </span>
              <span className="list-name">{galaxy.name}</span>
              <span className="list-meta">
                {galaxy.stars.length} 星 · 依据
                {galaxy.emergence.basis === "none"
                  ? " 无"
                  : ` ${emergenceLabel(galaxy.emergence.basis)}`}
              </span>
            </button>
          </li>
        ))}
      </ol>
      {undated.length > 0 && (
        <>
          <h3>无日期</h3>
          <ol>
            {undated.map((galaxy) => (
              <li key={galaxy.meme_id}>
                <button
                  type="button"
                  className="list-row"
                  onClick={() => onOpenGalaxy(galaxy)}
                >
                  <span className="list-date">无日期</span>
                  <span className="list-name">{galaxy.name}</span>
                  <span className="list-meta">{galaxy.stars.length} 星</span>
                </button>
              </li>
            ))}
          </ol>
        </>
      )}
    </div>
  );
}

export function GalaxyList({
  galaxy,
  activeStarId,
  onSelectStar,
}: {
  galaxy: Galaxy;
  activeStarId: string | null;
  onSelectStar: (star: Star) => void;
}) {
  const stars = orderedStars(galaxy.stars);
  const dated = stars.filter((star) => star.t !== null);
  const undated = stars.filter((star) => star.t === null);
  return (
    <div className="universe-list">
      <h2>{galaxy.name} · 列表视图</h2>
      <p className="muted">
        按日期排列。四阶段是因果关系，这里的顺序只是时间。
      </p>
      <h3>有时间</h3>
      {dated.length === 0 ? (
        <p className="muted">没有带日期的星体。</p>
      ) : (
        <ol>
          {dated.map((star) => (
            <StarRow
              key={star.id}
              star={star}
              active={star.id === activeStarId}
              onSelect={onSelectStar}
            />
          ))}
        </ol>
      )}
      <h3>无日期</h3>
      {undated.length === 0 ? (
        <p className="muted">没有无日期的星体。</p>
      ) : (
        <ol>
          {undated.map((star) => (
            <StarRow
              key={star.id}
              star={star}
              active={star.id === activeStarId}
              onSelect={onSelectStar}
            />
          ))}
        </ol>
      )}
      <h3>阶段覆盖</h3>
      <ul className="list-milestones">
        {STAGES.map((stage) => {
          const star = milestoneStar(galaxy, stage);
          return (
            <li key={stage}>
              <span className="milestone-stage">{stageLabel(stage)}</span>
              {star ? (
                <span>
                  {star.label} · {star.date ?? "无日期"}
                </span>
              ) : (
                <span className="milestone-empty">无证据</span>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function StarRow({
  star,
  active,
  onSelect,
}: {
  star: Star;
  active: boolean;
  onSelect: (star: Star) => void;
}) {
  return (
    <li>
      <button
        type="button"
        className={`list-row${active ? " is-active" : ""}`}
        onClick={() => onSelect(star)}
        aria-label={`${stageLabel(star.stage)}，${star.date ?? "无日期"}，${
          star.label
        }`}
      >
        <span className="list-date">{star.date ?? "无日期"}</span>
        <span className="list-name">{star.label}</span>
        <span className="list-meta">
          {stageLabel(star.stage)}
          {star.milestone ? " · 里程碑" : ""}
          {star.kind === "meme" ? " · 另一个梗" : ""}
        </span>
      </button>
    </li>
  );
}

function emergenceLabel(basis: string): string {
  return (
    {
      derivative: "衍生视频",
      popularized_by: "走红作品",
      source: "素材来源",
      none: "无",
    }[basis] ?? basis
  );
}
