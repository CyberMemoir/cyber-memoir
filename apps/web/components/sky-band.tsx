"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import type { Galaxy, Universe } from "@/lib/api";
import { galaxySprite } from "@/lib/galaxy-art";
import { useReducedMotion } from "@/lib/motion";

/*
 * The home page's sky: every published meme as a small galaxy strung along an arc,
 * the ecliptic of this dome, in date order - the same `u` the star map uses, so the
 * arc is a timeline and says so at its ends. A projector pointer tours the galaxies
 * the way a planetarium presenter walks an audience round the sky, and hands the
 * reader the one thing a curious visitor wants: what the meme is, how much evidence
 * it has, and a way in.
 */

type Frame = {
  width: number;
  height: number;
  x0: number;
  x1: number;
  base: number;
  lift: number;
};
const WIDE: Frame = {
  width: 1600,
  height: 420,
  x0: 110,
  x1: 1490,
  base: 334,
  lift: 196,
};
const NARROW: Frame = {
  width: 900,
  height: 640,
  x0: 70,
  x1: 830,
  base: 520,
  lift: 330,
};
const TOUR_MS = 5600;

type Placed = {
  galaxy: Galaxy;
  x: number;
  y: number;
  size: number;
  order: number;
};

function place(galaxies: Galaxy[], frame: Frame): Placed[] {
  const dated = galaxies
    .filter((galaxy) => galaxy.u !== null)
    .sort(
      (a, b) => (a.u ?? 0) - (b.u ?? 0) || (a.meme_id < b.meme_id ? -1 : 1),
    );
  const taken: { x: number; y: number; size: number }[] = [];
  return dated.map((galaxy, order) => {
    const along = galaxy.u ?? 0;
    const x = frame.x0 + along * (frame.x1 - frame.x0);
    const arc =
      frame.base - Math.sin(Math.PI * (0.08 + along * 0.84)) * frame.lift;
    const size = 40 + Math.sqrt(galaxy.stars.length) * 16;
    /* Galaxies close in time would overlap on the arc; they fan out above and below
       it, nearest slot first, and never move sideways, since sideways is time. */
    let y = arc;
    for (let lane = 1; lane < 9; lane += 1) {
      const clash = taken.some(
        (other) =>
          Math.hypot(other.x - x, other.y - y) < (other.size + size) * 0.52,
      );
      if (!clash) break;
      y = arc + Math.ceil(lane / 2) * (lane % 2 ? -1 : 1) * size * 0.78;
    }
    taken.push({ x, y, size });
    return { galaxy, x, y, size, order };
  });
}

function arcY(frame: Frame, along: number): number {
  return frame.base - Math.sin(Math.PI * (0.08 + along * 0.84)) * frame.lift;
}

function arcPath(frame: Frame): string {
  const points: string[] = [];
  for (let step = 0; step <= 60; step += 1) {
    const along = step / 60;
    const x = frame.x0 + along * (frame.x1 - frame.x0);
    const y =
      frame.base - Math.sin(Math.PI * (0.08 + along * 0.84)) * frame.lift;
    points.push(`${step ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)}`);
  }
  return points.join(" ");
}

