"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import type { Universe } from "@/lib/api";
import { galaxySprite } from "@/lib/galaxy-art";
import { Icon } from "./icons";

/** A reader-controlled tour of the real catalogue. The orbital artwork is
 * decoration; only the linked galaxy contains evidence and a dated timeline. */
export function SkyBand({ universe }: { universe: Universe | null }) {
  const galaxies = useMemo(
    () =>
      [...(universe?.galaxies ?? [])].sort(
        (a, b) =>
          b.stars.length - a.stars.length || a.meme_id.localeCompare(b.meme_id),
      ),
    [universe],
  );
  const [focus, setFocus] = useState(0);
  const [art, setArt] = useState<{ id: string; url: string } | null>(null);
  const selected = galaxies[focus % (galaxies.length || 1)];

  useEffect(() => {
    if (!selected) return;
    let active = true;
    void galaxySprite(selected.meme_id).then((url) => {
      if (active && url) setArt({ id: selected.meme_id, url });
    });
    return () => {
      active = false;
    };
  }, [selected]);

  return (
    <section className="atlas-feature" aria-label="馆藏巡览">
      <div className="atlas-topline">
        <span className="eyebrow">THE MEMORY ATLAS</span>
        <Link href="/universe">
          探索完整星图 <Icon name="arrow" size={14} />
        </Link>
      </div>
      <div className="atlas-plate">
        <svg viewBox="0 0 600 390" className="atlas-art" aria-hidden="true">
          <g className="atlas-orbits">
            <ellipse
              cx="300"
              cy="197"
              rx="235"
              ry="136"
              transform="rotate(-22 300 197)"
            />
            <ellipse
              cx="300"
              cy="197"
              rx="235"
              ry="136"
              transform="rotate(22 300 197)"
            />
            <circle cx="300" cy="197" r="166" />
            <path d="M 300 18 V 43 M 300 351 V 376 M 49 197 H 74 M 526 197 H 551" />
          </g>
          <g className="atlas-orbit-marks">
            {Array.from({ length: 48 }, (_, i) => {
              const angle = (i / 48) * Math.PI * 2;
              // Round SVG coordinates: server and browser trig can differ in the
              // last decimal place, which would otherwise warn during hydration.
              const x = (300 + Math.cos(angle) * 166).toFixed(3);
              const y = (197 + Math.sin(angle) * 166).toFixed(3);
              return <circle key={i} cx={x} cy={y} r={i % 6 === 0 ? 2 : 0.8} />;
            })}
          </g>
          {selected && art?.id === selected.meme_id && (
            <image
              key={art.id}
              className="atlas-nebula"
              href={art.url}
              x="132"
              y="29"
              width="336"
              height="336"
            />
          )}
          <g className="atlas-coordinate">
            <path d="M 412 119 L 464 68 H 547 M 187 273 L 136 321 H 55" />
            <circle cx="412" cy="119" r="3" />
            <circle cx="187" cy="273" r="3" />
            <text x="547" y="59" textAnchor="end">
              CULTURE / CONTEXT
            </text>
            <text x="55" y="341">
              TRACES OF MEMORY
            </text>
          </g>
        </svg>
        <span className="atlas-plate-note">星云为装饰 · 证据见星系</span>
      </div>
      {selected ? (
        <div className="atlas-caption">
          <div className="atlas-caption-heading">
            <div>
              <p className="eyebrow">
                馆藏巡览{" "}
                <span>
                  {" "}
                  / {String((focus % galaxies.length) + 1).padStart(
                    2,
                    "0",
                  )} — {String(galaxies.length).padStart(2, "0")}
                </span>
              </p>
              <h2>
                <Link
                  href={`/universe?meme=${encodeURIComponent(selected.meme_id)}`}
                >
                  {selected.name} <Icon name="arrow" size={20} />
                </Link>
              </h2>
            </div>
            <div className="atlas-pagination">
              <button
                aria-label="上一条馆藏"
                disabled={galaxies.length < 2}
                onClick={() =>
                  setFocus((i) => (i + galaxies.length - 1) % galaxies.length)
                }
              >
                ←
              </button>
              <button
                aria-label="下一条馆藏"
                disabled={galaxies.length < 2}
                onClick={() => setFocus((i) => (i + 1) % galaxies.length)}
              >
                →
              </button>
            </div>
          </div>
          <p className="atlas-definition">{selected.definition}</p>
          <div className="atlas-meta">
            <span>{selected.stars.length} 颗证据星</span>
            <span>最早记录 {selected.emergence.date ?? "日期未确认"}</span>
          </div>
        </div>
      ) : (
        <div className="atlas-caption atlas-unavailable">
          <h2>每一段记忆，都有一片星空。</h2>
          <Link href="/universe">
            打开梗的星图 <Icon name="arrow" size={16} />
          </Link>
        </div>
      )}
    </section>
  );
}
