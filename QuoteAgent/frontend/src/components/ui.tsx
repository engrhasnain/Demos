"use client";

/**
 * QuoteAgent's thin layer over the suite design system: status words to
 * chip colours, the ledger table, the page band, loading and error states.
 */

import type { CSSProperties, ReactNode } from "react";

import { Band, Banner, Spinner } from "@/design/Surface";
import { StatusChip, type ChipTone } from "@/design/StatusChip";
import { Reveal } from "@/design/Reveal";

export { Band, Banner, Button, Card, Empty, Eyebrow, LinkButton, Spinner, Stamp, Stat } from "@/design/Surface";
export { StatusChip } from "@/design/StatusChip";
export type { ChipTone } from "@/design/StatusChip";

/* ------------------------------------------------------------------ */
/* Status words to colours                                             */
/* ------------------------------------------------------------------ */
export function statusTone(status: string): ChipTone {
  if (["won", "sent", "priced", "matched", "answered", "approved", "active"].includes(status))
    return "pass";
  if (
    [
      "awaiting_customer",
      "awaiting_supplier",
      "awaiting_approval",
      "revised",
      "pending",
      "draft",
      "open",
    ].includes(status)
  )
    return "warn";
  if (
    ["lost", "cancelled", "needs_clarification", "non_catalogue", "rejected", "superseded"].includes(
      status,
    )
  )
    return "fail";
  if (status === "received") return "accent";
  return "neutral";
}

/** States that are still moving get a beating dot on their chip. */
export function isLive(status: string): boolean {
  return [
    "received",
    "awaiting_customer",
    "awaiting_supplier",
    "awaiting_approval",
    "revised",
    "pending",
  ].includes(status);
}

export const TONE_COLOUR: Record<ChipTone, string> = {
  pass: "var(--ds-pass)",
  fail: "var(--ds-fail)",
  warn: "var(--ds-warn)",
  info: "var(--ds-info)",
  accent: "var(--ds-accent)",
  neutral: "var(--ds-line-strong)",
};

export function Pill({
  children,
  tone = "neutral",
  title,
  pulse,
  surface,
  size,
}: {
  children: ReactNode;
  tone?: ChipTone;
  title?: string;
  pulse?: boolean;
  surface?: "light" | "dark";
  size?: "normal" | "small" | "large";
}) {
  return (
    <StatusChip tone={tone} title={title} pulse={pulse} surface={surface} size={size}>
      {children}
    </StatusChip>
  );
}

/* ------------------------------------------------------------------ */
/* Page band: every page opens on ink                                  */
/* ------------------------------------------------------------------ */
export function PageBand({
  eyebrow,
  title,
  accent,
  lede,
  actions,
  children,
  canvas,
  aside,
}: {
  eyebrow: ReactNode[];
  title: ReactNode;
  /** A second line of the title, in the accent colour. */
  accent?: ReactNode;
  lede?: ReactNode;
  actions?: ReactNode;
  children?: ReactNode;
  canvas?: ReactNode;
  aside?: ReactNode;
}) {
  return (
    <Band top canvas={canvas}>
      <div
        style={{
          display: "grid",
          gridTemplateColumns: aside ? "minmax(0, 1.15fr) minmax(0, 0.85fr)" : "minmax(0, 1fr)",
          gap: 32,
          alignItems: "end",
        }}
        className="qa-band-grid"
      >
        <div style={{ minWidth: 0 }}>
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              {eyebrow.map((part, index) => (
                <span key={index}>
                  {index > 0 && <span className="ds-eyebrow-sep">· </span>}
                  {part}
                </span>
              ))}
            </span>
          </Reveal>
          <Reveal index={1} y={32}>
            <h1 className="ds-display ds-band-title">
              {title}
              {accent && (
                <>
                  <br />
                  <span className="ds-accent-text">{accent}</span>
                </>
              )}
            </h1>
          </Reveal>
          {lede && (
            <Reveal index={2} y={28}>
              <p className="ds-band-lede">{lede}</p>
            </Reveal>
          )}
          {actions && (
            <Reveal index={3} y={24}>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 24 }}>{actions}</div>
            </Reveal>
          )}
        </div>
        {aside && (
          <Reveal index={2} y={36} style={{ minWidth: 0 }}>
            {aside}
          </Reveal>
        )}
      </div>
      {children}
    </Band>
  );
}

/* ------------------------------------------------------------------ */
/* Ledger table                                                        */
/* ------------------------------------------------------------------ */
export function Ledger({ head, children }: { head: ReactNode; children: ReactNode }) {
  return (
    <div className="ds-table-wrap">
      <table className="ds-table">
        <thead>
          <tr>{head}</tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Th({
  children,
  align = "left",
  width,
}: {
  children?: ReactNode;
  align?: "left" | "right" | "center";
  width?: string;
}) {
  return (
    <th style={width ? { width } : undefined} data-align={align === "left" ? undefined : align}>
      {children}
    </th>
  );
}

export function Td({
  children,
  align = "left",
  className = "",
  title,
  style,
  colSpan,
}: {
  children?: ReactNode;
  align?: "left" | "right" | "center";
  className?: string;
  title?: string;
  style?: CSSProperties;
  colSpan?: number;
}) {
  return (
    <td
      title={title}
      className={className}
      style={style}
      colSpan={colSpan}
      data-align={align === "left" ? undefined : align}
    >
      {children}
    </td>
  );
}

/* ------------------------------------------------------------------ */
/* Loading and errors                                                  */
/* ------------------------------------------------------------------ */
export function Loading({ what }: { what: string }) {
  return (
    <div
      role="status"
      style={{ display: "flex", alignItems: "center", gap: 10, padding: "28px 4px", color: "var(--ds-text-2)", fontSize: 14 }}
    >
      <Spinner /> {what}…
    </div>
  );
}

export function ErrorNote({ error }: { error: string }) {
  return (
    <Banner tone="fail" title="That did not work">
      {error}
    </Banner>
  );
}

/** Two-column label and value, for small detail lists. */
export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div
      style={{
        display: "grid",
        gridTemplateColumns: "minmax(7rem, auto) 1fr",
        gap: "2px 16px",
        alignItems: "baseline",
        padding: "8px 0",
        borderBottom: "1px solid var(--ds-line)",
        fontSize: 13.5,
      }}
    >
      <dt className="ds-mono-label">{label}</dt>
      <dd style={{ margin: 0, minWidth: 0, overflowWrap: "anywhere" }}>{children}</dd>
    </div>
  );
}
