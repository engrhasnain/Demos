"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { ScrollHeader } from "@/design/ScrollHeader";
import { clearSession, readToken, readUser, type SignedInUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { initials } from "@/lib/format";
import type { DemoState } from "@/lib/types";

const NAV = [
  { href: "/", label: "Desk" },
  { href: "/invoices", label: "Invoices" },
  { href: "/suppliers", label: "Suppliers" },
  { href: "/ledger", label: "Ledger" },
  { href: "/walkthrough", label: "Walkthrough" },
  { href: "/evidence", label: "Evidence" },
];

/** The six products of the suite, for the footer. */
const SUITE = [
  { name: "QuoteAgent", colour: "#f5a524" },
  { name: "LedgerFlow", colour: "#10b981", here: true },
  { name: "StockSense", colour: "#2f6bff" },
  { name: "FrontDeskAI", colour: "#ff6b4a" },
  { name: "PortalBot", colour: "#8b5cf6" },
  { name: "OpsAgent", colour: "#14b8a6" },
];

/** Invoice, purchase order and delivery joined into a triangle, and the ledger. */
export function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <span className="lf-brand-mark" style={{ width: size, height: size }} aria-hidden>
      <svg width={size * 0.66} height={size * 0.66} viewBox="0 0 22 22">
        <path d="M4 5 L13 5 L8.5 13 Z" fill="none" stroke="#0b0d12" strokeWidth="1.6" strokeLinejoin="round" />
        <path d="M13 5 L18 16" stroke="#0b0d12" strokeWidth="1.6" />
        <circle cx="4" cy="5" r="2.1" fill="#0b0d12" />
        <circle cx="13" cy="5" r="2.1" fill="#0b0d12" />
        <circle cx="8.5" cy="13" r="2.1" fill="#0b0d12" />
        <circle cx="18" cy="16.5" r="3.2" fill="none" stroke="#0b0d12" strokeWidth="1.8" />
      </svg>
    </span>
  );
}

function Brand() {
  return (
    <Link href="/" className="lf-brand" aria-label="LedgerFlow, the desk">
      <BrandMark />
      <span>
        <span className="lf-brand-name">
          Ledger<span>Flow</span>
        </span>
        <span className="lf-brand-sub">Hengtai Industrial Supply</span>
      </span>
    </Link>
  );
}

export function EnginePill({ state }: { state: DemoState | null }) {
  if (!state) return null;
  const builtIn = state.reading_engine === "built-in";
  return (
    <span
      className="ds-status-pill"
      title={
        builtIn
          ? "Invoices are read by the built-in engine: deterministic code, no key, no network."
          : "Invoices are read by an external model, held to the same strict schema and checked by code."
      }
    >
      <span className="ds-live-dot" aria-hidden />
      <span>{builtIn ? "Built-in engine" : "External model"}</span>
      <span className="ds-status-pill-faint">· {builtIn ? "no key needed" : "checked by code"}</span>
    </span>
  );
}

function Account({ user, onSignOut }: { user: SignedInUser | null; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (event: PointerEvent) => {
      if (box.current && !box.current.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    window.addEventListener("pointerdown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("pointerdown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className="lf-account" ref={box}>
      <button
        type="button"
        className="lf-account-button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
        title={user ? `${user.full_name}, ${user.role_label}` : "Account"}
      >
        <span className="lf-avatar">{initials(user?.full_name ?? "Signed in")}</span>
        <span aria-hidden className="lf-account-caret">
          ▾
        </span>
        <span className="ds-sr-only">Account</span>
      </button>
      {open && (
        <div className="lf-account-menu" role="menu">
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Signed in as
          </p>
          <p style={{ margin: "6px 0 0", fontWeight: 650, fontSize: 15 }}>{user?.full_name ?? "—"}</p>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: "var(--ds-ink-muted)" }}>{user?.role_label}</p>
          <p className="ds-mono" style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--ds-ink-faint)", overflowWrap: "anywhere" }}>
            {user?.email}
          </p>
          <button
            type="button"
            role="menuitem"
            className="ds-btn"
            data-tone="ink"
            data-size="small"
            data-full=""
            style={{ marginTop: 14 }}
            onClick={onSignOut}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const router = useRouter();
  const [user, setUser] = useState<SignedInUser | null>(null);
  const [checked, setChecked] = useState(false);

  const onSignIn = pathname === "/sign-in";
  const { data: state } = useLoad<DemoState>("/api/demo/state", [pathname]);

  useEffect(() => {
    const token = readToken();
    setUser(readUser());
    setChecked(true);
    if (!token && !onSignIn) router.replace("/sign-in");
  }, [onSignIn, router, pathname]);

  if (onSignIn) return <>{children}</>;
  if (!checked) return null;

  const signOut = () => {
    clearSession();
    router.replace("/sign-in");
  };

  const notice = state?.storage_is_temporary
    ? "Demonstration data — resets when the server restarts."
    : null;

  const nav = NAV.map((item) => ({
    ...item,
    active: item.href === "/" ? pathname === "/" : pathname.startsWith(item.href),
  }));

  return (
    <div style={notice ? ({ "--ds-header-h": "100px" } as CSSProperties) : undefined}>
      <ScrollHeader
        brand={<Brand />}
        nav={nav}
        status={<EnginePill state={state} />}
        actions={<Account user={user} onSignOut={signOut} />}
        menuFooter={
          <div style={{ display: "grid", gap: 12 }}>
            <EnginePill state={state} />
            <button type="button" className="ds-btn" data-tone="ink" onClick={signOut}>
              Sign out {user ? `(${user.full_name})` : ""}
            </button>
          </div>
        }
      />
      {notice && (
        <div role="status" className="lf-notice">
          <span>{notice}</span>
        </div>
      )}
      <div className="ds-header-spacer" aria-hidden />
      <main id="main" style={{ minHeight: "70vh" }}>
        {children}
      </main>
      <footer className="ds-band" style={{ borderTop: "1px solid var(--ds-ink-line)" }}>
        <div className="ds-band-inner lf-footer">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <BrandMark size={26} />
            <span style={{ fontSize: 13, color: "var(--ds-ink-muted)" }}>
              Fictional company, generated data. Every number opens.
            </span>
          </div>
          <div className="lf-suite">
            <span className="ds-mono-label">Hengtai operations suite</span>
            {SUITE.map((product) => (
              <span key={product.name} className="lf-suite-item" data-here={product.here ? "" : undefined}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: product.colour }} aria-hidden />
                {product.name}
              </span>
            ))}
          </div>
        </div>
      </footer>
    </div>
  );
}
