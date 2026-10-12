"use client";

/**
 * DemandField - StockSense's signature canvas.
 *
 * Real parts from this week's plan, drawn as nodes around the suppliers they
 * come from, joined by thin solid lines. A clock walks through their real
 * two years of weekly sales: a part sparks in the weeks it sold something
 * and sits dark in the weeks it did not, which for this catalogue is most of
 * them. Meanwhile the week's orders leave their parts one at a time and run
 * along the solid lines, through the supplier, into the cash-cap gauge,
 * which fills by each order's real cost until the plan's own committed
 * total is reached; then it empties and the round starts again.
 *
 * Suppliers that run late carry an amber ring. When the clock passes a
 * Lunar New Year in the history, the clusters whose country shut for it dim
 * and stop moving until the plants reopen.
 *
 * - Pauses off screen and in a background tab.
 * - prefers-reduced-motion: one still frame, gauge at the plan's real fill.
 * - The pointer brightens nodes near it and draws a line to the nearest.
 * - Decorative to assistive technology except for its label: every figure it
 *   shows is also on the page in text.
 */

import { useEffect, useRef } from "react";

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

export type FieldSupplier = {
  id: number;
  name: string;
  place: string;
  late: boolean;
  slipDays: number;
  /** Week ranges of the history in which this supplier's country was shut. */
  closed: [number, number][];
};

export type FieldPart = {
  id: number;
  code: string;
  supplierId: number;
  /** Real weekly sales, oldest first; null until loaded. */
  sold: number[] | null;
  /** Cash this week's order commits, 0 when it is not bought. */
  value: number;
  bought: boolean;
  prebuild: boolean;
  decisionWords: string;
};

type Props = {
  suppliers: FieldSupplier[];
  parts: FieldPart[];
  cap: number;
  committed: number;
  linesBought: number;
  /** Monday of week 0 of the history, ISO. */
  startsOn: string | null;
  activeId: number | null;
  label: string;
  className?: string;
};

const WEEK_MS = 780;
const PULSE_MS = 1650;
const MONTHS = [
  "JANUARY",
  "FEBRUARY",
  "MARCH",
  "APRIL",
  "MAY",
  "JUNE",
  "JULY",
  "AUGUST",
  "SEPTEMBER",
  "OCTOBER",
  "NOVEMBER",
  "DECEMBER",
];

type Placed = { x: number; y: number; bx: number; by: number; angle: number; speed: number; orbit: number };
type Pulse = {
  path: string[];
  start: number;
  duration: number;
  tone: "accent" | "warn";
  value: number;
  arrived: number;
  final?: boolean;
};
type Ripple = { x: number; y: number; start: number; tone: string; size: number };

