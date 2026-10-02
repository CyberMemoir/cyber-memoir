import type { Galaxy, Star, Universe } from "@/lib/api";

/* ---------------------------------------------------------------------------
 * Everything geometric about the two pictures lives here, and it reads only `u`,
 * `t`, `stars`, `bands` and `ticks`. Stage never reaches this file: it decides how
 * a star looks, never where it sits. The functions are pure, so the same payload
 * draws the same picture on every load.
 * ------------------------------------------------------------------------- */

/** What a star means is decided by the API's `stage`; only its style is ours. */
export const STAGES = [
  "source",
  "popularized_by",
  "derivative",
  "derived_meme",
] as const;
export type Stage = (typeof STAGES)[number];

type StageStyle = {
  /** Interface vocabulary for the four API stage values. Not meme content. */
  label: string;
  /** Fill, drawn as a CSS value so it follows the page's colour tokens. */
  color: string;
  /** Relative weight; milestone stars grow from here, never shrink. */
  size: number;
  shape: "diamond" | "square" | "circle" | "ring";
  /** Size and shape both differ, so the stage survives a colour-blind reader. */
  shapeNote: string;
};

export const STAGE_STYLE: Record<Stage, StageStyle> = {
  source: {
    label: "素材来源",
    color: "var(--stage-source)",
    size: 7.5,
    shape: "diamond",
    shapeNote: "菱形",
  },
  popularized_by: {
    label: "走红作品",
    color: "var(--stage-popular)",
    size: 11,
    shape: "square",
    shapeNote: "方块",
  },
  derivative: {
    label: "衍生视频",
    color: "var(--stage-derivative)",
    size: 5,
    shape: "circle",
    shapeNote: "圆点",
  },
  derived_meme: {
    label: "衍生梗",
    color: "var(--stage-derived)",
    size: 9.5,
    shape: "ring",
    shapeNote: "圆环",
  },
};

export function stageLabel(stage: string): string {
  return STAGE_STYLE[stage as Stage]?.label ?? stage;
}

/**
 * The duration a band swallowed, which its drawn width does not show. A band is cut
 * out of the axis and given a fixed width, so the number is the only honest part of
 * it. Past a year the reader gets years and one decimal; under it, days.
 */
export function bandLabel(days: number): string {
  if (days >= 365) return `沉寂 ${(days / 365).toFixed(1)} 年`;
  return `沉寂 ${days} 天`;
}

/**
 * Whether one picture can drop the year from its dates. A galaxy whose stars all fell
 * in one calendar year reads better as 05-04; one that spans 2021 to 2026 does not,
 * because 08-28 → 04-29 beside "沉寂 2.7 年" would claim eight months and the label
 * would contradict it. Undated entries say nothing about a year.
 */
export function allInOneYear(years: (string | null | undefined)[]): boolean {
  const present = new Set(
    years
      .filter((value): value is string => Boolean(value))
      .map((v) => v.slice(0, 4)),
  );
  return present.size <= 1;
}

/** `2026-08-20` when the year matters, `08-20` when every date shares one year. */
export function drawDate(date: string, oneYear: boolean): string {
  return oneYear ? date.slice(5) : date;
}

/**
 * The order a galaxy's stars are drawn and listed in: dated stars by their date,
 * undated ones after them. Ties break on id so the picture cannot reshuffle, and
 * the star panel keeps the same order as the map it opens from.
 */
export function orderedStars(stars: Star[]): Star[] {
  return [...stars].sort((a, b) => {
    if ((a.t === null) !== (b.t === null)) return a.t === null ? 1 : -1;
    if (a.t !== b.t) return (a.t ?? 0) - (b.t ?? 0);
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  });
}

/** The star a milestone slot points at, or null when the stage has no evidence. */
export function milestoneStar(galaxy: Galaxy, stage: string): Star | null {
  const id = galaxy.milestones?.[stage];
  if (!id) return null;
  return galaxy.stars.find((s) => s.id === id) ?? null;
}

/* ------------------------------- universe view ---------------------------- */

export const UNIVERSE_VIEW = { width: 1680, height: 880 };

/** u = 0 must not touch the page edge, and u = 1 must not run under the
 *  无日期 column, so the axis is inset inside the viewBox. */
export const AXIS_X0 = 130;
export const AXIS_X1 = 1150;
export const AXIS_Y = 200;
/** A galaxy whose `u` is null waits in this column, outside the time axis. */
export const UNDATED_X = 1400;
/** Dated galaxies within this distance of each other share the axis position. */
const SAME_INSTANT = 0.002;
/** One lane holds a glyph, its name and its count; lanes must not collide. */
const LANE = 148;
/** The first lane clears the axis and its date labels. */
const LANE_TOP = 110;
/** Characters drawn from a name before it is clipped with an ellipsis. */
export const NAME_LIMIT = 10;

