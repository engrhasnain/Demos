"use client";

/**
 * The screen-driving constellation: PortalBot's signature.
 *
 * Two clusters of screen fields - the carrier's booking form on the left,
 * the business system's order screen on the right - with the bot between
 * them. A bright operator node travels field to field along thin solid
 * lines as it fills each form, using the values from the real trace. Along
 * the bottom, every finished row locks in as a checkpoint, because the row
 * is the transaction.
 *
 * - A killed run freezes the whole chain; the resume visibly starts again
 *   from the last checkpoint, not from the beginning, and books nothing twice.
 * - A changed screen turns the carrier cluster coral, names the fields that
 *   moved, and halts before anything is sent.
 * - A row that needs a person stops at the check that refused it.
 *
 * The timeline runs only while the canvas is on screen and the tab is
 * visible. Under reduced motion it draws the final state as one still frame.
 */

import { useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import {
  Constellation,
  type ConstellationHandle,
  type ConstellationLink,
  type ConstellationNode,
  type Tone,
} from "@/design/Constellation";
import { seeded } from "@/design/canvas";
import { useInView, usePageVisible, useReducedMotion } from "@/design/motion";
import { BUSINESS_FIELDS, CARRIER_FIELDS, RENAMED_IN_V2, type DriveScenario } from "@/lib/scenario";

const CHAIN = 9;

type Banner = { tone: "pass" | "fail" | "warn" | "accent"; text: string } | null;

type DriveState = {
  lit: Record<string, Tone>;
  ring: string | null;
  labels: Record<string, { text: string; sub?: string; side?: ConstellationNode["side"] }>;
  locked: number;
  current: number;
  chain: Record<number, Tone>;
  chainLabel: Record<number, string>;
  frozen: boolean;
  carrierFail: boolean;
  banner: Banner;
  log: { tone: Tone; text: string; at: number }[];
};

type Ev = { at: number; pulse?: { path: string[]; dur: number; tone?: Tone }; set?: (state: DriveState) => DriveState };

/* ------------------------------------------------------------------ */
/* Layout                                                              */
/* ------------------------------------------------------------------ */
const jitter = seeded(77);
const CARRIER_POS = CARRIER_FIELDS.map((_, index) => {
  const col = index % 3;
  const row = Math.floor(index / 3);
  return { x: 0.07 + col * 0.105 + (jitter() - 0.5) * 0.03, y: 0.15 + row * 0.135 + (jitter() - 0.5) * 0.03 };
});
const BUSINESS_POS = [
  { x: 0.67, y: 0.19 },
  { x: 0.8, y: 0.14 },
  { x: 0.92, y: 0.23 },
  { x: 0.69, y: 0.36 },
  { x: 0.83, y: 0.4 },
  { x: 0.93, y: 0.52 },
];
const MIDDLE = {
  "m-addr": { x: 0.44, y: 0.81, word: "Address check" },
  "m-dg": { x: 0.555, y: 0.81, word: "Dangerous goods table" },
  "m-bot": { x: 0.525, y: 0.62, word: "PortalBot" },
  "m-shape": { x: 0.525, y: 0.4, word: "Form shape" },
} as const;
const BOOK = { x: 0.37, y: 0.66 };
const TRACK = { x: 0.4, y: 0.28 };
const chainX = (index: number) => 0.08 + (index * 0.84) / (CHAIN - 1);
const CHAIN_Y = 0.92;

const C = (index: number) => `c-${index}`;
const B = (index: number) => `b-${index}`;
const K = (index: number) => `k-${index}`;

function initial(scenario: DriveScenario): DriveState {
  const locked = scenario.kind === "resumed" || scenario.kind === "killed" ? 0 : 5;
  const chain: Record<number, Tone> = {};
  for (let index = 0; index < locked; index += 1) chain[index] = "pass";
  return {
    lit: {},
    ring: K(locked),
    labels: {},
    locked,
    current: locked,
    chain,
    chainLabel: {},
    frozen: false,
    carrierFail: false,
    banner: null,
    log: [],
  };
}

/** Apply one event, and write what it did into the machine log. */
function apply(previous: DriveState, fn: (s: DriveState) => DriveState, at: number): DriveState {
  const next = fn(previous);
  const lines = [...next.log];
  const fresh = Object.entries(next.labels).filter(
    ([id, value]) => !id.startsWith("persist:") && previous.labels[id] !== value,
  );
  for (const [id, value] of fresh) {
    lines.push({ tone: next.lit[id] ?? "accent", text: value.sub ? `${value.text}: ${value.sub}` : value.text, at });
  }
  if (next.banner && next.banner !== previous.banner) {
    lines.push({ tone: next.banner.tone, text: next.banner.text, at });
  }
  return lines.length === next.log.length ? next : { ...next, log: lines.slice(-4) };
}

/* ------------------------------------------------------------------ */
/* The timeline for one scenario                                       */
/* ------------------------------------------------------------------ */
function timeline(scenario: DriveScenario, compact: boolean): Ev[] {
  const events: Ev[] = [];
  let t = 120;
  const set = (fn: (s: DriveState) => DriveState, delay = 0) => events.push({ at: t + delay, set: fn });
  const wait = (ms: number) => {
    t += ms;
  };
  const hop = (from: string, to: string, dur: number, after: (s: DriveState) => DriveState, tone: Tone = "accent") => {
    events.push({ at: t, pulse: { path: [from, to], dur, tone } });
    t += dur;
    events.push({ at: t, set: (s) => after({ ...s, ring: to }) });
  };
  const light = (id: string, tone: Tone, text?: string, sub?: string, side?: ConstellationNode["side"]) => (s: DriveState): DriveState => ({
    ...s,
    lit: { ...s.lit, [id]: tone },
    labels: text ? { ...persistent(s.labels), [id]: { text, sub, side } } : persistent(s.labels),
  });
  const v = scenario.values ?? {};
  const ref = scenario.reference ?? "the next shipment";
  const fieldSpeed = compact ? 120 : 150;

  const checks = (cur: number, stopAt?: "address" | "dangerous") => {
    hop(K(cur), "m-addr", 420, light("m-addr", stopAt === "address" ? "warn" : "pass", "Address check", stopAt === "address" ? scenario.reason : scenario.address, "left"));
    if (stopAt === "address") return true;
    hop("m-addr", "m-dg", 280, light("m-dg", stopAt === "dangerous" ? "warn" : "pass", "Dangerous goods table", stopAt === "dangerous" ? scenario.reason : scenario.dangerous, "right"));
    if (stopAt === "dangerous") return true;
    hop("m-dg", "m-bot", 260, light("m-bot", "accent", "PortalBot", "picks up the row", "right"));
    hop("m-bot", "m-shape", 280, light("m-shape", "pass", "Form shape", "matches the script", "right"));
    return false;
  };

  const fill = (speed: number) => {
    hop("m-shape", C(0), 420, light(C(0), "accent", CARRIER_FIELDS[0].word, v.reference, "above"));
    for (let index = 1; index < CARRIER_FIELDS.length; index += 1) {
      const field = CARRIER_FIELDS[index];
      hop(C(index - 1), C(index), speed, light(C(index), "accent", field.word, v[field.key], index % 3 === 0 ? "left" : "above"));
    }
  };

  const writeBack = (cur: number, label: string) => {
    hop(C(CARRIER_FIELDS.length - 1), "c-book", 260, (s) => ({
      ...light("c-book", "pass", "Book", `booked once · ${scenario.carrier ?? "carrier"}`, "below")(s),
      chainLabel: { ...s.chainLabel, [cur]: "Booked" },
    }));
    hop("c-book", "c-trk", 320, light("c-trk", "pass", "Tracking number", scenario.tracking, "right"));
    hop("c-trk", B(0), 620, light(B(0), "accent", "Order number", scenario.order, "above"));
    const words = ["despatched", scenario.tracking, scenario.carrier, "today", "matches what was sent"];
    for (let index = 1; index < BUSINESS_FIELDS.length; index += 1) {
      hop(B(index - 1), B(index), 200, light(B(index), index === BUSINESS_FIELDS.length - 1 ? "pass" : "accent", BUSINESS_FIELDS[index].word, words[index - 1], index >= 4 ? "left" : "above"));
    }
    hop(B(BUSINESS_FIELDS.length - 1), K(cur), 560, (s) => ({
      ...s,
      locked: Math.max(s.locked, cur + 1),
      chain: { ...s.chain, [cur]: "pass" },
      chainLabel: { ...s.chainLabel, [cur]: label },
      labels: persistent(s.labels),
      banner: s.banner?.tone === "accent" ? s.banner : { tone: "pass", text: "Written back and read back · checkpoint locked" },
    }), "pass");
  };

  if (scenario.kind === "halted") {
    const cur = 5;
    set((s) => ({ ...s, chainLabel: { ...s.chainLabel, [cur]: scenario.run ? `Run ${scenario.run}` : "This run" } }));
    hop(K(cur), "m-bot", 480, light("m-bot", "accent", "PortalBot", "checks the form first", "right"));
    hop("m-bot", "m-shape", 320, light("m-shape", "warn", "Form shape", "reading the booking form", "right"));
    hop("m-shape", C(0), 380, light(C(0), "warn"));
    for (let index = 1; index < CARRIER_FIELDS.length; index += 1) {
      hop(C(index - 1), C(index), 90, light(C(index), "warn"), "warn");
    }
    wait(160);
    const movedIds = CARRIER_FIELDS.map((field, index) => (RENAMED_IN_V2[field.portal] ? index : -1)).filter((index) => index >= 0);
    set((s) => {
      const labels: DriveState["labels"] = {};
      movedIds.forEach((index, position) => {
        const field = CARRIER_FIELDS[index];
        labels[C(index)] = { text: field.word, sub: `${field.portal} → ${RENAMED_IN_V2[field.portal]}`, side: position === 0 ? "left" : "below" };
        labels[`persist:${C(index)}`] = labels[C(index)];
      });
      return { ...s, carrierFail: true, labels, lit: { ...s.lit, "m-shape": "fail" }, ring: "m-shape" };
    });
    wait(700);
    hop("m-shape", K(cur), 520, (s) => ({
      ...s,
      chain: { ...s.chain, [cur]: "fail" },
      chainLabel: { ...s.chainLabel, [cur]: "Halted" },
      banner: { tone: "fail", text: `Stopped before sending anything · ${scenario.reason ?? "the form moved"}` },
    }), "fail");
    return events;
  }

  if (scenario.kind === "resumed" || scenario.kind === "killed") {
    const killAt = 4;
    const n = scenario.killedAfter ?? 25;
    for (let index = 0; index <= killAt; index += 1) {
      const id = index;
      if (index > 0) events.push({ at: t, pulse: { path: [K(index - 1), K(index)], dur: 230, tone: "pass" } });
      t += index > 0 ? 230 : 120;
      set((s) => ({
        ...s,
        ring: K(id),
        locked: id + 1,
        current: id + 1,
        chain: { ...s.chain, [id]: "pass" },
        chainLabel: id === killAt ? { [id]: String(n) } : s.chainLabel,
      }));
    }
    wait(260);
    set((s) => ({
      ...s,
      frozen: true,
      ring: null,
      chain: { ...s.chain, [killAt + 1]: "fail" },
      chainLabel: { ...s.chainLabel, [killAt + 1]: "Killed" },
      banner: { tone: "fail", text: `Process killed after ${n} · every row says how far it got` },
    }));
    if (scenario.kind === "killed") return events;
    wait(1300);
    const cur = killAt + 1;
    set((s) => ({
      ...s,
      frozen: false,
      ring: K(killAt),
      chain: { ...s.chain, [cur]: "accent" },
      chainLabel: { [killAt]: `Last checkpoint · ${n}`, [cur]: String(n + 1) },
      banner: { tone: "accent", text: "Run again · it carries on from the last checkpoint" },
    }));
    wait(420);
    hop(K(killAt), K(cur), 380, (s) => s, "accent");
    hop(K(cur), "m-bot", 380, light("m-bot", "accent", "Asks the carrier first", `is ${ref} there?`, "right"));
    hop("m-bot", "m-shape", 260, light("m-shape", "pass", "Form shape", "matches the script", "right"));
    fill(compact ? 90 : 105);
    writeBack(cur, `${n + 1} · resumed`);
    set((s) => ({ ...s, banner: { tone: "pass", text: `Resumed from checkpoint ${n} · nothing booked twice` } }), 40);
    return events;
  }

  // One shipment, as far as its row got.
  const cur = 5;
  set((s) => ({ ...s, chainLabel: { ...s.chainLabel, [cur]: ref } }));
  if (scenario.kind === "held" && (scenario.stage === "address" || scenario.stage === "dangerous")) {
    checks(cur, scenario.stage);
    const from = scenario.stage === "address" ? "m-addr" : "m-dg";
    hop(from, K(cur), 480, (s) => ({
      ...s,
      chain: { ...s.chain, [cur]: "warn" },
      chainLabel: { [cur]: "Held" },
      banner: { tone: "warn", text: "Held for a person · nothing was sent to the portal" },
    }), "warn");
    return events;
  }
  checks(cur);
  fill(fieldSpeed);
  if (scenario.kind === "held" && scenario.stage === "book") {
    hop(C(CARRIER_FIELDS.length - 1), "c-book", 300, light("c-book", "warn", "Book", scenario.reason, "below"), "warn");
    hop("c-book", K(cur), 520, (s) => ({
      ...s,
      chain: { ...s.chain, [cur]: "warn" },
      chainLabel: { [cur]: "Held" },
      banner: { tone: "warn", text: "The portal refused it · held for a person, the run carried on" },
    }), "warn");
    return events;
  }
  if (scenario.kind === "booked" || (scenario.kind === "held" && scenario.stage === "collect")) {
    hop(C(CARRIER_FIELDS.length - 1), "c-book", 260, light("c-book", "pass", "Book", "booked once", "below"));
    hop("c-book", "c-trk", 320, light("c-trk", "warn", "Tracking number", "not ready yet", "right"), "warn");
    set((s) => ({
      ...s,
      chain: { ...s.chain, [cur]: "accent" },
      chainLabel: { [cur]: "Booked" },
      banner: { tone: "accent", text: "Booked · the next run collects the tracking number" },
    }));
    return events;
  }
  if (scenario.kind === "held" && scenario.stage === "write") {
    hop(C(CARRIER_FIELDS.length - 1), "c-book", 260, light("c-book", "pass", "Book", "booked once", "below"));
    hop("c-book", "c-trk", 320, light("c-trk", "pass", "Tracking number", scenario.tracking, "right"));
    hop("c-trk", B(0), 620, light(B(0), "accent", "Order number", scenario.order, "above"));
    hop(B(0), B(2), 260, light(B(2), "warn", "Tracking number", scenario.reason, "left"), "warn");
    hop(B(2), K(cur), 520, (s) => ({
      ...s,
      chain: { ...s.chain, [cur]: "warn" },
      chainLabel: { [cur]: "Held" },
      banner: { tone: "warn", text: "Booked, but the write back failed · held for a person" },
    }), "warn");
    return events;
  }
  writeBack(cur, `Done · ${ref.slice(-4)}`);
  return events;
}

/** Labels that must survive the operator moving on (renamed fields). */
function persistent(labels: DriveState["labels"]): DriveState["labels"] {
  const kept: DriveState["labels"] = {};
  for (const [id, value] of Object.entries(labels)) {
    if (id.startsWith("persist:")) {
      kept[id] = value;
      kept[id.slice(8)] = value;
    }
  }
  return kept;
}

function finalState(scenario: DriveScenario, events: Ev[]): DriveState {
  let state = initial(scenario);
  for (const event of events) if (event.set) state = apply(state, event.set, event.at);
  return state;
}

/* ------------------------------------------------------------------ */
/* The component                                                       */
/* ------------------------------------------------------------------ */
export function ScreenDrive({
  scenario,
  playKey = 0,
  compact = false,
  carrier = "Hsinchu Logistics",
  portalVersion = "v1",
  className = "",
  style,
  onDone,
  label,
}: {
  scenario: DriveScenario | null;
  playKey?: number;
  compact?: boolean;
  carrier?: string;
  portalVersion?: string;
  className?: string;
  style?: CSSProperties;
  onDone?: () => void;
  label?: string;
}) {
  const canvas = useRef<ConstellationHandle>(null);
  const reduce = useReducedMotion();
  const visible = usePageVisible();
  const [box, inView] = useInView<HTMLDivElement>({ once: false, threshold: 0.05, rootMargin: "0px" });
  const active = inView && visible;

  const events = useMemo(() => (scenario ? timeline(scenario, compact) : []), [scenario, compact]);
  const [state, setState] = useState<DriveState>(() => (scenario ? initial(scenario) : idleState()));
  const progress = useRef({ key: "", index: 0, elapsed: 0 });
  const done = useRef(onDone);
  done.current = onDone;

  const runKey = `${scenario?.key ?? "none"}:${playKey}:${compact ? 1 : 0}`;

  // Reduced motion: the final state, drawn once.
  useEffect(() => {
    if (!reduce || !scenario) return;
    setState(finalState(scenario, events));
    progress.current = { key: runKey, index: events.length, elapsed: Infinity };
  }, [reduce, scenario, events, runKey]);

  useEffect(() => {
    if (reduce || !scenario) return;
    if (progress.current.key !== runKey) {
      progress.current = { key: runKey, index: 0, elapsed: 0 };
      setState(initial(scenario));
    }
    if (!active) return;
    let frame = 0;
    let last = performance.now();
    const tick = (now: number) => {
      const p = progress.current;
      p.elapsed += Math.min(64, now - last);
      last = now;
      while (p.index < events.length && events[p.index].at <= p.elapsed) {
        const event = events[p.index];
        if (event.pulse) {
          canvas.current?.pulse(event.pulse.path, {
            duration: event.pulse.dur,
            tone: event.pulse.tone ?? "accent",
            size: 3.4,
          });
        }
        if (event.set) {
          const fn = event.set;
          const at = event.at;
          setState((previous) => apply(previous, fn, at));
        }
        p.index += 1;
        if (p.index === events.length) done.current?.();
      }
      if (p.index < events.length) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [active, reduce, scenario, events, runKey]);

  const { nodes, links } = useMemo(() => scene(state, compact), [state, compact]);
  const cluster = state.carrierFail;

  return (
    <div ref={box} className={`pb-drive ${className}`} style={style} data-compact={compact ? "" : undefined}>
      <div className="pb-frame" data-side="carrier" data-fail={cluster ? "" : undefined} aria-hidden />
      <div className="pb-frame" data-side="business" aria-hidden />
      <div className="pb-drive-canvas">
        <Constellation
          ref={canvas}
          nodes={nodes}
          links={links}
          ambient={compact ? 22 : 40}
          reach={compact ? 80 : 110}
          introStagger={12}
          label={label ?? describe(scenario)}
        />
      </div>
      <div className="pb-frame-title" data-side="carrier" data-fail={cluster ? "" : undefined} aria-hidden>
        <span className="pb-frame-dots">
          <i />
          <i />
          <i />
        </span>
        <span className="pb-frame-name">{cluster ? "Carrier portal · form changed" : "Carrier portal"}</span>
        <span className="pb-frame-sub">
          {carrier} · form version {portalVersion === "v2" ? "2" : "1"}
        </span>
      </div>
      <div className="pb-frame-title" data-side="business" aria-hidden>
        <span className="pb-frame-signal" />
        <span className="pb-frame-name">Order screen</span>
        <span className="pb-frame-sub">business system · no way in but the screen</span>
      </div>
      <div className="pb-drive-chain-caption" aria-hidden>
        Checkpoints · the row is the transaction
      </div>
      {!compact && state.log.length > 0 && (
        <ol className="pb-log" aria-hidden>
          {state.log.map((line, index) => (
            <li key={`${line.at}-${index}-${line.text}`} data-tone={line.tone}>
              <span className="pb-log-time">T+{(line.at / 1000).toFixed(2).padStart(5, "0")}</span>
              <span className="pb-log-tag">{tagOf(line.tone, line.text)}</span>
              <span className="pb-log-text">{line.text}</span>
            </li>
          ))}
        </ol>
      )}
      {state.banner && (
        <div key={state.banner.text} className="pb-drive-banner" data-tone={state.banner.tone} aria-hidden>
          <span className="pb-drive-tag">[ {tagOf(state.banner.tone, state.banner.text)} ]</span>
          {state.banner.text}
        </div>
      )}
      {state.frozen && <div className="pb-drive-frost" aria-hidden />}
    </div>
  );
}

function idleState(): DriveState {
  return {
    lit: {},
    ring: "m-bot",
    labels: {},
    locked: 5,
    current: 5,
    chain: { 0: "pass", 1: "pass", 2: "pass", 3: "pass", 4: "pass" },
    chainLabel: {},
    frozen: false,
    carrierFail: false,
    banner: null,
    log: [],
  };
}

const TAG: Record<string, string> = { pass: "OK", fail: "HALT", warn: "HOLD", accent: "RUN", light: "··", muted: "··" };

function tagOf(tone: string, text: string): string {
  if (tone === "fail" && /killed/i.test(text)) return "KILL";
  return TAG[tone] ?? "··";
}

function describe(scenario: DriveScenario | null): string {
  if (!scenario) return "The carrier portal and the business system, with PortalBot between them.";
  switch (scenario.kind) {
    case "halted":
      return "The carrier's booking form changed; the run stopped before sending anything.";
    case "resumed":
      return `A run killed after ${scenario.killedAfter} shipments, resumed from its last checkpoint without booking anything twice.`;
    case "killed":
      return `A run killed after ${scenario.killedAfter} shipments; every row says how far it got.`;
    case "held":
      return `${scenario.reference} held for a person: ${scenario.reason}.`;
    case "booked":
      return `${scenario.reference} booked; the tracking number is collected on the next run.`;
    default:
      return `${scenario.reference} booked in the carrier portal and written back into the business system.`;
  }
}

/* ------------------------------------------------------------------ */
/* State into nodes and links                                          */
/* ------------------------------------------------------------------ */
function scene(state: DriveState, compact: boolean) {
  const nodes: ConstellationNode[] = [];
  const links: ConstellationLink[] = [];
  const frozen = state.frozen;
  const tone = (id: string, fallback: Tone): Tone => (frozen ? "muted" : state.lit[id] ?? fallback);
  const label = (id: string) => {
    const value = state.labels[id];
    if (!value) return {};
    if (compact && !state.ring?.startsWith(id) && state.ring !== id) return {};
    return { label: value.text, sub: compact ? undefined : value.sub, side: value.side };
  };

  CARRIER_FIELDS.forEach((field, index) => {
    const id = C(index);
    const moved = Boolean(RENAMED_IN_V2[field.portal]) && state.carrierFail;
    nodes.push({
      id,
      ...CARRIER_POS[index],
      r: moved ? 4 : 2.8,
      tone: state.carrierFail && !frozen ? "fail" : tone(id, "muted"),
      lit: !frozen && (Boolean(state.lit[id]) || moved),
      ring: state.ring === id || moved,
      ...label(id),
    });
    if (index > 0 && index % 3 !== 0) links.push({ from: C(index - 1), to: id, tone: state.carrierFail ? "fail" : "light", lit: Boolean(state.lit[id]) && !frozen });
    if (index >= 3) links.push({ from: C(index - 3), to: id, tone: state.carrierFail ? "fail" : "light" });
  });
  nodes.push({ id: "c-book", ...BOOK, r: 3.6, tone: state.carrierFail && !frozen ? "fail" : tone("c-book", "light"), lit: Boolean(state.lit["c-book"]) && !frozen, ring: state.ring === "c-book", ...label("c-book") });
  nodes.push({ id: "c-trk", ...TRACK, r: 3.4, tone: state.carrierFail && !frozen ? "fail" : tone("c-trk", "light"), lit: Boolean(state.lit["c-trk"]) && !frozen, ring: state.ring === "c-trk", ...label("c-trk") });
  links.push({ from: C(CARRIER_FIELDS.length - 1), to: "c-book", tone: state.carrierFail ? "fail" : "light", lit: Boolean(state.lit["c-book"]) && !frozen });
  links.push({ from: "c-book", to: "c-trk", tone: "light", lit: Boolean(state.lit["c-trk"]) && !frozen });
  links.push({ from: C(2), to: "c-trk", tone: state.carrierFail ? "fail" : "light" });

  BUSINESS_FIELDS.forEach((field, index) => {
    const id = B(index);
    nodes.push({
      id,
      ...BUSINESS_POS[index],
      r: index === 2 ? 3.4 : 2.8,
      tone: tone(id, "muted"),
      lit: Boolean(state.lit[id]) && !frozen,
      ring: state.ring === id,
      ...label(id),
    });
    if (index > 0) links.push({ from: B(index - 1), to: id, tone: "light", lit: Boolean(state.lit[id]) && !frozen });
    if (index >= 3) links.push({ from: B(index - 3), to: id, tone: "light" });
  });
  links.push({ from: "c-trk", to: B(0), tone: "accent", lit: Boolean(state.lit[B(0)]) && !frozen });

  (Object.keys(MIDDLE) as (keyof typeof MIDDLE)[]).forEach((id) => {
    const place = MIDDLE[id];
    nodes.push({
      id,
      x: place.x,
      y: place.y,
      r: id === "m-bot" ? 5 : 3.4,
      tone: tone(id, id === "m-bot" ? "accent" : "light"),
      lit: (Boolean(state.lit[id]) || id === "m-bot") && !frozen,
      ring: id === "m-bot" || state.ring === id,
      ...(state.labels[id] ? label(id) : !compact && id === "m-bot" ? { label: "PortalBot", side: "right" as const } : {}),
      drift: id === "m-bot" ? 1.5 : 3,
    });
  });
  links.push({ from: "m-addr", to: "m-dg", tone: "light", lit: Boolean(state.lit["m-dg"]) && !frozen });
  links.push({ from: "m-addr", to: "m-bot", tone: "light" });
  links.push({ from: "m-dg", to: "m-bot", tone: "light", lit: Boolean(state.lit["m-bot"]) && !frozen });
  links.push({ from: "m-bot", to: "m-shape", tone: "accent", lit: Boolean(state.lit["m-shape"]) && !frozen });
  links.push({ from: "m-shape", to: C(0), tone: state.carrierFail ? "fail" : "light", lit: Boolean(state.lit[C(0)]) && !frozen });
  links.push({ from: "m-bot", to: "c-book", tone: "light" });
  links.push({ from: "m-bot", to: B(5), tone: "light" });

  for (let index = 0; index < CHAIN; index += 1) {
    const id = K(index);
    const chainTone = state.chain[index];
    const isLocked = index < state.locked && chainTone === "pass";
    const text = state.chainLabel[index];
    nodes.push({
      id,
      x: chainX(index),
      y: CHAIN_Y,
      r: isLocked || chainTone ? 3.6 : 2.4,
      tone: frozen && chainTone !== "fail" ? "muted" : chainTone ?? "muted",
      lit: !frozen && Boolean(chainTone),
      ring: state.ring === id || (chainTone === "fail" && !compact) || (isLocked && index === state.locked - 1 && !frozen),
      ...(state.labels[id] && !text ? label(id) : text ? { label: text, side: "above" as const } : {}),
      drift: 1.5,
    });
    if (index > 0) {
      links.push({ from: K(index - 1), to: id, tone: index < state.locked ? "pass" : "light", lit: index < state.locked && !frozen });
    }
  }
  const cur = Math.min(CHAIN - 1, state.current);
  links.push({ from: K(cur), to: "m-addr", tone: "light" });
  links.push({ from: B(5), to: K(cur), tone: "light" });

  return { nodes, links };
}
