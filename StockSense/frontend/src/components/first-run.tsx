"use client";

/**
 * The guided first run: build the company, then work out the first week.
 *
 * Two presses, each a real call to the server. While the server works, the
 * constellation builds with it: the company is the ringed node in the
 * middle and every stage lights up as a cluster around it, with a pulse
 * from the company to the cluster. The server answers once, when it has
 * finished, so the bar follows the time the work usually takes and is
 * marked as an estimate; it completes, with the real counts, when the
 * answer arrives.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { Band, Button } from "@/design/Surface";
import {
  Constellation,
  type ConstellationHandle,
  type ConstellationLink,
  type ConstellationNode,
} from "@/design/Constellation";
import { CountUp } from "@/design/CountUp";
import { Meter } from "@/design/Meter";
import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { StepRail } from "@/design/StepRail";
import { prefersReducedMotion } from "@/design/motion";
import { ApiError, api, readUser } from "@/lib/api";
import { count, millions, plural } from "@/lib/format";
import type { PlanRun } from "@/lib/types";
import { ErrorNote } from "@/components/ui";

type Stage = { key: string; label: string; weight: number; dots: number };

const LOAD_STAGES: Stage[] = [
  { key: "people", label: "The buying team and their roles", weight: 0.03, dots: 4 },
  { key: "suppliers", label: "Suppliers, with their real delivery record", weight: 0.05, dots: 8 },
  { key: "parts", label: "The catalogue: parts, packs and minimums", weight: 0.17, dots: 12 },
  { key: "history", label: "Two years of weekly sales, part by part", weight: 0.55, dots: 14 },
  { key: "supersessions", label: "Parts that replaced other parts", weight: 0.05, dots: 5 },
  { key: "orders", label: "The buyers' own orders, for the replay", weight: 0.15, dots: 9 },
];

const PLAN_STAGES: Stage[] = [
  { key: "classify", label: "Classify every part by how it sells", weight: 0.12, dots: 6 },
  { key: "clean", label: "Clean the history: empty shelves, project orders", weight: 0.18, dots: 7 },
  { key: "forecast", label: "Forecast with the method that suits the pattern", weight: 0.25, dots: 10 },
  { key: "cover", label: "Size the cover from the supplier's real record", weight: 0.2, dots: 8 },
  { key: "decide", label: "Decide: order, order before the shutdown, or watch", weight: 0.15, dots: 7 },
  { key: "cash", label: "Fit the week's orders inside the cash cap", weight: 0.1, dots: 6 },
];

const SIZES = [
  { key: "full", label: "Everything", hint: "18,000 parts, 140 suppliers", seconds: 70 },
  { key: "medium", label: "Medium", hint: "6,000 parts, 90 suppliers", seconds: 24 },
  { key: "small", label: "Quick", hint: "1,500 parts, 40 suppliers", seconds: 7 },
] as const;

type LoadResult = { seconds: number; counts: Record<string, number> };

function buildScene(stages: Stage[], done: number, active: number, compact: boolean, hubLabel: string) {
  const nodes: ConstellationNode[] = [
    { id: "hub", x: 0.5, y: 0.5, r: 6, tone: "accent", ring: true, lit: true, label: hubLabel, side: "below", drift: 1 },
  ];
  const links: ConstellationLink[] = [];
  stages.forEach((stage, index) => {
    const angle = -Math.PI / 2 + (index / stages.length) * Math.PI * 2;
    const cx = 0.5 + Math.cos(angle) * (compact ? 0.34 : 0.35);
    const cy = 0.5 + Math.sin(angle) * (compact ? 0.36 : 0.37);
    const isDone = index < done;
    const isActive = index === active;
    const id = `c-${index}`;
    nodes.push({
      id,
      x: cx,
      y: cy,
      r: isActive ? 4.2 : 3.2,
      tone: isDone ? "accent" : isActive ? "warn" : "muted",
      lit: isDone || isActive,
      ring: isActive,
      label: compact ? undefined : stage.label.split(":")[0].split(",")[0],
      side: Math.cos(angle) < -0.2 ? "left" : Math.cos(angle) > 0.2 ? "right" : Math.sin(angle) < 0 ? "above" : "below",
    });
    links.push({ from: "hub", to: id, tone: isDone ? "accent" : "light", lit: isDone });
    for (let dot = 0; dot < stage.dots; dot += 1) {
      const spread = (dot / stage.dots) * Math.PI * 2 + index;
      const distance = 0.045 + (dot % 3) * 0.02;
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
    if (index > 0) links.push({ from: `c-${index - 1}`, to: id, tone: "light", lit: isDone && index - 1 < done });
  });
  return { nodes, links };
}

/** Time-based progress that never claims to be finished before the server says so. */
function useEstimate(running: boolean, seconds: number) {
  const [fraction, setFraction] = useState(0);
  useEffect(() => {
    if (!running) return;
    const started = performance.now();
    setFraction(0);
    const handle = window.setInterval(() => {
      const elapsed = (performance.now() - started) / 1000;
      // Linear to the usual time, then creeping towards (never reaching) 97%.
      const linear = elapsed / Math.max(1, seconds);
      const value = linear < 0.9 ? linear : 0.9 + 0.07 * (1 - Math.exp(-(linear - 0.9) * 2.5));
      setFraction(Math.min(0.97, value));
    }, 200);
    return () => window.clearInterval(handle);
  }, [running, seconds]);
  return fraction;
}

