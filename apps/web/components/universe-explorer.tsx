"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { flushSync } from "react-dom";
import { useReducedMotion, withTransition } from "@/lib/motion";
import { api, type Galaxy, type Star, type Universe } from "@/lib/api";
import { GalaxyGraph, UniverseGraph } from "./universe-graphs";
import { GalaxyList, UniverseList } from "./universe-list";
import { MilestoneRail } from "./milestone-rail";
import { StarPanel } from "./star-panel";
import {
  GALAXY_VIEW,
  UNIVERSE_VIEW,
  layoutUniverse,
  STAGE_STYLE,
  STAGES,
} from "./universe-layout";

/** Below this width the map becomes a sky wider than the screen, scrolled natively. */
const NARROW = "(max-width: 760px)";
/** Pan and zoom limits. The picture is drawn in its own coordinate system, so the
 *  same factor means something very different on the wide universe axis and on a
 *  galaxy: the universe caps below 1 so a reader can take in the whole span. */
const MIN_ZOOM = 0.6;
const MAX_ZOOM = 14;
const MAX_UNIVERSE_ZOOM = 4;
/** How much of the picture one wheel notch takes up. */
const WHEEL_STEP = 0.0018;

type View = { k: number; x: number; y: number };
const IDENTITY: View = { k: 1, x: 0, y: 0 };
const asTransform = (view: View) =>
  `translate(${view.x},${view.y}) scale(${view.k})`;

