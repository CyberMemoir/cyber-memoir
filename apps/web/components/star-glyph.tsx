import type { Star } from "@/lib/api";
import { STAGE_STYLE, type Stage } from "./universe-layout";

/**
 * One evidence star. What it looks like is the only thing stage decides:
 *
 * - a white-hot core inside a glow in the role's colour - colour marks evidence, and
 *   nothing decorative on the map carries one;
 * - the role's shape drawn around the core as a thin catalogue mark, always present,
 *   so the stage survives a colour-blind reader and a greyscale print;
 * - diffraction spikes on milestones only, the way the brightest stars in a
 *   telescope image carry them, so "first of its stage" reads at a glance.
 *
 * Nothing here reads `t`, `at` or `date` except the ignition delay, which is how
 * the stars light up in the order they happened.
 */
export function StarGlyph({
  star,
  x,
  y,
  active,
  scale = 1,
  inert = false,
  onSelect,
  onHover,
}: {
  star: Star;
  x: number;
  y: number;
  active?: boolean;
  scale?: number;
  /** Drawn only: a thumbnail's stars are not focus stops or buttons. */
  inert?: boolean;
  onSelect: (star: Star) => void;
  onHover?: (starId: string | null) => void;
}) {
  const style = STAGE_STYLE[star.stage as Stage] ?? STAGE_STYLE.derivative;
  const size = style.size * scale * (star.milestone ? 1.35 : 1);
  const hit = Math.max(size + 10, 15);
  const mark = size + 3.5;
  const shape = () => {
    switch (style.shape) {
      case "diamond":
        return (
          <path
            className="star-mark"
            d={`M ${x} ${y - mark * 1.2} L ${x + mark * 1.2} ${y} L ${x} ${y + mark * 1.2} L ${
              x - mark * 1.2
            } ${y} Z`}
          />
        );
      case "square":
        return (
          <rect
            className="star-mark"
            x={x - mark}
            y={y - mark}
            width={mark * 2}
            height={mark * 2}
            rx={1.5}
          />
        );
      case "ring":
        return <circle className="star-mark ring" cx={x} cy={y} r={mark} />;
      default:
        return <circle className="star-mark" cx={x} cy={y} r={mark} />;
    }
  };
  const spike = size * 4.2;
  return (
    <g
      className={`star stage-${star.stage}${star.milestone ? " milestone" : ""}${
        active ? " is-active" : ""
      }${star.t === null ? " is-undated" : ""}`}
      role={inert ? undefined : "button"}
      tabIndex={inert ? undefined : 0}
      aria-hidden={inert || undefined}
      aria-label={inert ? undefined : `${star.milestone ? "里程碑：" : ""}${ariaFor(star)}`}
      data-star-id={star.id}
      data-kind={star.kind}
      style={
        {
          "--stage": style.color,
          "--ignite": `${Math.round(260 + (star.t ?? 1.08) * 1500)}ms`,
        } as React.CSSProperties
      }
      onClick={(event) => {
        if (inert) return;
        event.stopPropagation();
        onSelect(star);
      }}
      onKeyDown={(event) => {
        if (!inert && (event.key === "Enter" || event.key === " ")) {
          event.preventDefault();
          event.stopPropagation();
          onSelect?.(star);
        }
      }}
      onMouseEnter={() => onHover?.(star.id)}
      onMouseLeave={() => onHover?.(null)}
      onFocus={() => onHover?.(star.id)}
      onBlur={() => onHover?.(null)}
    >
      <circle className="star-hit" cx={x} cy={y} r={hit} />
      <circle className="star-glow" cx={x} cy={y} r={size * 2.9} />
      {star.milestone && (
        <path
          className="star-spikes"
          d={`M ${x - spike} ${y} L ${x + spike} ${y} M ${x} ${y - spike} L ${x} ${y + spike}`}
        />
      )}
      {star.milestone && <circle className="star-halo" cx={x} cy={y} r={mark + 6} />}
      {active && <circle className="star-active-ring" cx={x} cy={y} r={mark + 11} />}
      {shape()}
      <circle className="star-core" cx={x} cy={y} r={Math.max(size * 0.46, 2.2)} />
    </g>
  );
}

function ariaFor(star: Star): string {
  const label = STAGE_STYLE[star.stage as Stage]?.label ?? star.stage;
  return [label, star.date ?? "无日期", star.label].join("，");
}