export function DemandField({
  suppliers,
  parts,
  cap,
  committed,
  linesBought,
  startsOn,
  activeId,
  label,
  className = "",
}: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const props = useRef({ suppliers, parts, cap, committed, linesBought, startsOn, activeId });
  props.current = { suppliers, parts, cap, committed, linesBought, startsOn, activeId };
  const redraw = useRef<() => void>(() => undefined);
  const relayout = useRef<() => void>(() => undefined);

  useEffect(() => {
    relayout.current();
    redraw.current();
  }, [suppliers, parts, cap, committed, activeId]);

  useEffect(() => {
    const canvas = canvasRef.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let palette: Palette = readPalette(canvas, "dark");
    let mono = getComputedStyle(canvas).fontFamily || "monospace";
    let display = getComputedStyle(document.body).fontFamily || "sans-serif";
    let width = 0;
    let height = 0;
    let compact = false;
    let frame = 0;
    let running = false;
    let onScreen = false;
    let last = performance.now();
    let clock = 0;
    const pointer = { x: 0, y: 0, on: false };

    // ------------------------------------------------------------ state
    const random = seeded(20261012);
    const ambient = Array.from({ length: 54 }, () => ({
      bx: random(),
      by: random(),
      angle: random() * Math.PI * 2,
      speed: (0.00005 + random() * 0.0001) * (random() < 0.5 ? -1 : 1),
      orbit: 5 + random() * 18,
      size: 0.6 + random() * 1.1,
      phase: random() * Math.PI * 2,
    }));
    const hubs = new Map<number, Placed>();
    const nodes = new Map<number, Placed>();
    const lit = new Map<number, number>();
    const pulses: Pulse[] = [];
    const ripples: Ripple[] = [];
    let gauge = { x: 0, y: 0, r: 40 };
    let fill = 0;
    let fillTarget = 0;
    let queueIndex = 0;
    let lastPulse = -PULSE_MS;
    let phase: "lines" | "rest" | "hold" | "empty" = "lines";
    let phaseStart = 0;
    let week = 0;
    let weekStarted = 0;
    let started = false;

    const weeksOf = () => Math.max(1, ...props.current.parts.map((part) => part.sold?.length ?? 0), 104);

    const layout = () => {
      const { suppliers: list, parts: items } = props.current;
      compact = width < 560;
      gauge = {
        x: width * (compact ? 0.77 : 0.76),
        y: height * (compact ? 0.27 : 0.3),
        r: Math.max(compact ? 38 : 56, Math.min(width, height) * (compact ? 0.16 : 0.17)),
      };
      const count = Math.max(1, list.length);
      const cx = width * (compact ? 0.47 : 0.43);
      const cy = height * (compact ? 0.64 : 0.44);
      const rx = width * (compact ? 0.32 : 0.29);
      const ry = height * (compact ? 0.27 : 0.25);
      list.forEach((supplier, index) => {
        const t = count === 1 ? 0.5 : index / (count - 1);
        const angle = Math.PI * (0.55 + 0.92 * t);
        const r = seeded(supplier.id * 31 + 7);
        const previous = hubs.get(supplier.id);
        const bx = cx + Math.cos(angle) * rx;
        const by = cy + Math.sin(angle) * ry;
        hubs.set(supplier.id, {
          bx,
          by,
          x: previous?.x ?? bx,
          y: previous?.y ?? by,
          angle: previous?.angle ?? r() * Math.PI * 2,
          speed: (0.00012 + r() * 0.00012) * (r() < 0.5 ? -1 : 1),
          orbit: 3,
        });
      });
      for (const id of Array.from(hubs.keys())) {
        if (!list.some((supplier) => supplier.id === id)) hubs.delete(id);
      }
      const bySupplier = new Map<number, FieldPart[]>();
      items.forEach((part) => {
        const group = bySupplier.get(part.supplierId) ?? [];
        group.push(part);
        bySupplier.set(part.supplierId, group);
      });
      nodes.clear();
      bySupplier.forEach((group, supplierId) => {
        const hub = hubs.get(supplierId);
        if (!hub) return;
        const away = Math.atan2(hub.by - gauge.y, hub.bx - gauge.x);
        group.forEach((part, index) => {
          const spread = group.length === 1 ? 0 : (index / (group.length - 1) - 0.5) * 2.4;
          const angle = away + spread;
          const distance = (compact ? 30 : 44) + (index % 2) * (compact ? 12 : 18);
          const r = seeded(part.id * 17 + 3);
          nodes.set(part.id, {
            bx: hub.bx + Math.cos(angle) * distance,
            by: hub.by + Math.sin(angle) * distance,
            x: 0,
            y: 0,
            angle: r() * Math.PI * 2,
            speed: (0.0002 + r() * 0.00025) * (r() < 0.5 ? -1 : 1),
            orbit: 2.5 + r() * 3,
          });
        });
      });
    };
    relayout.current = layout;

    const resize = () => {
      const box = canvas.getBoundingClientRect();
      width = box.width;
      height = box.height;
      canvas.width = Math.max(1, Math.round(width * dpr));
      canvas.height = Math.max(1, Math.round(height * dpr));
      context.setTransform(dpr, 0, 0, dpr, 0, 0);
      layout();
    };

    const closedNow = (supplier: FieldSupplier | undefined) =>
      Boolean(supplier?.closed.some(([from, to]) => week >= from && week <= to));

    const pointOf = (key: string): Point | null => {
      if (key === "gauge") return gauge;
      const [kind, id] = key.split(":");
      const placed = kind === "h" ? hubs.get(Number(id)) : nodes.get(Number(id));
      return placed ? { x: placed.x, y: placed.y } : null;
    };

    const near = (p: Point) => {
      if (!pointer.on) return 0;
      const d = Math.hypot(p.x - pointer.x, p.y - pointer.y);
      return d < 140 ? 1 - d / 140 : 0;
    };

    const queue = () => props.current.parts.filter((part) => part.bought && part.value > 0);

    const sendNext = (now: number) => {
      const { cap: total } = props.current;
      const list = queue();
      if (phase === "lines") {
        if (queueIndex < list.length) {
          const part = list[queueIndex];
          queueIndex += 1;
          pulses.push({
            path: [`p:${part.id}`, `h:${part.supplierId}`, "gauge"],
            start: now,
            duration: 1500,
            tone: part.prebuild ? "warn" : "accent",
            value: total > 0 ? part.value / total : 0,
            arrived: 0,
          });
          lit.set(part.id, 1);
          return;
        }
        // The rest of the week's lines, as one burst from every supplier.
        phase = "rest";
        phaseStart = now;
        const ids = props.current.suppliers.map((supplier) => supplier.id);
        if (!ids.length) {
          fillTarget = props.current.cap > 0 ? clamp01(props.current.committed / props.current.cap) : 0;
          phase = "hold";
          return;
        }
        ids.forEach((id, index) => {
          pulses.push({
            path: [`h:${id}`, "gauge"],
            start: now + index * 110,
            duration: 1000,
            tone: "accent",
            value: 0,
            arrived: 0,
            final: index === ids.length - 1,
          });
        });
      }
    };

    const draw = (now: number, dt: number) => {
      clock = now;
      context.clearRect(0, 0, width, height);
      if (width < 4 || height < 4) return;
      const { suppliers: list, parts: items, cap: total, committed: spent, linesBought: bought, startsOn: start, activeId: active } =
        props.current;
      const target = total > 0 ? clamp01(spent / total) : 0;
      const weeks = weeksOf();

      // ------------------------------------------------ the week clock
      if (!started) {
        started = true;
        week = Math.min(weeks - 1, Math.max(0, weeks - 40));
        weekStarted = now;
        // Open on the plan's real fill, swept in; the replay of the orders follows.
        fillTarget = target;
        phase = "hold";
        phaseStart = now;
      }
      if (!reduce && now - weekStarted >= WEEK_MS) {
        weekStarted = now;
        week = (week + 1) % weeks;
        for (const part of items) {
          const quantity = part.sold?.[week] ?? 0;
          if (quantity > 0) {
            const peak = Math.max(1, ...(part.sold ?? [1]));
            const size = 0.45 + 0.55 * clamp01(Math.log10(1 + quantity) / Math.log10(1 + peak));
            lit.set(part.id, Math.max(lit.get(part.id) ?? 0, size));
            const node = nodes.get(part.id);
            if (node) ripples.push({ x: node.x, y: node.y, start: now, tone: palette.accent, size });
          }
        }
      }

      // ------------------------------------------------ positions
      for (const [id, hub] of hubs) {
        const supplier = list.find((item) => item.id === id);
        if (!reduce && !closedNow(supplier)) hub.angle += hub.speed * dt;
        hub.x = hub.bx + Math.cos(hub.angle) * (reduce ? 0 : hub.orbit);
        hub.y = hub.by + Math.sin(hub.angle) * (reduce ? 0 : hub.orbit) * 0.8;
      }
      for (const part of items) {
        const node = nodes.get(part.id);
        const hub = hubs.get(part.supplierId);
        if (!node || !hub) continue;
        const supplier = list.find((item) => item.id === part.supplierId);
        if (!reduce && !closedNow(supplier)) node.angle += node.speed * dt;
        const dx = hub.x - hub.bx;
        const dy = hub.y - hub.by;
        node.x = node.bx + dx + Math.cos(node.angle) * (reduce ? 0 : node.orbit);
        node.y = node.by + dy + Math.sin(node.angle) * (reduce ? 0 : node.orbit) * 0.8;
      }

      // ------------------------------------------------ ambient catalogue
      const field = ambient.map((dot) => {
        if (!reduce) dot.angle += dot.speed * dt;
        return {
          x: dot.bx * width + Math.cos(dot.angle) * dot.orbit,
          y: dot.by * height + Math.sin(dot.angle) * dot.orbit * 0.7,
          size: dot.size,
          phase: dot.phase,
        };
      });
      const reach = compact ? 80 : 108;
      for (let i = 0; i < field.length; i += 1) {
        for (let j = i + 1; j < field.length; j += 1) {
          const a = field[i];
          const b = field[j];
          const dx = a.x - b.x;
          if (dx > reach || dx < -reach) continue;
          const dy = a.y - b.y;
          if (dy > reach || dy < -reach) continue;
          const d = Math.hypot(dx, dy);
          if (d < reach) drawLine(context, a, b, palette.line, (1 - d / reach) * 0.17, 0.6);
        }
      }

      // ------------------------------------------------ solid links
      for (const supplier of list) {
        const hub = hubs.get(supplier.id);
        if (!hub) continue;
        const closed = closedNow(supplier);
        drawLine(
          context,
          hub,
          gauge,
          supplier.late ? palette.warn : palette.line,
          closed ? 0.05 : supplier.late ? 0.16 : 0.18,
          0.9,
        );
      }
      for (const part of items) {
        const node = nodes.get(part.id);
        const hub = hubs.get(part.supplierId);
        if (!node || !hub) continue;
        const glow = lit.get(part.id) ?? 0;
        const supplier = list.find((item) => item.id === part.supplierId);
        const closed = closedNow(supplier);
        drawLine(
          context,
          node,
          hub,
          glow > 0.05 ? palette.accent : palette.line,
          (closed ? 0.08 : 0.2) + glow * 0.45,
          0.8 + glow * 0.6,
        );
      }

      // ------------------------------------------------ the cash gauge
      if (reduce) fill = target;
      fill += (fillTarget - fill) * (reduce ? 1 : 1 - Math.pow(0.004, dt / 1000));
      drawRing(context, gauge, gauge.r, palette.line, 0.42, 1);
      drawRing(context, gauge, gauge.r - 9, palette.line, 0.16, 1);
      for (let tick = 0; tick < 40; tick += 1) {
        const a = -Math.PI / 2 + (tick / 40) * Math.PI * 2;
        const inner = gauge.r + 4;
        const outer = gauge.r + (tick % 10 === 0 ? 10 : 7);
        drawLine(
          context,
          { x: gauge.x + Math.cos(a) * inner, y: gauge.y + Math.sin(a) * inner },
          { x: gauge.x + Math.cos(a) * outer, y: gauge.y + Math.sin(a) * outer },
          tick / 40 <= fill ? palette.accent : palette.line,
          tick / 40 <= fill ? 0.9 : 0.25,
          1,
        );
      }
      {
        const mark = -Math.PI / 2 + Math.PI * 2 * target;
        drawLine(
          context,
          { x: gauge.x + Math.cos(mark) * (gauge.r - 14), y: gauge.y + Math.sin(mark) * (gauge.r - 14) },
          { x: gauge.x + Math.cos(mark) * (gauge.r + 14), y: gauge.y + Math.sin(mark) * (gauge.r + 14) },
          palette.light,
          0.85,
          1.5,
        );
      }
      if (fill > 0.001) {
        context.strokeStyle = `rgb(${palette.accent})`;
        context.lineWidth = compact ? 4 : 6;
        context.lineCap = "butt";
        context.beginPath();
        context.arc(gauge.x, gauge.y, gauge.r, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * Math.min(1, fill));
        context.stroke();
        const head = -Math.PI / 2 + Math.PI * 2 * Math.min(1, fill);
        drawNode(
          context,
          gauge.x + Math.cos(head) * gauge.r,
          gauge.y + Math.sin(head) * gauge.r,
          compact ? 3 : 3.6,
          palette.accent,
          1,
          1.8,
        );
      }
      context.textAlign = "center";
      context.textBaseline = "middle";
      context.fillStyle = `rgba(${palette.labelText},0.96)`;
      context.font = `600 ${Math.round(gauge.r * 0.46)}px ${display}`;
      context.fillText(`${Math.round(fill * 100)}%`, gauge.x, gauge.y - gauge.r * 0.08);
      context.font = `600 ${compact ? 8.5 : 9.5}px ${mono}`;
      context.fillStyle = `rgba(${palette.light},0.62)`;
      context.fillText("OF THE CASH CAP", gauge.x, gauge.y + gauge.r * 0.34);
      if (phase === "hold" || (reduce && bought > 0)) {
        context.fillStyle = `rgb(${palette.accent})`;
        context.font = `600 ${compact ? 9 : 10.5}px ${mono}`;
        context.fillText(
          `${bought.toLocaleString("en-GB")} LINES BOUGHT`,
          gauge.x,
          gauge.y + gauge.r + (compact ? 22 : 26),
        );
      } else {
        context.fillStyle = `rgba(${palette.light},0.55)`;
        context.font = `600 ${compact ? 9 : 10}px ${mono}`;
        context.fillText("THIS WEEK'S ORDERS", gauge.x, gauge.y + gauge.r + (compact ? 22 : 26));
      }
      context.textAlign = "left";

      // ------------------------------------------------ the order pulses
      if (!reduce && items.length) {
        if (phase === "lines" && now - lastPulse > PULSE_MS) {
          lastPulse = now;
          sendNext(now);
        }
        if (phase === "hold" && now - phaseStart > 3600) {
          phase = "empty";
          phaseStart = now;
          fillTarget = 0;
        }
        if (phase === "empty" && now - phaseStart > 1400) {
          phase = "lines";
          queueIndex = 0;
          lastPulse = now - PULSE_MS * 0.6;
        }
      }
      for (let index = pulses.length - 1; index >= 0; index -= 1) {
        const pulse = pulses[index];
        const elapsed = now - pulse.start;
        if (elapsed < 0) continue;
        const points = pulse.path.map(pointOf).filter(Boolean) as Point[];
        if (points.length < 2) {
          pulses.splice(index, 1);
          continue;
        }
        const fraction = clamp01(elapsed / pulse.duration);
        const fade = pulse.arrived ? clamp01(1 - (now - pulse.arrived) / 600) : 1;
        const rgb = pulse.tone === "warn" ? palette.warn : palette.accent;
        drawPartialPolyline(context, points, fraction, rgb, 0.5 * fade, 1.3);
        if (fraction < 1) {
          drawComet(context, points, fraction, rgb, compact ? 2.4 : 2.9);
        } else if (!pulse.arrived) {
          pulse.arrived = now;
          fillTarget = Math.min(1, fillTarget + pulse.value);
          ripples.push({ x: gauge.x, y: gauge.y, start: now, tone: rgb, size: 1.6 });
          if (pulse.final) {
            fillTarget = target;
            phase = "hold";
            phaseStart = now;
          }
        }
        if (pulse.arrived && fade <= 0) pulses.splice(index, 1);
      }

      // ------------------------------------------------ ripples
      for (let index = ripples.length - 1; index >= 0; index -= 1) {
        const ripple = ripples[index];
        const t = (now - ripple.start) / 900;
        if (t >= 1) {
          ripples.splice(index, 1);
          continue;
        }
        const big = ripple.x === gauge.x && ripple.y === gauge.y;
        drawRing(
          context,
          ripple,
          (big ? gauge.r : 3) + t * (big ? 18 : 14 * ripple.size),
          ripple.tone,
          (1 - t) * (big ? 0.5 : 0.75),
          1.1,
        );
      }

      // ------------------------------------------------ pointer threads
      if (pointer.on) {
        const candidates: { p: Point; k: number }[] = [];
        for (const p of field) {
          const k = near(p);
          if (k > 0.3) candidates.push({ p, k });
        }
        for (const node of nodes.values()) {
          const k = near(node);
          if (k > 0.15) candidates.push({ p: node, k: k + 0.25 });
        }
        candidates
          .sort((a, b) => b.k - a.k)
          .slice(0, 6)
          .forEach(({ p, k }) => drawLine(context, p, pointer, palette.accent, Math.min(0.75, k * 0.7), 1));
      }

      // ------------------------------------------------ ambient nodes
      for (const p of field) {
        const k = near(p);
        const twinkle = reduce ? 0.45 : 0.32 + Math.sin(now * 0.0014 + p.phase) * 0.18;
        drawNode(context, p.x, p.y, p.size * (1 + k * 0.8), k > 0.3 ? palette.accent : palette.muted, twinkle + k * 0.5, 0.4 + k);
      }

      // ------------------------------------------------ parts
      let hovered: { part: FieldPart; node: Placed } | null = null;
      for (const part of items) {
        const node = nodes.get(part.id);
        if (!node) continue;
        const supplier = list.find((item) => item.id === part.supplierId);
        const closed = closedNow(supplier);
        const glow = lit.get(part.id) ?? 0;
        if (!reduce && glow > 0) lit.set(part.id, Math.max(0, glow - dt / 900));
        const k = near(node);
        if (pointer.on && Math.hypot(node.x - pointer.x, node.y - pointer.y) < 14) hovered = { part, node };
        const isActive = part.id === active;
        const radius = (compact ? 2 : 2.4) * (1 + glow * 1.3 + k * 0.5 + (isActive ? 0.5 : 0));
        const tone = glow > 0.05 || isActive ? (part.prebuild ? palette.warn : palette.accent) : palette.light;
        drawNode(
          context,
          node.x,
          node.y,
          radius,
          tone,
          Math.min(1, (closed ? 0.3 : 0.42) + glow * 0.6 + k * 0.4 + (isActive ? 0.5 : 0)),
          0.25 + glow * 1.6 + k * 0.8 + (isActive ? 1 : 0),
        );
        if (isActive) {
          const beat = reduce ? 0 : (Math.sin(now * 0.004) + 1) / 2;
          drawRing(context, node, radius + 6 + beat * 3, tone, 0.6, 1.1);
          drawRing(context, node, radius + 13 + beat * 5, tone, 0.22, 1);
        }
      }

      // ------------------------------------------------ suppliers
      context.font = `500 10.5px ${mono}`;
      context.textBaseline = "middle";
      for (const supplier of list) {
        const hub = hubs.get(supplier.id);
        if (!hub) continue;
        const closed = closedNow(supplier);
        const rgb = closed ? palette.muted : supplier.late ? palette.warn : palette.light;
        const k = near(hub);
        if (supplier.late && !closed) {
          const beat = reduce ? 0 : (Math.sin(now * 0.0026 + supplier.id) + 1) / 2;
          drawRing(context, hub, 9 + beat * 3, palette.warn, 0.5, 1);
        }
        if (closed) drawRing(context, hub, 11, palette.warn, 0.35, 1);
        drawNode(context, hub.x, hub.y, compact ? 3.4 : 4.2, rgb, closed ? 0.45 : 0.95, closed ? 0.3 : 0.9 + k);
        if (!compact || closed) {
          const sub = closed
            ? "CLOSED · LUNAR NEW YEAR"
            : supplier.late
              ? `${supplier.place.toUpperCase()} · ${Math.round(supplier.slipDays)} DAYS LATE`
              : supplier.place.toUpperCase();
          drawPill(context, hub, compact ? supplier.name.split(" ")[0] : supplier.name, sub, closed ? palette.warn : rgb, palette, closed ? 0.6 : 0.92, compact);
        }
      }

      // ------------------------------------------------ hover and active labels
      const activePart = items.find((part) => part.id === active);
      const activeNode = activePart ? nodes.get(activePart.id) : undefined;
      if (activePart && activeNode) {
        drawTag(context, activeNode, activePart.code, activePart.decisionWords.toUpperCase(), activePart.prebuild ? palette.warn : palette.accent, palette, width);
      }
      if (hovered && hovered.part.id !== active) {
        drawTag(context, hovered.node, hovered.part.code, hovered.part.decisionWords.toUpperCase(), palette.light, palette, width);
      }

      // ------------------------------------------------ the week stamp
      const date = start ? new Date(`${start}T00:00:00`) : null;
      if (date) date.setDate(date.getDate() + week * 7);
      context.font = `600 ${compact ? 9.5 : 10.5}px ${mono}`;
      context.fillStyle = `rgba(${palette.light},0.6)`;
      const line1 = date
        ? `SALES · WEEK OF ${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`
        : "SALES HISTORY";
      context.fillText(line1, 2, compact ? 12 : 14);
      context.fillStyle = `rgba(${palette.light},0.38)`;
      context.fillText(`WEEK ${week + 1} OF ${weeks} · A NODE LIGHTS WHEN THE PART SOLD`, 2, compact ? 27 : 31);
      void clock;
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
      weekStarted = last - (clock ? 0 : WEEK_MS * 0.5);
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
      mono = getComputedStyle(canvas).fontFamily || mono;
      display = getComputedStyle(document.body).fontFamily || display;
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
    const onVisibility = () => (document.visibilityState === "hidden" ? stop() : start());
    document.addEventListener("visibilitychange", onVisibility);
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
    document.addEventListener("pointerleave", onLeave);

    return () => {
      stop();
      redraw.current = () => undefined;
      relayout.current = () => undefined;
      visibility.disconnect();
      sizing.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      window.removeEventListener("pointermove", onMove);
      document.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className={`ds-constellation ${className}`}
      role="img"
      aria-label={label}
    />
  );
}

/** A supplier's name in a small solid pill beside its node. */
function drawPill(
  context: CanvasRenderingContext2D,
  at: Point,
  text: string,
  sub: string,
  rgb: string,
  palette: Palette,
  alpha: number,
  compact: boolean,
) {
  const padX = 7;
  const lineH = 13;
  context.font = `600 ${compact ? 9.5 : 10.5}px ${context.font.split("px ")[1] ?? "monospace"}`;
  const textWidth = Math.max(context.measureText(text).width, context.measureText(sub).width);
  const boxW = textWidth + padX * 2;
  const boxH = lineH * 2 + 6;
  const x = at.x - boxW - 12;
  const y = at.y - boxH / 2;
  context.globalAlpha = alpha;
  roundedRect(context, Math.max(2, x), y, boxW, boxH, 3);
  context.fillStyle = `rgb(${palette.labelFill})`;
  context.fill();
  context.strokeStyle = `rgb(${palette.labelLine})`;
  context.lineWidth = 1;
  context.stroke();
  context.fillStyle = `rgba(${palette.labelText},0.94)`;
  context.fillText(text, Math.max(2, x) + padX, y + 3 + lineH / 2);
  context.fillStyle = `rgb(${rgb})`;
  context.fillText(sub, Math.max(2, x) + padX, y + 3 + lineH + lineH / 2);
  context.globalAlpha = 1;
}

/** The part a person is looking at: its number and what the plan does with it. */
function drawTag(
  context: CanvasRenderingContext2D,
  at: Point,
  code: string,
  sub: string,
  rgb: string,
  palette: Palette,
  width: number,
) {
  const padX = 8;
  const lineH = 14;
  const textWidth = Math.max(context.measureText(code).width, context.measureText(sub).width);
  const boxW = textWidth + padX * 2;
  const boxH = lineH * 2 + 8;
  let x = at.x + 16;
  if (x + boxW > width - 4) x = at.x - 16 - boxW;
  const y = at.y - boxH - 8;
  roundedRect(context, x, y, boxW, boxH, 3);
  context.fillStyle = `rgb(${palette.labelFill})`;
  context.fill();
  context.strokeStyle = `rgb(${rgb})`;
  context.lineWidth = 1.2;
  context.stroke();
  context.fillStyle = `rgba(${palette.labelText},0.96)`;
  context.fillText(code, x + padX, y + 4 + lineH / 2);
  context.fillStyle = `rgb(${rgb})`;
  context.fillText(sub, x + padX, y + 4 + lineH + lineH / 2);
}
