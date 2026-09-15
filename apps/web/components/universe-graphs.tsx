"use client";
import type { Galaxy, Star, Universe } from "@/lib/api";
import { StarGlyph } from "./star-glyph";
import {
  AXIS_X0,
  AXIS_X1,
  AXIS_Y,
  GALAXY_VIEW,
  NAME_LIMIT,
  UNIVERSE_VIEW,
  UNDATED_X,
  allInOneYear,
  axisEnd,
  bandLabel,
  drawDate,
  layoutUniverse,
  placeStars,
  polar,
  radiusAt,
  type PlacedGalaxy,
} from "./universe-layout";

/** SVG text has no auto-truncation, and a galaxy name may run off the canvas. */
function clip(text: string, characters: number): string {
  return text.length > characters
    ? `${text.slice(0, characters - 1)}…`
    : text;
}

/* --------------------------------------------------------------- universe -- */

export function UniverseGraph({
  universe,
  onOpenGalaxy,
}: {
  universe: Universe;
  onOpenGalaxy: (galaxy: Galaxy) => void;
}) {
  const { placed, undated } = layoutUniverse(universe);
  const byId = new Map(placed.map((item) => [item.galaxy.meme_id, item]));
  const end = axisEnd(universe);
  /* Whether the year can be dropped is a property of this picture, decided from its
     own dates: one calendar year may say 08-20, a span of years may not. */
  const oneYear = allInOneYear([
    ...universe.galaxies.map((galaxy) => galaxy.emergence.date),
    ...universe.axis.ticks.map((tick) => tick.date),
  ]);
  /* The bands run from above the axis down to just past it and stop: a galaxy is
     never inside a quiet period - that is what the band means - so the rectangles
     must not reach the glyphs. They stop well above the first lane. */
  const y0 = AXIS_Y - 330;
  const y1 = AXIS_Y + 40;

  return (
    <>
      <g className="universe-static">
        {/* Quiet periods: a fixed width that lies about the duration, hence the label. */}
        {universe.axis.bands.map((band) => (
          <g className="quiet-band axis-band" key={`${band.date_from}-${band.date_to}`}>
            <rect
              x={AXIS_X0 + band.start * (AXIS_X1 - AXIS_X0)}
              y={y0}
              width={Math.max(
                (band.end - band.start) * (AXIS_X1 - AXIS_X0),
                3,
              )}
              height={y1 - y0}
            />
            <text
              x={
                AXIS_X0 +
                ((band.start + band.end) / 2) * (AXIS_X1 - AXIS_X0)
              }
              y={y0 - 14}
              textAnchor="middle"
            >
              {bandLabel(band.days)}
            </text>
          </g>
        ))}
        {/* The time axis itself, with its direction stated rather than implied. */}
        <line className="time-axis" x1={AXIS_X0 - 40} y1={AXIS_Y} x2={end + 30} y2={AXIS_Y} />
        <path
          className="axis-arrow"
          d={`M ${end + 30} ${AXIS_Y} l -13 -6 l 0 12 Z`}
        />
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
        {undated.length > 0 && (
          <g className="undated-column">
            <line
              x1={UNDATED_X}
              y1={AXIS_Y - 230}
              x2={UNDATED_X}
              y2={AXIS_Y + 130}
              className="undated-rule"
            />
            <text x={UNDATED_X} y={AXIS_Y - 250} textAnchor="middle">
              无日期
            </text>
            <text
              x={UNDATED_X}
              y={AXIS_Y - 226}
              textAnchor="middle"
              className="undated-note"
            >
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
            onOpen={onOpenGalaxy}
          />
        ))}
      </g>
    </>
  );
}

