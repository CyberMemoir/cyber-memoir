"use client";
import type { Galaxy } from "@/lib/api";
import { gaussian, hashSeed, seeded } from "@/lib/seeded";
import {
  GALAXY_VIEW,
  armAngle,
  dustRadius,
} from "@/components/universe-layout";

/*
 * Decoration only. Everything drawn here is colourless - warm or cool white, never
 * above ~15% saturation - small, and not interactive, so it can never be mistaken
 * for evidence, which owns the four role colours, the role shapes, and diffraction
 * spikes. The dust follows the same arms the evidence stars ride, so the picture
 * reads as one galaxy, and it thins out inside a quiet period, so silence looks like
 * what it is: a dark lane with nothing in it.
 */

type Rgb = [number, number, number];
const WARM: Rgb = [255, 238, 218];
const COOL: Rgb = [230, 234, 246];
const NEUTRAL: Rgb = [238, 239, 243];

/** A soft round sprite, drawn once, stamped thousands of times. */
function sprite(size: number): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = size;
  const context = canvas.getContext("2d")!;
  const gradient = context.createRadialGradient(
    size / 2,
    size / 2,
    0,
    size / 2,
    size / 2,
    size / 2,
  );
  gradient.addColorStop(0, "rgba(255,255,255,1)");
  gradient.addColorStop(0.25, "rgba(255,255,255,0.55)");
  gradient.addColorStop(1, "rgba(255,255,255,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, size, size);
  return canvas;
}

function toUrl(canvas: HTMLCanvasElement): Promise<string | null> {
  return new Promise((resolve) =>
    canvas.toBlob(
      (blob) => resolve(blob ? URL.createObjectURL(blob) : null),
      "image/png",
    ),
  );
}

function dot(
  context: CanvasRenderingContext2D,
  glow: HTMLCanvasElement,
  x: number,
  y: number,
  size: number,
  alpha: number,
  [r, g, b]: Rgb,
) {
  if (size < 1.3) {
    context.fillStyle = `rgba(${r},${g},${b},${alpha})`;
    context.fillRect(x - size / 2, y - size / 2, size, size);
    return;
  }
  context.globalAlpha = alpha;
  context.drawImage(
    glow,
    x - size * 1.6,
    y - size * 1.6,
    size * 3.2,
    size * 3.2,
  );
  context.globalAlpha = 1;
}

/** Quiet periods, in `t`, as [low, high] pairs. */
function quietSpans(galaxy: Galaxy): [number, number][] {
  return galaxy.bands.map((band) => [
    Math.min(band.start, band.end),
    Math.max(band.start, band.end),
  ]);
}

/**
 * The dust of one meme's galaxy, as an image covering the galaxy view's own
 * coordinate box, so it pans and zooms with the evidence drawn over it.
 */