export type PlacedGalaxy = {
  galaxy: Galaxy;
  x: number;
  y: number;
  row: number;
  /** Marked when two or more galaxies share the spot, so the reader knows to look. */
  stacked: boolean;
  radius: number;
};

const isUndated = (galaxy: Galaxy) => galaxy.u === null;

/** Galaxy names are CJK, so a width estimate from the character count is close
 *  enough to keep two labels from colliding, and needs no measuring in the DOM. */
function estimatedWidth(galaxy: Galaxy): number {
  const name = galaxy.name.slice(0, NAME_LIMIT).length * 19 + 30;
  /* "10 星 · 08-20" is wider than a short name, so it can set the box width. */
  const count = galaxy.emergence.date ? 145 : 75;
  return Math.max(name, count);
}

/**
 * Group neighbours by axis position. Grouping is by near-equality rather than an
 * exact key because u is a float derived from a date, and two galaxies on the same
 * day come back with the same float.
 */
function isSameInstant(a: number, b: number): boolean {
  return Math.abs(a - b) < SAME_INSTANT;
}

/**
 * Dense periods add rows instead of reusing an occupied one. The SVG grows with
 * the layout, so labels stay readable even when many records share the same day.
 */
function chooseLane(
  taken: { left: number; right: number; row: number }[],
  span: { left: number; right: number },
): number {
  for (let row = 0; row <= taken.length; row += 1) {
    const occupied = taken.some(
      (box) =>
        box.row === row && span.left < box.right && span.right > box.left,
    );
    if (!occupied) return row;
  }
  return taken.length;
}

/** Glyph area grows with the star count, so a nine-star galaxy reads as bigger. */
function glyphRadius(galaxy: Galaxy): number {
  return Math.min(36, 15 + Math.sqrt(galaxy.stars.length) * 5);
}

export function layoutUniverse(universe: Universe): {
  placed: PlacedGalaxy[];
  undated: PlacedGalaxy[];
  height: number;
} {
  const placed: PlacedGalaxy[] = [];
  const taken: { left: number; right: number; row: number }[] = [];
  for (const galaxy of universe.galaxies
    .filter((g) => !isUndated(g))
    .sort(
      (a, b) => (a.u ?? 0) - (b.u ?? 0) || (a.meme_id < b.meme_id ? -1 : 1),
    )) {
    const x = AXIS_X0 + (galaxy.u ?? 0) * (AXIS_X1 - AXIS_X0);
    const width = estimatedWidth(galaxy);
    const span = { left: x - width / 2, right: x + width / 2 };
    const row = chooseLane(taken, span);
    const stacked = placed.some((other) =>
      isSameInstant(other.galaxy.u ?? 0, galaxy.u ?? 0),
    );
    taken.push({ ...span, row });
    placed.push({
      galaxy,
      x,
      y: AXIS_Y + LANE_TOP + row * LANE,
      row,
      stacked,
      radius: glyphRadius(galaxy),
    });
  }
  const undated = universe.galaxies
    .filter(isUndated)
    .sort((a, b) => a.meme_id.localeCompare(b.meme_id))
    .map((galaxy, index) => ({
      galaxy,
      x: UNDATED_X,
      y: AXIS_Y + 110 + index * LANE,
      row: index,
      stacked: false,
      radius: glyphRadius(galaxy),
    }));
  const height = Math.max(
    UNIVERSE_VIEW.height,
    ...[...placed, ...undated].map((item) => item.y + item.radius + 100),
  );
  return { placed, undated, height };
}

/** A faint arc from a galaxy to the one it was built on. Both ends move with the
 *  reader's pan, so a link can disappear off the edge - it is a relation, not
 *  an edge to be followed by eye. */
export function linkPath(from: PlacedGalaxy, to: PlacedGalaxy): string {
  const [x1, y1, x2, y2] = [from.x, from.y, to.x, to.y];
  const arch = Math.min(70 + Math.abs(x2 - x1) * 0.08, 160);
  const [cx, cy] = [(x1 + x2) / 2, (y1 + y2) / 2 - arch];
  return `M ${x1} ${y1} Q ${cx} ${cy} ${x2} ${y2}`;
}

/** How far the axis arrow reaches: the last tick when there is no dated galaxy. */
export function axisEnd(universe: Universe): number {
  const positions = [
    ...universe.galaxies.map((g) => g.u).filter((u): u is number => u !== null),
    ...universe.axis.ticks.map((t) => t.t),
  ];
  const furthest = positions.length ? Math.max(...positions) : 1;
  return AXIS_X0 + furthest * (AXIS_X1 - AXIS_X0);
}

