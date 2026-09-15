import type { Star } from "@/lib/api";
import { STAGE_STYLE, type Stage } from "./universe-layout";

/**
 * One star glyph. Stage decides colour, size and shape; `milestone` adds a halo;
 * the hovered star gets an outer ring. Nothing here reads `t`, `at` or `date`.
 */
export function StarGlyph({
  star,
  x,
  y,
  active,
  scale = 1,
  onSelect,
  onHover,
}: {
  star: Star;
  x: number;
  y: number;
  active?: boolean;
  scale?: number;
  onSelect: (star: Star) => void;
  onHover?: (starId: string | null) => void;
}) {
  const style = STAGE_STYLE[star.stage as Stage] ?? STAGE_STYLE.derivative;
  const size = style.size * scale * (star.milestone ? 1.5 : 1);
  const hit = Math.max(size + 9, 13);
  const body = () => {
    switch (style.shape) {
      case "diamond":
        return (
          <path
            d={`M ${x} ${y - size} L ${x + size} ${y} L ${x} ${y + size} L ${
              x - size
            } ${y} Z`}
            fill={style.color}
          />
        );
      case "square":
        return (
          <rect
            x={x - size}
            y={y - size}
            width={size * 2}
            height={size * 2}
            rx={1.5}
            fill={style.color}
          />
        );
      case "ring":
        return (
          <circle
            cx={x}
            cy={y}
            r={size}
            fill="none"
            stroke={style.color}
            strokeWidth={Math.max(2.4, size * 0.5)}
          />
        );
      default:
        return <circle cx={x} cy={y} r={size} fill={style.color} />;
    }
  };
  return (
    <g
      className={`star stage-${star.stage}${star.milestone ? " milestone" : ""}${
        active ? " is-active" : ""
      }`}
      role="button"
      tabIndex={0}
      aria-label={`${star.milestone ? "里程碑：" : ""}${ariaFor(star)}`}
      data-star-id={star.id}
      data-kind={star.kind}
      onClick={(event) => {
        event.stopPropagation();
        onSelect(star);
      }}
      onKeyDown={(event) => {
        if (event.key === "Enter" || event.key === " ") {
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
      <circle cx={x} cy={y} r={hit} fill="transparent" />
      {star.milestone && (
        <circle
          className="star-halo"
          cx={x}
          cy={y}
          r={size + 7}
          fill="none"
          stroke={style.color}
          strokeWidth={1.2}
        />
      )}
      {active && (
        <circle
          className="star-active-ring"
          cx={x}
          cy={y}
          r={size + 11}
          fill="none"
          stroke={style.color}
          strokeWidth={1.4}
        />
      )}
      {body()}
      {star.kind === "meme" && (
        <circle
          cx={x}
          cy={y}
          r={Math.max(size * 0.28, 1.6)}
          fill="var(--bg)"
          stroke={style.color}
          strokeWidth={1}
        />
      )}
    </g>
  );
}

function ariaFor(star: Star): string {
  const label = STAGE_STYLE[star.stage as Stage]?.label ?? star.stage;
  return [label, star.date ?? "无日期", star.label].join("，");
}
