"use client";

/**
 * Where a request is in its life, in plain words, for the step rail on the
 * case page and the small dot rail on lists.
 */

import type { CSSProperties } from "react";

import type { RailStep } from "@/design/StepRail";

export const LIFECYCLE: RailStep[] = [
  { key: "received", label: "Received" },
  { key: "read", label: "Read and matched" },
  { key: "asked", label: "Questions and suppliers" },
  { key: "priced", label: "Priced" },
  { key: "approval", label: "Approval" },
  { key: "sent", label: "Quote sent" },
  { key: "decided", label: "Won or lost" },
];

export type Progress = {
  index: number;
  tone: "accent" | "pass" | "warn" | "fail";
  complete: boolean;
};

export function progressOf(status: string, needsRepricing = false): Progress {
  if (needsRepricing) return { index: 3, tone: "fail", complete: false };
  switch (status) {
    case "received":
      return { index: 0, tone: "accent", complete: false };
    case "parsed":
    case "matched":
      return { index: 1, tone: "accent", complete: false };
    case "revised":
      return { index: 1, tone: "warn", complete: false };
    case "awaiting_customer":
    case "awaiting_supplier":
      return { index: 2, tone: "warn", complete: false };
    case "priced":
      return { index: 3, tone: "accent", complete: false };
    case "awaiting_approval":
      return { index: 4, tone: "warn", complete: false };
    case "sent":
      return { index: 5, tone: "pass", complete: false };
    case "won":
      return { index: 6, tone: "pass", complete: true };
    case "lost":
    case "cancelled":
      return { index: 6, tone: "fail", complete: false };
    default:
      return { index: 0, tone: "accent", complete: false };
  }
}

const COLOUR = {
  accent: "var(--ds-accent)",
  pass: "var(--ds-pass)",
  warn: "var(--ds-warn)",
  fail: "var(--ds-fail)",
};

/** Seven dots on a solid line: done, the current one beating, the rest empty. */
export function MiniRail({ status, label }: { status: string; label?: string }) {
  const progress = progressOf(status);
  const colour = COLOUR[progress.tone];
  return (
    <span
      role="img"
      aria-label={label ?? `Step ${progress.index + 1} of ${LIFECYCLE.length}: ${LIFECYCLE[progress.index].label}`}
      style={{ position: "relative", display: "inline-flex", alignItems: "center", gap: 7, height: 12 }}
    >
      <span
        aria-hidden
        style={{ position: "absolute", left: 3, right: 3, top: 5, height: 2, borderRadius: 2, background: "var(--ds-line)" }}
      />
      <span
        aria-hidden
        className="qa-mini-fill"
        style={
          {
            position: "absolute",
            left: 3,
            top: 5,
            height: 2,
            width: `calc(${(progress.index / (LIFECYCLE.length - 1)) * 100}% - 6px)`,
            borderRadius: 2,
            background: colour,
          } as CSSProperties
        }
      />
      {LIFECYCLE.map((step, index) => {
        const done = progress.complete || index < progress.index;
        const active = !progress.complete && index === progress.index;
        return (
          <span
            key={step.key}
            aria-hidden
            className={active ? "qa-mini-dot qa-mini-dot-active" : "qa-mini-dot"}
            style={
              {
                position: "relative",
                width: 8,
                height: 8,
                borderRadius: "50%",
                background: done || active ? colour : "var(--ds-surface)",
                boxShadow: done || active ? "none" : "inset 0 0 0 2px var(--ds-line-strong)",
                "--dot": colour,
              } as CSSProperties
            }
          />
        );
      })}
    </span>
  );
}
