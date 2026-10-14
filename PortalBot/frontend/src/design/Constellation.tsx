"use client";

/**
 * Constellation - the suite's signature canvas.
 *
 * Slowly drifting glowing nodes joined by thin solid lines whose opacity
 * fades with distance. A product passes its own nodes and links (built from
 * real data) and the canvas adds an ambient field around them. Pulses travel
 * along solid links; nodes light up as they arrive. The pointer brightens
 * nodes near it and draws a line to the nearest few.
 *
 * - Pauses when off screen or in a background tab.
 * - Under prefers-reduced-motion it draws one still frame, with every node
 *   in its final state, whenever the props change.
 * - Purely decorative to assistive technology unless `label` is given; the
 *   same facts are always on the page in text.
 *
 * Imperative handle: `pulse(path, options)` sends a glowing node along a path
 * of node ids; `flash(id)` rings a node once.
 */

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  type CSSProperties,
} from "react";

import {
  clamp01,
  drawComet,
  drawLine,
  drawNode,
  drawPartialPolyline,
  drawRing,
  readPalette,
  roundedRect,
  seeded,
  type Palette,
  type Point,
  type Tone,
} from "./canvas";

export type { Tone } from "./canvas";

export type ConstellationNode = {
  id: string;
  /** Position as a fraction (0..1) of the canvas box. */
  x: number;
  y: number;
  /** Core radius in pixels. */
  r?: number;
  tone?: Tone;
  /** Mono label drawn in a small solid pill beside the node. */
  label?: string;
  /** A second line under the label, in the node's colour (an amount, a status). */
  sub?: string;
  side?: "left" | "right" | "above" | "below";
  /** Hidden nodes fade out; shown nodes fade in. Default shown. */
  visible?: boolean;
  /** Brighter, larger glow. */
  lit?: boolean;
  /** Draw breathing rings around it (hubs and gates). */
  ring?: boolean;
  /** How far it drifts around its place, in pixels. Default 3. */
  drift?: number;
};

export type ConstellationLink = {
  from: string;
  to: string;
  tone?: Tone;
  visible?: boolean;
  lit?: boolean;
};

export type PulseOptions = {
  duration?: number;
  tone?: Tone;
  delay?: number;
  size?: number;
  /** Leave the travelled line lit for a moment after arrival. Default true. */
  trail?: boolean;
  onArrive?: () => void;
};

export type ConstellationHandle = {
  pulse: (path: string[], options?: PulseOptions) => void;
  flash: (id: string, tone?: Tone) => void;
};

type NodeState = {
  alpha: number;
  lit: number;
  angle: number;
  speed: number;
  born: number;
  order: number;
  /** Last drawn place, radius and colour, so a removed node can fade out. */
  x: number;
  y: number;
  r: number;
  tone: Tone;
  seen: number;
};

type Ambient = { bx: number; by: number; angle: number; speed: number; orbit: number; size: number; phase: number };

type Pulse = {
  path: string[];
  start: number;
  duration: number;
  tone: Tone;
  size: number;
  trail: boolean;
  arrived: number;
  onArrive?: () => void;
};

type Ripple = { id: string; start: number; tone: Tone };

export const Constellation = forwardRef<
  ConstellationHandle,
  {
    nodes: ConstellationNode[];
    links?: ConstellationLink[];
    /** Number of ambient nodes in the background field. */
    ambient?: number;
    /** Ambient link distance in pixels. */
    reach?: number;
    surface?: "dark" | "light";
    /** Random traffic along these paths, every `every` milliseconds. */
    traffic?: { paths: string[][]; every: number; tone?: Tone };
    /** Fade nodes in one after another on first show, in milliseconds. */
    introStagger?: number;
    seed?: number;
    className?: string;
    style?: CSSProperties;
    label?: string;
  }
