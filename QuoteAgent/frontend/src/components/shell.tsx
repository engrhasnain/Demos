"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { ScrollHeader } from "@/design/ScrollHeader";
import { clearSession, readToken, readUser, type SignedInUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { initials } from "@/lib/format";
import type { SystemStatus } from "@/lib/types";

const NAV = [
  { href: "/", label: "Overview" },
  { href: "/requests", label: "Requests" },
  { href: "/catalogue", label: "Catalogue" },
  { href: "/duty-tables", label: "Duty and currency" },
  { href: "/business-case", label: "Business case" },
  { href: "/demo", label: "Walkthrough" },
  { href: "/acceptance", label: "Acceptance criteria" },
];

/** The six products of the suite, for the footer. */
const SUITE = [
  { name: "QuoteAgent", colour: "#f5a524", here: true },
  { name: "LedgerFlow", colour: "#10b981" },
  { name: "StockSense", colour: "#2f6bff" },
  { name: "FrontDeskAI", colour: "#ff6b4a" },
  { name: "PortalBot", colour: "#8b5cf6" },
  { name: "OpsAgent", colour: "#14b8a6" },
];

export function BrandMark({ size = 32 }: { size?: number }) {
  // Three request lines meeting at one gate: the quote being assembled.
  return (
    <span className="qa-brand-mark" style={{ width: size, height: size }} aria-hidden>
      <svg width={size * 0.62} height={size * 0.62} viewBox="0 0 20 20">
        <path d="M3 4 L13 10 M3 10 L13 10 M3 16 L13 10" stroke="var(--ds-ink-text)" strokeWidth="1.4" />
        <circle cx="3" cy="4" r="1.9" fill="var(--ds-ink-text)" />
        <circle cx="3" cy="10" r="1.9" fill="var(--ds-ink-text)" />
        <circle cx="3" cy="16" r="1.9" fill="var(--ds-ink-text)" />
        <circle cx="15" cy="10" r="3.4" fill="none" stroke="var(--ds-accent)" strokeWidth="2" />
      </svg>
    </span>
  );
}

function Brand() {
  return (
    <Link href="/" className="qa-brand" aria-label="QuoteAgent, overview">
      <BrandMark />
      <span>
        <span className="qa-brand-name">
          Quote<span>Agent</span>
        </span>
        <span className="qa-brand-sub">Hengtai Industrial Supply</span>
      </span>
    </Link>
  );
}

function EnginePill({ status }: { status: SystemStatus | null }) {
  if (!status) return null;
  const builtIn = status.reasoning_engine.active_engine === "built-in";
  return (
    <span className="ds-status-pill" title={status.reasoning_engine.explanation}>
      <span className="ds-live-dot" aria-hidden />
      <span>{builtIn ? "Built-in engine" : "External model"}</span>
      <span className="ds-status-pill-faint">
        · {builtIn ? "no key needed" : status.reasoning_engine.model || "configured"}
      </span>
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
    <div className="qa-account" ref={box}>
      <button
        type="button"
        className="qa-account-button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
        title={user ? `${user.full_name}, ${user.role_label}` : "Account"}
      >
        <span className="qa-avatar">{initials(user?.full_name ?? "Signed in")}</span>
        <span aria-hidden style={{ fontSize: 10, color: "var(--ds-ink-muted)", paddingRight: 4 }}>
          ▾
        </span>
        <span className="ds-sr-only">Account</span>
      </button>
      {open && (
        <div className="qa-account-menu" role="menu">
          <p className="ds-mono-label" style={{ margin: 0, color: "var(--ds-ink-faint)" }}>
            Signed in as
          </p>
          <p style={{ margin: "6px 0 0", fontWeight: 600, fontSize: 15 }}>{user?.full_name ?? "—"}</p>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: "var(--ds-ink-muted)" }}>
            {user?.role_label}
          </p>
          <p
            className="ds-mono"
            style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--ds-ink-faint)", overflowWrap: "anywhere" }}
          >
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
  const [signedIn, setSignedIn] = useState(false);
  const [checked, setChecked] = useState(false);

  const onSignIn = pathname === "/sign-in";
  const { data: status, error: statusError } = useLoad<SystemStatus>("/api/system/status", [pathname]);
  // The accounts are created by loading the demonstration data, so on an empty
  // database nobody can sign in yet. Until it is loaded the first-run screen
  // is open without signing in; the server allows that load only then.
  const firstRun = status ? !status.data_loaded : statusError ? false : null;

  useEffect(() => {
    const token = readToken();
    setSignedIn(Boolean(token));
    setUser(readUser());
    setChecked(true);
    if (token || onSignIn || firstRun === null) return;
    if (!firstRun) router.replace("/sign-in");
    else if (pathname !== "/") router.replace("/");
  }, [onSignIn, router, pathname, firstRun]);

  if (onSignIn) return <>{children}</>;
  if (!checked) return null;
  if (!signedIn && !(firstRun && pathname === "/")) return null;

  const signOut = () => {
    clearSession();
    router.replace("/sign-in");
  };

  const notice = status?.storage_warning
    ? { tone: "warn", text: status.storage_warning, link: null }
    : status && !status.data_loaded && pathname !== "/"
      ? { tone: "warn", text: "No demonstration data yet.", link: { href: "/", label: "Load it" } }
      : null;

  const nav = NAV.map((item) => ({
    ...item,
    active: item.href === "/" ? pathname === "/" : pathname.startsWith(item.href),
  }));

  return (
    <div
      style={
        notice
          ? ({ "--ds-header-h": "calc(var(--ds-header-top) + var(--ds-header-bar) + 36px)" } as CSSProperties)
          : undefined
      }
    >
      <ScrollHeader
        brand={<Brand />}
        nav={nav}
        status={<EnginePill status={status} />}
        actions={signedIn ? <Account user={user} onSignOut={signOut} /> : undefined}
        menuFooter={
          <div style={{ display: "grid", gap: 12 }}>
            <EnginePill status={status} />
            {signedIn && (
              <button type="button" className="ds-btn" data-tone="ink" onClick={signOut}>
                Sign out {user ? `(${user.full_name})` : ""}
              </button>
            )}
          </div>
        }
      />
      {notice && (
        <div
          role="status"
          style={{
            position: "fixed",
            top: "calc(var(--ds-header-top) + var(--ds-header-bar))",
            left: 0,
            right: 0,
            zIndex: 39,
            height: 36,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 10,
            padding: "0 16px",
            background: "var(--ds-warn)",
            color: "var(--ds-on-fill)",
            fontSize: 13,
            fontWeight: 600,
            whiteSpace: "nowrap",
            overflow: "hidden",
            textOverflow: "ellipsis",
          }}
        >
          <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{notice.text}</span>
          {notice.link && (
            <Link href={notice.link.href} style={{ color: "inherit", textDecoration: "underline", textUnderlineOffset: 3 }}>
              {notice.link.label}
            </Link>
          )}
        </div>
      )}
      <div className="ds-header-spacer" aria-hidden />
      <main id="main" style={{ minHeight: "70vh" }}>
        {children}
      </main>
      <footer className="ds-band" style={{ borderTop: "1px solid var(--ds-ink-line)" }}>
        <div
          className="ds-band-inner"
          style={{ paddingTop: 28, paddingBottom: 28, display: "flex", flexWrap: "wrap", gap: "18px 32px", alignItems: "center", justifyContent: "space-between" }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <BrandMark size={26} />
            <span style={{ fontSize: 13, color: "var(--ds-ink-muted)" }}>
              Fictional company, generated data. Every number opens.
            </span>
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 16px" }}>
            <span className="ds-mono-label">Hengtai operations suite</span>
            {SUITE.map((product) => (
              <span
                key={product.name}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 7,
                  fontSize: 12.5,
                  fontWeight: product.here ? 700 : 500,
                  color: product.here ? "var(--ds-ink-text)" : "var(--ds-ink-muted)",
                }}
              >
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
