"use client";

/**
 * LedgerFlow's thin layer over the suite design system: what an invoice's
 * state means as a chip, the page band, the ledger table, loading and error
 * states. Everything visual comes from src/design.
 */

import type { CSSProperties, ReactNode } from "react";

import { Band, Banner, Spinner } from "@/design/Surface";
import { StatusChip, type ChipTone } from "@/design/StatusChip";
import { Reveal } from "@/design/Reveal";
import type { InvoiceBrief } from "@/lib/types";

export { Band, Banner, Button, Card, Empty, LinkButton, Spinner, Stamp, Stat } from "@/design/Surface";
export { StatusChip } from "@/design/StatusChip";
export type { ChipTone } from "@/design/StatusChip";

/* ------------------------------------------------------------------ */
/* What an invoice's state means, in one chip                          */
/* ------------------------------------------------------------------ */
export type MatchState = {
  /** The chip's words, always plain. */
  label: string;
  tone: ChipTone;
  /** Still moving: the chip gets a beating dot. */
  live: boolean;
  /** Which corner of the three-way match broke, if one did. */
  broken: "invoice" | "order" | "delivery" | null;
};

/** Exception headlines that point at one corner of the triangle. */
const ORDER_PROBLEMS = ["Priced above the order", "No purchase order"];
const DELIVERY_PROBLEMS = ["Nothing has arrived yet", "Only part of it has arrived"];

export function matchState(invoice: Pick<InvoiceBrief, "status" | "headline" | "headline_severity" | "kind">): MatchState {
  const broken = ORDER_PROBLEMS.includes(invoice.headline)
    ? "order"
    : DELIVERY_PROBLEMS.includes(invoice.headline)
      ? "delivery"
      : invoice.headline_severity === "block"
        ? "invoice"
        : null;
  switch (invoice.status) {
    case "posted":
      return { label: "Posted", tone: "pass", live: false, broken: null };
    case "approved":
      return { label: "Approved", tone: "accent", live: true, broken: null };
    case "checked":
      return { label: "Matched", tone: "accent", live: true, broken: null };
    case "awaiting_approval":
      return { label: "Needs approval", tone: "warn", live: true, broken: null };
    case "exception":
      return invoice.headline_severity === "block"
        ? { label: "Stopped", tone: "fail", live: true, broken: broken ?? "invoice" }
        : { label: "Held", tone: "warn", live: true, broken };
    case "rejected":
      return { label: "Rejected", tone: "fail", live: false, broken };
    case "cancelled":
      return { label: "Cancelled", tone: "neutral", live: false, broken: null };
    default:
      return { label: "Reading", tone: "info", live: true, broken: null };
  }
}

export function severityTone(severity: string): ChipTone {
  if (severity === "block") return "fail";
  if (severity === "hold") return "warn";
  return "neutral";
}

export function severityWords(severity: string): string {
  if (severity === "block") return "Stops payment";
  if (severity === "hold") return "Holds part";
  return "Noted";
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
/* The match glyph: the triangle in miniature, for lists               */
/* ------------------------------------------------------------------ */
const GLYPH_TONE: Record<string, string> = {
  ok: "var(--ds-accent)",
  pass: "var(--ds-pass)",
  warn: "var(--ds-warn)",
  fail: "var(--ds-fail)",
  off: "var(--ds-line-strong)",
};

/**
 * Invoice, purchase order and delivery as three nodes joined by solid lines,
 * and the ledger as a fourth. The corner that broke is coloured and beats;
 * the ledger node fills when the bill is in.
 */
export function MatchGlyph({
  state,
  posted,
  size = 34,
  dark = false,
}: {
  state: MatchState;
  posted: boolean;
  size?: number;
  dark?: boolean;
}) {
  const bad = state.tone === "fail" ? "fail" : "warn";
  const corner = (name: "invoice" | "order" | "delivery") =>
    state.broken === name ? bad : state.tone === "info" || state.tone === "neutral" ? "off" : "ok";
  const edge = (a: "invoice" | "order" | "delivery", b: "invoice" | "order" | "delivery") =>
    state.broken === a || state.broken === b ? bad : corner(a) === "off" ? "off" : "ok";
  const ledger = posted ? "pass" : state.tone === "warn" && !state.broken ? "warn" : "off";
  const points = { invoice: [5, 6], order: [21, 6], delivery: [13, 19] } as const;
  const line = (a: keyof typeof points, b: keyof typeof points) => (
    <line
      x1={points[a][0]}
      y1={points[a][1]}
      x2={points[b][0]}
      y2={points[b][1]}
      stroke={GLYPH_TONE[edge(a, b)]}
      strokeWidth={1.4}
      strokeLinecap="round"
    />
  );
  return (
    <svg
      className="lf-glyph"
      width={size}
      height={(size * 24) / 34}
      viewBox="0 0 34 24"
      role="img"
      aria-label={`Three-way match: ${state.label}${posted ? ", in the ledger" : ""}`}
      data-dark={dark ? "" : undefined}
    >
      {line("invoice", "order")}
      {line("order", "delivery")}
      {line("delivery", "invoice")}
      <line x1={21} y1={6} x2={30} y2={13} stroke={GLYPH_TONE[ledger === "off" ? "off" : ledger]} strokeWidth={1.2} />
      {(Object.keys(points) as (keyof typeof points)[]).map((name) => {
        const tone = corner(name);
        const beating = state.broken === name && state.live;
        return (
          <g key={name}>
            {beating && (
              <circle className="lf-glyph-ping" cx={points[name][0]} cy={points[name][1]} r={3.2} fill={GLYPH_TONE[tone]} />
            )}
            <circle cx={points[name][0]} cy={points[name][1]} r={2.9} fill={GLYPH_TONE[tone]} />
          </g>
        );
      })}
      <circle
        cx={30}
        cy={13}
        r={3.4}
        fill={ledger === "pass" ? GLYPH_TONE.pass : dark ? "var(--ds-ink-2)" : "var(--ds-surface)"}
        stroke={GLYPH_TONE[ledger]}
        strokeWidth={1.5}
      />
    </svg>
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
  back,
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
  back?: ReactNode;
}) {
  return (
    <Band top canvas={canvas}>
      <div className="lf-band-grid" data-aside={aside ? "" : undefined}>
        <div style={{ minWidth: 0 }}>
          {back && (
            <Reveal y={16} className="lf-back">
              {back}
            </Reveal>
          )}
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
              <div className="lf-actions">{actions}</div>
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

/** A section heading on the work surface: mono label, then a title. */
export function SectionHead({
  label,
  title,
  action,
  id,
}: {
  label: string;
  title: ReactNode;
  action?: ReactNode;
  id?: string;
}) {
  return (
    <Reveal>
      <div className="lf-section-head">
        <div style={{ minWidth: 0 }}>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            {label}
          </p>
          <h2 id={id} className="ds-title lf-section-title">
            {title}
          </h2>
        </div>
        {action}
      </div>
    </Reveal>
  );
}

/* ------------------------------------------------------------------ */
/* Ledger table                                                        */
/* ------------------------------------------------------------------ */
export function Ledger({ head, children, className = "" }: { head: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={`ds-table-wrap ${className}`}>
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
/* Loading, errors, small detail lists                                 */
/* ------------------------------------------------------------------ */
export function Loading({ what }: { what: string }) {
  return (
    <div role="status" className="lf-loading">
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

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="lf-field">
      <dt className="ds-mono-label">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
