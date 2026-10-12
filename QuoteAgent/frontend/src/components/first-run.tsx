"use client";

/**
 * The guided first run: build Hengtai, then quote for it.
 *
 * One press asks the server to generate the company from a fixed seed. While
 * it works, the constellation builds with it: the company is the ringed node
 * in the middle, and every stage the server finishes (warehouses, sales team,
 * suppliers, catalogue, stock, prices, cross-references, customers,
 * contracts, duty tables, rates, sample requests, worked requests) lights up
 * as a cluster around it, with a pulse from the company to the cluster. The
 * stage list on the left is the same progress, in words.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { Band, Banner, Button } from "@/design/Surface";
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
import { api } from "@/lib/api";
import { useAction, usePoll } from "@/lib/hooks";
import type { LoadProgress } from "@/lib/types";
import { ErrorNote } from "@/components/ui";

/** Short names for the clusters, in the order the server builds them. */
const CLUSTER_WORDS = [
  "Warehouses",
  "Sales team",
  "Suppliers",
  "Catalogue",
  "Stock",
  "Prices",
  "Cross-references",
  "Customers",
  "Contracts",
  "Duty tables",
  "Rates",
  "Sample requests",
  "Worked requests",
];
/** How many dots each cluster gets: roughly its share of the company. */
const CLUSTER_SIZE = [3, 5, 7, 11, 6, 6, 8, 10, 6, 4, 4, 5, 8];

const WHAT_YOU_GET: [number, string][] = [
  [18000, "parts"],
  [1200, "customers"],
  [140, "suppliers"],
  [29000, "cross-references"],
  [4, "duty tables"],
  [25, "worked requests"],
];

function buildScene(stageCount: number, done: Set<number>, active: number, compact: boolean) {
  const nodes: ConstellationNode[] = [
    {
      id: "hub",
      x: 0.5,
      y: 0.5,
      r: 6,
      tone: "accent",
      ring: true,
      lit: true,
      label: "Hengtai",
      side: "below",
      drift: 1,
    },
  ];
  const links: ConstellationLink[] = [];
  for (let index = 0; index < stageCount; index += 1) {
    const angle = -Math.PI / 2 + (index / stageCount) * Math.PI * 2;
    const cx = 0.5 + Math.cos(angle) * (compact ? 0.36 : 0.37);
    const cy = 0.5 + Math.sin(angle) * (compact ? 0.38 : 0.39);
    const isDone = done.has(index);
    const isActive = index === active;
    const id = `c-${index}`;
    nodes.push({
      id,
      x: cx,
      y: cy,
      r: isActive ? 4 : 3.2,
      tone: isDone ? "accent" : isActive ? "warn" : "muted",
      lit: isDone || isActive,
      ring: isActive,
      visible: true,
      label: compact ? undefined : CLUSTER_WORDS[index] ?? `Stage ${index + 1}`,
      side: Math.cos(angle) < -0.2 ? "left" : Math.cos(angle) > 0.2 ? "right" : Math.sin(angle) < 0 ? "above" : "below",
    });
    links.push({ from: "hub", to: id, tone: isDone ? "accent" : "light", lit: isDone });
    const size = CLUSTER_SIZE[index] ?? 5;
    for (let dot = 0; dot < size; dot += 1) {
      const spread = (dot / size) * Math.PI * 2 + index;
      const distance = 0.045 + (dot % 3) * 0.018;
      const dotId = `d-${index}-${dot}`;
      nodes.push({
        id: dotId,
        x: cx + Math.cos(spread) * distance,
        y: cy + Math.sin(spread) * distance * 1.25,
        r: 1.6,
        tone: isDone ? "light" : "muted",
        visible: isDone,
        drift: 4,
      });
      links.push({ from: id, to: dotId, tone: "accent", lit: isDone });
    }
    if (index > 0) {
      links.push({ from: `c-${index - 1}`, to: id, tone: "light", lit: isDone && done.has(index - 1) });
    }
  }
  return { nodes, links };
}

