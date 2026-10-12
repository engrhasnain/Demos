/**
 * Canvas 2D helpers for the suite's constellation style: glowing nodes, thin
 * SOLID links whose opacity fades with distance, pulses that travel along a
 * solid line with a short fading tail. Never dashes.
 */

export type Point = { x: number; y: number };

export type Tone = "accent" | "pass" | "fail" | "warn" | "light" | "muted";

export type Palette = Record<Tone, string> & { line: string; labelText: string; labelFill: string; labelLine: string };

/** Reads the suite colours from CSS, so a product's accent reaches its canvas. */
export function readPalette(element: Element, surface: "dark" | "light"): Palette {
  const style = getComputedStyle(element);
  const get = (name: string, fallback: string) =>
    (style.getPropertyValue(name).trim() || fallback).replace(/\s+/g, "");
  const dark = surface === "dark";
  return {
    accent: get("--ds-accent-rgb", "245,165,36"),
    pass: get("--ds-pass-rgb", "34,197,94"),
    fail: get("--ds-fail-rgb", "242,85,90"),
    warn: get("--ds-warn-rgb", "247,103,7"),
    light: dark ? "226,229,236" : "74,80,96",
    muted: dark ? "125,134,151" : "160,164,172",
    line: dark ? "154,163,178" : "102,108,122",
    labelText: dark ? "243,244,246" : "11,13,18",
    labelFill: dark ? "18,21,28" : "255,255,255",
    labelLine: dark ? "38,43,54" : "203,203,194",
  };
}

const sprites = new Map<string, HTMLCanvasElement>();

/** A soft radial glow rendered once per colour; far cheaper than shadowBlur. */
function glowSprite(rgb: string): HTMLCanvasElement {
  const cached = sprites.get(rgb);
  if (cached) return cached;
  const sprite = document.createElement("canvas");
  sprite.width = sprite.height = 64;
  const context = sprite.getContext("2d");
  if (context) {
    const gradient = context.createRadialGradient(32, 32, 0, 32, 32, 32);
    gradient.addColorStop(0, `rgba(${rgb},0.9)`);
    gradient.addColorStop(0.25, `rgba(${rgb},0.42)`);
    gradient.addColorStop(0.6, `rgba(${rgb},0.1)`);
    gradient.addColorStop(1, `rgba(${rgb},0)`);
    context.fillStyle = gradient;
    context.fillRect(0, 0, 64, 64);
  }
  sprites.set(rgb, sprite);
  return sprite;
}

/** A glowing node: a small halo and a crisp core. */
export function drawNode(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  radius: number,
  rgb: string,
  alpha = 1,
  glow = 1,
) {
  if (alpha <= 0.01) return;
  if (glow > 0) {
    const size = radius * 4.6 * glow;
    context.globalAlpha = Math.min(1, alpha * (0.3 + 0.45 * Math.min(glow, 1.4)));
    context.drawImage(glowSprite(rgb), x - size, y - size, size * 2, size * 2);
  }
  context.globalAlpha = alpha;
  context.fillStyle = `rgb(${rgb})`;
  context.beginPath();
  context.arc(x, y, radius, 0, Math.PI * 2);
  context.fill();
  context.globalAlpha = 1;
}

export function drawLine(
  context: CanvasRenderingContext2D,
  a: Point,
  b: Point,
  rgb: string,
  alpha: number,
  width = 1,
) {
  if (alpha <= 0.004) return;
  context.strokeStyle = `rgba(${rgb},${alpha})`;
  context.lineWidth = width;
  context.beginPath();
  context.moveTo(a.x, a.y);
  context.lineTo(b.x, b.y);
  context.stroke();
}

export function drawRing(
  context: CanvasRenderingContext2D,
  centre: Point,
  radius: number,
  rgb: string,
  alpha: number,
  width = 1,
) {
  if (alpha <= 0.004) return;
  context.strokeStyle = `rgba(${rgb},${alpha})`;
  context.lineWidth = width;
  context.beginPath();
  context.arc(centre.x, centre.y, Math.max(0.5, radius), 0, Math.PI * 2);
  context.stroke();
}

function lengths(points: Point[]) {
  const segments: number[] = [];
  let total = 0;
  for (let index = 1; index < points.length; index += 1) {
    const length = Math.hypot(
      points[index].x - points[index - 1].x,
      points[index].y - points[index - 1].y,
    );
    segments.push(length);
    total += length;
  }
  return { segments, total };
}

/** The point a fraction of the way along a polyline, by length. */
export function pointAlong(points: Point[], fraction: number): Point {
  if (points.length === 1) return points[0];
  const { segments, total } = lengths(points);
  let distance = Math.max(0, Math.min(1, fraction)) * total;
  for (let index = 0; index < segments.length; index += 1) {
    if (distance <= segments[index] || index === segments.length - 1) {
      const k = segments[index] ? Math.min(1, distance / segments[index]) : 0;
      return {
        x: points[index].x + (points[index + 1].x - points[index].x) * k,
        y: points[index].y + (points[index + 1].y - points[index].y) * k,
      };
    }
    distance -= segments[index];
  }
  return points[points.length - 1];
}

/** The first part of a polyline: a solid line filling node to node. */
export function drawPartialPolyline(
  context: CanvasRenderingContext2D,
  points: Point[],
  fraction: number,
  rgb: string,
  alpha: number,
  width = 1.4,
) {
  if (points.length < 2 || fraction <= 0 || alpha <= 0.004) return;
  const { segments, total } = lengths(points);
  let left = Math.min(1, fraction) * total;
  context.strokeStyle = `rgba(${rgb},${alpha})`;
  context.lineWidth = width;
  context.lineCap = "round";
  context.lineJoin = "round";
  context.beginPath();
  context.moveTo(points[0].x, points[0].y);
  for (let index = 0; index < segments.length && left > 0; index += 1) {
    const k = Math.min(1, left / (segments[index] || 1));
    context.lineTo(
      points[index].x + (points[index + 1].x - points[index].x) * k,
      points[index].y + (points[index + 1].y - points[index].y) * k,
    );
    left -= segments[index];
  }
  context.stroke();
}

/** A bright node travelling along a path with a short fading tail. */
export function drawComet(
  context: CanvasRenderingContext2D,
  points: Point[],
  fraction: number,
  rgb: string,
  size = 3,
) {
  for (let step = 4; step >= 1; step -= 1) {
    const behind = fraction - step * 0.03;
    if (behind < 0) continue;
    const point = pointAlong(points, behind);
    drawNode(context, point.x, point.y, size * (1 - step * 0.15), rgb, 0.55 - step * 0.11, 0.5);
  }
  const head = pointAlong(points, fraction);
  drawNode(context, head.x, head.y, size, rgb, 1, 2);
}

/** A rounded rectangle path, for label pills. */
export function roundedRect(
  context: CanvasRenderingContext2D,
  x: number,
  y: number,
  width: number,
  height: number,
  radius: number,
) {
  const r = Math.min(radius, height / 2, width / 2);
  context.beginPath();
  context.moveTo(x + r, y);
  context.arcTo(x + width, y, x + width, y + height, r);
  context.arcTo(x + width, y + height, x, y + height, r);
  context.arcTo(x, y + height, x, y, r);
  context.arcTo(x, y, x + width, y, r);
  context.closePath();
}

/** Deterministic random numbers, so a layout is the same on every visit. */
export function seeded(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const clamp01 = (value: number) => Math.max(0, Math.min(1, value));
