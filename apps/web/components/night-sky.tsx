"use client";
import { useEffect, useRef, useState } from "react";
import { gaussian, seeded } from "@/lib/seeded";
import { useReducedMotion } from "@/lib/motion";

/*
 * The dome every page sits under. It is drawn once into a square canvas as wide as
 * the viewport's diagonal and turned by a CSS transform, the way a planetarium's
 * projector turns the sky: one static texture, moved by the compositor, no per-frame
 * drawing. The brightest stars twinkle as DOM dots with CSS animations, and a meteor
 * crosses now and then. All of it is decoration: colourless, behind the content,
 * hidden from assistive technology, and absent under reduced motion except the
 * still sky itself.
 */

type Bright = {
  x: number;
  y: number;
  size: number;
  delay: number;
  duration: number;
};

const SEED = 20260919;

function paintSky(canvas: HTMLCanvasElement, side: number): Bright[] {
  const ratio = Math.min(window.devicePixelRatio || 1, 1.5);
  canvas.width = Math.round(side * ratio);
  canvas.height = Math.round(side * ratio);
  const context = canvas.getContext("2d");
  if (!context) return [];
  context.scale(ratio, ratio);
  const random = seeded(SEED);

  /* The Milky Way: a band crossing the dome, a diffuse glow first, then its stars,
     then dark rifts carved back out of it. */
  const band = { angle: -0.52, width: side * 0.13 };
  const [ux, uy] = [Math.cos(band.angle), Math.sin(band.angle)];
  const [nx, ny] = [-uy, ux];
  const centre = side / 2;
  context.globalCompositeOperation = "lighter";
  for (let index = 0; index < 26; index += 1) {
    const along = (random() - 0.5) * side * 1.1;
    const across = gaussian(random) * band.width * 0.35;
    const x = centre + ux * along + nx * across;
    const y = centre + uy * along + ny * across;
    const radius = band.width * (0.5 + random() * 0.9);
    const glow = context.createRadialGradient(x, y, 0, x, y, radius);
    const warm = random() < 0.4;
    glow.addColorStop(
      0,
      warm ? "rgba(214,208,198,0.045)" : "rgba(200,202,208,0.045)",
    );
    glow.addColorStop(1, "rgba(200,202,208,0)");
    context.fillStyle = glow;
    context.fillRect(x - radius, y - radius, radius * 2, radius * 2);
  }
  const bandStars = Math.round((side * side) / 520);
  for (let index = 0; index < bandStars; index += 1) {
    const along = (random() - 0.5) * side * 1.2;
    const across = gaussian(random) * band.width * 0.42;
    const x = centre + ux * along + nx * across;
    const y = centre + uy * along + ny * across;
    const alpha = 0.1 + random() * 0.32;
    context.fillStyle = `rgba(234,235,239,${alpha})`;
    const size = 0.35 + random() * 0.55;
    context.fillRect(x, y, size, size);
  }
  context.globalCompositeOperation = "destination-out";
  for (let index = 0; index < 90; index += 1) {
    const along = (random() - 0.5) * side;
    const across = gaussian(random) * band.width * 0.12 + band.width * 0.05;
    const x = centre + ux * along + nx * across;
    const y = centre + uy * along + ny * across;
    const radius = 18 + random() * 60;
    const rift = context.createRadialGradient(x, y, 0, x, y, radius);
    rift.addColorStop(0, "rgba(0,0,0,0.22)");
    rift.addColorStop(1, "rgba(0,0,0,0)");
    context.fillStyle = rift;
    context.fillRect(x - radius, y - radius, radius * 2, radius * 2);
  }

  /* The field: faint stars everywhere, a few bright ones. */
  context.globalCompositeOperation = "lighter";
  const field = Math.round((side * side) / 1500);
  const bright: Bright[] = [];
  for (let index = 0; index < field; index += 1) {
    const x = random() * side;
    const y = random() * side;
    const magnitude = Math.pow(random(), 3.2);
    const size = 0.45 + magnitude * 1.9;
    const alpha = 0.22 + magnitude * 0.7;
    const tint = random();
    const colour =
      tint < 0.12 ? "255,238,220" : tint < 0.3 ? "226,232,245" : "242,243,247";
    if (size > 1.5) {
      const glow = context.createRadialGradient(x, y, 0, x, y, size * 3.2);
      glow.addColorStop(0, `rgba(${colour},${alpha})`);
      glow.addColorStop(0.3, `rgba(${colour},${alpha * 0.28})`);
      glow.addColorStop(1, `rgba(${colour},0)`);
      context.fillStyle = glow;
      context.fillRect(x - size * 3.2, y - size * 3.2, size * 6.4, size * 6.4);
      if (bright.length < 46) {
        bright.push({
          x: x / side,
          y: y / side,
          size: size * 2.2,
          delay: random() * 6,
          duration: 2.6 + random() * 4.2,
        });
      }
    } else {
      context.fillStyle = `rgba(${colour},${alpha})`;
      context.beginPath();
      context.arc(x, y, size / 2, 0, Math.PI * 2);
      context.fill();
    }
  }
  context.globalCompositeOperation = "source-over";
  return bright;
}

