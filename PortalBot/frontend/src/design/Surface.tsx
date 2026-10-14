/**
 * Surfaces and controls: the ink band, the white card, buttons, stats,
 * banners. Server-safe (no hooks), so they can be used anywhere.
 */

import Link from "next/link";
import type { CSSProperties, ReactNode } from "react";

/* ------------------------------------------------------------------ */
/* Ink band                                                            */
/* ------------------------------------------------------------------ */
export function Band({
  children,
  top = false,
  canvas,
  className = "",
  innerClassName = "",
  style,
}: {
  children: ReactNode;
  /** The first band on a page: runs up behind the fixed header. */
  top?: boolean;
  /** A Constellation (or anything) drawn behind the content. */
  canvas?: ReactNode;
  className?: string;
  innerClassName?: string;
  style?: CSSProperties;
}) {
  return (
    <section className={`ds-band ${className}`} data-top={top ? "" : undefined} style={style}>
      {canvas && <div className="ds-band-canvas">{canvas}</div>}
      <div className={`ds-band-inner ${innerClassName}`}>{children}</div>
    </section>
  );
}

export function Eyebrow({ parts }: { parts: ReactNode[] }) {
  return (
    <span className="ds-eyebrow">
      <span className="ds-live-dot" data-tone="accent" aria-hidden />
      {parts.map((part, index) => (
        <span key={index}>
          {index > 0 && <span className="ds-eyebrow-sep">· </span>}
          {part}
        </span>
      ))}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* Card                                                                */
/* ------------------------------------------------------------------ */
export function Card({
  eyebrow,
  title,
  subtitle,
  action,
  children,
  tone,
  flush = false,
  className = "",
  style,
  id,
}: {
  eyebrow?: ReactNode;
  title?: ReactNode;
  subtitle?: ReactNode;
  action?: ReactNode;
  children?: ReactNode;
  tone?: "accent" | "ink";
  flush?: boolean;
  className?: string;
  style?: CSSProperties;
  id?: string;
}) {
  return (
    <section className={`ds-card ${className}`} data-tone={tone} style={style} id={id}>
      {(title || eyebrow || action) && (
        <header className="ds-card-head">
          <div style={{ minWidth: 0 }}>
            {eyebrow && <p className="ds-mono-label" style={{ margin: 0 }}>{eyebrow}</p>}
            {title && <h2 className="ds-card-title">{title}</h2>}
            {subtitle && <p className="ds-card-sub">{subtitle}</p>}
          </div>
          {action && <div style={{ flexShrink: 0 }}>{action}</div>}
        </header>
      )}
      <div className="ds-card-body" data-flush={flush ? "" : undefined}>
        {children}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Buttons                                                             */
/* ------------------------------------------------------------------ */
export type ButtonTone = "primary" | "secondary" | "ink" | "danger" | "ghost";

export function Spinner() {
  return <span className="ds-spinner" aria-hidden />;
}

export function Button({
  children,
  onClick,
  tone = "secondary",
  size,
  disabled,
  busy,
  type = "button",
  title,
  full,
  arrow,
}: {
  children: ReactNode;
  onClick?: () => void;
  tone?: ButtonTone;
  size?: "small" | "large";
  disabled?: boolean;
  busy?: boolean;
  type?: "button" | "submit";
  title?: string;
  full?: boolean;
  arrow?: boolean;
}) {
  return (
    <button
      type={type}
      title={title}
      onClick={onClick}
      disabled={disabled || busy}
      aria-busy={busy || undefined}
      className="ds-btn"
      data-tone={tone}
      data-size={size}
      data-full={full ? "" : undefined}
    >
      {busy && <Spinner />}
      {children}
      {arrow && !busy && (
        <span className="ds-btn-arrow" aria-hidden>
          →
        </span>
      )}
    </button>
  );
}

export function LinkButton({
  href,
  children,
  tone = "secondary",
  size,
  arrow,
  external,
}: {
  href: string;
  children: ReactNode;
  tone?: ButtonTone;
  size?: "small" | "large";
  arrow?: boolean;
  external?: boolean;
}) {
  const inner = (
    <>
      {children}
      {arrow && (
        <span className="ds-btn-arrow" aria-hidden>
          →
        </span>
      )}
    </>
  );
  if (external) {
    return (
      <a href={href} target="_blank" rel="noreferrer" className="ds-btn" data-tone={tone} data-size={size}>
        {inner}
      </a>
    );
  }
  return (
    <Link href={href} className="ds-btn" data-tone={tone} data-size={size}>
      {inner}
    </Link>
  );
}

/* ------------------------------------------------------------------ */
/* Big number on a band                                                */
/* ------------------------------------------------------------------ */
export function Stat({
  label,
  value,
  unit,
  tone,
  note,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: ReactNode;
  tone?: "accent" | "pass" | "warn" | "fail";
  note?: ReactNode;
}) {
  return (
    <div style={{ minWidth: 0 }}>
      <span className="ds-stat-value" data-tone={tone}>
        {value}
        {unit && <span className="ds-stat-unit">{unit}</span>}
      </span>
      <span className="ds-mono-label ds-stat-label">{label}</span>
      {note && (
        <span style={{ display: "block", marginTop: 4, fontSize: 12, color: "var(--ds-ink-muted)" }}>
          {note}
        </span>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Banner, empty state, stamp                                          */
/* ------------------------------------------------------------------ */
export function Banner({
  tone = "accent",
  title,
  children,
  action,
  className = "",
}: {
  tone?: "pass" | "fail" | "warn" | "accent" | "neutral";
  title?: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`ds-banner ${className}`} data-tone={tone} role={tone === "fail" ? "alert" : undefined}>
      <div style={{ minWidth: 0, flex: "1 1 280px" }}>
        {title && <p className="ds-banner-title" style={{ margin: 0 }}>{title}</p>}
        {children && <div className="ds-banner-text">{children}</div>}
      </div>
      {action}
    </div>
  );
}

export function Empty({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="ds-empty">
      <p style={{ margin: 0, fontWeight: 600 }}>{title}</p>
      {children && (
        <div style={{ marginTop: 4, fontSize: 13.5, color: "var(--ds-text-2)" }}>{children}</div>
      )}
    </div>
  );
}

/** A part number or reference, stamped in mono on ink. */
export function Stamp({
  children,
  title,
  tone = "ink",
}: {
  children: ReactNode;
  title?: string;
  tone?: "ink" | "light";
}) {
  return (
    <span className="ds-stamp" data-tone={tone} title={title}>
      {children}
    </span>
  );
}
