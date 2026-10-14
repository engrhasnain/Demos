"use client";

/**
 * The operations brain: OpsAgent's signature canvas.
 *
 * OpsAgent sits in the middle. Around it are the five systems it reads
 * across, each a hub with its own cluster: the reviewed queries that read it
 * (small orbiting nodes) and its records (tiny dots, lit as far as the asker's
 * reach goes). Every hub sits inside a permission ring.
 *
 * - An open ring has a gap facing the core: the asker's role reaches it.
 * - A closed ring is a full circle: nothing the asker types can open it.
 * - When a question is asked, a glowing node travels from the core along a
 *   solid line to each system the plan touches and lights the query it ran.
 *   A step the role check refuses stops at the ring, which turns coral and
 *   rings outward: a fooled plan reaches nothing extra, made visible.
 *
 * Thin solid lines only (alpha fades with distance), glowing nodes, pointer
 * lines. Pauses off screen and in a background tab; under reduced motion it
 * draws one still frame with everything in its final state.
 */

import { forwardRef, useEffect, useImperativeHandle, useRef } from "react";

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
} from "@/design/canvas";
import { DOMAINS, type DomainId } from "@/lib/words";

export type BrainDomain = {
  id: DomainId;
  label: string;
  short: string;
  /** Second line under the label: "4 accounts in reach", "Closed to this role". */
  sub?: string;
  /** The asker's role cannot open this system at all. */
  closed?: boolean;
  /** Share of the system's records the asker may see, 0..1. */
  reach?: number;
  capabilities: { name: string; allowed: boolean }[];
};

export type BrainStep = { capability: string; domain: DomainId; blocked?: boolean };

export type BrainHandle = {
  /** Send a question through: pulses to every step's system, in order. */
  play: (steps: BrainStep[], options?: { document?: boolean; gap?: number }) => void;
};

type Comet = {
  points: () => Point[];
  start: number;
  duration: number;
  rgb: keyof Palette;
  size: number;
  arrived: number;
  onArrive?: () => void;
};

type Ripple = { at: () => Point; start: number; rgb: keyof Palette; size: number };

const RECORDS = 12;

export const OpsBrain = forwardRef<
  BrainHandle,
  {
    domains: BrainDomain[];
    /** Capability names to show lit (the last plan). */
    lit?: string[];
    /** Show the attached document beside the core. */
    document?: boolean;
    /** Idle traffic to the open systems when nothing is being asked. */
    idle?: boolean;
    /** Build-up: how many systems are switched on (first run). Default all. */
    built?: number;
    className?: string;
    label?: string;
  }
