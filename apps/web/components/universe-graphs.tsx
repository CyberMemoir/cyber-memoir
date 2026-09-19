"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Galaxy, Star, Universe } from "@/lib/api";
import { galaxySprite, renderGalaxyDust } from "@/lib/galaxy-art";
import { useReducedMotion } from "@/lib/motion";
import { hashSeed, seeded } from "@/lib/seeded";
import { StarGlyph } from "./star-glyph";
import {
  AXIS_X0,
  AXIS_X1,
  AXIS_Y,
  GALAXY_VIEW,
  NAME_LIMIT,
  STAGES,
  UNDATED_X,
  allInOneYear,
  armPath,
  axisEnd,
  bandLabel,
  drawDate,
  layoutUniverse,
  placeStars,
  radiusAt,
  type PlacedGalaxy,
} from "./universe-layout";

/** SVG text has no auto-truncation, and a galaxy name may run off the canvas. */
function clip(text: string, characters: number): string {
  return text.length > characters
    ? `${text.slice(0, characters - 1)}…`
    : text;
}

/** How long the ignition sweep takes to cross the whole axis. */
const SWEEP_MS = 2400;

/* --------------------------------------------------------------- universe -- */

export function UniverseGraph({
  universe,
  onOpenGalaxy,
}: {
  universe: Universe;
  onOpenGalaxy: (galaxy: Galaxy) => void;
}) {
  const { placed, undated } = useMemo(() => layoutUniverse(universe), [universe]);
  const byId = new Map(placed.map((item) => [item.galaxy.meme_id, item]));
  const end = axisEnd(universe);
  /* Whether the year can be dropped is a property of this picture, decided from its
     own dates: one calendar year may say 08-20, a span of years may not. */
  const oneYear = allInOneYear([
    ...universe.galaxies.map((galaxy) => galaxy.emergence.date),
    ...universe.axis.ticks.map((tick) => tick.date),
  ]);
  const [sprites, setSprites] = useState<Record<string, string>>({});
  useEffect(() => {
    let active = true;
    for (const galaxy of universe.galaxies) {
      void galaxySprite(galaxy.meme_id).then((url) => {
        if (active && url) setSprites((current) => ({ ...current, [galaxy.meme_id]: url }));
      });
    }
    return () => {
      active = false;
    };
  }, [universe]);

  /* The time cursor: galaxies past it are not yet born and dim. It moves between
     the dates the archive actually has, so its readout never invents a day. */
  const stops = useMemo(
    () => placed.map((item) => item.x).filter((x, i, all) => all.indexOf(x) === i),
    [placed],
  );
  const [cursor, setCursor] = useState<number | null>(null);
  const cursorX = cursor ?? end;
  const born = placed.filter((item) => item.x <= cursorX + 0.5);
  const latest = born[born.length - 1]?.galaxy.emergence.date ?? null;
  const handle = useRef<SVGGElement | null>(null);

  const toUser = (clientX: number) => {
    const surface = handle.current?.closest("g.zoom-surface") as SVGGraphicsElement | null;
    const matrix = surface?.getScreenCTM();
    if (!matrix) return null;
    return new DOMPoint(clientX, 0).matrixTransform(matrix.inverse()).x;
  };
  const snap = (x: number) => {
    const clamped = Math.min(Math.max(x, AXIS_X0), end);
    return clamped >= end - 2 ? null : clamped;
  };
  const step = (direction: number) => {
    const current = cursor ?? end;
    const index = stops.findIndex((x) => x > current + 0.5);
    const at = index === -1 ? stops.length : index;
    const next = stops[Math.min(Math.max(at - 1 + direction, 0), stops.length - 1)];
    setCursor(direction > 0 && at >= stops.length ? null : snap(next ?? end));
  };

  /* The bands run from above the axis down to just past it and stop: a galaxy is
     never inside a quiet period - that is what the band means - so the rectangles
     must not reach the glyphs. They stop well above the first lane. */
  const y0 = AXIS_Y - 150;
  const y1 = AXIS_Y + 40;

  return (
    <>
      <g className="universe-static">
        {/* Quiet periods: dark lanes of fixed width that lie about the duration,
            hence the label with the true length. */}
        {universe.axis.bands.map((band) => (
          <g className="quiet-band axis-band" key={`${band.date_from}-${band.date_to}`}>
            <rect
              x={AXIS_X0 + band.start * (AXIS_X1 - AXIS_X0)}
              y={y0}
              width={Math.max((band.end - band.start) * (AXIS_X1 - AXIS_X0), 3)}
              height={y1 - y0}
            />
            <text
              x={AXIS_X0 + ((band.start + band.end) / 2) * (AXIS_X1 - AXIS_X0)}
              y={y0 - 14}
              textAnchor="middle"
            >
              {bandLabel(band.days)}
            </text>
          </g>
        ))}
        {/* The time axis itself, with its direction stated rather than implied. */}
        <line className="time-axis" x1={AXIS_X0 - 40} y1={AXIS_Y} x2={end + 30} y2={AXIS_Y} />
        <path className="axis-arrow" d={`M ${end + 30} ${AXIS_Y} l -13 -6 l 0 12 Z`} />
        <text className="axis-direction" x={end + 34} y={AXIS_Y + 6}>
          时间 →
        </text>
        {universe.axis.ticks.map((tick) => (
          <g className="axis-tick" key={`${tick.t}-${tick.date}`}>
            <line
              x1={AXIS_X0 + tick.t * (AXIS_X1 - AXIS_X0)}
              y1={AXIS_Y - 8}
              x2={AXIS_X0 + tick.t * (AXIS_X1 - AXIS_X0)}
              y2={AXIS_Y + 8}
            />
            <text
              x={AXIS_X0 + tick.t * (AXIS_X1 - AXIS_X0)}
              y={AXIS_Y + 30}
              textAnchor="middle"
            >
              {drawDate(tick.date, oneYear)}
            </text>
          </g>
        ))}
        {/* The ignition sweep: a line of light crossing the axis once, lighting each
            galaxy as it passes the day that galaxy first has evidence. */}
        <line
          className="time-sweep"
          x1={AXIS_X0}
          y1={y0 + 20}
          x2={AXIS_X0}
          y2={AXIS_Y + 60}
          style={{ "--sweep": `${end - AXIS_X0}px` } as React.CSSProperties}
        />
        {undated.length > 0 && (
          <g className="undated-column">
            <line
              x1={UNDATED_X}
              y1={AXIS_Y - 110}
              x2={UNDATED_X}
              y2={AXIS_Y + 560}
              className="undated-rule"
            />
            <text x={UNDATED_X} y={AXIS_Y - 150} textAnchor="middle">
              无日期
            </text>
            <text x={UNDATED_X} y={AXIS_Y - 126} textAnchor="middle" className="undated-note">
              有证据，未定日
            </text>
          </g>
        )}
      </g>

      {/* Relations, drawn under the galaxies so a curve never covers a star. */}
      <g className="universe-links">
        {universe.links.map((link) => {
          const from = byId.get(link.from_meme_id);
          const to = byId.get(link.to_meme_id);
          if (!from || !to) return null;
          const arch = Math.min(70 + Math.abs(to.x - from.x) * 0.08, 160);
          return (
            <path
              className="galaxy-link"
              key={`${link.from_meme_id}-${link.to_meme_id}`}
              d={`M ${from.x} ${from.y} Q ${(from.x + to.x) / 2} ${
                (from.y + to.y) / 2 - arch
              } ${to.x} ${to.y}`}
            />
          );
        })}
      </g>

      <g className="universe-galaxies">
        {[...placed, ...undated].map((item) => (
          <GalaxyGlyph
            key={item.galaxy.meme_id}
            item={item}
            oneYear={oneYear}
            sprite={sprites[item.galaxy.meme_id]}
            future={item.galaxy.u !== null && item.x > cursorX + 0.5}
            onOpen={onOpenGalaxy}
          />
        ))}
      </g>

      {/* The time cursor. Dragging it asks "what existed by this day?"; the answer is
          counted from the evidence, and its date is the last real one it passed. */}
      <g
        ref={handle}
        className={`time-cursor${cursor === null ? " is-rest" : ""}`}
        role="slider"
        tabIndex={0}
        aria-label="时间游标：拖动或用方向键，查看截至某一天已经出现的梗"
        aria-valuemin={0}
        aria-valuemax={placed.length}
        aria-valuenow={born.length}
        aria-valuetext={`截至 ${latest ?? "起点"}，已有 ${born.length} 个梗`}
        onPointerDown={(event) => {
          event.stopPropagation();
          (event.currentTarget as SVGGElement).setPointerCapture(event.pointerId);
          const x = toUser(event.clientX);
          if (x !== null) setCursor(snap(x));
        }}
        onPointerMove={(event) => {
          if (!(event.currentTarget as SVGGElement).hasPointerCapture(event.pointerId)) return;
          const x = toUser(event.clientX);
          if (x !== null) setCursor(snap(x));
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowRight" || event.key === "ArrowUp") step(1);
          else if (event.key === "ArrowLeft" || event.key === "ArrowDown") step(-1);
          else if (event.key === "Home") setCursor(AXIS_X0);
          else if (event.key === "End") setCursor(null);
          else return;
          event.preventDefault();
        }}
      >
        <line className="time-cursor-line" x1={cursorX} y1={y0 + 10} x2={cursorX} y2={AXIS_Y + 12} />
        <rect className="time-cursor-hit" x={cursorX - 16} y={AXIS_Y - 26} width={32} height={52} />
        <path
          className="time-cursor-knob"
          d={`M ${cursorX} ${AXIS_Y - 11} L ${cursorX + 9} ${AXIS_Y} L ${cursorX} ${AXIS_Y + 11} L ${
            cursorX - 9
          } ${AXIS_Y} Z`}
        />
        <text className="time-cursor-readout" x={cursorX} y={y0 - 2} textAnchor="middle">
          {cursor === null
            ? `拖动游标回看 · 共 ${placed.length} 个梗`
            : `截至 ${latest ? drawDate(latest, oneYear) : "起点"} · ${born.length} 个梗`}
        </text>
      </g>
    </>
  );
}

