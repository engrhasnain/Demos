"use client";

/** Small product pieces on top of the suite design system. */

import type { ReactNode } from "react";

import { Banner, Button, Spinner } from "@/design/Surface";
import { StatusChip } from "@/design/StatusChip";
import { OUTCOME_WORDS, channelWord, type Outcome } from "@/lib/format";

export function ErrorNote({ error, onRetry }: { error: string; onRetry?: () => void }) {
  return (
    <Banner
      tone="fail"
      title="That did not work"
      action={onRetry && <Button onClick={onRetry} tone="secondary" size="small">Retry</Button>}
    >
      {error}
    </Banner>
  );
}

export function Loading({ what, dark = false }: { what: string; dark?: boolean }) {
  return (
    <div className="fd-loading" data-dark={dark ? "" : undefined} role="status">
      <Spinner /> {what}…
    </div>
  );
}

/** A small coloured mark for the channel a customer came in on. */
export function ChannelMark({ channel, withWord = true }: { channel: string; withWord?: boolean }) {
  return (
    <span className="fd-channel" data-channel={channel}>
      <span className="fd-channel-dot" aria-hidden />
      {withWord && channelWord(channel)}
    </span>
  );
}

export function OutcomeChip({
  outcome,
  surface = "light",
  size,
}: {
  outcome: Outcome;
  surface?: "light" | "dark";
  size?: "small" | "normal" | "large";
}) {
  const words = OUTCOME_WORDS[outcome];
  return (
    <StatusChip tone={words.tone} surface={surface} size={size} pulse={outcome === "verifying" || outcome === "handed"}>
      {words.label}
    </StatusChip>
  );
}

export function SectionHead({
  eyebrow,
  title,
  action,
  id,
}: {
  eyebrow: string;
  title: ReactNode;
  action?: ReactNode;
  id?: string;
}) {
  return (
    <div className="fd-section-head">
      <div>
        <p className="ds-mono-label" style={{ margin: 0 }}>
          {eyebrow}
        </p>
        <h2 id={id} className="ds-title fd-section-title">
          {title}
        </h2>
      </div>
      {action}
    </div>
  );
}
