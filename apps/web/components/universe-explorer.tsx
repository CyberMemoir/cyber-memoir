"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { api, type Galaxy, type Star, type Universe } from "@/lib/api";
import { GalaxyGraph, UniverseGraph } from "./universe-graphs";
import { GalaxyList, UniverseList } from "./universe-list";
import { MilestoneRail } from "./milestone-rail";
import { StarPanel } from "./star-panel";
import { GALAXY_VIEW, STAGE_STYLE, STAGES } from "./universe-layout";

const UNIVERSE_BOX = { width: 1680, height: 1060 };
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

  /* Pan and zoom belong to the reader, and both are kept in state so that a
     re-render cannot leave the picture and the gesture disagreeing. Pointer capture
     is deliberately not used: capturing on the svg retargets the pointerup, and the
     browser then sends the click to the svg instead of to the glyph that was hit. */
  useEffect(() => {
    const node = svgRef.current;
    if (!node || listView) return;
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
      event.preventDefault();
      zoomAt(Math.exp(-event.deltaY * WHEEL_STEP), local(event));
    };
    const onPointerDown = (event: PointerEvent) => {
      if (event.button !== 0) return;
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

  const openGalaxy = useCallback(
    (next: Galaxy) => {
      navigate(next.meme_id);
      setPill(`已进入星系：${next.name}`);
    },
    [navigate],
  );

  /** A star whose kind is `meme` is another galaxy, and opens that one. */
  const openStar = useCallback(
    (star: Star) => {
      if (star.kind === "meme" && star.target_id) {
        navigate(star.target_id);
        setPill("已进入另一个梗的星系");
        return;
      }
      setActiveStar(star);
    },
    [navigate],
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
        <button className="text-button" onClick={() => setReloads((n) => n + 1)}>
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
            onClick={() => setView(IDENTITY)}
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
        <div className={`universe-stage${galaxy ? " is-galaxy" : ""}`}>
          <svg
            ref={svgRef}
            className="universe-svg"
            viewBox={`0 0 ${
              galaxy ? GALAXY_VIEW.width : UNIVERSE_BOX.width
            } ${galaxy ? GALAXY_VIEW.height : UNIVERSE_BOX.height}`}
            preserveAspectRatio="xMidYMid meet"
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
                />
              ) : (
                <UniverseGraph universe={universe} onOpenGalaxy={openGalaxy} />
              )}
            </g>
          </svg>
        </div>
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

      {!galaxy && !listView && (
        <p className="muted universe-hint">
          滚动缩放，拖动平移。点一个梗进入它的星系。
        </p>
      )}

      {activeStar && (
        <StarPanel star={activeStar} onClose={() => setActiveStar(null)} />
      )}
    </div>
  );
}

function Legend({ galaxy }: { galaxy: Galaxy | null }) {
  return (
    <section className="universe-legend" aria-label="图例">
      <h2>图例</h2>
      <ul>
        {STAGES.map((stage) => {
          const style = STAGE_STYLE[stage];
          return (
            <li key={stage} data-stage={stage}>
              <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
                {style.shape === "diamond" && (
                  <path d="M 11 3 L 19 11 L 11 19 L 3 11 Z" fill={style.color} />
                )}
                {style.shape === "square" && (
                  <rect x="4" y="4" width="14" height="14" fill={style.color} />
                )}
                {style.shape === "circle" && (
                  <circle cx="11" cy="11" r="5" fill={style.color} />
                )}
                {style.shape === "ring" && (
                  <circle
                    cx="11"
                    cy="11"
                    r="6"
                    fill="none"
                    stroke={style.color}
                    strokeWidth="3"
                  />
                )}
              </svg>
              <span>{style.label}</span>
            </li>
          );
        })}
        <li>
          <svg width="22" height="22" viewBox="0 0 22 22" aria-hidden="true">
            <circle
              cx="11"
              cy="11"
              r="8"
              fill="none"
              stroke="var(--muted)"
              strokeWidth="1"
              strokeDasharray="2 3"
            />
          </svg>
          <span>虚线表示无证据或无日期；实心外环表示里程碑</span>
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