export async function renderGalaxyDust(
  galaxy: Galaxy,
  scale = 1.5,
): Promise<string | null> {
  const { width, height, cx, cy, rOut } = GALAXY_VIEW;
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext("2d");
  if (!context) return null;
  context.scale(scale, scale);
  const random = seeded(hashSeed(galaxy.meme_id));
  const glow = sprite(32);
  const quiet = quietSpans(galaxy);
  const inQuiet = (t: number) => quiet.some(([lo, hi]) => t > lo && t < hi);

  /* The disk's faint body light, then the core. */
  const disk = context.createRadialGradient(cx, cy, 0, cx, cy, rOut * 1.2);
  disk.addColorStop(0, "rgba(224,226,232,0.10)");
  disk.addColorStop(0.45, "rgba(210,212,219,0.045)");
  disk.addColorStop(1, "rgba(210,212,219,0)");
  context.fillStyle = disk;
  context.fillRect(0, 0, width, height);
  const core = context.createRadialGradient(cx, cy, 0, cx, cy, 175);
  core.addColorStop(0, "rgba(255,241,222,0.62)");
  core.addColorStop(0.18, "rgba(255,232,206,0.30)");
  core.addColorStop(0.55, "rgba(240,226,210,0.07)");
  core.addColorStop(1, "rgba(240,226,210,0)");
  context.fillStyle = core;
  context.fillRect(0, 0, width, height);

  context.globalCompositeOperation = "lighter";

  /* The disk between the arms: faint, even, and present through quiet periods too,
     so a silence reads as a thinned lane in a galaxy rather than a hole in it. */
  for (let index = 0; index < 4200; index += 1) {
    const radius = Math.pow(random(), 0.7) * rOut * 1.08;
    const angle = random() * Math.PI * 2;
    dot(
      context,
      glow,
      cx + radius * Math.cos(angle),
      cy + radius * Math.sin(angle),
      0.5 + random() * 0.7,
      0.07 + random() * 0.18,
      NEUTRAL,
    );
  }

  /* The halo: an old, even scatter well beyond the arms. */
  for (let index = 0; index < 1700; index += 1) {
    const radius = Math.sqrt(random()) * rOut * 1.28;
    const angle = random() * Math.PI * 2;
    dot(
      context,
      glow,
      cx + radius * Math.cos(angle),
      cy + radius * Math.sin(angle),
      0.6 + random() * 0.6,
      0.08 + random() * 0.2,
      NEUTRAL,
    );
  }

  /* The bulge: dense, warm, round. */
  for (let index = 0; index < 2600; index += 1) {
    const radius = Math.abs(gaussian(random)) * 58;
    const angle = random() * Math.PI * 2;
    dot(
      context,
      glow,
      cx + radius * Math.cos(angle),
      cy + radius * Math.sin(angle),
      0.7 + random() * 1.1,
      0.18 + random() * 0.5,
      WARM,
    );
  }

  /* The arms. `t` runs from inside the core out past the last evidence, so the arm
     winds in and fades out instead of starting and stopping on the data. */
  for (let arm = 0; arm < 2; arm += 1) {
    for (let index = 0; index < 7000; index += 1) {
      const t = -0.42 + Math.pow(random(), 0.92) * 1.58;
      if (inQuiet(t) && random() < 0.8) continue;
      const radius = t > 1 ? dustRadius(1) + (t - 1) * 230 : dustRadius(t);
      const width = 9 + radius * 0.085;
      const offset = gaussian(random) * width;
      const angle = armAngle(t, arm) + gaussian(random) * 0.035;
      const fade = t > 1 ? Math.max(0, 1 - (t - 1) / 0.16) : 1;
      const x = cx + radius * Math.cos(angle) - offset * Math.sin(angle);
      const y = cy + radius * Math.sin(angle) + offset * Math.cos(angle);
      const bright = random() < 0.05;
      dot(
        context,
        glow,
        x,
        y,
        bright ? 1.4 + random() * 1.4 : 0.55 + random() * 0.8,
        (bright ? 0.5 : 0.16 + random() * 0.42) * fade,
        t < 0.05 ? WARM : COOL,
      );
    }
    /* Star-forming knots: tight, brighter clumps strung along the arm. */
    for (let knot = 0; knot < 34; knot += 1) {
      const t = random() * 1.02;
      if (inQuiet(t)) continue;
      const [kx, ky] = [
        cx + dustRadius(t) * Math.cos(armAngle(t, arm)),
        cy + dustRadius(t) * Math.sin(armAngle(t, arm)),
      ];
      const spread = 3 + random() * 5;
      for (let index = 0; index < 22; index += 1) {
        dot(
          context,
          glow,
          kx + gaussian(random) * spread,
          ky + gaussian(random) * spread,
          0.8 + random() * 1.3,
          0.25 + random() * 0.45,
          COOL,
        );
      }
    }
  }

  /* Dust lanes: carved out along the inner, trailing edge of each arm. */
  context.globalCompositeOperation = "destination-out";
  for (let arm = 0; arm < 2; arm += 1) {
    for (let index = 0; index < 2600; index += 1) {
      const t = -0.25 + random() * 1.3;
      const radius = dustRadius(Math.min(t, 1));
      const angle = armAngle(t, arm) - 0.11 - Math.abs(gaussian(random)) * 0.03;
      const x = cx + radius * Math.cos(angle);
      const y = cy + radius * Math.sin(angle);
      context.globalAlpha = 0.05 + random() * 0.08;
      context.drawImage(glow, x - 7, y - 7, 14, 14);
    }
  }
  context.globalAlpha = 1;
  context.globalCompositeOperation = "source-over";
  return toUrl(canvas);
}

const spriteCache = new Map<string, Promise<string | null>>();

/**
 * A small generic spiral for the universe view and the home sky, one per meme,
 * seeded by its id so each keeps its own shape and angle.
 */
export function galaxySprite(
  memeId: string,
  size = 200,
): Promise<string | null> {
  const key = `${memeId}:${size}`;
  const cached = spriteCache.get(key);
  if (cached) return cached;
  const made = (async () => {
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = size;
    const context = canvas.getContext("2d");
    if (!context) return null;
    const random = seeded(hashSeed(memeId));
    const glow = sprite(16);
    const c = size / 2;
    const tilt = 0.45 + random() * 0.4;
    const spin = random() * Math.PI * 2;
    const winding = 3.2 + random() * 1.6;
    context.translate(c, c);
    context.rotate(spin);
    context.scale(1, tilt);
    const core = context.createRadialGradient(0, 0, 0, 0, 0, size * 0.22);
    core.addColorStop(0, "rgba(255,240,220,0.95)");
    core.addColorStop(0.3, "rgba(255,230,205,0.35)");
    core.addColorStop(1, "rgba(255,230,205,0)");
    context.fillStyle = core;
    context.fillRect(-c, -c, size, size);
    context.globalCompositeOperation = "lighter";
    for (let arm = 0; arm < 2; arm += 1) {
      for (let index = 0; index < 900; index += 1) {
        const s = Math.pow(random(), 0.8);
        const radius = s * size * 0.46;
        const angle = arm * Math.PI + s * winding + gaussian(random) * 0.16;
        const x = radius * Math.cos(angle) + gaussian(random) * 2.2;
        const y = radius * Math.sin(angle) + gaussian(random) * 2.2;
        dot(
          context,
          glow,
          x,
          y,
          0.5 + random() * 1.2,
          (0.2 + random() * 0.55) * (1 - s * 0.55),
          s < 0.18 ? WARM : COOL,
        );
      }
    }
    for (let index = 0; index < 500; index += 1) {
      const radius = Math.abs(gaussian(random)) * size * 0.07;
      const angle = random() * Math.PI * 2;
      dot(
        context,
        glow,
        radius * Math.cos(angle),
        radius * Math.sin(angle),
        0.6 + random(),
        0.3 + random() * 0.5,
        WARM,
      );
    }
    return toUrl(canvas);
  })();
  spriteCache.set(key, made);
  return made;
}