export function FirstRun({
  onFinished,
  serverless,
}: {
  onFinished: () => void;
  serverless: boolean;
}) {
  const { busy, error, run } = useAction();
  const [started, setStarted] = useState(false);
  const [size, setSize] = useState<"full" | "quick">(serverless ? "quick" : "full");
  const [complete, setComplete] = useState(false);
  const progress = usePoll<LoadProgress>("/api/system/load-progress", started && !complete, 450);
  const canvas = useRef<ConstellationHandle>(null);
  const [compact, setCompact] = useState(false);
  const stageBox = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const element = stageBox.current;
    if (!element) return;
    const measure = () => setCompact(element.getBoundingClientRect().width < 560);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  // Once the server says it is finished: stop polling, let the last
  // clusters light up, then open the overview.
  useEffect(() => {
    if (complete || !started || !progress) return;
    if (!progress.running && progress.finished_at && !progress.error) setComplete(true);
  }, [complete, started, progress]);
  useEffect(() => {
    if (!complete) return;
    const handle = window.setTimeout(onFinished, 1600);
    return () => window.clearTimeout(handle);
  }, [complete, onFinished]);

  const begin = () =>
    void run("load", async () => {
      const response = await api.post<{ mode?: string }>("/api/system/load-demo-data", {
        product_target: size === "full" ? 18000 : 2000,
        customer_target: size === "full" ? 1200 : 150,
      });
      if (response?.mode === "synchronous") {
        onFinished();
        return;
      }
      setStarted(true);
      window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
    });

  const stages = progress?.stages ?? [];
  const stageCount = stages.length || CLUSTER_WORDS.length;
  const finished = Boolean(progress && !progress.running && progress.finished_at && !progress.error);
  const doneSet = useMemo(() => {
    const set = new Set<number>();
    stages.forEach((stage, index) => {
      if (stage.done || finished) set.add(index);
    });
    return set;
  }, [stages, finished]);
  const activeIndex =
    progress?.running && !finished ? stages.findIndex((stage) => stage.key === progress.stage) : -1;

  const scene = useMemo(
    () => buildScene(stageCount, doneSet, activeIndex, compact),
    [stageCount, doneSet, activeIndex, compact],
  );

  // A pulse from the company to every cluster as it completes.
  const announced = useRef(new Set<number>());
  useEffect(() => {
    doneSet.forEach((index) => {
      if (announced.current.has(index)) return;
      announced.current.add(index);
      canvas.current?.pulse(["hub", `c-${index}`], { duration: 700, tone: "accent", size: 3 });
    });
  }, [doneSet]);
  useEffect(() => {
    if (activeIndex < 0) return;
    canvas.current?.pulse(["hub", `c-${activeIndex}`], { duration: 900, tone: "warn", size: 2.6 });
  }, [activeIndex, progress?.done]);

  const fraction = finished
    ? 1
    : progress
      ? (doneSet.size + (progress.total ? Math.min(1, progress.done / progress.total) : 0) * (activeIndex >= 0 ? 1 : 0)) /
        Math.max(1, stageCount)
      : 0;
  const percent = Math.round(fraction * 100);

  return (
    <Band top>
      <div className="qa-first" data-started={started ? "" : undefined}>
        <div className="qa-first-copy">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              First run <span className="ds-eyebrow-sep">·</span> about thirty seconds
            </span>
          </Reveal>
          <Reveal index={1} y={36}>
            <h1 className="ds-display qa-hero-title">
              Build the company.
              <br />
              <span className="ds-accent-text">Then quote for it.</span>
            </h1>
          </Reveal>
          <Reveal index={2}>
            <p className="ds-band-lede" style={{ fontSize: 17 }}>
              One press builds Hengtai Industrial Supply from a fixed seed: two warehouses, the sales team, the
              catalogue, customers with their contracts, the dated duty tables for 2026 and two dozen requests
              already worked through the agent. Everyone who presses it gets the same company.
            </p>
          </Reveal>

          {!started && (
            <Reveal index={3}>
              <div className="qa-get">
                {WHAT_YOU_GET.map(([value, label], index) => (
                  <div key={label}>
                    <span className="ds-stat-value" style={{ fontSize: 26 }}>
                      <CountUp to={value} delay={index * 90} />
                    </span>
                    <span className="ds-mono-label ds-stat-label">{label}</span>
                  </div>
                ))}
              </div>

              {serverless && (
                <div style={{ marginTop: 18 }}>
                  <Banner tone="warn" title="Running on serverless functions">
                    Choose the smaller set, so the load finishes inside one request.
                  </Banner>
                </div>
              )}

              <div className="qa-size" role="radiogroup" aria-label="How much data to build">
                {(
                  [
                    ["quick", "Smaller", "2,000 parts, 150 customers"],
                    ["full", "Everything", "18,000 parts, 1,200 customers"],
                  ] as const
                ).map(([key, label, hint]) => (
                  <button
                    key={key}
                    type="button"
                    role="radio"
                    aria-checked={size === key}
                    className="qa-size-option"
                    data-selected={size === key ? "" : undefined}
                    onClick={() => setSize(key)}
                  >
                    <span className="qa-size-dot" aria-hidden />
                    <span>
                      <span style={{ display: "block", fontWeight: 600, fontSize: 15 }}>{label}</span>
                      <span className="ds-mono" style={{ display: "block", marginTop: 3, fontSize: 11.5, color: "var(--ds-ink-muted)" }}>
                        {hint}
                      </span>
                    </span>
                  </button>
                ))}
              </div>

              {error && (
                <div style={{ marginTop: 16 }}>
                  <ErrorNote error={error} />
                </div>
              )}

              <div style={{ marginTop: 20 }}>
                <Button tone="primary" size="large" busy={busy === "load"} onClick={begin} arrow>
                  Load the demonstration data
                </Button>
              </div>
            </Reveal>
          )}

          {started && (
            <div className="qa-progress" aria-live="polite">
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 16 }}>
                <span className="ds-display qa-progress-number">
                  <CountUp to={percent} duration={700} suffix="%" />
                </span>
                <StatusChip
                  tone={progress?.error ? "fail" : finished ? "pass" : "accent"}
                  surface="dark"
                  pulse={!finished && !progress?.error}
                  size="large"
                >
                  {progress?.error ? "Stopped" : finished ? "Ready" : `Stage ${progress?.stage_number ?? 1} of ${stageCount}`}
                </StatusChip>
              </div>
              <div style={{ marginTop: 14 }}>
                <Meter value={fraction} size="large" label={`${percent} per cent built`} />
              </div>
              <p style={{ margin: "12px 0 0", fontSize: 15, fontWeight: 600 }}>
                {progress?.error
                  ? "Something went wrong"
                  : finished
                    ? "Hengtai is ready. Opening the overview…"
                    : progress?.stage_label || "Starting"}
              </p>
              {progress?.running && progress.total > 1 && (
                <p className="ds-mono" style={{ margin: "4px 0 0", fontSize: 12, color: "var(--ds-ink-muted)" }}>
                  {progress.done.toLocaleString("en-GB")} of {progress.total.toLocaleString("en-GB")}
                </p>
              )}
              {progress?.error && (
                <div style={{ marginTop: 12 }}>
                  <ErrorNote error={progress.error} />
                </div>
              )}
            </div>
          )}
          {started && stages.length > 0 && (
            <div className="qa-first-stages">
              <NodeChain
                stagger={40}
                live={!finished}
                fill={stageCount ? doneSet.size / stageCount : 0}
                items={stages.map((stage, index) => {
                  const isDone = doneSet.has(index);
                  const isActive = index === activeIndex;
                  return {
                    key: stage.key,
                    tone: isDone ? "accent" : isActive ? "warn" : undefined,
                    state: isDone ? "done" : isActive ? "active" : "waiting",
                    marker: isDone ? "✓" : String(index + 1).padStart(2, "0"),
                    content: (
                      <span
                        style={{
                          display: "block",
                          paddingTop: 4,
                          fontSize: 13.5,
                          fontWeight: isActive ? 700 : 500,
                          color: isDone ? "var(--ds-ink-text)" : isActive ? "var(--ds-ink-text)" : "var(--ds-ink-faint)",
                        }}
                      >
                        {stage.label}
                      </span>
                    ),
                  };
                })}
              />
            </div>
          )}
        </div>

        <div className="qa-first-stage" ref={stageBox}>
          <div className="qa-first-canvas">
            <Constellation
              ref={canvas}
              nodes={scene.nodes}
              links={scene.links}
              ambient={compact ? 26 : 48}
              introStagger={10}
              label={`Building Hengtai: ${doneSet.size} of ${stageCount} stages done`}
            />
          </div>
        </div>
      </div>
    </Band>
  );
}
