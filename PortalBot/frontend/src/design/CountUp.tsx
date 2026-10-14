"use client";

/**
 * A number that counts up when it comes into view.
 *
 * The animation is decoration only: the last frame is always `final`, the
 * exact text the server (or the formatter) produced, so a money figure is
 * never shown rounded once the count has finished. A hidden copy of the final
 * text reserves the width, so nothing around it shifts while it counts, and
 * screen readers only ever hear the final value.
 *
 * When `to` changes later (a person edits an input) it counts from the old
 * value to the new one, quicker.
 */

import { useEffect, useRef } from "react";

import { easeOutExpo, prefersReducedMotion, useInView } from "./motion";

function grouped(value: number, decimals: number): string {
  return value.toLocaleString("en-GB", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

export function CountUp({
  to,
  final,
  decimals = 0,
  duration = 1400,
  delay = 0,
  prefix = "",
  suffix = "",
  align = "start",
  className = "",
}: {
  /** The value to count to. */
  to: number;
  /** Exact text for the last frame. Defaults to `to` with grouping. */
  final?: string;
  decimals?: number;
  duration?: number;
  delay?: number;
  prefix?: string;
  suffix?: string;
  align?: "start" | "end";
  className?: string;
}) {
  const [ref, inView] = useInView<HTMLSpanElement>({ threshold: 0.2 });
  const live = useRef<HTMLSpanElement>(null);
  const shown = useRef<number | null>(null);
  const finalText = final ?? `${prefix}${grouped(to, decimals)}${suffix}`;

  useEffect(() => {
    const element = live.current;
    if (!element) return;
    const target = Number.isFinite(to) ? to : 0;

    if (!inView) {
      element.textContent = `${prefix}${grouped(0, decimals)}${suffix}`;
      return;
    }
    if (prefersReducedMotion()) {
      element.textContent = finalText;
      shown.current = target;
      return;
    }

    const from = shown.current ?? 0;
    const length = shown.current === null ? duration : Math.min(700, duration);
    let frame = 0;
    let start = 0;
    const tick = (now: number) => {
      if (!start) start = now + (shown.current === null ? delay : 0);
      const progress = Math.max(0, Math.min(1, (now - start) / length));
      const value = from + (target - from) * easeOutExpo(progress);
      if (progress >= 1) {
        element.textContent = finalText;
        shown.current = target;
        return;
      }
      element.textContent = `${prefix}${grouped(value, decimals)}${suffix}`;
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => {
      cancelAnimationFrame(frame);
      // A count that was interrupted resumes from wherever it had reached.
      if (shown.current === null) shown.current = from;
    };
  }, [inView, to, finalText, decimals, duration, delay, prefix, suffix]);

  return (
    <span ref={ref} className={`ds-countup ${className}`} data-align={align}>
      <span aria-hidden className="ds-countup-ghost">
        {finalText}
      </span>
      <span aria-hidden className="ds-countup-live" ref={live}>
        {`${prefix}${grouped(0, decimals)}${suffix}`}
      </span>
      <span className="ds-sr-only">{finalText}</span>
    </span>
  );
}
