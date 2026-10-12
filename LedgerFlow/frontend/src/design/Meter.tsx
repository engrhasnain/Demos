"use client";

/**
 * Meter - a solid bar that fills when it scrolls into view, with an optional
 * mark where the pass bar sits. The fill is a transform, so it is cheap; the
 * label beside it carries the actual figure, so nobody has to read a bar.
 */

import type { CSSProperties } from "react";

import { useInView } from "./motion";

const FILL: Record<string, string> = {
  accent: "var(--ds-accent)",
  pass: "var(--ds-pass)",
  warn: "var(--ds-warn)",
  fail: "var(--ds-fail)",
  info: "var(--ds-info)",
  ink: "var(--ds-ink)",
};

export function Meter({
  value,
  mark,
  markLabel,
  tone = "accent",
  size = "normal",
  delay = 0,
  label,
  className = "",
}: {
  /** 0..1 */
  value: number;
  /** 0..1, where the pass bar sits. */
  mark?: number;
  markLabel?: string;
  tone?: keyof typeof FILL;
  size?: "small" | "normal" | "large";
  delay?: number;
  label?: string;
  className?: string;
}) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.3 });
  const clamped = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  return (
    <div
      ref={ref}
      className={`ds-meter ${className}`}
      data-size={size}
      data-shown={shown ? "" : undefined}
      role={label ? "img" : undefined}
      aria-label={label}
      aria-hidden={label ? undefined : true}
      style={
        {
          "--ds-meter": clamped,
          "--ds-meter-fill": FILL[tone] ?? FILL.accent,
          "--ds-d": `${delay}ms`,
        } as CSSProperties
      }
    >
      <div className="ds-meter-fill">
        <span />
      </div>
      {mark !== undefined && (
        <span
          className="ds-meter-mark"
          data-edge={mark > 0.88 ? "end" : mark < 0.12 ? "start" : undefined}
          style={{ left: `${Math.max(0, Math.min(1, mark)) * 100}%` }}
        >
          {markLabel && <span className="ds-meter-mark-label">{markLabel}</span>}
        </span>
      )}
    </div>
  );
}