/* -------------------------------- galaxy view ----------------------------- */

export const GALAXY_VIEW = {
  width: 1080,
  height: 1020,
  cx: 540,
  cy: 500,
  rIn: 190,
  rOut: 460,
  /** Undated stars sit outside R_OUT: they are evidenced, just not placed in time. */
  rUndated: 545,
};

export type PlacedStar = {
  star: Star;
  x: number;
  y: number;
  r: number;
  index: number;
};

/**
 * A meme's galaxy is a two-armed spiral whose arms are time. Radius is still time and
 * nothing else - `t = 0` sits on the inner rim, `t = 1` on the outer - and the arm
 * only decides the angle, which is itself a function of `t`. So a star's date alone
 * fixes how far out it sits, and the arm it rides adds no claim of its own.
 *
 * The arms start at the core's rim pointing up-left and wind clockwise by `turn`
 * over the whole span, so the eye can follow early to late the way a real arm reads.
 */
export const ARM = { start: -Math.PI * 0.74, turn: Math.PI * 1.25 };
/** Two stars on one arm within this much `t` of each other would overlap. */
const SAME_DATE = 0.025;
/** Sideways step, in radians, between stars that share a date on the same arm. */
const LANE_STEP = 0.075;

export function armAngle(t: number, arm: number): number {
  return ARM.start + arm * Math.PI + ARM.turn * t;
}

/**
 * Where the dust sits at a given `t`. Inside `t = 0` the arm winds into the core, so
 * the decoration is continuous; no star is ever placed there.
 */
export function dustRadius(t: number): number {
  const { rIn, rOut } = GALAXY_VIEW;
  return t >= 0 ? rIn + t * (rOut - rIn) : Math.max(rIn * (1 + t / 0.42), 0);
}

export function armPoint(t: number, arm: number, spread = 0): [number, number] {
  const { cx, cy } = GALAXY_VIEW;
  const radius = dustRadius(t);
  const angle = armAngle(t, arm) + spread;
  return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)];
}

/** The arm as an SVG path, sampled finely enough to read as a curve at any zoom. */
export function armPath(arm: number, from = 0, to = 1, steps = 72): string {
  const points: string[] = [];
  for (let step = 0; step <= steps; step += 1) {
    const [x, y] = armPoint(from + ((to - from) * step) / steps, arm);
    points.push(`${step ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)}`);
  }
  return points.join(" ");
}

export function placeStars(stars: Star[]): PlacedStar[] {
  const { cx, cy, rUndated } = GALAXY_VIEW;
  const GOLDEN = Math.PI * (3 - Math.sqrt(5));
  const onArm: { t: number; arm: number }[] = [];
  return orderedStars(stars).map((star, index) => {
    if (star.t === null || star.t === undefined) {
      /* Evidenced but undated: outside the rim, off the arms, never on time. */
      const theta = -Math.PI / 2 + index * GOLDEN + GOLDEN;
      return {
        star,
        x: cx + rUndated * Math.cos(theta),
        y: cy + rUndated * Math.sin(theta),
        r: rUndated,
        index,
      };
    }
    const t = star.t;
    const arm = index % 2;
    /* Stars sharing a date on one arm step sideways, alternating, never along it:
       moving along the arm would move them in time. */
    const crowd = onArm.filter(
      (other) => other.arm === arm && Math.abs(other.t - t) < SAME_DATE,
    ).length;
    onArm.push({ t, arm });
    const lane = crowd === 0 ? 0 : Math.ceil(crowd / 2) * (crowd % 2 ? 1 : -1);
    const radius = GALAXY_VIEW.rIn + t * (GALAXY_VIEW.rOut - GALAXY_VIEW.rIn);
    const theta = armAngle(t, arm) + lane * LANE_STEP;
    return {
      star,
      x: cx + radius * Math.cos(theta),
      y: cy + radius * Math.sin(theta),
      r: radius,
      index,
    };
  });
}

export const radiusAt = (t: number) =>
  GALAXY_VIEW.rIn + t * (GALAXY_VIEW.rOut - GALAXY_VIEW.rIn);

/** Polar helper for the ticks, the bands and the radial time axis. */
export function polar(radius: number, angle: number): [number, number] {
  return [
    GALAXY_VIEW.cx + radius * Math.cos(angle),
    GALAXY_VIEW.cy + radius * Math.sin(angle),
  ];
}

/** Angle 0 in SVG is due east; the labels run up the east side of the rings. */
export const LABEL_ANGLE = -Math.PI / 2;