export function UniverseExplorer({ initialMemeId }: { initialMemeId: string }) {
  const router = useRouter();
  const [universe, setUniverse] = useState<Universe | null>(null);
  const [error, setError] = useState("");
  const [reloads, setReloads] = useState(0);
  const [memeId, setMemeId] = useState(initialMemeId);
  const [listView, setListView] = useState(false);
  const [activeStar, setActiveStar] = useState<Star | null>(null);
  const [hoveredStar, setHoveredStar] = useState<string | null>(null);
  const [view, setView] = useState<View>(IDENTITY);
  const [pill, setPill] = useState("");
  const svgRef = useRef<SVGSVGElement | null>(null);
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [labelScale, setLabelScale] = useState(1);
  const reduced = useReducedMotion();

  /* /v1/universe is one fast request and is deliberately uncached server side. */
  useEffect(() => {
    let active = true;
    setError("");
    api<Universe>("/v1/universe")
      .then((data) => {
        if (active) setUniverse(data);
      })
      .catch((e: Error) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [reloads]);

  const galaxy = useMemo(
    () => universe?.galaxies.find((g) => g.meme_id === memeId) ?? null,
    [universe, memeId],
  );
  const universeHeight = useMemo(
    () => (universe ? layoutUniverse(universe).height : UNIVERSE_VIEW.height),
    [universe],
  );

  /* Back and forward change the query string without remounting this component. */
  useEffect(() => {
    const sync = () =>
      setMemeId(new URLSearchParams(window.location.search).get("meme") ?? "");
    window.addEventListener("popstate", sync);
    return () => window.removeEventListener("popstate", sync);
  }, []);

  const navigate = useCallback(
    (id: string) => {
      setMemeId(id);
      setActiveStar(null);
      router.push(
        id ? `/universe?meme=${encodeURIComponent(id)}` : "/universe",
        { scroll: false },
      );
    },
    [router],
  );

  /* Each view is a fresh picture, so a transform from the last one would point at
     nothing. The React state is the only writer of the group's transform. */
  useEffect(() => {
    setView(IDENTITY);
  }, [memeId, listView]);

  /* Text in the picture is drawn in viewBox units, so it shrinks with the picture.
     Labels are scaled back up by however much the picture is shrunk, enough to stay
     readable (about 11px and up) on any screen. */
  useEffect(() => {
    const node = svgRef.current;
    if (!node || listView) return;
    if (!galaxy) {
      setLabelScale(1);
      return;
    }
    const width = GALAXY_VIEW.width;
    const height = GALAXY_VIEW.height;
    const observer = new ResizeObserver(() => {
      /* The picture is fitted inside the element ("meet"), so on a wide screen it is
         limited by height, not width: the real shrink is the larger of the two. */
      const box = node.getBoundingClientRect();
      const shrink = Math.max(
        width / (box.width || width),
        height / (box.height || height),
      );
      setLabelScale(Math.max(1, shrink * 0.86));
    });
    observer.observe(node);
    return () => observer.disconnect();
  }, [galaxy, listView, universe]);

  /* A phone opens the scrolled sky where it matters: the newest memes, or the core. */
  useEffect(() => {
    const stage = stageRef.current;
    if (!stage || listView || !window.matchMedia(NARROW).matches) return;
    const frame = window.requestAnimationFrame(() => {
      if (galaxy) {
        stage.scrollLeft = (stage.scrollWidth - stage.clientWidth) / 2;
        return;
      }
      /* The newest galaxy sits near the right edge, with the ones before it in view. */
      const box = stage.getBoundingClientRect();
      const right = Math.max(
        ...[
          ...stage.querySelectorAll(
            ".galaxy, .axis-direction, .time-cursor-readout",
          ),
        ].map(
          (node) =>
            node.getBoundingClientRect().right - box.left + stage.scrollLeft,
        ),
        0,
      );
      stage.scrollLeft = Math.max(right - stage.clientWidth + 16, 0);
    });
    return () => window.cancelAnimationFrame(frame);
  }, [galaxy, listView, universe]);

  /* Pan and zoom belong to the reader, and both are kept in state so that a
     re-render cannot leave the picture and the gesture disagreeing. Pointer capture
     is deliberately not used: capturing on the svg retargets the pointerup, and the
     browser then sends the click to the svg instead of to the glyph that was hit. */
  useEffect(() => {
    const node = svgRef.current;
    if (!node || listView) return;
    /* On a phone the picture scrolls natively instead: a custom drag would fight the
       browser's own horizontal scroll, and pinch still zooms the page. */
    if (window.matchMedia(NARROW).matches) return;
    const pointers = new Map<number, { x: number; y: number }>();
    let pinch: { distance: number; centre: [number, number] } | null = null;

    const local = (event: { clientX: number; clientY: number }) => {
      const rect = node.getBoundingClientRect();
      return [event.clientX - rect.left, event.clientY - rect.top] as const;
    };
    const zoomAt = (factor: number, [cx, cy]: readonly [number, number]) => {
      setView((current) => {
        const ceiling = galaxy ? MAX_ZOOM : MAX_UNIVERSE_ZOOM;
        const k = Math.min(Math.max(current.k * factor, MIN_ZOOM), ceiling);
        const ratio = k / current.k;
        return {
          k,
          x: cx - ratio * (cx - current.x),
          y: cy - ratio * (cy - current.y),
        };
      });
    };
    const onWheel = (event: WheelEvent) => {
      /* A plain wheel belongs to the page: the picture is taller than the viewport,
         and the rail and the legend under it are how the picture gets explained.
         Ctrl or Cmd means zoom, which is also what a trackpad pinch sends. */
      if (!event.ctrlKey && !event.metaKey) return;
      event.preventDefault();
      /* Firefox reports lines rather than pixels, so one notch would barely move. */
      const delta = event.deltaMode === 1 ? event.deltaY * 16 : event.deltaY;
      zoomAt(Math.exp(-delta * WHEEL_STEP), local(event));
    };
    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
      /* The time cursor is dragged, not the picture under it. */
      if ((event.target as Element | null)?.closest(".time-cursor")) return;
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pointers.size === 2) {
        const [a, b] = [...pointers.values()];
        pinch = {
          distance: Math.hypot(a.x - b.x, a.y - b.y),
          centre: [(a.x + b.x) / 2, (a.y + b.y) / 2],
        };
      }
    };
    const onPointerMove = (event: PointerEvent) => {
      const previous = pointers.get(event.pointerId);
      if (!previous) return;
      if (pointers.size === 1) {
        setView((current) => ({
          ...current,
          x: current.x + (event.clientX - previous.x),
          y: current.y + (event.clientY - previous.y),
        }));
      }
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
      if (pointers.size === 2 && pinch) {
        const [a, b] = [...pointers.values()];
        const distance = Math.hypot(a.x - b.x, a.y - b.y);
        if (pinch.distance > 0) {
          const rect = node.getBoundingClientRect();
          zoomAt(distance / pinch.distance, [
            pinch.centre[0] - rect.left,
            pinch.centre[1] - rect.top,
          ]);
        }
        pinch.distance = distance;
      }
    };
    const onPointerUp = (event: PointerEvent) => {
      pointers.delete(event.pointerId);
      if (pointers.size < 2) pinch = null;
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    node.addEventListener("pointerdown", onPointerDown);
    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp);
    window.addEventListener("pointercancel", onPointerUp);
    return () => {
      node.removeEventListener("wheel", onWheel);
      node.removeEventListener("pointerdown", onPointerDown);
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
      window.removeEventListener("pointercancel", onPointerUp);
    };
  }, [listView, universe, galaxy]);

  /* Entering a galaxy is a flight, not a page swap: the universe falls away and the
     galaxy grows in, where the browser can animate between the two states. */
  const openGalaxy = useCallback(
    (next: Galaxy) => {
      withTransition(() => flushSync(() => navigate(next.meme_id)), reduced);
      setPill(`已进入星系：${next.name}`);
    },
    [navigate, reduced],
  );

  /** A star whose kind is `meme` is another galaxy, and opens that one. */
  const openStar = useCallback(
    (star: Star) => {
      if (star.kind === "meme" && star.target_id) {
        const target = star.target_id;
        withTransition(() => flushSync(() => navigate(target)), reduced);
        setPill("已进入另一个梗的星系");
        return;
      }
      setActiveStar(star);
    },
    [navigate, reduced],
  );

  useEffect(() => {
    if (!pill) return;
    const timer = window.setTimeout(() => setPill(""), 2600);
    return () => window.clearTimeout(timer);
  }, [pill]);

  /* Tab moves through the glyphs. Escape closes the panel, then zooms out. */
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      if (activeStar) {
        setActiveStar(null);
        return;
      }
      if (memeId) navigate("");
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeStar, memeId, navigate]);

  if (error) {
    return (
      <div className="error" role="alert">
        星图读取失败：{error}
        <button
          className="text-button"
          onClick={() => setReloads((n) => n + 1)}
        >
          重试
        </button>
      </div>
    );
  }
  if (!universe) {
    return (
      <p className="loading-line" role="status">
        正在读取星图…
      </p>
    );
  }
  if (universe.galaxies.length === 0) {
    return (
      <div className="empty-state">
        <h3>星图还是空的</h3>
        <p>目前没有已发布的梗。第一条记录通过审核后，这里会出现第一颗星。</p>
      </div>
    );
  }

  return (
    <div className="universe-explorer">
      <div className="universe-toolbar">
        <div className="universe-crumbs">
          <button
            type="button"
            className="text-button"
            onClick={() => navigate("")}
            disabled={!memeId}
          >
            宇宙视图
          </button>
          {galaxy && (
            <>
              <span aria-hidden="true">/</span>
              <strong>{galaxy.name}</strong>
            </>
          )}
        </div>
        <div className="universe-controls">
          <button
            type="button"
            className="button outline small"
            aria-pressed={listView}
            onClick={() => setListView((value) => !value)}
          >
            {listView ? "星图视图" : "列表视图"}
          </button>
          <button
            type="button"
            className="button outline small"
            onClick={() => {
              setView(IDENTITY);
              stageRef.current?.scrollTo({
                top: 0,
                left: 0,
                behavior: "instant",
              });
            }}
          >
            重置视图
          </button>
        </div>
      </div>
      <p className="visually-hidden" role="status">
        {pill}
      </p>

      {listView ? (
        galaxy ? (
          <GalaxyList
            galaxy={galaxy}
            activeStarId={activeStar?.id ?? null}
            onSelectStar={openStar}
          />
        ) : (
          <UniverseList universe={universe} onOpenGalaxy={openGalaxy} />
        )
      ) : (
        <>
          <p className="swipe-hint">
            {galaxy
              ? "左右滑动，看整个星系。"
              : "滑动星图探索；时间从左往右，同日记录向下排列。"}
          </p>
          <div
            ref={stageRef}
            className={`universe-stage${galaxy ? " is-galaxy" : " is-universe"}`}
            role="region"
            aria-label="可滚动星图"
            tabIndex={0}
          >
            <svg
              ref={svgRef}
              key={galaxy ? galaxy.meme_id : "universe"}
              className="universe-svg"
              viewBox={`0 0 ${
                galaxy ? GALAXY_VIEW.width : UNIVERSE_VIEW.width
              } ${galaxy ? GALAXY_VIEW.height : universeHeight}`}
              preserveAspectRatio="xMidYMid meet"
              style={{ "--label-scale": labelScale } as React.CSSProperties}
              aria-label={
                galaxy
                  ? `${galaxy.name} 的星系图。半径是时间，越靠外越晚。`
                  : "宇宙视图。横轴是时间，每个点是一个梗。"
              }
            >
              <g className="zoom-surface" transform={asTransform(view)}>
                {galaxy ? (
                  <GalaxyGraph
                    galaxy={galaxy}
                    activeStarId={activeStar?.id ?? hoveredStar}
                    onSelectStar={openStar}
                    onHoverStar={setHoveredStar}
                    labelScale={labelScale}
                  />
                ) : (
                  <UniverseGraph
                    universe={universe}
                    onOpenGalaxy={openGalaxy}
                  />
                )}
              </g>
            </svg>
          </div>
        </>
      )}

      {!listView && galaxy && (
        <MilestoneRail
          galaxy={galaxy}
          activeId={hoveredStar ?? activeStar?.id ?? null}
          onHover={setHoveredStar}
          onSelect={openStar}
        />
      )}

      <Legend galaxy={galaxy} />

      {!listView && (
        <p className="muted universe-hint">
          Ctrl + 滚轮缩放，拖动平移。
          {galaxy
            ? " 离核心越远越晚；沿旋臂向外流动的微光，就是时间的方向。"
            : " 点一个梗进入它的星系；拖动时间轴上的菱形游标，回看某一天已有哪些梗。"}
        </p>
      )}

      {activeStar && (
        <StarPanel star={activeStar} onClose={() => setActiveStar(null)} />
      )}
    </div>
  );
}

