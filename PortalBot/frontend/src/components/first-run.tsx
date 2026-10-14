"use client";

/**
 * The guided first run: load a day of shipments, with progress.
 *
 * One press asks the server to build the day from a fixed seed: the staff
 * and who is on duty, a hundred and eighty shipments with the awkward ones in
 * proportion, a fresh carrier portal and an order record for each shipment
 * in the business system. The server does it in one request, so while it
 * works the stages show as in progress; when it answers, each stage locks in
 * with the real counts it returned, and the constellation fills cluster by
 * cluster around the day.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import {
  Constellation,
  type ConstellationHandle,
  type ConstellationLink,
  type ConstellationNode,
} from "@/design/Constellation";
import { CountUp } from "@/design/CountUp";
import { Meter } from "@/design/Meter";
import { NodeChain } from "@/design/NodeChain";
import { prefersReducedMotion } from "@/design/motion";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Band, Button } from "@/design/Surface";
import { ErrorNote } from "@/components/ui";
import { switchTo } from "@/components/shell";
import { api, readUser } from "@/lib/api";
import type { LoadResult } from "@/lib/types";

type Stage = { key: string; label: string; dots: number; tone: "light" | "warn" | "accent"; count: (r: LoadResult) => string };

const STAGES: Stage[] = [
  { key: "clear", label: "Clear yesterday's rows and runs", dots: 3, tone: "light", count: () => "a clean slate" },
  { key: "staff", label: "Staff, and who is on duty for one-time codes", dots: 5, tone: "light", count: (r) => `${r.counts.staff ?? 0} people` },
  { key: "shipments", label: "Today's shipments, each with its own derived key", dots: 18, tone: "accent", count: (r) => `${r.counts.shipments ?? 0} shipments` },
  {
    key: "awkward",
    label: "The awkward ones, in proportion",
    dots: 7,
    tone: "warn",
    count: (r) =>
      `${(r.counts.planted_bad_postcode ?? 0) + (r.counts.planted_overweight ?? 0) + (r.counts.planted_undeclared ?? 0)} awkward · ${r.counts.planted_declarable ?? 0} declarable`,
  },
  { key: "portal", label: "A fresh carrier portal, booking form version 1", dots: 6, tone: "light", count: () => "version 1" },
  { key: "orders", label: "An order record for every shipment, in the business system", dots: 9, tone: "light", count: (r) => `${r.counts.shipments ?? 0} orders` },
];

function buildScene(done: number, active: number, compact: boolean) {
  const nodes: ConstellationNode[] = [
    { id: "hub", x: 0.5, y: 0.5, r: 6, tone: "accent", ring: true, lit: true, label: compact ? undefined : "Today", side: "below", drift: 1 },
  ];
  const links: ConstellationLink[] = [];
  STAGES.forEach((stage, index) => {
    const angle = -Math.PI / 2 + (index / STAGES.length) * Math.PI * 2;
    const cx = 0.5 + Math.cos(angle) * 0.34;
    const cy = 0.5 + Math.sin(angle) * 0.36;
    const isDone = index < done;
    const isActive = index === active;
    const id = `c-${index}`;
    nodes.push({
      id,
      x: cx,
      y: cy,
      r: isActive ? 4.2 : 3.4,
      tone: isDone ? (stage.tone === "warn" ? "warn" : "accent") : isActive ? "accent" : "muted",
      lit: isDone || isActive,
      ring: isActive,
      label: compact ? undefined : stage.label.split(",")[0].split(" with ")[0],
      side: Math.cos(angle) < -0.2 ? "left" : Math.cos(angle) > 0.2 ? "right" : Math.sin(angle) < 0 ? "above" : "below",
    });
    links.push({ from: "hub", to: id, tone: isDone ? "accent" : "light", lit: isDone });
    for (let dot = 0; dot < stage.dots; dot += 1) {
      const spin = (dot / stage.dots) * Math.PI * 2 + index;
      const distance = 0.04 + (dot % 3) * 0.02;
      const dotId = `d-${index}-${dot}`;
      nodes.push({
        id: dotId,
        x: cx + Math.cos(spin) * distance,
        y: cy + Math.sin(spin) * distance * 1.25,
        r: 1.7,
        tone: stage.tone === "warn" ? "warn" : "light",
        visible: isDone,
        drift: 4,
      });
      links.push({ from: id, to: dotId, tone: stage.tone === "warn" ? "warn" : "accent", lit: isDone });
    }
    if (index > 0) links.push({ from: `c-${index - 1}`, to: id, tone: "light", lit: isDone && index - 1 < done });
  });
  return { nodes, links };
}

export function FirstRun({ onFinished, again = false }: { onFinished: () => void; again?: boolean }) {
  const [phase, setPhase] = useState<"idle" | "working" | "locking" | "ready">("idle");
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<LoadResult | null>(null);
  const [done, setDone] = useState(0);
  const [active, setActive] = useState(-1);
  const [compact, setCompact] = useState(false);
  const stage = useRef<HTMLDivElement>(null);
  const canvas = useRef<ConstellationHandle>(null);
  const user = readUser();
  const isAdmin = user?.role === "administrator";

  useEffect(() => {
    const element = stage.current;
    if (!element) return;
    const measure = () => setCompact(element.getBoundingClientRect().width < 560);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // While the server works: the stages show as in progress, one after another.
  useEffect(() => {
    if (phase !== "working") return;
    const handle = window.setInterval(() => setActive((value) => (value + 1) % 3), 650);
    return () => window.clearInterval(handle);
  }, [phase]);

  // When it answers: each stage locks in with its real count.
  useEffect(() => {
    if (phase !== "locking") return;
    if (done >= STAGES.length) {
      setPhase("ready");
      setActive(-1);
      return;
    }
    const handle = window.setTimeout(
      () => {
        setDone((value) => value + 1);
        setActive(done + 1 < STAGES.length ? done + 1 : -1);
      },
      prefersReducedMotion() ? 0 : 380,
    );
    return () => window.clearTimeout(handle);
  }, [phase, done]);

  useEffect(() => {
    if (done > 0) canvas.current?.pulse(["hub", `c-${done - 1}`], { duration: 600, tone: "accent", size: 3.2 });
  }, [done]);
  useEffect(() => {
    if (active >= 0 && phase === "working") canvas.current?.pulse(["hub", `c-${active}`], { duration: 640, tone: "accent", size: 2.6 });
  }, [active, phase]);

  const begin = async () => {
    setError(null);
    setPhase("working");
    setActive(0);
    setDone(0);
    const started = performance.now();
    try {
      const response = await api.post<LoadResult>("/api/demo/load", { shipments: 180 });
      const wait = Math.max(0, 1600 - (performance.now() - started));
      window.setTimeout(() => {
        setResult(response);
        setActive(0);
        setPhase("locking");
      }, prefersReducedMotion() ? 0 : wait);
    } catch (cause) {
      setPhase("idle");
      setActive(-1);
      setError(cause instanceof Error ? cause.message : String(cause));
    }
  };

  const scene = useMemo(() => buildScene(done, active, compact), [done, active, compact]);
  const fraction = phase === "ready" ? 1 : phase === "locking" ? done / STAGES.length : phase === "working" ? 0.08 : 0;
  const percent = Math.round(fraction * 100);
  const started = phase !== "idle";

  return (
    <Band top>
      <div className="pb-first">
        <div style={{ minWidth: 0, padding: "24px 0 36px" }}>
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              {again ? "Start the day again" : "First run"} <span className="ds-eyebrow-sep">·</span> a few seconds
            </span>
          </Reveal>
          <Reveal index={1} y={36}>
            <h1 className="ds-display pb-hero-title">
              Load the day.
              <br />
              <span className="ds-accent-text pb-light">Then let it drive both screens.</span>
            </h1>
          </Reveal>
          <Reveal index={2}>
            <p className="ds-band-lede" style={{ fontSize: 16.5 }}>
              One press builds the morning at Hengtai from a fixed seed: a hundred and eighty shipments with the awkward
              ones in proportion, a fresh carrier portal, and an order record for each one in the old business system.
              Everyone who presses it gets the same day.
            </p>
          </Reveal>

          {!started && (
            <Reveal index={3}>
              <div className="pb-first-get">
                {(
                  [
                    [180, "shipments"],
                    [2, "systems, no way in but the screen"],
                    [0, "booked twice"],
                  ] as const
                ).map(([value, label], index) => (
                  <div key={label}>
                    <span className="ds-stat-value" style={{ fontSize: 30 }}>
                      <CountUp to={value} delay={index * 90} />
                    </span>
                    <span className="ds-mono-label ds-stat-label">{label}</span>
                  </div>
                ))}
              </div>
              {error && (
                <div style={{ marginTop: 16 }}>
                  <ErrorNote error={error} />
                </div>
              )}
              <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 24 }}>
                {isAdmin ? (
                  <Button tone="primary" size="large" onClick={() => void begin()} arrow>
                    {again ? "Load a fresh day" : "Load the day's shipments"}
                  </Button>
                ) : (
                  <Button
                    tone="primary"
                    size="large"
                    onClick={() =>
                      void switchTo("admin@hengtai-industrial.example")
                        .then(() => window.location.reload())
                        .catch((cause: unknown) => setError(String(cause)))
                    }
                    arrow
                  >
                    Switch to the administrator to load it
                  </Button>
                )}
                {again && (
                  <Button tone="ink" size="large" onClick={onFinished}>
                    Keep today as it is
                  </Button>
                )}
              </div>
              <p className="ds-mono" style={{ margin: "14px 0 0", fontSize: 11.5, color: "var(--ds-ink-faint)" }}>
                Only an administrator may load a day. It replaces every row, run and flag.
              </p>
            </Reveal>
          )}

          {started && (
            <div style={{ marginTop: 26 }} aria-live="polite">
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 16 }}>
                <span className="ds-display pb-progress-number">
                  <CountUp to={percent} duration={600} suffix="%" />
                </span>
                <StatusChip tone={phase === "ready" ? "pass" : "accent"} surface="dark" pulse={phase !== "ready"} size="large">
                  {phase === "ready" ? "Ready" : phase === "working" ? "Building on the server" : `Stage ${Math.min(done + 1, STAGES.length)} of ${STAGES.length}`}
                </StatusChip>
              </div>
              <div style={{ marginTop: 14 }}>
                <Meter value={fraction} size="large" label={`${percent} per cent loaded`} />
              </div>
              <div className="pb-first-stages">
                <NodeChain
                  stagger={50}
                  live={phase !== "ready"}
                  fill={done / STAGES.length}
                  items={STAGES.map((item, index) => {
                    const isDone = index < done;
                    const isActive = index === active && phase !== "ready";
                    return {
                      key: item.key,
                      tone: isDone ? (item.tone === "warn" ? "warn" : "accent") : isActive ? "info" : undefined,
                      state: isDone ? "done" : isActive ? "active" : "waiting",
                      marker: isDone ? "✓" : String(index + 1).padStart(2, "0"),
                      content: (
                        <span style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", gap: "2px 12px", paddingTop: 4 }}>
                          <span
                            style={{
                              fontSize: 13.5,
                              fontWeight: isActive ? 700 : 500,
                              color: isDone || isActive ? "var(--ds-ink-text)" : "var(--ds-ink-faint)",
                            }}
                          >
                            {item.label}
                          </span>
                          {isDone && result && (
                            <span className="ds-mono" style={{ fontSize: 11.5, color: "var(--ds-accent)" }}>
                              {item.count(result)}
                            </span>
                          )}
                        </span>
                      ),
                    };
                  })}
                />
              </div>
              {phase === "ready" && (
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 14, marginTop: 20 }}>
                  <Button tone="primary" size="large" onClick={onFinished} arrow>
                    Open the control room
                  </Button>
                  <span className="ds-mono" style={{ fontSize: 12, color: "var(--ds-ink-muted)" }}>
                    Built in {result?.seconds ?? 0} seconds by the server
                  </span>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="pb-first-stage" ref={stage}>
          <Constellation
            ref={canvas}
            nodes={scene.nodes}
            links={scene.links}
            ambient={compact ? 26 : 46}
            introStagger={10}
            label={`Loading the day: ${done} of ${STAGES.length} stages done`}
          />
        </div>
      </div>
    </Band>
  );
}