function GalaxyGlyph({
  item,
  oneYear,
  sprite,
  future,
  onOpen,
}: {
  item: PlacedGalaxy;
  oneYear: boolean;
  sprite?: string;
  future: boolean;
  onOpen: (galaxy: Galaxy) => void;
}) {
  const { galaxy, x, y, radius, stacked, row } = item;
  const short = clip(galaxy.name, NAME_LIMIT);
  const art = radius * 3.4;
  return (
    <g
      className={`galaxy${stacked ? " is-stacked" : ""}${future ? " is-future" : ""}`}
      role="button"
      tabIndex={0}
      aria-label={`${galaxy.name}，出现于 ${
        galaxy.emergence.date ?? "无日期"
      }，${galaxy.stars.length} 颗星。打开星系。`}
      data-meme-id={galaxy.meme_id}
      style={
        {
          "--ignite": `${Math.round(120 + (galaxy.u ?? 1.05) * SWEEP_MS)}ms`,
        } as React.CSSProperties
      }
      onClick={() => onOpen(galaxy)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(galaxy);
        }
      }}
    >
      <circle className="galaxy-hit" cx={x} cy={y} r={Math.max(radius + 14, 26)} />
      <circle className="galaxy-body" cx={x} cy={y} r={radius} data-stars={galaxy.stars.length} />
      {sprite && (
        <image
          className="galaxy-art"
          href={sprite}
          x={x - art / 2}
          y={y - art / 2}
          width={art}
          height={art}
        />
      )}
      {stacked && (
        <text className="galaxy-lane" x={x + radius * 0.9} y={y - radius * 0.7} textAnchor="middle">
          {row + 1}
        </text>
      )}
      <text className="galaxy-name" x={x} y={y + radius + 22} textAnchor="middle">
        {short}
      </text>
      <text className="galaxy-count" x={x} y={y + radius + 38} textAnchor="middle">
        {galaxy.stars.length} 星 ·{" "}
        {galaxy.emergence.date ? drawDate(galaxy.emergence.date, oneYear) : "无日期"}
      </text>
    </g>
  );
}