export function SkyBand({ universe }: { universe: Universe | null }) {
  const wrapper = useRef<HTMLDivElement | null>(null);
  const [frame, setFrame] = useState<Frame>(WIDE);
  const [sprites, setSprites] = useState<Record<string, string>>({});
  const [focus, setFocus] = useState(0);
  const [pausedUntil, setPausedUntil] = useState(0);
  const [captionHeight, setCaptionHeight] = useState(0);
  const reduced = useReducedMotion();

  /* The caption row has to reserve space for the caption, which is absolutely
     positioned so it can slide sideways without the page reflowing. A fixed height
     guesses, and a definition that wraps one line further than the guess prints over
     the headline below. So the row is told what the tallest caption so far needed:
     measured, never shrinking, so the tour cannot make the page jump either. */
  const measure = useCallback((node: HTMLAnchorElement) => {
    const observer = new ResizeObserver(([entry]) => {
      const height = entry.borderBoxSize?.[0]?.blockSize ?? node.offsetHeight;
      setCaptionHeight((tallest) => Math.max(tallest, Math.ceil(height)));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const node = wrapper.current;
    if (!node) return;
    const observer = new ResizeObserver(([entry]) => {
      setFrame((current) => {
        const next = entry.contentRect.width < 720 ? NARROW : WIDE;
        if (next !== current) setCaptionHeight(0);
        return next;
      });
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  const placed = useMemo(
    () => (universe ? place(universe.galaxies, frame) : []),
    [universe, frame],
  );

  /* The tour opens on the galaxy with the most evidence: the fullest picture. */
  useEffect(() => {
    if (!placed.length) return;
    let richest = 0;
    placed.forEach((item, index) => {
      if (item.galaxy.stars.length > placed[richest].galaxy.stars.length)
        richest = index;
    });
    setFocus(richest);
  }, [placed]);

  useEffect(() => {
    let active = true;
    for (const item of placed) {
      void galaxySprite(item.galaxy.meme_id).then((url) => {
        if (active && url) {
          setSprites((current) => ({ ...current, [item.galaxy.meme_id]: url }));
        }
      });
    }
    return () => {
      active = false;
    };
  }, [placed]);

  useEffect(() => {
    if (reduced || placed.length < 2) return;
    const timer = window.setInterval(() => {
      if (document.hidden || Date.now() < pausedUntil) return;
      setFocus((current) => (current + 1) % placed.length);
    }, TOUR_MS);
    return () => window.clearInterval(timer);
  }, [reduced, placed.length, pausedUntil]);

  const target = placed[focus];
  const first = placed[0]?.galaxy.emergence.date;
  const last = placed[placed.length - 1]?.galaxy.emergence.date;
  const pct = (value: number, of: number) => `${(value / of) * 100}%`;
  const hold = (index: number) => {
    setFocus(index);
    setPausedUntil(Date.now() + 14000);
  };

  return (
    <div
      ref={wrapper}
      className={`sky-band${placed.length ? " is-ready" : ""}`}
    >
      <svg
        className="sky-band-svg"
        viewBox={`0 0 ${frame.width} ${frame.height}`}
        style={{ aspectRatio: `${frame.width} / ${frame.height}` }}
        role="group"
        aria-label="已发布的梗，按首次出现的日期排列在天空中。选择一个，进入它的星系。"
      >
        <path className="ecliptic" d={arcPath(frame)} />
        {first && (
          <text
            className="ecliptic-end"
            fontSize={frame === NARROW ? 24 : 15}
            x={frame.x0 - 30}
            y={arcY(frame, 0) + 64}
            textAnchor="start"
          >
            {first}
          </text>
        )}
        {last && (
          <text
            className="ecliptic-end"
            fontSize={frame === NARROW ? 24 : 15}
            x={frame.x1 + 30}
            y={arcY(frame, 1) + 64}
            textAnchor="end"
          >
            {last} · 时间 →
          </text>
        )}
        {placed.map((item, index) => {
          const url = sprites[item.galaxy.meme_id];
          return (
            <Link
              key={item.galaxy.meme_id}
              href={`/universe?meme=${encodeURIComponent(item.galaxy.meme_id)}`}
              className={`sky-galaxy${index === focus ? " is-focus" : ""}`}
              aria-label={`${item.galaxy.name}，${item.galaxy.stars.length} 颗证据星，首次出现于 ${item.galaxy.emergence.date ?? "无日期"}。进入星系。`}
              onMouseEnter={() => hold(index)}
              onFocus={() => hold(index)}
              style={{ "--order": item.order } as React.CSSProperties}
            >
              <circle
                className="sky-galaxy-hit"
                cx={item.x}
                cy={item.y}
                r={item.size * 0.55}
              />
              <circle
                className="sky-galaxy-glow"
                cx={item.x}
                cy={item.y}
                r={item.size * 0.34}
              />
              {url && (
                <image
                  href={url}
                  x={item.x - item.size / 2}
                  y={item.y - item.size / 2}
                  width={item.size}
                  height={item.size}
                />
              )}
            </Link>
          );
        })}
        {target && (
          <line
            key={`beam-${target.galaxy.meme_id}`}
            className="projector-beam"
            x1={target.x}
            y1={target.y + target.size * 0.42}
            x2={target.x}
            y2={frame.height}
          />
        )}
        {target && (
          <g
            className="projector-pointer"
            style={{
              transform: `translate(${target.x}px, ${target.y - target.size * 0.5}px)`,
            }}
            aria-hidden="true"
          >
            <path d="M 0 -6 L -7 -20 L -2.2 -18.4 L -2.2 -38 L 2.2 -38 L 2.2 -18.4 L 7 -20 Z" />
          </g>
        )}
      </svg>
      {/* The caption hangs below the sky, never over it, on the beam dropped from the
          galaxy being shown. */}
      <div
        className="sky-caption-row"
        style={captionHeight ? { height: `${captionHeight}px` } : undefined}
      >
        {target && (
          <Link
            href={`/universe?meme=${encodeURIComponent(target.galaxy.meme_id)}`}
            className="sky-caption"
            ref={measure}
            style={{
              left: `clamp(8px, calc(${pct(target.x, frame.width)} - var(--caption-w) / 2), calc(100% - var(--caption-w) - 8px))`,
            }}
            aria-hidden="true"
            tabIndex={-1}
            key={target.galaxy.meme_id}
          >
            <span className="sky-caption-name">{target.galaxy.name}</span>
            <span className="sky-caption-meta">
              {target.galaxy.stars.length} 颗证据星 · 首次出现{" "}
              {target.galaxy.emergence.date ?? "无日期"}
            </span>
            {target.galaxy.definition && (
              <span className="sky-caption-def">
                {target.galaxy.definition.length > 44
                  ? `${target.galaxy.definition.slice(0, 43)}…`
                  : target.galaxy.definition}
              </span>
            )}
            <span className="sky-caption-go">进入星系 →</span>
          </Link>
        )}
      </div>
    </div>
  );
}