>(function Constellation(
  {
    nodes,
    links = [],
    ambient = 46,
    reach = 118,
    surface = "dark",
    traffic,
    introStagger = 28,
    seed = 20261012,
    className = "",
    style,
    label,
  },
  handle,
) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const props = useRef({ nodes, links, traffic });
  props.current = { nodes, links, traffic };

  const states = useRef(new Map<string, NodeState>());
  const pulses = useRef<Pulse[]>([]);
  const ripples = useRef<Ripple[]>([]);
  const redraw = useRef<() => void>(() => undefined);
  const reduceRef = useRef(false);
  const clock = useRef(0);

  const pulse = useCallback((path: string[], options: PulseOptions = {}) => {
    if (reduceRef.current || path.length < 2) {
      options.onArrive?.();
      return;
    }
    pulses.current.push({
      path,
      start: clock.current + (options.delay ?? 0),
      duration: options.duration ?? 900,
      tone: options.tone ?? "accent",
      size: options.size ?? 2.8,
      trail: options.trail ?? true,
      arrived: 0,
      onArrive: options.onArrive,
    });
    if (pulses.current.length > 80) pulses.current.splice(0, pulses.current.length - 80);
  }, []);

  const flash = useCallback((id: string, tone: Tone = "accent") => {
    if (reduceRef.current) return;
    ripples.current.push({ id, start: clock.current, tone });
  }, []);

  useImperativeHandle(handle, () => ({ pulse, flash }), [pulse, flash]);

  // Ask for a still frame whenever the nodes change (reduced motion, paused).
  useEffect(() => {
    redraw.current();
  }, [nodes, links]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    reduceRef.current = reduce;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let palette: Palette = readPalette(canvas, surface);
    let font = getComputedStyle(canvas).fontFamily || "monospace";
    let width = 0;
    let height = 0;
    let frame = 0;
    let running = false;
    let onScreen = false;
    let last = performance.now();
    let lastTraffic = 0;
    let order = 0;
    const pointer = { x: 0, y: 0, on: false };

    const random = seeded(seed);
    const field: Ambient[] = Array.from({ length: ambient }, () => ({
      bx: random(),
      by: random(),
      angle: random() * Math.PI * 2,
      speed: (0.00006 + random() * 0.00012) * (random() < 0.5 ? -1 : 1),
      orbit: 6 + random() * 22,
      size: 0.7 + random() * 1.3,
      phase: random() * Math.PI * 2,
    }));

    const resize = () => {
      const box = canvas.getBoundingClientRect();
      width = box.width;
      height = box.height;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const stateOf = (id: string, now: number): NodeState => {
      let state = states.current.get(id);
      if (!state) {
        const r = seeded(hash(id))();
        state = {
          alpha: 0,
          lit: 0,
          angle: r * Math.PI * 2,
          speed: (0.00018 + r * 0.00022) * (r < 0.5 ? -1 : 1),
          born: now,
          order: order++,
          x: 0,
          y: 0,
          r: 2.6,
          tone: "light",
          seen: now,
        };
        states.current.set(id, state);
      }
      return state;
    };

    const positions = new Map<string, Point>();

    const draw = (now: number, dt: number) => {
      clock.current = now;
      context.clearRect(0, 0, width, height);
      if (width < 4 || height < 4) return;
      const { nodes: list, links: edges, traffic: flow } = props.current;
      const ease = reduce ? 1 : 1 - Math.pow(0.0025, dt / 1000);

      // ---------------------------------------------------- real nodes
      positions.clear();
      for (const node of list) {
        const state = stateOf(node.id, now);
        if (!reduce) state.angle += state.speed * dt;
        const gate = reduce ? 0 : Math.max(0, now - state.born - state.order * introStagger);
        const wanted = node.visible === false || (gate <= 0 && !reduce) ? 0 : 1;
        state.alpha += (wanted - state.alpha) * ease;
        state.lit += ((node.lit ? 1 : 0) - state.lit) * ease;
        const drift = reduce ? 0 : node.drift ?? 3;
        state.x = node.x * width + Math.cos(state.angle) * drift;
        state.y = node.y * height + Math.sin(state.angle) * drift * 0.8;
        state.r = node.r ?? 2.6;
        state.tone = node.tone ?? "light";
        state.seen = now;
        positions.set(node.id, { x: state.x, y: state.y });
      }

      // nodes that were removed fade out where they last were
      for (const [id, state] of states.current) {
        if (state.seen === now) continue;
        state.alpha += (0 - state.alpha) * ease;
        if (state.alpha < 0.01 || reduce) {
          states.current.delete(id);
          continue;
        }
        drawNode(context, state.x, state.y, state.r, palette[state.tone], state.alpha * 0.8, 0.7);
      }

      // ---------------------------------------------------- ambient field
      const ambientPoints: (Point & { size: number; phase: number })[] = field.map((dot) => {
        if (!reduce) dot.angle += dot.speed * dt;
        return {
          x: dot.bx * width + Math.cos(dot.angle) * dot.orbit,
          y: dot.by * height + Math.sin(dot.angle) * dot.orbit * 0.7,
          size: dot.size,
          phase: dot.phase,
        };
      });

      const meshAlpha = surface === "dark" ? 0.27 : 0.18;
      for (let i = 0; i < ambientPoints.length; i += 1) {
        const a = ambientPoints[i];
        for (let j = i + 1; j < ambientPoints.length; j += 1) {
          const b = ambientPoints[j];
          const dx = a.x - b.x;
          if (dx > reach || dx < -reach) continue;
          const dy = a.y - b.y;
          if (dy > reach || dy < -reach) continue;
          const d = Math.hypot(dx, dy);
          if (d < reach) drawLine(context, a, b, palette.line, (1 - d / reach) * meshAlpha, 0.7);
        }
        // faint threads from the field to nearby real nodes
        for (const node of list) {
          const p = positions.get(node.id);
          const s = states.current.get(node.id);
          if (!p || !s || s.alpha < 0.05) continue;
          const d = Math.hypot(a.x - p.x, a.y - p.y);
          if (d < reach * 0.9) {
            drawLine(context, a, p, palette.line, (1 - d / (reach * 0.9)) * meshAlpha * 0.8 * s.alpha, 0.6);
          }
        }
      }

      // ---------------------------------------------------- real links
      for (const edge of edges) {
        const a = positions.get(edge.from);
        const b = positions.get(edge.to);
        const sa = states.current.get(edge.from);
        const sb = states.current.get(edge.to);
        if (!a || !b || !sa || !sb || edge.visible === false) continue;
        const visibility = Math.min(sa.alpha, sb.alpha);
        const tone = palette[edge.tone ?? "light"];
        const base = surface === "dark" ? 0.16 : 0.22;
        drawLine(context, a, b, tone, visibility * (edge.lit ? 0.62 : base), edge.lit ? 1.3 : 0.9);
      }

      // ---------------------------------------------------- traffic
      if (!reduce && flow && flow.paths.length && now - lastTraffic > flow.every) {
        lastTraffic = now;
        const path = flow.paths[Math.floor(Math.random() * flow.paths.length)];
        pulses.current.push({
          path,
          start: now,
          duration: 1100,
          tone: flow.tone ?? "accent",
          size: 2.2,
          trail: true,
          arrived: 0,
        });
      }

      // ---------------------------------------------------- pulses
      for (let index = pulses.current.length - 1; index >= 0; index -= 1) {
        const item = pulses.current[index];
        const elapsed = now - item.start;
        if (elapsed < 0) continue;
        const points = item.path.map((id) => positions.get(id)).filter(Boolean) as Point[];
        if (points.length < 2) {
          pulses.current.splice(index, 1);
          continue;
        }
        const fraction = clamp01(elapsed / item.duration);
        const fade = item.arrived ? clamp01(1 - (now - item.arrived) / 650) : 1;
        if (item.trail) {
          drawPartialPolyline(context, points, fraction, palette[item.tone], 0.55 * fade, 1.4);
        }
        if (fraction < 1) {
          drawComet(context, points, fraction, palette[item.tone], item.size);
        } else if (!item.arrived) {
          item.arrived = now;
          ripples.current.push({ id: item.path[item.path.length - 1], start: now, tone: item.tone });
          item.onArrive?.();
        }
        if (item.arrived && fade <= 0) pulses.current.splice(index, 1);
      }

      // ---------------------------------------------------- ripples
      for (let index = ripples.current.length - 1; index >= 0; index -= 1) {
        const ripple = ripples.current[index];
        const p = positions.get(ripple.id);
        const t = (now - ripple.start) / 900;
        if (!p || t >= 1) {
          ripples.current.splice(index, 1);
          continue;
        }
        drawRing(context, p, 4 + t * 20, palette[ripple.tone], (1 - t) * 0.7, 1.2);
      }

      // ---------------------------------------------------- pointer
      const near = (p: Point) => {
        if (!pointer.on) return 0;
        const d = Math.hypot(p.x - pointer.x, p.y - pointer.y);
        return d < 150 ? 1 - d / 150 : 0;
      };
      if (pointer.on) {
        const candidates: { p: Point; k: number }[] = [];
        for (const p of ambientPoints) {
          const k = near(p);
          if (k > 0.25) candidates.push({ p, k });
        }
        for (const node of list) {
          const p = positions.get(node.id);
          const s = states.current.get(node.id);
          if (!p || !s || s.alpha < 0.3) continue;
          const k = near(p);
          if (k > 0.2) candidates.push({ p, k: k + 0.2 });
        }
        candidates
          .sort((a, b) => b.k - a.k)
          .slice(0, 6)
          .forEach(({ p, k }) =>
            drawLine(context, p, pointer, palette.accent, Math.min(0.75, k * 0.65), 1),
          );
      }

      // ---------------------------------------------------- draw nodes
      for (const p of ambientPoints) {
        const k = near(p);
        const twinkle = reduce ? 0.7 : 0.55 + Math.sin(now * 0.0016 + p.phase) * 0.3;
        drawNode(
          context,
          p.x,
          p.y,
          p.size * (1 + k * 0.9),
          k > 0.3 ? palette.accent : palette.muted,
          Math.min(1, twinkle + k * 0.6),
          0.55 + k,
        );
      }

      context.font = `500 10.5px ${font}`;
      context.textBaseline = "middle";
      for (const node of list) {
        const p = positions.get(node.id);
        const s = states.current.get(node.id);
        if (!p || !s || s.alpha < 0.02) continue;
        const k = near(p);
        const rgb = palette[node.tone ?? "light"];
        const radius = (node.r ?? 2.6) * (1 + s.lit * 0.45 + k * 0.5);
        const pulseBeat = reduce ? 0 : (Math.sin(now * 0.0032 + s.order) + 1) / 2;

        if (node.ring) {
          const breathe = reduce ? 0 : pulseBeat * 3;
          drawRing(context, p, radius + 6 + breathe, rgb, 0.45 * s.alpha, 1);
          drawRing(context, p, radius + 13 + breathe * 1.6, rgb, 0.2 * s.alpha, 1);
        }
        drawNode(
          context,
          p.x,
          p.y,
          radius,
          rgb,
          s.alpha * (0.75 + 0.25 * s.lit + k * 0.2),
          0.7 + s.lit * 0.9 + k * 0.8 + (node.ring ? pulseBeat * 0.4 : 0),
        );

        if (node.label) {
          drawLabel(context, node, p, radius, s.alpha, palette, rgb);
        }
      }
    };

    const tick = (now: number) => {
      const dt = Math.min(48, now - last);
      last = now;
      draw(now, dt);
      if (running) frame = requestAnimationFrame(tick);
    };
    const start = () => {
      if (running || reduce || !onScreen || document.visibilityState === "hidden") return;
      running = true;
      last = performance.now();
      frame = requestAnimationFrame(tick);
    };
    const stop = () => {
      running = false;
      cancelAnimationFrame(frame);
    };
    const still = () => {
      if (!running) draw(performance.now(), 16);
    };
    redraw.current = still;

    resize();
    still();
    document.fonts?.ready.then(() => {
      font = getComputedStyle(canvas).fontFamily || font;
      still();
    });

    const visibility = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting;
        if (onScreen) start();
        else stop();
      },
      { rootMargin: "60px 0px" },
    );
    visibility.observe(canvas);
    const sizing = new ResizeObserver(() => {
      resize();
      palette = readPalette(canvas, surface);
      still();
    });
    sizing.observe(canvas);
    const onVisibility = () => (document.visibilityState === "hidden" ? stop() : start());
    document.addEventListener("visibilitychange", onVisibility);

    const onMove = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      const box = canvas.getBoundingClientRect();
      pointer.x = event.clientX - box.left;
      pointer.y = event.clientY - box.top;
      pointer.on =
        pointer.x >= -40 && pointer.y >= -40 && pointer.x <= box.width + 40 && pointer.y <= box.height + 40;
      if (reduce) still();
    };
    const onLeave = () => {
      pointer.on = false;
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    document.addEventListener("pointerleave", onLeave);

    return () => {
      stop();
      redraw.current = () => undefined;
      visibility.disconnect();
      sizing.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
    };
  }, [ambient, reach, surface, introStagger, seed]);

  return (
    <canvas
      ref={canvasRef}
      className={`ds-constellation ${className}`}
      style={style}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  );
});