/* ---------------------------------------------------------------- galaxy --- */

/** Glows are radial gradients per stage, since a gradient cannot inherit a colour
 *  from whichever element happens to reference it. */
function StageGlows() {
  const colour: Record<string, string> = {
    source: "var(--stage-source)",
    popularized_by: "var(--stage-popular)",
    derivative: "var(--stage-derivative)",
    derived_meme: "var(--stage-derived)",
  };
  return (
    <defs>
      {STAGES.map((stage) => (
        <radialGradient id={`glow-${stage}`} key={stage}>
          <stop offset="0" style={{ stopColor: colour[stage], stopOpacity: 0.85 }} />
          <stop offset="0.28" style={{ stopColor: colour[stage], stopOpacity: 0.32 }} />
          <stop offset="1" style={{ stopColor: colour[stage], stopOpacity: 0 }} />
        </radialGradient>
      ))}
      <marker
        id="arm-arrow"
        viewBox="0 0 10 10"
        refX="6"
        refY="5"
        markerWidth="7"
        markerHeight="7"
        orient="auto-start-reverse"
      >
        <path d="M 0 1 L 8 5 L 0 9" className="arm-arrow" />
      </marker>
    </defs>
  );
}

/** Dust drifting outward along the arms: time flowing from early to late. */
function Motes({ memeId }: { memeId: string }) {
  const motes = useMemo(() => {
    const random = seeded(hashSeed(`${memeId}:motes`));
    return [0, 1].flatMap((arm) =>
      Array.from({ length: 22 }, (_, index) => {
        const duration = 15 + random() * 9;
        return {
          key: `${arm}-${index}`,
          path: armPath(arm, -0.08, 1.06, 60),
          duration,
          begin: -random() * duration,
          size: 0.9 + random() * 1.3,
          lateral: (random() - 0.5) * 22,
        };
      }),
    );
  }, [memeId]);
  return (
    <g className="motes" aria-hidden="true">
      {motes.map((mote) => (
        <circle
          key={mote.key}
          className="mote"
          opacity={0}
          r={mote.size}
          cx={0}
          cy={mote.lateral * 0.3}
        >
          <animateMotion
            path={mote.path}
            dur={`${mote.duration}s`}
            begin={`${mote.begin}s`}
            repeatCount="indefinite"
            rotate="auto"
          />
          <animate
            attributeName="opacity"
            values="0;0.85;0.85;0"
            keyTimes="0;0.12;0.82;1"
            dur={`${mote.duration}s`}
            begin={`${mote.begin}s`}
            repeatCount="indefinite"
          />
        </circle>
      ))}
    </g>
  );
}