/** One legend key, drawn with the same parts as the star it explains. */
function LegendStar({
  stage,
  milestone,
}: {
  stage: (typeof STAGES)[number];
  milestone?: boolean;
}) {
  const style = STAGE_STYLE[stage];
  const c = 13;
  const m = 6.5;
  return (
    <svg
      width="26"
      height="26"
      viewBox="0 0 26 26"
      aria-hidden="true"
      className={`legend-star stage-${stage}`}
    >
      <circle cx={c} cy={c} r={11} className="legend-glow" />
      {milestone && (
        <path
          d={`M 1 ${c} L 25 ${c} M ${c} 1 L ${c} 25`}
          className="legend-spikes"
        />
      )}
      {style.shape === "diamond" && (
        <path
          d={`M ${c} ${c - m * 1.2} L ${c + m * 1.2} ${c} L ${c} ${c + m * 1.2} L ${c - m * 1.2} ${c} Z`}
          className="legend-mark"
        />
      )}
      {style.shape === "square" && (
        <rect
          x={c - m}
          y={c - m}
          width={m * 2}
          height={m * 2}
          rx={1.2}
          className="legend-mark"
        />
      )}
      {style.shape === "circle" && (
        <circle cx={c} cy={c} r={m} className="legend-mark" />
      )}
      {style.shape === "ring" && (
        <circle cx={c} cy={c} r={m} className="legend-mark ring" />
      )}
      <circle cx={c} cy={c} r={2.4} className="legend-core" />
    </svg>
  );
}

