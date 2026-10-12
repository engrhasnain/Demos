"use client";

/**
 * StockSense's thin layer over the suite design system: decisions and
 * demand patterns to chip colours, the page band, the ledger table, loading
 * and error states.
 */

import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

import { Band, Banner, Spinner } from "@/design/Surface";
import { StatusChip, type ChipTone } from "@/design/StatusChip";
import { Reveal } from "@/design/Reveal";

export {
  Band,
  Banner,
  Button,
  Card,
  Empty,
  Eyebrow,
  LinkButton,
  Spinner,
  Stamp,
  Stat,
} from "@/design/Surface";
export { StatusChip } from "@/design/StatusChip";
export type { ChipTone } from "@/design/StatusChip";

/* ------------------------------------------------------------------ */
/* Words to colours                                                    */
/* ------------------------------------------------------------------ */
/** Cobalt means buy, amber means buy now because of the shutdown. */
export function decisionTone(decision: string): ChipTone {
  if (decision === "order") return "accent";
  if (decision === "prebuild") return "warn";
  if (decision === "deferred") return "fail";
  return "neutral";
}

export function reasonTone(reason: string): ChipTone {
  if (reason === "below_reorder_point") return "accent";
  if (reason === "shutdown_cover") return "warn";
  if (reason === "no_cash" || reason === "below_minimum") return "fail";
  if (reason === "dead_stock") return "warn";
  if (reason === "covered") return "pass";
  return "neutral";
}

/** The occasional patterns are the hard ones. */
export function patternTone(kind: string): ChipTone {
  if (kind === "smooth") return "pass";
  if (kind === "erratic") return "info";
  if (kind === "intermittent") return "accent";
  if (kind === "lumpy") return "warn";
  if (kind === "no_demand") return "fail";
  return "neutral";
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
  back?: { href: string; label: string };
}) {
  return (
    <Band top canvas={canvas}>
      <div className="ss-band-grid" data-aside={aside ? "" : undefined}>
        <div style={{ minWidth: 0 }}>
          {back && (
            <Reveal y={20}>
              <Link href={back.href} className="ss-back">
                <span aria-hidden>←</span> {back.label}
              </Link>
            </Reveal>
          )}
          <Reveal y={24}>
            <span className="ds-eyebrow" style={back ? { marginTop: 16 } : undefined}>
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              {eyebrow.map((part, index) => (
                <span key={index}>
                  {index > 0 && <span className="ds-eyebrow-sep">· </span>}
                  {part}
                </span>
              ))}
            </span>
          </Reveal>
          <Reveal index={1} y={34}>
            <h1 className="ds-display ds-band-title ss-band-title">
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
              <div className="ss-actions">{actions}</div>
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

/** A section heading on the work surface. */
export function SectionHead({
  label,
  title,
  lede,
  action,
  id,
}: {
  label: string;
  title: ReactNode;
  lede?: ReactNode;
  action?: ReactNode;
  id?: string;
}) {
  return (
    <Reveal>
      <div className="ss-section-head">
        <div style={{ minWidth: 0 }}>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            {label}
          </p>
          <h2 id={id} className="ds-title ss-section-title">
            {title}
          </h2>
          {lede && <p className="ss-section-lede">{lede}</p>}
        </div>
        {action}
      </div>
    </Reveal>
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
export function Loading({ what, dark }: { what: string; dark?: boolean }) {
  return (
    <div role="status" className="ss-loading" data-dark={dark ? "" : undefined}>
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
    <div className="ss-field">
      <dt className="ds-mono-label">{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}

/** A tiny coloured key for a chart. */
export function Key({ colour, label, ring }: { colour: string; label: string; ring?: boolean }) {
  return (
    <span className="ss-key">
      <span
        className="ss-key-swatch"
        data-ring={ring ? "" : undefined}
        style={{ background: ring ? "transparent" : colour, borderColor: colour }}
        aria-hidden
      />
      {label}
    </span>
  );
}
