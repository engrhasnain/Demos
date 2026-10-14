"use client";

/**
 * TraceSheet - the panel every clickable number opens.
 *
 * It slides in from the right with expo-out over an ink scrim. The ink head
 * shows the figure and a small constellation of the calculation: every input
 * is a node, each step is a node, the answer is a ringed node on the right,
 * and pulses run from the inputs through the steps into the answer as the
 * sheet opens. Below, the steps rise in one by one on a node chain and each
 * input lights up in turn, so the eye is walked through the arithmetic.
 *
 * Escape and the scrim close it; focus moves into it on open and back to the
 * number that opened it on close.
 */

import { useEffect, useMemo, useRef, type ReactNode } from "react";

import { Constellation, type ConstellationHandle, type ConstellationNode, type ConstellationLink } from "./Constellation";
import { NodeChain } from "./NodeChain";
import { prefersReducedMotion } from "./motion";

export type TraceInputView = {
  label: string;
  value: string;
  source?: string;
  /** Plain words for the kind of record, for example "Customer contract". */
  sourceKind?: string;
};

export type TraceStepView = {
  label: string;
  formula: string;
  result: string;
  unit?: string;
  note?: string;
  inputs: TraceInputView[];
};

export function TraceSheet({
  closing,
  onClose,
  onExited,
  eyebrow = "How this was worked out",
  heading,
  figure,
  steps,
  children,
  foot,
}: {
  closing: boolean;
  onClose: () => void;
  onExited: () => void;
  eyebrow?: string;
  heading: string;
  figure: ReactNode;
  steps: TraceStepView[];
  children?: ReactNode;
  foot?: ReactNode;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const opener = useRef<Element | null>(null);
  const diagram = useRef<ConstellationHandle>(null);

  useEffect(() => {
    opener.current = document.activeElement;
    closeButton.current?.focus({ preventScroll: true });
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = previous;
      const element = opener.current as HTMLElement | null;
      element?.focus?.({ preventScroll: true });
    };
  }, []);

  useEffect(() => {
    if (!closing) return;
    const handle = window.setTimeout(onExited, prefersReducedMotion() ? 0 : 320);
    return () => window.clearTimeout(handle);
  }, [closing, onExited]);

  const scene = useMemo(() => buildScene(steps), [steps]);

  // Send the pulses through the calculation once the sheet has slid in.
  useEffect(() => {
    const timers: number[] = [];
    timers.push(
      window.setTimeout(() => {
        scene.routes.forEach((route, index) => {
          diagram.current?.pulse(route.path, {
            delay: route.delay,
            duration: 650,
            tone: "accent",
            size: index === scene.routes.length - 1 ? 3.2 : 2.4,
          });
        });
      }, 420),
    );
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [scene]);

  return (
    <div className="ds-sheet-root" data-closing={closing ? "" : undefined}>
      <div className="ds-sheet-scrim" onClick={onClose} aria-hidden />
      <aside className="ds-sheet" role="dialog" aria-modal="true" aria-label={`${heading}: how it was worked out`}>
        <header className="ds-sheet-head">
          {steps.length > 0 && (
            <div className="ds-sheet-head-canvas">
              <Constellation
                ref={diagram}
                nodes={scene.nodes}
                links={scene.links}
                ambient={14}
                reach={90}
                introStagger={45}
                seed={steps.length * 97 + 11}
              />
            </div>
          )}
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
            <span className="ds-mono-label">{eyebrow}</span>
            <button ref={closeButton} type="button" className="ds-close" onClick={onClose}>
              Close
              <span aria-hidden>×</span>
            </button>
          </div>
          <p className="ds-sheet-heading">{heading}</p>
          <div className="ds-sheet-figure">{figure}</div>
        </header>

        <div className="ds-sheet-body">
          {children}
          {steps.length > 0 && <TraceSteps steps={steps} />}
        </div>

        {foot && <footer className="ds-sheet-foot">{foot}</footer>}
      </aside>
    </div>
  );
}

/** The worked steps, on a node chain, inputs lighting up in turn. */
export function TraceSteps({ steps }: { steps: TraceStepView[] }) {
  let order = 0;
  return (
    <NodeChain
      stagger={140}
      items={steps.map((step, index) => ({
        key: `${step.label}-${index}`,
        tone: index === steps.length - 1 ? "accent" : undefined,
        marker: String(index + 1).padStart(2, "0"),
        content: (
          <div style={{ paddingBottom: 6 }}>
            <p className="ds-trace-step-title">{step.label}</p>
            <p className="ds-trace-formula">{step.formula}</p>
            <p className="ds-trace-result">
              <span style={{ color: "var(--ds-text-3)" }}>= </span>
              <b>{step.result}</b>
              {step.unit && <span style={{ color: "var(--ds-text-3)" }}> {step.unit}</span>}
            </p>
            {step.note && (
              <p style={{ marginTop: 6, fontSize: 12.5, lineHeight: 1.5, color: "var(--ds-text-2)" }}>
                {step.note}
              </p>
            )}
            {step.inputs.length > 0 && (
              <ul className="ds-trace-inputs">
                {step.inputs.map((input, position) => {
                  const delay = 380 + index * 140 + (order++ % 24) * 110;
                  return (
                    <li
                      key={`${input.label}-${position}`}
                      className="ds-trace-input"
                      style={{ "--ds-d": `${delay}ms` } as React.CSSProperties}
                    >
                      <span className="ds-trace-input-label">{input.label}</span>
                      <span className="ds-trace-input-value">{input.value}</span>
                      {input.source && (
                        <span className="ds-trace-input-source">
                          <span className="ds-chip" data-tone="neutral" data-size="small">
                            {input.sourceKind || "From"}
                          </span>
                          {input.source}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            )}
          </div>
        ),
      }))}
    />
  );
}

/* ------------------------------------------------------------------ */
/* The little diagram in the head: inputs -> steps -> answer           */
/* ------------------------------------------------------------------ */
function buildScene(steps: TraceStepView[]) {
  const nodes: ConstellationNode[] = [];
  const links: ConstellationLink[] = [];
  const routes: { path: string[]; delay: number }[] = [];
  const count = Math.max(1, steps.length);
  const left = 0.5;
  const right = 0.86;

  steps.forEach((step, index) => {
    const x = count === 1 ? (left + right) / 2 : left + ((right - 0.08 - left) * index) / (count - 1);
    const y = 0.42 + Math.sin(index * 1.7) * 0.16;
    const id = `step-${index}`;
    nodes.push({ id, x, y, r: 3, tone: "accent", lit: true, drift: 4 });
    step.inputs.slice(0, 5).forEach((_, position) => {
      const inputId = `in-${index}-${position}`;
      const angle = -Math.PI / 2 + ((position + 0.5) / Math.max(1, Math.min(5, step.inputs.length))) * Math.PI;
      nodes.push({
        id: inputId,
        x: x - 0.06 - Math.cos(angle) * 0.03,
        y: Math.min(0.92, Math.max(0.08, y + Math.sin(angle) * 0.3)),
        r: 2,
        tone: "light",
        drift: 5,
      });
      links.push({ from: inputId, to: id, tone: "light" });
      routes.push({ path: [inputId, id], delay: index * 260 + position * 90 });
    });
    if (index > 0) {
      links.push({ from: `step-${index - 1}`, to: id, tone: "accent", lit: true });
      routes.push({ path: [`step-${index - 1}`, id], delay: index * 260 + 120 });
    }
  });
  nodes.push({ id: "answer", x: 0.94, y: 0.5, r: 4.2, tone: "accent", ring: true, lit: true, drift: 2 });
  if (steps.length) {
    links.push({ from: `step-${steps.length - 1}`, to: "answer", tone: "accent", lit: true });
    routes.push({ path: [`step-${steps.length - 1}`, "answer"], delay: steps.length * 260 + 200 });
  }
  return { nodes, links, routes };
}