export function GalaxyGraph({
  galaxy,
  activeStarId,
  onSelectStar,
  onHoverStar,
  labelScale = 1,
  still = false,
}: {
  galaxy: Galaxy;
  activeStarId: string | null;
  onSelectStar: (star: Star) => void;
  onHoverStar: (starId: string | null) => void;
  /** How much the stylesheet enlarges the picture's text; used to space labels. */
  labelScale?: number;
  /** A still picture (the meme page's thumbnail): no focus stops, no drifting dust. */
  still?: boolean;
}) {
  const placed = placeStars(galaxy.stars);
  const { cx, cy, rIn, rOut, rUndated, width, height } = GALAXY_VIEW;
  const hasUndated = galaxy.stars.some((star) => star.t === null);
  const reduced = useReducedMotion();
  const [dust, setDust] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    let made: string | null = null;
    setDust(null);
    void renderGalaxyDust(galaxy).then((url) => {
      made = url;
      if (active) setDust(url);
      else if (url) URL.revokeObjectURL(url);
    });
    return () => {
      active = false;
      if (made) URL.revokeObjectURL(made);
    };
  }, [galaxy]);

  /* Whether the year can be dropped is decided from this galaxy's own dates, since
     it is this picture the reader compares: 2021 to 2026 must say so. */
  const oneYear = allInOneYear([
    ...galaxy.stars.map((star) => star.date),
    ...galaxy.ticks.map((tick) => tick.date),
    ...galaxy.bands.flatMap((band) => [band.date_from, band.date_to]),
  ]);
  /* Every evidence star carries a label. Milestones and the open star carry their
     name and date; every other star carries its date. Labels sit outward from the
     core on the star's own side, try the inward side when that is taken, and a date
     label yields only when both would collide - the list view, the rail and the star
     panel still carry every date. Sizes are estimated in viewBox units, already
     multiplied by the same scale the stylesheet applies to the text. */
  const k = labelScale;
  const boxes: { x0: number; x1: number; y0: number; y1: number }[] = [];
  const hits = (box: { x0: number; x1: number; y0: number; y1: number }) =>
    boxes.some((o) => box.x0 < o.x1 && box.x1 > o.x0 && box.y0 < o.y1 && box.y1 > o.y0);
  const priority = (item: (typeof placed)[number]) =>
    item.star.id === activeStarId ? 0 : item.star.milestone ? 1 : 2;
  const labels = [...placed]
    .sort((a, b) => priority(a) - priority(b) || a.index - b.index)
    .flatMap((item) => {
      const named = priority(item) < 2;
      const dateText = item.star.date ? drawDate(item.star.date, oneYear) : "无日期";
      const name = named ? clip(item.star.label, 14) : "";
      const width =
        (name ? name.length * 16 * k + 8 * k : 0) + dateText.length * 13 * 0.56 * k;
      const height = 18 * k;
      const dx = item.x - cx;
      const dy = item.y - cy;
      const distance = Math.hypot(dx, dy) || 1;
      for (const side of [1, -1]) {
        const push = side * (20 + 4 * k);
        const x = item.x + (dx / distance) * push;
        const y = item.y + (dy / distance) * push + 5 * k;
        const anchor = (dx >= 0) === side > 0 ? "start" : "end";
        const box = anchor === "start"
          ? { x0: x, x1: x + width, y0: y - height, y1: y + 4 }
          : { x0: x - width, x1: x, y0: y - height, y1: y + 4 };
        if (!hits(box) || named) {
          boxes.push(box);
          return [{
            key: item.star.id,
            text: name,
            date: dateText,
            x,
            y,
            anchor: anchor as "start" | "end",
            stage: item.star.stage,
            active: item.star.id === activeStarId,
            named,
          }];
        }
      }
      return [];
    });
  return (
    <>
      <StageGlows />
      {dust && (
        <image className="galaxy-dust" href={dust} x={0} y={0} width={width} height={height} />
      )}
      <g className="galaxy-static">
        {/* Orbits at the dated ticks: radius is time, so a star's orbit is its date. */}
        {galaxy.ticks.map((tick) => (
          <circle
            key={`${tick.t}-${tick.date}`}
            cx={cx}
            cy={cy}
            r={radiusAt(tick.t)}
            className="tick-ring"
          />
        ))}
        {/* The arms as faint rails, with the direction of time drawn on them. */}
        {[0, 1].map((arm) => (
          <path key={arm} className="arm-rail" d={armPath(arm, 0, 1)} markerEnd="url(#arm-arrow)" />
        ))}
        {/* Quiet periods as dark lanes across the arms: cut out of the radius, but the
            label still carries the true number of days, since the drawn lane does not. */}
        {galaxy.bands.map((band) => {
          const outer = radiusAt(band.start);
          const inner = radiusAt(band.end);
          return (
            <g className="quiet-band galaxy-band" key={`${band.start}-${band.end}`}>
              <path className="band-annulus" d={annulus(cx, cy, outer, inner)} />
              <circle className="band-edge" cx={cx} cy={cy} r={outer} />
              <circle className="band-edge" cx={cx} cy={cy} r={inner} />
              <line className="band-spoke" x1={cx - outer} y1={cy} x2={cx - inner} y2={cy} />
            </g>
          );
        })}
        {/* The radial scale: time runs outward, and says so. */}
        <line className="time-axis radial" x1={cx + rIn} y1={cy} x2={cx + rOut + 26} y2={cy} />
        <path className="axis-arrow" d={`M ${cx + rOut + 26} ${cy} l -13 -6 l 0 12 Z`} />
        <text className="axis-direction radial" x={cx + rIn + 6} y={cy - 10}>
          早 →
        </text>
        <text className="axis-direction radial" x={cx + rOut - 18} y={cy - 10}>
          晚
        </text>
        {galaxy.bands.map((band, index) => {
          const inner = radiusAt(band.end);
          const right = Math.min(cx - inner - 6, cx - 120);
          const left = right - 118;
          /* Bands can share almost the same radius, so their captions are stacked
             upwards to the left of the centre, innermost first. */
          const stack = galaxy.bands.length - index;
          const y = cy - 146 - stack * 55;
          const dates = `${drawDate(band.date_from, oneYear)} → ${drawDate(band.date_to, oneYear)}`;
          return (
            <g className="band-caption" key={`caption-${band.start}-${band.end}`}>
              <line className="tick-leader" x1={cx - inner} y1={cy} x2={right} y2={y + 7} />
              <rect className="band-caption-bg" x={left} y={y - 16} width={right - left + 8} height={39} rx={4} />
              <text className="band-label" x={right} y={y} textAnchor="end">
                {bandLabel(band.days)}
              </text>
              <text className="band-dates" x={right} y={y + 18} textAnchor="end">
                {dates}
              </text>
            </g>
          );
        })}
        {hasUndated && (
          <g className="undated-ring">
            <circle cx={cx} cy={cy} r={rUndated} fill="none" className="undated-rule" />
            <text x={cx} y={cy - rUndated - 8} textAnchor="middle" className="undated-label">
              无日期 · 有证据，未定日
            </text>
          </g>
        )}
      </g>
      {!reduced && !still && <Motes memeId={galaxy.meme_id} />}
      <g className="galaxy-stars">
        {placed.map((item) => (
          <StarGlyph
            key={item.star.id}
            star={item.star}
            x={item.x}
            y={item.y}
            active={item.star.id === activeStarId}
            onSelect={onSelectStar}
            onHover={onHoverStar}
            inert={still}
          />
        ))}
      </g>
      <g className="star-labels" aria-hidden="true">
        {labels.map((label) => (
          <text
            key={label.key}
            className={`star-label stage-${label.stage}${label.active ? " is-active" : ""}${
              label.named ? "" : " date-only"
            }`}
            x={label.x}
            y={label.y}
            textAnchor={label.anchor}
          >
            {label.text}
            <tspan className="star-label-date" dx={label.text ? 6 : 0}>
              {label.date}
            </tspan>
          </text>
        ))}
      </g>
    </>
  );
}

/** A full ring of `outer` minus a full ring of `inner`, as one even-odd path. */
function annulus(cx: number, cy: number, outer: number, inner: number): string {
  const ring = (r: number, sweep: number) =>
    `M ${cx - r} ${cy} A ${r} ${r} 0 1 ${sweep} ${cx + r} ${cy} A ${r} ${r} 0 1 ${sweep} ${cx - r} ${cy} Z`;
  return `${ring(outer, 1)} ${ring(inner, 0)}`;
}