function GalaxyGlyph({
  item,
  oneYear,
  onOpen,
}: {
  item: PlacedGalaxy;
  oneYear: boolean;
  onOpen: (galaxy: Galaxy) => void;
}) {
  const { galaxy, x, y, radius, stacked, row } = item;
  const short = clip(galaxy.name, NAME_LIMIT);
  return (
    <g
      className={`galaxy${stacked ? " is-stacked" : ""}`}
      role="button"
      tabIndex={0}
      aria-label={`${galaxy.name}，出现于 ${
        galaxy.emergence.date ?? "无日期"
      }，${galaxy.stars.length} 颗星。打开星系。`}
      data-meme-id={galaxy.meme_id}
      onClick={() => onOpen(galaxy)}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          onOpen(galaxy);
        }
      }}
    >
      <circle className="galaxy-hit" cx={x} cy={y} r={Math.max(radius + 12, 24)} />
      <circle
        className="galaxy-body"
        cx={x}
        cy={y}
        r={radius}
        data-stars={galaxy.stars.length}
      />
      {stacked && (
        <text className="galaxy-lane" x={x} y={y + 4} textAnchor="middle">
          {row + 1}
        </text>
      )}
      <text className="galaxy-name" x={x} y={y + radius + 20} textAnchor="middle">
        {short}
      </text>
      <text
        className="galaxy-count"
        x={x}
        y={y + radius + 35}
        textAnchor="middle"
      >
        {galaxy.stars.length} 星 ·{" "}
        {galaxy.emergence.date
          ? drawDate(galaxy.emergence.date, oneYear)
          : "无日期"}
      </text>
    </g>
  );
}

/* ---------------------------------------------------------------- galaxy --- */

