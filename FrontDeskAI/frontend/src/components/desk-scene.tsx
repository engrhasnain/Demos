"use client";

/**
 * FrontDesk's signature: the two-channel conversation constellation.
 *
 * Customers arrive on two channels - the website (light) and LINE (green) -
 * each its own cluster on the left. Every customer is joined by a thin solid
 * line to the identity ring around the assistant in the middle. Nothing gets
 * past the ring without verification: a visitor's pulse that has not proved
 * who it is stops at the ring, and the ring flashes.
 *
 * On the right, each customer's records are a small cluster that stays unlit.
 * Only the verified customer's own cluster lights up when their pulse
 * arrives; everybody else's stays unlit - the isolation promise, drawn.
 * Bookings carry on to the technician diary; handovers go to the person.
 *
 * Built from real conversations (the caller passes them in). Pointer, pause
 * off screen and reduced motion come from the suite's Constellation.
 */

import { forwardRef, useCallback, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";

import {
  Constellation,
  type ConstellationHandle,
  type ConstellationLink,
  type ConstellationNode,
  type Tone,
} from "@/design/Constellation";
import { prefersReducedMotion } from "@/design/motion";
import type { Outcome } from "@/lib/format";
import { shorten } from "@/lib/format";

export type SceneCustomer = {
  /** Conversation reference. */
  id: string;
  channel: string;
  /** The customer the conversation is verified as, if any. */
  owner: string | null;
  outcome: Outcome;
};

export type SceneHandle = {
  /** Send one conversation through the scene, as it actually went. */
  play: (id: string, options?: { outcome?: Outcome; owner?: string | null; delay?: number }) => void;
};

const GATES = 12;
const PER_CHANNEL = 6;
const OWNERS = 5;

type Layout = {
  web: [number, number];
  line: [number, number];
  core: [number, number];
  ring: [number, number];
  ownersX: number;
  ownersY: [number, number];
  person: [number, number];
  calendar: [number, number];
  spread: [number, number];
};

const WIDE: Layout = {
  web: [0.13, 0.27],
  line: [0.13, 0.75],
  core: [0.5, 0.5],
  ring: [0.105, 0.17],
  ownersX: 0.83,
  ownersY: [0.3, 0.72],
  person: [0.86, 0.1],
  calendar: [0.84, 0.92],
  spread: [0.07, 0.11],
};

const COMPACT: Layout = {
  web: [0.15, 0.22],
  line: [0.15, 0.8],
  core: [0.5, 0.5],
  ring: [0.15, 0.15],
  ownersX: 0.84,
  ownersY: [0.3, 0.7],
  person: [0.84, 0.09],
  calendar: [0.84, 0.92],
  spread: [0.09, 0.1],
};

function gateIndexFor(x: number, y: number, layout: Layout): number {
  const angle = Math.atan2((y - layout.core[1]) / layout.ring[1], (x - layout.core[0]) / layout.ring[0]);
  const step = (Math.PI * 2) / GATES;
  return ((Math.round(angle / step) % GATES) + GATES) % GATES;
}

export const DeskScene = forwardRef<
  SceneHandle,
  {
    customers: SceneCustomer[];
    /** Customer names whose records appear on the right (the first few). */
    owners: string[];
    technicians?: number;
    compact?: boolean;
    /** Show the words beside the nodes. */
    labels?: boolean;
    /** Ambient arrivals that stop at the ring. */
    ambientTraffic?: boolean;
    /** Whose records start lit (a verified conversation on the chat page). */
    initiallyLit?: string | null;
    className?: string;
    label?: string;
    seed?: number;
    surface?: "dark" | "light";
  }
>(function DeskScene(
  {
    customers,
    owners,
    technicians = 6,
    compact = false,
    labels = true,
    ambientTraffic = true,
    initiallyLit = null,
    className = "",
    label,
    seed,
    surface = "light",
  },
  handle,
) {
  const canvas = useRef<ConstellationHandle>(null);
  const [litOwner, setLitOwner] = useState<string | null>(initiallyLit);
  const [litGate, setLitGate] = useState<{ index: number; tone: Tone } | null>(null);
  const [heldGate, setHeldGate] = useState<number | null>(null);
  const [personLit, setPersonLit] = useState(false);
  const [calendarLit, setCalendarLit] = useState(false);
  const layout = compact ? COMPACT : WIDE;

  useEffect(() => {
    // a conversation that is (or becomes) verified lights its own records
    if (initiallyLit) setLitOwner(initiallyLit);
  }, [initiallyLit]);

  const shownOwners = useMemo(() => {
    const list = owners.filter(Boolean).slice(0, OWNERS);
    if (litOwner && !list.includes(litOwner)) list.splice(0, list.length >= OWNERS ? 1 : 0, litOwner);
    while (list.length < 3) list.push(`other-${list.length}`);
    return list;
  }, [owners, litOwner]);

  const byChannel = useMemo(() => {
    const web = customers.filter((c) => c.channel !== "line").slice(0, PER_CHANNEL);
    const line = customers.filter((c) => c.channel === "line").slice(0, PER_CHANNEL);
    return { web, line };
  }, [customers]);

  const positions = useMemo(() => {
    const map = new Map<string, [number, number]>();
    const place = (list: SceneCustomer[], centre: [number, number], channel: string) => {
      const count = Math.max(list.length, 3);
      for (let index = 0; index < count; index += 1) {
        const angle = -Math.PI * 0.75 + (index / Math.max(1, count - 1)) * Math.PI * 1.5;
        const radius = index % 2 ? 1 : 0.72;
        const x = centre[0] + Math.cos(angle) * layout.spread[0] * radius * 0.9 + 0.012;
        const y = centre[1] + Math.sin(angle) * layout.spread[1] * radius;
        const id = list[index] ? `c-${list[index].id}` : `c-${channel}-quiet-${index}`;
        map.set(id, [x, y]);
      }
    };
    place(byChannel.web, layout.web, "web");
    place(byChannel.line, layout.line, "line");
    return map;
  }, [byChannel, layout]);

  const { nodes, links, traffic } = useMemo(() => {
    const nodes: ConstellationNode[] = [];
    const links: ConstellationLink[] = [];

    // ------------------------------------------------ the assistant and its ring
    nodes.push({
      id: "core",
      x: layout.core[0],
      y: layout.core[1],
      r: compact ? 5.5 : 7,
      tone: "accent",
      ring: true,
      lit: true,
      drift: 0.8,
      label: labels ? "Assistant" : undefined,
      sub: labels ? "picks an intent, never a customer" : undefined,
      side: "below",
    });
    for (let index = 0; index < GATES; index += 1) {
      const angle = (index / GATES) * Math.PI * 2;
      const lit = litGate?.index === index || heldGate === index;
      nodes.push({
        id: `g-${index}`,
        x: layout.core[0] + Math.cos(angle) * layout.ring[0],
        y: layout.core[1] + Math.sin(angle) * layout.ring[1],
        r: lit ? 3.4 : 2.2,
        tone: heldGate === index ? "warn" : litGate?.index === index ? litGate.tone : "light",
        lit,
        drift: 0.6,
      });
      links.push({ from: `g-${index}`, to: `g-${(index + 1) % GATES}`, tone: "accent", lit: true });
    }
    if (labels) {
      nodes.push({
        id: "ring-label",
        x: layout.core[0],
        y: layout.core[1] - layout.ring[1],
        r: 0.01,
        tone: "muted",
        label: "Identity check",
        sub: "order number and email",
        side: "above",
        drift: 0,
      });
    }

    // ------------------------------------------------ the two channels
    const channels: { key: string; list: SceneCustomer[]; centre: [number, number]; tone: Tone; word: string }[] = [
      { key: "web", list: byChannel.web, centre: layout.web, tone: "light", word: "Website" },
      { key: "line", list: byChannel.line, centre: layout.line, tone: "pass", word: "LINE" },
    ];
    for (const channel of channels) {
      const hub = `h-${channel.key}`;
      nodes.push({
        id: hub,
        x: channel.centre[0] - (compact ? 0.06 : 0.055),
        y: channel.centre[1],
        r: 3.6,
        tone: channel.tone,
        lit: true,
        label: labels ? channel.word : undefined,
        sub: labels ? `${channel.list.length} conversation${channel.list.length === 1 ? "" : "s"}` : undefined,
        side: channel.key === "web" ? "above" : "below",
        drift: 1.5,
      });
      const count = Math.max(channel.list.length, 3);
      for (let index = 0; index < count; index += 1) {
        const customer = channel.list[index];
        const id = customer ? `c-${customer.id}` : `c-${channel.key}-quiet-${index}`;
        const place = positions.get(id) ?? channel.centre;
        nodes.push({
          id,
          x: place[0],
          y: place[1],
          r: customer ? 2.8 : 1.6,
          tone: customer ? channel.tone : "muted",
          lit: Boolean(customer?.owner),
          drift: 3.5,
        });
        links.push({ from: hub, to: id, tone: channel.tone });
        const gate = gateIndexFor(place[0], place[1], layout);
        links.push({ from: id, to: `g-${gate}`, tone: channel.tone, lit: Boolean(customer?.owner) && litOwner === customer?.owner });
      }
    }

    // ------------------------------------------------ each customer's records
    const [top, bottom] = layout.ownersY;
    shownOwners.forEach((owner, index) => {
      const y = shownOwners.length > 1 ? top + ((bottom - top) * index) / (shownOwners.length - 1) : (top + bottom) / 2;
      const isLit = owner === litOwner;
      const id = `d-${owner}`;
      nodes.push({
        id,
        x: layout.ownersX,
        y,
        r: isLit ? 4.2 : 2.6,
        tone: isLit ? "accent" : "muted",
        lit: isLit,
        ring: isLit,
        drift: 1.6,
        label: labels && isLit ? shorten(owner, compact ? 14 : 24) : undefined,
        sub: labels && isLit ? "their own records only" : undefined,
        side: "left",
      });
      for (let dot = 0; dot < 4; dot += 1) {
        const angle = (dot / 4) * Math.PI * 2 + index;
        const dotId = `dd-${owner}-${dot}`;
        nodes.push({
          id: dotId,
          x: layout.ownersX + Math.cos(angle) * (compact ? 0.055 : 0.04),
          y: y + Math.sin(angle) * 0.055,
          r: isLit ? 2 : 1.4,
          tone: isLit ? "light" : "muted",
          lit: isLit,
          drift: 3,
        });
        links.push({ from: id, to: dotId, tone: isLit ? "accent" : "muted", lit: isLit });
      }
      if (isLit) links.push({ from: "core", to: id, tone: "accent", lit: true });
    });
    if (labels) {
      const dark = [...shownOwners].reverse().find((owner) => owner !== litOwner);
      const hub = nodes.find((node) => node.id === `d-${dark}`);
      if (hub) {
        hub.label = compact ? "Others" : "Other customers";
        hub.sub = "stay locked";
      }
    }

    // ------------------------------------------------ a person, and the diary
    nodes.push({
      id: "person",
      x: layout.person[0],
      y: layout.person[1],
      r: personLit ? 5 : 4,
      tone: "warn",
      lit: personLit,
      ring: personLit,
      drift: 1.2,
      label: labels ? "A person" : undefined,
      sub: labels ? "one tap away" : undefined,
      side: "left",
    });
    links.push({ from: "core", to: "person", tone: "warn", lit: personLit });
    nodes.push({
      id: "cal",
      x: layout.calendar[0],
      y: layout.calendar[1],
      r: calendarLit ? 4.6 : 3.6,
      tone: "pass",
      lit: calendarLit,
      ring: calendarLit,
      drift: 1.2,
      label: labels ? "Technician diary" : undefined,
      sub: labels ? `${technicians} technicians` : undefined,
      side: "left",
    });
    links.push({ from: "core", to: "cal", tone: "pass", lit: calendarLit });
    for (let index = 0; index < Math.min(technicians, 8); index += 1) {
      const id = `t-${index}`;
      nodes.push({
        id,
        x: layout.calendar[0] + 0.035 + (index % 4) * (compact ? 0.02 : 0.016),
        y: layout.calendar[1] - 0.04 + Math.floor(index / 4) * 0.05,
        r: 1.6,
        tone: calendarLit ? "pass" : "light",
        drift: 2,
      });
      links.push({ from: "cal", to: id, tone: "pass", lit: calendarLit });
    }

    // ------------------------------------------------ ambient arrivals
    const traffic: string[][] = [];
    for (const channel of channels) {
      const count = Math.max(channel.list.length, 3);
      for (let index = 0; index < count; index += 1) {
        const customer = channel.list[index];
        const id = customer ? `c-${customer.id}` : `c-${channel.key}-quiet-${index}`;
        const place = positions.get(id) ?? channel.centre;
        traffic.push([`h-${channel.key}`, id, `g-${gateIndexFor(place[0], place[1], layout)}`]);
      }
    }
    return { nodes, links, traffic };
  }, [layout, compact, labels, byChannel, positions, shownOwners, litOwner, litGate, heldGate, personLit, calendarLit, technicians]);

  const timers = useRef<number[]>([]);
  const later = useCallback((ms: number, work: () => void) => {
    timers.current.push(window.setTimeout(work, ms));
  }, []);

  const play = useCallback(
    (id: string, options: { outcome?: Outcome; owner?: string | null; delay?: number } = {}) => {
      const customer = customers.find((item) => item.id === id);
      const outcome = options.outcome ?? customer?.outcome ?? "answered";
      const owner = options.owner !== undefined ? options.owner : customer?.owner ?? null;
      const node = `c-${id}`;
      const place = positions.get(node);
      const gateIndex = place ? gateIndexFor(place[0], place[1], layout) : 6;
      const gate = `g-${gateIndex}`;
      const reduce = prefersReducedMotion();
      const delay = options.delay ?? 0;

      const finish = () => {
        if (outcome === "handed") setPersonLit(true);
        if (outcome === "booked") setCalendarLit(true);
      };

      if (reduce) {
        setLitOwner(owner);
        setPersonLit(outcome === "handed");
        setCalendarLit(outcome === "booked");
        setHeldGate(outcome === "verifying" || !owner ? gateIndex : null);
        setLitGate(owner ? { index: gateIndex, tone: "pass" } : null);
        return;
      }

      setPersonLit(false);
      setCalendarLit(false);
      setHeldGate(null);
      setLitGate(null);
      if (!owner) setLitOwner(null);

      const first = place ? [node, gate] : [gate];
      if (outcome === "verifying" || (!owner && outcome !== "handed")) {
        canvas.current?.pulse(first, {
          delay,
          duration: 900,
          tone: "warn",
          size: 3,
          onArrive: () => {
            setHeldGate(gateIndex);
            canvas.current?.flash(gate, "warn");
            later(1600, () => setHeldGate(null));
          },
        });
        return;
      }

      const toCore = [...first, "core"];
      const tail: string[] =
        outcome === "handed"
          ? ["person"]
          : outcome === "booked" && owner
            ? [`d-${owner}`, "cal"]
            : outcome === "refused"
              ? []
              : owner
                ? [`d-${owner}`]
                : [];
      canvas.current?.pulse(toCore, {
        delay,
        duration: 1000,
        tone: owner ? "pass" : "warn",
        size: 3,
        onArrive: () => {
          if (owner) setLitGate({ index: gateIndex, tone: "pass" });
          if (outcome === "refused") {
            canvas.current?.flash("core", "fail");
            return;
          }
          if (!tail.length) return finish();
          if (owner && tail[0] === `d-${owner}`) {
            canvas.current?.pulse(["core", `d-${owner}`], {
              duration: 700,
              tone: "accent",
              size: 3.2,
              onArrive: () => {
                setLitOwner(owner);
                if (tail[1]) {
                  canvas.current?.pulse([`d-${owner}`, "cal"], {
                    duration: 900,
                    tone: "pass",
                    size: 3,
                    onArrive: finish,
                  });
                } else finish();
              },
            });
            return;
          }
          canvas.current?.pulse(["core", ...tail], { duration: 900, tone: "warn", size: 3.2, onArrive: finish });
        },
      });
    },
    [customers, positions, layout, later],
  );

  useImperativeHandle(handle, () => ({ play }), [play]);

  return (
    <Constellation
      ref={canvas}
      className={className}
      nodes={nodes}
      links={links}
      traffic={ambientTraffic ? { paths: traffic, every: 1500, tone: "light" } : undefined}
      ambient={compact ? 22 : 44}
      reach={compact ? 86 : 112}
      introStagger={14}
      seed={seed}
      label={label}
      surface={surface}
    />
  );
});
