import type { Galaxy } from "@/lib/api";
import {
  STAGE_STYLE,
  allInOneYear,
  bandLabel,
  drawDate,
  orderedStars,
  type Stage,
} from "./universe-layout";

/*
 * A meme's history as one instrument: its evidence stars strung along a time rail,
 * each in its role colour, placed by the same compressed `t` the galaxy uses for
 * radius. Quiet periods are the dim spans between, labelled with their true length,
 * since the drawn width does not carry it. Undated evidence is not placed on a rail
 * that is time; the list beneath still carries it.
 */
const X0 = 60;
const X1 = 940;
const AXIS = 86;

export function TimeStrip({ galaxy }: { galaxy: Galaxy }) {
  const stars = orderedStars(galaxy.stars).filter((star) => star.t !== null);
  if (!stars.length) return null;
  const oneYear = allInOneYear(stars.map((star) => star.date));
  const at = (t: number) => X0 + t * (X1 - X0);
  /* Dates alternate above and below the rail when neighbours would collide. */
  const lastByRow = [-Infinity, -Infinity];
  const labelled = stars.map((star) => {
    const x = at(star.t ?? 0);
    const row = x - lastByRow[0] >= 96 ? 0 : x - lastByRow[1] >= 96 ? 1 : -1;
    if (row >= 0) lastByRow[row] = x;
    return { star, x, row };
  });
  return (
    <div className="time-strip">
      <svg
        viewBox="0 0 1000 170"
        className="time-strip-svg"
        role="img"
        aria-label={`${galaxy.name} 的传播时间轴：${stars.length} 条有日期的证据，从早到晚排列。`}
      >
        {galaxy.bands.map((band) => {
          const lo = Math.min(band.start, band.end);
          const hi = Math.max(band.start, band.end);
          return (
            <g key={`${band.start}-${band.end}`} className="strip-quiet">
              <rect
                x={at(lo)}
                y={AXIS - 22}
                width={Math.max(at(hi) - at(lo), 2)}
                height={44}
              />
              <text x={(at(lo) + at(hi)) / 2} y={AXIS - 30} textAnchor="middle">
                {bandLabel(band.days)}
              </text>
            </g>
          );
        })}
        <line
          className="strip-axis"
          x1={X0 - 30}
          y1={AXIS}
          x2={X1 + 30}
          y2={AXIS}
        />
        <path
          className="strip-arrow"
          d={`M ${X1 + 30} ${AXIS} l -11 -5 l 0 10 Z`}
        />
        <text className="strip-direction" x={X0 - 30} y={AXIS - 30}>
          早
        </text>
        <text
          className="strip-direction"
          x={X1 + 30}
          y={AXIS - 30}
          textAnchor="end"
        >
          晚 →
        </text>
        {labelled.map(({ star, x, row }) => {
          const colour =
            STAGE_STYLE[star.stage as Stage]?.color ?? "var(--ink-2)";
          return (
            <g
              key={star.id}
              className={`strip-star${star.milestone ? " milestone" : ""}`}
            >
              <title>{`${STAGE_STYLE[star.stage as Stage]?.label ?? star.stage} · ${star.date} · ${star.label}`}</title>
              <circle
                cx={x}
                cy={AXIS}
                r={star.milestone ? 13 : 9}
                fill={colour}
                opacity={0.22}
              />
              <circle
                cx={x}
                cy={AXIS}
                r={star.milestone ? 6 : 4.5}
                fill="none"
                stroke={colour}
                strokeWidth={1.6}
              />
              <circle cx={x} cy={AXIS} r={2.2} fill="#fff" />
              {row >= 0 && (
                <text
                  x={x}
                  y={row === 0 ? AXIS + 40 : AXIS + 64}
                  textAnchor="middle"
                  className="strip-date"
                >
                  {drawDate(star.date ?? "", oneYear)}
                </text>
              )}
            </g>
          );
        })}
      </svg>
    </div>
  );
}