export function GalaxyGraph({
  galaxy,
  activeStarId,
  onSelectStar,
  onHoverStar,
}: {
  galaxy: Galaxy;
  activeStarId: string | null;
  onSelectStar: (star: Star) => void;
  onHoverStar: (starId: string | null) => void;
}) {
  const placed = placeStars(galaxy.stars);
  const { cx, cy, rIn, rOut, rUndated } = GALAXY_VIEW;
  const hasUndated = galaxy.stars.some((star) => star.t === null);
  /* Whether the year can be dropped is decided from this galaxy's own dates, since
     it is this picture the reader compares: 2021 to 2026 must say so. */
  const oneYear = allInOneYear([
    ...galaxy.stars.map((star) => star.date),
    ...galaxy.ticks.map((tick) => tick.date),
    ...galaxy.bands.flatMap((band) => [band.date_from, band.date_to]),
  ]);
  /**
   * Each date sits just inside its own ring, on a diagonal away from the radial axis
   * and the 早/晚 labels, drawn with its outer end against the ring it names. Where
   * two rings are too close for both labels to be legible - the early sources of a
   * galaxy like 闹吃VS古振兴 are days apart - the inner one is dropped; the list view
   * and the star panel still carry every date.
   */
  const ringLabels: { key: string; date: string; x: number; y: number }[] = [];
  const DIAGONAL = Math.PI / 4;
  const cos = Math.cos(DIAGONAL);
  const sin = Math.sin(DIAGONAL);
  /* How far apart two labelled rings must be. A month-based axis puts a galaxy's
     earliest sources days apart, and at that density the radius step can be smaller
     than one label is tall, so the requirement grows with the number of dates. */
  const step = Math.max(18, Math.floor(170 / Math.max(galaxy.ticks.length - 1, 1)));
  let lastRadius = -Infinity;
  for (const tick of [...galaxy.ticks].sort((a, b) => a.t - b.t)) {
    const radius = radiusAt(tick.t) - 10;
    if (radius - lastRadius < step) continue;
    lastRadius = radius;
    ringLabels.push({
      key: `${tick.t}-${tick.date}`,
      date: drawDate(tick.date, oneYear),
      x: cx + radius * cos,
      y: cy - radius * sin,
    });
  }
  return (
    <>
      <g className="galaxy-static">
        {galaxy.ticks.map((tick) => {
          const radius = radiusAt(tick.t);
          const [ex, ey] = polar(radius, 0);
          const [ix, iy] = polar(radius, Math.PI);
          return (
            <g className="galaxy-tick" key={`${tick.t}-${tick.date}`}>
              <circle
                cx={cx}
                cy={cy}
                r={radius}
                fill="none"
                className="tick-ring"
              />
              <line className="tick-spoke" x1={ix} y1={iy} x2={ex} y2={ey} />
            </g>
          );
        })}
        {/* Quiet periods as dashed annuli: cut out of the radius, but the label
            still carries the true number of days, since the drawn ring does not. */}
        {galaxy.bands.map((band) => {
          const outer = radiusAt(band.start);
          const inner = radiusAt(band.end);
          return (
            <g
              className="quiet-band galaxy-band"
              key={`${band.start}-${band.end}`}
            >
              <path className="band-annulus" d={annulus(cx, cy, outer, inner)} />
              <line
                className="band-spoke"
                x1={cx - outer}
                y1={cy}
                x2={cx - inner}
                y2={cy}
              />
            </g>
          );
        })}
        {/* The radial axis: time runs outward, and says so. */}
        <line
          className="time-axis radial"
          x1={cx + rIn}
          y1={cy}
          x2={cx + rOut + 26}
          y2={cy}
        />
        <path
          className="axis-arrow"
          d={`M ${cx + rOut + 26} ${cy} l -13 -6 l 0 12 Z`}
        />
        <text className="axis-direction radial" x={cx + rIn - 210} y={cy - 10}>
          早 →
        </text>
        <text className="axis-direction radial" x={cx + rOut - 130} y={cy - 10}>
          晚
        </text>
        {/* Every label after every shape it could be drawn under, which is why the
            dates and the band captions come last. */}
        {ringLabels.map(({ key, date, x, y }) => (
          <text className="tick-date" key={key} x={x} y={y} textAnchor="end">
            {date}
          </text>
        ))}
        {galaxy.bands.map((band, index) => {
          const outer = radiusAt(band.start);
          const inner = radiusAt(band.end);
          const right = Math.min(cx - inner - 6, cx - 120);
          const left = right - 118;
          /* Bands can share almost the same radius, so their captions are stacked
             upwards to the left of the centre, innermost first. The stack starts
             high enough to clear the dates that run inside the rings diagonally. */
          const stack = galaxy.bands.length - index;
          const y = cy - 146 - stack * 55;
          const dates = `${drawDate(band.date_from, oneYear)} → ${drawDate(
            band.date_to,
            oneYear,
          )}`;
          return (
            <g className="band-caption" key={`caption-${band.start}-${band.end}`}>
              <line
                className="tick-leader"
                x1={cx - inner}
                y1={cy}
                x2={right}
                y2={y + 7}
              />
              <rect
                className="band-caption-bg"
                x={left}
                y={y - 16}
                width={right - left + 8}
                height={39}
              />
              <text className="band-label" x={right} y={y} textAnchor="end">
                {bandLabel(band.days)}
              </text>
              <text className="band-dates" x={right} y={y + 18} textAnchor="end">
                {dates}
              </text>
            </g>
          );
        })}
        <circle className="centre" cx={cx} cy={cy} r={3} />
        {hasUndated && (
          <g className="undated-ring">
            <circle
              cx={cx}
              cy={cy}
              r={rUndated}
              fill="none"
              className="undated-rule"
            />
            <text
              x={cx}
              y={cy - rUndated - 8}
              textAnchor="middle"
              className="undated-label"
            >
              无日期 · 有证据，未定日
            </text>
          </g>
        )}
      </g>
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
          />
        ))}
      </g>
    </>
  );
}

/** A full ring of `outer` minus a full ring of `inner`, as one even-odd path. */
function annulus(
  cx: number,
  cy: number,
  outer: number,
  inner: number,
): string {
  const ring = (r: number, sweep: number) =>
    `M ${cx - r} ${cy} A ${r} ${r} 0 1 ${sweep} ${cx + r} ${cy} A ${r} ${r} 0 1 ${sweep} ${cx - r} ${cy} Z`;
  return `${ring(outer, 1)} ${ring(inner, 0)}`;
}