type Meteor = {
  id: number;
  x: number;
  y: number;
  angle: number;
  length: number;
};

export function NightSky() {
  const canvas = useRef<HTMLCanvasElement | null>(null);
  const [side, setSide] = useState(0);
  const [bright, setBright] = useState<Bright[]>([]);
  const [meteor, setMeteor] = useState<Meteor | null>(null);
  const reduced = useReducedMotion();

  /* The sky is square and as wide as the viewport's diagonal, so turning it never
     shows a corner. It is repainted only when the viewport outgrows it. */
  useEffect(() => {
    const measure = () => {
      const needed =
        Math.ceil(Math.hypot(window.innerWidth, window.innerHeight)) + 24;
      setSide((current) => (needed > current ? needed : current));
    };
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  useEffect(() => {
    if (!side || !canvas.current) return;
    setBright(paintSky(canvas.current, side));
  }, [side]);

  /* A meteor every so often, never while hidden, never under reduced motion. */
  useEffect(() => {
    if (reduced) return;
    let timer = 0;
    let serial = 0;
    const random = seeded(Date.now() & 0xffff);
    const schedule = () => {
      timer = window.setTimeout(
        () => {
          if (!document.hidden) {
            serial += 1;
            setMeteor({
              id: serial,
              x: 8 + random() * 70,
              y: 4 + random() * 34,
              angle: 18 + random() * 22,
              length: 120 + random() * 160,
            });
          }
          schedule();
        },
        9000 + random() * 14000,
      );
    };
    schedule();
    return () => window.clearTimeout(timer);
  }, [reduced]);

  return (
    <div className="night-sky" aria-hidden="true">
      <div
        className="sky-rotor"
        style={
          side
            ? {
                width: side,
                height: side,
                marginLeft: -side / 2,
                marginTop: -side / 2,
              }
            : undefined
        }
      >
        <canvas ref={canvas} className="sky-canvas" />
        {!reduced &&
          bright.map((star, index) => (
            <span
              key={index}
              className="twinkle"
              style={{
                left: `${star.x * 100}%`,
                top: `${star.y * 100}%`,
                width: star.size,
                height: star.size,
                animationDelay: `${star.delay}s`,
                animationDuration: `${star.duration}s`,
              }}
            />
          ))}
      </div>
      {meteor && !reduced && (
        <span
          key={meteor.id}
          className="meteor"
          style={
            {
              left: `${meteor.x}%`,
              top: `${meteor.y}%`,
              width: meteor.length,
              "--angle": `${meteor.angle}deg`,
            } as React.CSSProperties
          }
          onAnimationEnd={() => setMeteor(null)}
        />
      )}
      <div className="sky-vignette" />
    </div>
  );
}