function Legend({ galaxy }: { galaxy: Galaxy | null }) {
  return (
    <section className="universe-legend" aria-label="图例">
      <h2>图例</h2>
      <ul>
        {STAGES.map((stage) => (
          <li key={stage} data-stage={stage}>
            <LegendStar stage={stage} />
            <span>
              {STAGE_STYLE[stage].label}
              <small>{STAGE_STYLE[stage].shapeNote}</small>
            </span>
          </li>
        ))}
        <li data-key="milestone">
          <LegendStar stage="source" milestone />
          <span>十字星芒：里程碑（该阶段最早的一条证据）</span>
        </li>
        <li data-key="no-evidence">
          <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
            <rect
              x="3"
              y="6"
              width="20"
              height="14"
              rx="3"
              className="legend-absent"
            />
          </svg>
          <span>虚线空槽：无证据（该阶段一条证据都没有，见里程碑轨道）</span>
        </li>
        <li data-key="no-date">
          <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
            <circle cx="13" cy="13" r="9" className="legend-absent" />
          </svg>
          <span>虚线圆环：无日期（有证据，未定日，画在最外圈）</span>
        </li>
        <li data-key="decoration">
          <svg width="26" height="26" viewBox="0 0 26 26" aria-hidden="true">
            <circle cx="7" cy="9" r="1" className="legend-dust" />
            <circle cx="15" cy="15" r="1.4" className="legend-dust" />
            <circle cx="20" cy="7" r="0.8" className="legend-dust" />
            <circle cx="10" cy="19" r="0.9" className="legend-dust" />
          </svg>
          <span>无色微光：星尘装饰，不是证据，不可点击</span>
        </li>
      </ul>
      {galaxy && galaxy.ticks.length > 0 && (
        <p className="muted">
          这个星系的时间跨度：{galaxy.ticks[0].date} →{" "}
          {galaxy.ticks[galaxy.ticks.length - 1].date}
        </p>
      )}
    </section>
  );
}