function stageAt(stages: Stage[], fraction: number): number {
  let total = 0;
  for (let index = 0; index < stages.length; index += 1) {
    total += stages[index].weight;
    if (fraction < total) return index;
  }
  return stages.length - 1;
}

export function FirstRun({
  mode,
  partsLoaded,
  lastPlanSeconds,
  onFinished,
}: {
  mode: "load" | "plan";
  partsLoaded: number;
  lastPlanSeconds?: number;
  onFinished: () => void;
}) {
  const user = readUser();
  const mayLoad = user?.role === "administrator";
  const mayPlan = Boolean(user && user.role !== "viewer");
  const [size, setSize] = useState<(typeof SIZES)[number]["key"]>("full");
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState<LoadResult | null>(null);
  const [planned, setPlanned] = useState<PlanRun | null>(null);
  const [step, setStep] = useState<"load" | "plan">(mode);
  const canvas = useRef<ConstellationHandle>(null);
  const stageBox = useRef<HTMLDivElement>(null);
  const [compact, setCompact] = useState(false);

  useEffect(() => {
    const element = stageBox.current;
    if (!element) return;
    const measure = () => setCompact(element.getBoundingClientRect().width < 560);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const stages = step === "load" ? LOAD_STAGES : PLAN_STAGES;
  const expected =
    step === "load"
      ? SIZES.find((option) => option.key === size)?.seconds ?? 60
      : lastPlanSeconds && lastPlanSeconds > 1
        ? lastPlanSeconds
        : Math.max(4, (loaded?.counts.parts ?? partsLoaded) / 520);
  const estimate = useEstimate(running, expected);
  const finished = step === "load" ? Boolean(loaded) && !running : Boolean(planned) && !running;
  const fraction = finished ? 1 : running ? estimate : 0;
  const active = running ? stageAt(stages, fraction) : -1;
  const done = finished ? stages.length : running ? active : 0;

  const scene = useMemo(
    () => buildScene(stages, done, active, compact, step === "load" ? "Hengtai" : "This week"),
    [stages, done, active, compact, step],
  );

  const announced = useRef(new Set<string>());
  useEffect(() => {
    for (let index = 0; index < done; index += 1) {
      const key = `${step}-${index}`;
      if (announced.current.has(key)) continue;
      announced.current.add(key);
      canvas.current?.pulse(["hub", `c-${index}`], { duration: 700, tone: "accent", size: 3, delay: index * 60 });
    }
  }, [done, step]);
  useEffect(() => {
    if (active < 0) return;
    const handle = window.setInterval(() => {
      canvas.current?.pulse(["hub", `c-${active}`], { duration: 900, tone: "warn", size: 2.6 });
    }, 1300);
    return () => window.clearInterval(handle);
  }, [active]);

  const load = async () => {
    setError(null);
    setRunning(true);
    window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
    try {
      const result = await api.post<LoadResult>("/api/demo/load", { size });
      setLoaded(result);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setRunning(false);
    }
  };

  const plan = async () => {
    setError(null);
    setStep("plan");
    setRunning(true);
    window.scrollTo({ top: 0, behavior: prefersReducedMotion() ? "auto" : "smooth" });
    try {
      const result = await api.post<PlanRun>("/api/plan", {});
      setPlanned(result);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setRunning(false);
    }
  };

  const percent = Math.round(fraction * 100);
  const railCurrent = planned ? 2 : step === "plan" ? 1 : 0;

  return (
    <Band top>
      <div className="ss-first" data-started={running || finished ? "" : undefined}>
        <div className="ss-first-copy">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              First run <span className="ds-eyebrow-sep">·</span> two steps
            </span>
          </Reveal>
          <Reveal index={1} y={36}>
            <h1 className="ds-display ss-hero-title ss-first-title">
              {step === "load" ? "Build the company." : "Work out this week."}
              <br />
              <span className="ds-accent-text">
                {step === "load" ? "Then decide what to buy." : "Every part, inside the cash."}
              </span>
            </h1>
          </Reveal>
          <Reveal index={2}>
            <div className="ss-first-rail">
              <StepRail
                label="First run"
                current={railCurrent}
                complete={Boolean(planned)}
                steps={[
                  { key: "load", label: "Build the company", sub: loaded || mode === "plan" ? "done" : "administrator" },
                  { key: "plan", label: "Work out this week", sub: planned ? "done" : "any buyer" },
                  { key: "desk", label: "Open the desk", sub: planned ? "ready" : "next" },
                ]}
              />
            </div>
          </Reveal>

          {!running && !finished && step === "load" && (
            <Reveal index={3}>
              <p className="ds-band-lede">
                One press builds Hengtai Industrial Supply from a fixed seed: the buying team, a hundred and forty
                suppliers with their real delivery records, eighteen thousand parts, two years of weekly sales with the
                empty shelves and project orders left in, and the buyers&apos; own orders to replay against.
              </p>
              <div className="ss-size" role="radiogroup" aria-label="How much to build">
                {SIZES.map((option) => (
                  <button
                    key={option.key}
                    type="button"
                    role="radio"
                    aria-checked={size === option.key}
                    className="ss-size-option"
                    data-selected={size === option.key ? "" : undefined}
                    onClick={() => setSize(option.key)}
                  >
                    <span className="ss-size-dot" aria-hidden />
                    <span>
                      <span style={{ display: "block", fontWeight: 600, fontSize: 15 }}>{option.label}</span>
                      <span className="ds-mono" style={{ display: "block", marginTop: 3, fontSize: 11.5, color: "var(--ds-ink-muted)" }}>
                        {option.hint}
                      </span>
                    </span>
                  </button>
                ))}
              </div>
              <div style={{ marginTop: 22, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 14 }}>
                <Button tone="primary" size="large" disabled={!mayLoad} onClick={load} arrow>
                  Build the company
                </Button>
                {!mayLoad && (
                  <span style={{ fontSize: 13, color: "var(--ds-ink-muted)" }}>
                    Only the administrator can load the catalogue.
                  </span>
                )}
              </div>
            </Reveal>
          )}

          {(running || finished) && (
            <div className="ss-progress" aria-live="polite">
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 16 }}>
                <span className="ds-display ss-progress-number">
                  <CountUp to={percent} duration={500} suffix="%" />
                </span>
                <StatusChip
                  tone={error ? "fail" : finished ? "pass" : "accent"}
                  surface="dark"
                  pulse={running}
                  size="large"
                >
                  {error ? "Stopped" : finished ? "Done" : `Stage ${active + 1} of ${stages.length}`}
                </StatusChip>
              </div>
              <div style={{ marginTop: 14 }}>
                <Meter value={fraction} size="large" label={`${percent} per cent`} />
              </div>
              <p style={{ margin: "12px 0 0", fontSize: 15, fontWeight: 600 }}>
                {error
                  ? "Something went wrong"
                  : finished
                    ? step === "load"
                      ? `Built in ${loaded?.seconds ?? 0} seconds.`
                      : `Worked out in ${planned?.seconds ?? 0} seconds.`
                    : stages[Math.max(0, active)].label}
              </p>
              {running && (
                <p className="ds-mono" style={{ margin: "4px 0 0", fontSize: 11.5, color: "var(--ds-ink-faint)" }}>
                  The server answers once, when it has finished. This bar follows the usual time, about{" "}
                  {plural(Math.round(expected), "second")}.
                </p>
              )}
            </div>
          )}

          {error && (
            <div style={{ marginTop: 14 }}>
              <ErrorNote error={error} />
            </div>
          )}

          {(running || finished) && (
            <div className="ss-first-stages">
              <NodeChain
                stagger={45}
                live={running}
                fill={done / stages.length}
                items={stages.map((stage, index) => {
                  const isDone = index < done;
                  const isActive = index === active;
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
                          fontWeight: isActive ? 600 : 500,
                          color: isDone || isActive ? "var(--ds-ink-text)" : "var(--ds-ink-faint)",
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

          {loaded && step === "load" && !running && (
            <Reveal>
              <div className="ss-built">
                {(
                  [
                    ["parts", "parts"],
                    ["suppliers", "suppliers"],
                    ["weeks_of_history", "weeks of history"],
                    ["demand_points", "weekly sales figures"],
                    ["supersessions", "replaced parts"],
                    ["buyer_orders", "buyers' orders"],
                  ] as const
                ).map(([key, label], index) => (
                  <div key={key}>
                    <span className="ds-stat-value" style={{ fontSize: 26 }}>
                      <CountUp to={loaded.counts[key] ?? 0} delay={index * 90} />
                    </span>
                    <span className="ds-mono-label ds-stat-label">{label}</span>
                  </div>
                ))}
              </div>
              <div style={{ marginTop: 24, display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center" }}>
                <Button tone="primary" size="large" onClick={plan} disabled={!mayPlan} arrow>
                  Work out this week
                </Button>
                <span style={{ fontSize: 13, color: "var(--ds-ink-muted)" }}>
                  Looks at every part and fits the orders inside the cash cap.
                </span>
              </div>
            </Reveal>
          )}

          {step === "plan" && !running && !planned && !loaded && (
            <Reveal index={3}>
              <p className="ds-band-lede">
                {count(partsLoaded)} parts are loaded. One press looks at every one of them: classifies how it sells,
                cleans its history, forecasts it, sizes its cover from what the supplier really does, decides, and fits
                the week&apos;s orders inside the cash cap.
              </p>
              <div style={{ marginTop: 22 }}>
                <Button tone="primary" size="large" onClick={plan} disabled={!mayPlan} arrow>
                  Work out this week
                </Button>
              </div>
            </Reveal>
          )}

          {planned && !running && (
            <Reveal>
              <div className="ss-built">
                <div>
                  <span className="ds-stat-value" style={{ fontSize: 26 }}>
                    <CountUp to={planned.parts_considered} />
                  </span>
                  <span className="ds-mono-label ds-stat-label">parts looked at</span>
                </div>
                <div>
                  <span className="ds-stat-value" data-tone="accent" style={{ fontSize: 26 }}>
                    <CountUp to={planned.lines_recommended} delay={90} />
                  </span>
                  <span className="ds-mono-label ds-stat-label">lines to order</span>
                </div>
                <div>
                  <span className="ds-stat-value" style={{ fontSize: 26 }}>
                    {millions(planned.cash_committed)}
                  </span>
                  <span className="ds-mono-label ds-stat-label">of {millions(planned.cash_cap)} committed</span>
                </div>
              </div>
              <div style={{ marginTop: 24 }}>
                <Button tone="primary" size="large" onClick={onFinished} arrow>
                  Open the desk
                </Button>
              </div>
            </Reveal>
          )}
        </div>

        <div className="ss-first-stage" ref={stageBox}>
          <div className="ss-first-canvas">
            <Constellation
              ref={canvas}
              nodes={scene.nodes}
              links={scene.links}
              ambient={compact ? 26 : 50}
              introStagger={10}
              label={`${step === "load" ? "Building the company" : "Working out this week"}: ${done} of ${stages.length} stages done`}
            />
          </div>
        </div>
      </div>
    </Band>
  );
}
