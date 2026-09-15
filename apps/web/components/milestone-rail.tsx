"use client";
import type { Star } from "@/lib/api";
import { STAGES, milestoneStar, stageLabel } from "./universe-layout";

/**
 * The four stages in model order, not time order. Most real galaxies leave two or
 * three of these empty, so an empty slot has to look like the archive saying "no
 * evidence" rather than like something failed to load.
 */
export function MilestoneRail({
  galaxy,
  activeId,
  onHover,
  onSelect,
}: {
  galaxy: import("@/lib/api").Galaxy;
  activeId: string | null;
  onHover: (starId: string | null) => void;
  onSelect: (star: Star) => void;
}) {
  return (
    <section className="milestone-rail" aria-labelledby="milestone-rail-title">
      <div className="milestone-rail-head">
        <h2 id="milestone-rail-title">阶段里程碑</h2>
        <p className="muted">按阶段排列，非时间顺序</p>
      </div>
      <ol className="milestone-list">
        {STAGES.map((stage) => {
          const star = milestoneStar(galaxy, stage);
          return (
            <li
              key={stage}
              className={`milestone-slot stage-${stage}${
                star ? "" : " is-empty"
              }${star && star.id === activeId ? " is-active" : ""}`}
              data-stage={stage}
              onMouseEnter={() => onHover(star ? star.id : null)}
              onMouseLeave={() => onHover(null)}
            >
              <span className="milestone-stage">{stageLabel(stage)}</span>
              {star ? (
                <button
                  type="button"
                  className="milestone-star"
                  onClick={() => onSelect(star)}
                >
                  <span className="milestone-label">{star.label}</span>
                  <span className="milestone-date">
                    {star.date ?? "无日期"}
                  </span>
                </button>
              ) : (
                <span className="milestone-empty" data-empty="true">
                  无证据
                </span>
              )}
            </li>
          );
        })}
      </ol>
    </section>
  );
}
