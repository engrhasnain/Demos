/**
 * StatusChip - a solid status label.
 *
 * Solid fill, dark mono uppercase text, so it reads at a glance on both the
 * ink bands and the white cards. `pulse` adds a beating dot for states that
 * are live (waiting, running). Words are always plain: "Waiting for
 * approval", never a code.
 */

import type { ReactNode } from "react";

export type ChipTone = "pass" | "fail" | "warn" | "info" | "accent" | "neutral";

export function StatusChip({
  tone = "neutral",
  children,
  pulse = false,
  surface = "light",
  size = "normal",
  title,
  className = "",
}: {
  tone?: ChipTone;
  children: ReactNode;
  pulse?: boolean;
  surface?: "light" | "dark";
  size?: "normal" | "small" | "large";
  title?: string;
  className?: string;
}) {
  return (
    <span
      className={`ds-chip ${className}`}
      data-tone={tone}
      data-surface={surface}
      data-size={size}
      title={title}
    >
      {pulse && <span className="ds-chip-dot" aria-hidden />}
      {children}
    </span>
  );
}

/** A small beating dot, for "live" headers. */
export function LiveDot({ tone = "pass" }: { tone?: ChipTone }) {
  return <span className="ds-live-dot" data-tone={tone} aria-hidden />;
}
