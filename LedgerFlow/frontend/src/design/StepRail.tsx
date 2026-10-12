"use client";

/**
 * StepRail - where one record is in its life, left to right.
 *
 * Done steps are filled, the current one rings, and a glowing node runs into
 * it along the solid connector. The fills draw in one after another when the
 * rail scrolls into view. Below 760 px it turns into a vertical rail.
 */

import type { CSSProperties } from "react";

import { useInView } from "./motion";

export type RailStep = { key: string; label: string; sub?: string };

const TONE: Record<string, { color: string; rgb: string }> = {
  accent: { color: "var(--ds-accent)", rgb: "var(--ds-accent-rgb)" },
  pass: { color: "var(--ds-pass)", rgb: "var(--ds-pass-rgb)" },
  warn: { color: "var(--ds-warn)", rgb: "var(--ds-warn-rgb)" },
  fail: { color: "var(--ds-fail)", rgb: "var(--ds-fail-rgb)" },
};

export function StepRail({
  steps,
  current,
  tone = "accent",
  complete = false,
  label,
}: {
  steps: RailStep[];
  /** Index of the step the record is at. */
  current: number;
  tone?: "accent" | "pass" | "warn" | "fail";
  /** Every step done (the record is finished). */
  complete?: boolean;
  label?: string;
}) {
  const [ref, shown] = useInView<HTMLOListElement>({ threshold: 0.2 });
  const colours = TONE[tone] ?? TONE.accent;
  return (
    <ol
      ref={ref}
      className="ds-rail"
      aria-label={label}
      data-shown={shown ? "" : undefined}
      style={
        {
          "--rail-count": steps.length,
          "--rail-tone": colours.color,
          "--rail-rgb": colours.rgb,
        } as CSSProperties
      }
    >
      {steps.map((step, index) => {
        const state =
          complete || index < current ? "done" : index === current ? "active" : "waiting";
        return (
          <li
            key={step.key}
            className="ds-rail-step"
            data-state={state}
            aria-current={state === "active" ? "step" : undefined}
            style={{ "--ds-d": `${index * 110}ms` } as CSSProperties}
          >
            <span className="ds-rail-fill" aria-hidden />
            <span className="ds-rail-pulse" aria-hidden />
            <span className="ds-rail-node" aria-hidden />
            <span className="ds-rail-label">{step.label}</span>
            {step.sub && <span className="ds-rail-sub">{step.sub}</span>}
          </li>
        );
      })}
    </ol>
  );
}