function drawLabel(
  context: CanvasRenderingContext2D,
  node: ConstellationNode,
  p: Point,
  radius: number,
  alpha: number,
  palette: Palette,
  rgb: string,
) {
  const text = node.label ?? "";
  const sub = node.sub ?? "";
  const padX = 7;
  const lineH = 14;
  const textWidth = Math.max(context.measureText(text).width, sub ? context.measureText(sub).width : 0);
  const boxW = textWidth + padX * 2;
  const boxH = sub ? lineH * 2 + 6 : lineH + 6;
  const side = node.side ?? "right";
  const gap = radius + 9 + (node.ring ? 12 : 0);
  let x = p.x + gap;
  let y = p.y - boxH / 2;
  if (side === "left") x = p.x - gap - boxW;
  if (side === "above") {
    x = p.x - boxW / 2;
    y = p.y - gap - boxH;
  }
  if (side === "below") {
    x = p.x - boxW / 2;
    y = p.y + gap;
  }
  context.globalAlpha = alpha;
  roundedRect(context, x, y, boxW, boxH, 6);
  context.fillStyle = `rgb(${palette.labelFill})`;
  context.fill();
  context.strokeStyle = `rgb(${palette.labelLine})`;
  context.lineWidth = 1;
  context.stroke();
  context.fillStyle = `rgba(${palette.labelText},0.92)`;
  context.fillText(text, x + padX, y + 3 + lineH / 2);
  if (sub) {
    context.fillStyle = `rgb(${rgb})`;
    context.fillText(sub, x + padX, y + 3 + lineH + lineH / 2);
  }
  context.globalAlpha = 1;
}

function hash(text: string): number {
  let value = 2166136261;
  for (let index = 0; index < text.length; index += 1) {
    value ^= text.charCodeAt(index);
    value = Math.imul(value, 16777619);
  }
  return value >>> 0;
}