>(function OpsBrain({ domains, lit = [], document: withDocument = false, idle = true, built, className = "", label }, handle) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const props = useRef({ domains, lit, withDocument, idle, built });
  props.current = { domains, lit, withDocument, idle, built };
  const comets = useRef<Comet[]>([]);
  const ripples = useRef<Ripple[]>([]);
  const clockRef = useRef(0);
  const reduceRef = useRef(false);
  const redraw = useRef<() => void>(() => undefined);
  const lastPlay = useRef(-99999);
  /** Per system: when a ring was last struck, and per query: when it last lit. */
  const struck = useRef(new Map<string, number>());
  const glow = useRef(new Map<string, number>());
  const geometry = useRef<{
    core: Point;
    hub: (id: DomainId) => Point;
    capability: (name: string) => Point | null;
    gate: (id: DomainId) => Point;
    doc: Point;
  } | null>(null);

  useImperativeHandle(
    handle,
    () => ({
      play(steps, options = {}) {
        const now = clockRef.current;
        lastPlay.current = now;
        const gap = options.gap ?? 520;
        let delay = 0;
        if (options.document && geometry.current) {
          const g = geometry.current;
          comets.current.push({
            points: () => [g.doc, g.core],
            start: now,
            duration: 650,
            rgb: "fail",
            size: 2.6,
            arrived: 0,
            onArrive: () => ripples.current.push({ at: () => g.doc, start: clockRef.current, rgb: "fail", size: 26 }),
          });
          delay += 520;
        }
        steps.forEach((step) => {
          const g = geometry.current;
          if (!g) return;
          const start = now + delay;
          if (step.blocked) {
            comets.current.push({
              points: () => [g.core, g.gate(step.domain)],
              start,
              duration: 760,
              rgb: "fail",
              size: 3.2,
              arrived: 0,
              onArrive: () => {
                struck.current.set(step.domain, clockRef.current);
                ripples.current.push({ at: () => g.gate(step.domain), start: clockRef.current, rgb: "fail", size: 34 });
              },
            });
          } else {
            comets.current.push({
              points: () => {
                const target = g.capability(step.capability);
                return target ? [g.core, g.hub(step.domain), target] : [g.core, g.hub(step.domain)];
              },
              start,
              duration: 900,
              rgb: "accent",
              size: 3.2,
              arrived: 0,
              onArrive: () => {
                glow.current.set(step.capability, clockRef.current);
                const target = g.capability(step.capability);
                ripples.current.push({
                  at: () => g.capability(step.capability) ?? g.hub(step.domain),
                  start: clockRef.current,
                  rgb: "accent",
                  size: target ? 22 : 30,
                });
              },
            });
          }
          delay += gap;
        });
        if (reduceRef.current) {
          // No travel under reduced motion: show the final state at once.
          steps.forEach((step) => {
            if (step.blocked) struck.current.set(step.domain, clockRef.current);
            else glow.current.set(step.capability, clockRef.current);
          });
          comets.current = [];
          redraw.current();
        }
      },
    }),
    [],
  );

  useEffect(() => {
    redraw.current();
  }, [domains, lit, withDocument, built]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    reduceRef.current = reduce;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let palette: Palette = readPalette(canvas, "dark");
    let font = getComputedStyle(canvas).fontFamily || "monospace";
    let width = 0;
    let height = 0;
    let frame = 0;
    let running = false;
    let onScreen = false;
    let last = performance.now();
    let lastIdle = 0;
    const born = performance.now();
    const pointer = { x: 0, y: 0, on: false };

    const random = seeded(61803);
    const field = Array.from({ length: 34 }, () => ({
      bx: random(),
      by: random(),
      angle: random() * Math.PI * 2,
      speed: (0.00005 + random() * 0.0001) * (random() < 0.5 ? -1 : 1),
      orbit: 6 + random() * 20,
      size: 0.6 + random() * 1.1,
      phase: random() * Math.PI * 2,
    }));
    // Each system's records orbit on their own tilt and speed.
    const recordSeeds = DOMAINS.map((_, index) => {
      const r = seeded(1000 + index * 77);
      return Array.from({ length: RECORDS }, () => ({
        angle: r() * Math.PI * 2,
        speed: (0.00008 + r() * 0.00012) * (r() < 0.5 ? -1 : 1),
        distance: 0.72 + r() * 0.42,
        size: 0.8 + r() * 0.9,
        phase: r() * Math.PI * 2,
      }));
    });
    const spin = DOMAINS.map((_, index) => ({ angle: index * 1.3, speed: (index % 2 ? -1 : 1) * 0.00009 }));

    const resize = () => {
      const box = canvas.getBoundingClientRect();
      width = box.width;
      height = box.height;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
    };

    const draw = (now: number, dt: number) => {
      clockRef.current = now;
      context.clearRect(0, 0, width, height);
      if (width < 40 || height < 40) return;
      const { domains: list, lit: litNow, withDocument: docOn, idle: idleOn, built: builtCount } = props.current;
      const compact = width < 520;
      const age = reduce ? 99999 : now - born;
      const intro = (index: number) => (reduce ? 1 : clamp01((age - 150 - index * 140) / 700));

      const cx = width * 0.5;
      const cy = height * 0.5;
      const rx = Math.min(width * (compact ? 0.33 : 0.35), height * 0.62);
      const ry = Math.min(height * (compact ? 0.33 : 0.35), width * 0.5);
      const base = Math.min(width, height);
      const clusterR = Math.max(16, base * (compact ? 0.065 : 0.06));
      const ringR = clusterR * 2.05;
      const core: Point = { x: cx, y: cy };
      const doc: Point = { x: cx - rx * 0.42, y: cy + ry * 0.62 };

      // ------------------------------------------------ place everything
      const hubs = new Map<DomainId, Point>();
      const caps = new Map<string, Point>();
      const gates = new Map<DomainId, Point>();
      DOMAINS.forEach((domain, index) => {
        const angle = -Math.PI / 2 + (index / DOMAINS.length) * Math.PI * 2;
        const hub = {
          x: cx + Math.cos(angle) * rx + (reduce ? 0 : Math.cos(now * 0.0004 + index) * 2),
          y: cy + Math.sin(angle) * ry + (reduce ? 0 : Math.sin(now * 0.00035 + index) * 2),
        };
        hubs.set(domain.id, hub);
        const towards = Math.atan2(cy - hub.y, cx - hub.x);
        gates.set(domain.id, { x: hub.x + Math.cos(towards) * ringR, y: hub.y + Math.sin(towards) * ringR });
        const entry = list.find((item) => item.id === domain.id);
        const spinState = spin[index];
        if (!reduce) spinState.angle += spinState.speed * dt;
        const names = entry?.capabilities ?? [];
        names.forEach((capability, position) => {
          const a = spinState.angle + (position / Math.max(1, names.length)) * Math.PI * 2;
          caps.set(capability.name, {
            x: hub.x + Math.cos(a) * clusterR,
            y: hub.y + Math.sin(a) * clusterR * 0.86,
          });
        });
      });
      geometry.current = {
        core,
        hub: (id) => hubs.get(id) ?? core,
        capability: (name) => caps.get(name) ?? null,
        gate: (id) => gates.get(id) ?? core,
        doc,
      };

      // ------------------------------------------------ the map: grid and range rings
      const step = compact ? 44 : 56;
      context.strokeStyle = `rgba(${palette.line},0.06)`;
      context.lineWidth = 1;
      context.beginPath();
      for (let x = (cx % step) + 0.5; x < width; x += step) {
        context.moveTo(x, 0);
        context.lineTo(x, height);
      }
      for (let y = (cy % step) + 0.5; y < height; y += step) {
        context.moveTo(0, y);
        context.lineTo(width, y);
      }
      context.stroke();
      [0.36, 0.68, 1.02].forEach((k, ring) => {
        context.strokeStyle = `rgba(${palette.accent},${0.07 + (ring === 2 ? 0.03 : 0)})`;
        context.beginPath();
        context.ellipse(cx, cy, rx * k, ry * k, 0, 0, Math.PI * 2);
        context.stroke();
      });
      // a slow sweep from the core, like a scope
      if (!reduce) {
        const sweep = (now * 0.00035) % (Math.PI * 2);
        drawLine(
          context,
          core,
          { x: cx + Math.cos(sweep) * rx * 1.02, y: cy + Math.sin(sweep) * ry * 1.02 },
          palette.accent,
          0.16,
          1,
        );
      }

      // ------------------------------------------------ ambient field
      const ambient = field.map((dot) => {
        if (!reduce) dot.angle += dot.speed * dt;
        return {
          x: dot.bx * width + Math.cos(dot.angle) * dot.orbit,
          y: dot.by * height + Math.sin(dot.angle) * dot.orbit * 0.7,
          size: dot.size,
          phase: dot.phase,
        };
      });
      const reach = Math.min(130, base * 0.2);
      for (let i = 0; i < ambient.length; i += 1) {
        for (let j = i + 1; j < ambient.length; j += 1) {
          const d = Math.hypot(ambient[i].x - ambient[j].x, ambient[i].y - ambient[j].y);
          if (d < reach) drawLine(context, ambient[i], ambient[j], palette.line, (1 - d / reach) * 0.16, 0.6);
        }
      }

      // ------------------------------------------------ hub to hub ring
      DOMAINS.forEach((domain, index) => {
        const next = DOMAINS[(index + 1) % DOMAINS.length];
        const k = Math.min(intro(index), intro((index + 1) % DOMAINS.length));
        drawLine(context, hubs.get(domain.id)!, hubs.get(next.id)!, palette.line, 0.1 * k, 0.7);
      });

      // ------------------------------------------------ systems
      const near = (p: Point) => {
        if (!pointer.on) return 0;
        const d = Math.hypot(p.x - pointer.x, p.y - pointer.y);
        return d < 150 ? 1 - d / 150 : 0;
      };

      context.font = `600 ${compact ? 9.5 : 10.5}px ${font}`;
      context.textBaseline = "middle";

      DOMAINS.forEach((domain, index) => {
        const entry = list.find((item) => item.id === domain.id);
        const on = builtCount === undefined || index < builtCount;
        const k = intro(index) * (on ? 1 : 0.35);
        const hub = hubs.get(domain.id)!;
        const closed = Boolean(entry?.closed);
        const share = clamp01(entry?.reach ?? 1);
        const hit = struck.current.get(domain.id);
        const sinceHit = hit === undefined ? 99999 : now - hit;
        // coral flares on impact, then holds a coral tint for a while
        const coral = hit === undefined ? 0 : sinceHit < 900 ? 1 : Math.max(0.45, 1 - (sinceHit - 900) / 9000);

        // core to hub: the solid line every question travels
        drawLine(context, core, closed ? gates.get(domain.id)! : hub, closed ? palette.line : palette.accent, (closed ? 0.18 : 0.3) * k, 1);

        // records: tiny dots, lit as far as this person's reach goes
        const seeds = recordSeeds[index];
        const lightCount = Math.round(share * RECORDS);
        seeds.forEach((seed, position) => {
          if (!reduce) seed.angle += seed.speed * dt;
          const p = {
            x: hub.x + Math.cos(seed.angle) * clusterR * seed.distance * 1.45,
            y: hub.y + Math.sin(seed.angle) * clusterR * seed.distance * 1.25,
          };
          const inReach = on && !closed && position < lightCount;
          const twinkle = reduce ? 0.8 : 0.6 + Math.sin(now * 0.002 + seed.phase) * 0.3;
          const proximity = near(p);
          if (inReach) drawLine(context, hub, p, palette.accent, 0.12 * k, 0.6);
          drawNode(
            context,
            p.x,
            p.y,
            seed.size * (1 + proximity * 0.8),
            inReach ? palette.accent : palette.muted,
            k * (inReach ? twinkle : 0.35 + proximity * 0.3),
            inReach ? 0.5 + proximity : 0.2,
          );
        });

        // the queries that read this system
        (entry?.capabilities ?? []).forEach((capability) => {
          const p = caps.get(capability.name);
          if (!p) return;
          const lastLit = glow.current.get(capability.name);
          const flare = lastLit === undefined ? 0 : clamp01(1 - (now - lastLit) / 2600);
          const isLit = litNow.includes(capability.name);
          const allowed = capability.allowed && !closed;
          const proximity = near(p);
          drawLine(context, hub, p, allowed ? palette.accent : palette.line, (allowed ? 0.42 : 0.2) * k + flare * 0.4, allowed ? 1 : 0.8);
          drawNode(
            context,
            p.x,
            p.y,
            (isLit ? 3.6 : 2.4) * (1 + flare * 0.6 + proximity * 0.4),
            allowed ? (isLit || flare > 0 ? "255,255,255" : palette.accent) : palette.muted,
            k * (allowed ? 0.95 : 0.5),
            allowed ? 0.7 + flare * 1.4 + (isLit ? 0.8 : 0) + proximity * 0.6 : 0.2,
          );
        });

        // the hub itself
        const beat = reduce ? 0.5 : (Math.sin(now * 0.0026 + index * 1.7) + 1) / 2;
        const hubTone = closed ? palette.light : palette.accent;
        drawNode(context, hub.x, hub.y, (compact ? 4 : 5) * (1 + near(hub) * 0.35), hubTone, k, 0.9 + beat * 0.5 + near(hub));

        // the permission ring: a gap towards the core when open, whole when closed
        const ringTone = coral > 0 ? palette.fail : closed ? palette.light : palette.accent;
        const ringAlpha = k * (coral > 0 ? 0.55 + coral * 0.4 : closed ? 0.55 : 0.32);
        const ringWidth = coral > 0 ? 1.6 + coral : closed ? 1.5 : 1;
        context.strokeStyle = `rgba(${ringTone},${ringAlpha})`;
        context.lineWidth = ringWidth;
        context.beginPath();
        if (closed) {
          context.arc(hub.x, hub.y, ringR, 0, Math.PI * 2);
        } else {
          const towards = Math.atan2(cy - hub.y, cx - hub.x);
          const opening = 0.42;
          context.arc(hub.x, hub.y, ringR, towards + opening, towards - opening + Math.PI * 2);
        }
        context.stroke();
        if (closed) {
          // a second, tighter ring: the door is shut on both sides
          drawRing(context, hub, ringR + 5, coral > 0 ? palette.fail : palette.light, k * (coral > 0 ? 0.35 * coral : 0.14), 1);
        }

        // label
        const angle = -Math.PI / 2 + (index / DOMAINS.length) * Math.PI * 2;
        const side = Math.cos(angle) < -0.3 ? "left" : Math.cos(angle) > 0.3 ? "right" : Math.sin(angle) < 0 ? "above" : "below";
        drawPill(
          context,
          hub,
          ringR + (closed ? 10 : 6),
          side,
          (compact ? domain.short : domain.label).toUpperCase(),
          compact ? "" : entry?.sub ?? "",
          coral > 0.5 ? palette.fail : closed ? palette.light : palette.accent,
          palette,
          k,
          compact,
        );
      });

      // ------------------------------------------------ the document
      if (docOn) {
        drawLine(context, doc, core, palette.fail, 0.3, 1);
        drawNode(context, doc.x, doc.y, 3.4, palette.fail, 1, 1);
        drawRing(context, doc, 9, palette.fail, 0.5, 1);
        drawPill(context, doc, 12, "below", "ATTACHED DOCUMENT", compact ? "" : "read as text only", palette.fail, palette, 1, compact);
      }

      // ------------------------------------------------ idle traffic
      if (!reduce && idleOn && now - lastPlay.current > 5200 && now - lastIdle > 1500 && age > 1800) {
        lastIdle = now;
        const open = list.filter((item) => !item.closed && item.capabilities.some((c) => c.allowed));
        const pick = open[Math.floor(Math.random() * Math.max(1, open.length))];
        if (pick) {
          const allowed = pick.capabilities.filter((c) => c.allowed);
          const capability = allowed[Math.floor(Math.random() * allowed.length)];
          comets.current.push({
            points: () => {
              const target = capability ? caps.get(capability.name) : null;
              const hub = hubs.get(pick.id)!;
              return target ? [core, hub, target] : [core, hub];
            },
            start: now,
            duration: 1200,
            rgb: "accent",
            size: 2.2,
            arrived: 0,
          });
        }
      }

      // ------------------------------------------------ comets
      for (let index = comets.current.length - 1; index >= 0; index -= 1) {
        const item = comets.current[index];
        const elapsed = now - item.start;
        if (elapsed < 0) continue;
        const points = item.points();
        const fraction = clamp01(elapsed / item.duration);
        const fade = item.arrived ? clamp01(1 - (now - item.arrived) / 700) : 1;
        drawPartialPolyline(context, points, fraction, palette[item.rgb] as string, 0.6 * fade, 1.5);
        if (fraction < 1) {
          drawComet(context, points, fraction, palette[item.rgb] as string, item.size);
        } else if (!item.arrived) {
          item.arrived = now;
          item.onArrive?.();
        }
        if (item.arrived && fade <= 0) comets.current.splice(index, 1);
      }

      // ------------------------------------------------ ripples
      for (let index = ripples.current.length - 1; index >= 0; index -= 1) {
        const ripple = ripples.current[index];
        const t = (now - ripple.start) / 1100;
        if (t >= 1) {
          ripples.current.splice(index, 1);
          continue;
        }
        const at = ripple.at();
        drawRing(context, at, 4 + t * ripple.size, palette[ripple.rgb] as string, (1 - t) * 0.8, 1.6);
        drawRing(context, at, 2 + t * ripple.size * 0.55, palette[ripple.rgb] as string, (1 - t) * 0.5, 1);
      }

      // ------------------------------------------------ pointer lines
      if (pointer.on) {
        const candidates: { p: Point; k: number }[] = [];
        for (const p of ambient) {
          const k = near(p);
          if (k > 0.25) candidates.push({ p, k });
        }
        hubs.forEach((p) => {
          const k = near(p);
          if (k > 0.15) candidates.push({ p, k: k + 0.3 });
        });
        caps.forEach((p) => {
          const k = near(p);
          if (k > 0.2) candidates.push({ p, k: k + 0.15 });
        });
        candidates
          .sort((a, b) => b.k - a.k)
          .slice(0, 6)
          .forEach(({ p, k }) => drawLine(context, p, pointer, palette.accent, Math.min(0.7, k * 0.6), 1));
      }

      // ------------------------------------------------ ambient nodes
      for (const p of ambient) {
        const k = near(p);
        const twinkle = reduce ? 0.6 : 0.45 + Math.sin(now * 0.0015 + p.phase) * 0.3;
        drawNode(context, p.x, p.y, p.size * (1 + k * 0.9), k > 0.3 ? palette.accent : palette.muted, Math.min(1, twinkle + k * 0.6), 0.5 + k);
      }

      // ------------------------------------------------ the core
      const beat = reduce ? 0.5 : (Math.sin(now * 0.003) + 1) / 2;
      const coreR = compact ? 7 : 9;
      drawRing(context, core, coreR + 9 + beat * 4, palette.accent, 0.45, 1.2);
      drawRing(context, core, coreR + 20 + beat * 7, palette.accent, 0.18, 1);
      drawNode(context, core.x, core.y, coreR * (1 + near(core) * 0.2), palette.accent, 1, 1.6 + beat * 0.6);
      drawNode(context, core.x, core.y, coreR * 0.42, "255,255,255", 0.95, 0);
      drawPill(context, core, coreR + 26, "below", "OPSAGENT", compact ? "" : "picks from reviewed queries", palette.accent, palette, 1, compact);
    };

    const tick = (now: number) => {
      const dt = Math.min(48, now - last);
      last = now;
      draw(now, dt);
      if (running) frame = requestAnimationFrame(tick);
    };
    const start = () => {
      if (running || reduce || !onScreen || window.document.visibilityState === "hidden") return;
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
    window.document.fonts?.ready.then(() => {
      font = getComputedStyle(canvas).fontFamily || font;
      still();
    });

    const visibility = new IntersectionObserver(
      ([entry]) => {
        onScreen = entry.isIntersecting;
        if (onScreen) start();
        else stop();
      },
      { rootMargin: "40px 0px" },
    );
    visibility.observe(canvas);
    const sizing = new ResizeObserver(() => {
      resize();
      palette = readPalette(canvas, "dark");
      still();
    });
    sizing.observe(canvas);
    const onVisibility = () => (window.document.visibilityState === "hidden" ? stop() : start());
    window.document.addEventListener("visibilitychange", onVisibility);
    const onMove = (event: PointerEvent) => {
      if (event.pointerType === "touch") return;
      const box = canvas.getBoundingClientRect();
      pointer.x = event.clientX - box.left;
      pointer.y = event.clientY - box.top;
      pointer.on = pointer.x >= -30 && pointer.y >= -30 && pointer.x <= box.width + 30 && pointer.y <= box.height + 30;
      if (reduce) still();
    };
    const onLeave = () => {
      pointer.on = false;
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    window.document.addEventListener("pointerleave", onLeave);

    return () => {
      stop();
      redraw.current = () => undefined;
      visibility.disconnect();
      sizing.disconnect();
      window.document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onMove);
      window.document.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={`ds-constellation ${className}`}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
    />
  );
});

function drawPill(
  context: CanvasRenderingContext2D,
  at: Point,
  gap: number,
  side: "left" | "right" | "above" | "below",
  text: string,
  sub: string,
  rgb: string,
  palette: Palette,
  alpha: number,
  compact: boolean,
) {
  if (alpha <= 0.02) return;
  const padX = compact ? 6 : 8;
  const lineH = compact ? 13 : 15;
  const width = Math.max(context.measureText(text).width, sub ? context.measureText(sub).width : 0) + padX * 2;
  const heightBox = sub ? lineH * 2 + 6 : lineH + 6;
  let x = at.x + gap;
  let y = at.y - heightBox / 2;
  if (side === "left") x = at.x - gap - width;
  if (side === "above") {
    x = at.x - width / 2;
    y = at.y - gap - heightBox;
  }
  if (side === "below") {
    x = at.x - width / 2;
    y = at.y + gap;
  }
  const box = context.canvas.getBoundingClientRect();
  x = Math.max(4, Math.min(box.width - width - 4, x));
  y = Math.max(4, Math.min(box.height - heightBox - 4, y));
  context.globalAlpha = alpha;
  roundedRect(context, x, y, width, heightBox, 2);
  context.fillStyle = "rgb(12,24,46)";
  context.fill();
  context.strokeStyle = `rgba(${rgb},0.55)`;
  context.lineWidth = 1;
  context.stroke();
  context.fillStyle = `rgba(${palette.labelText},0.95)`;
  context.fillText(text, x + padX, y + 3 + lineH / 2);
  if (sub) {
    context.fillStyle = `rgb(${rgb})`;
    context.fillText(sub, x + padX, y + 3 + lineH + lineH / 2);
  }
  context.globalAlpha = 1;
}
