"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { ScrollHeader } from "@/design/ScrollHeader";
import { ClosingBand } from "@/components/closing-band";
import { clearSession, readToken, readUser, type SignedInUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { DemoState } from "@/lib/types";

const NAV = [
  { href: "/", label: "Desk" },
  { href: "/plan", label: "To order" },
  { href: "/parts", label: "Parts" },
  { href: "/suppliers", label: "Suppliers" },
  { href: "/evidence", label: "Evidence" },
];

/**
 * The mark: a part's year at a glance. Two dark weeks, a spike, a dark
 * week, a smaller sale: intermittent demand in four strokes.
 */
export function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <span className="ss-brand-mark" style={{ width: size, height: size }} aria-hidden>
      <svg width={size * 0.64} height={size * 0.64} viewBox="0 0 20 20">
        <circle cx="3" cy="16.4" r="1.5" fill="var(--ds-on-accent)" opacity="0.7" />
        <rect x="6.2" y="3" width="2.8" height="14.9" fill="var(--ds-on-accent)" />
        <circle cx="12" cy="16.4" r="1.5" fill="var(--ds-on-accent)" opacity="0.7" />
        <rect x="15" y="9.5" width="2.8" height="8.4" fill="var(--ds-on-accent)" />
      </svg>
    </span>
  );
}

function Brand() {
  return (
    <Link href="/" className="ss-brand" aria-label="StockSense, the desk">
      <BrandMark />
      <span>
        <span className="ss-brand-name">
          Stock<span>Sense</span>
        </span>
        <span className="ss-brand-sub">Hengtai Industrial Supply</span>
      </span>
    </Link>
  );
}

export function EnginePill({ state }: { state: DemoState | null }) {
  if (!state) return null;
  const builtIn = state.engine === "built-in";
  return (
    <span
      className="ds-status-pill"
      title={
        builtIn
          ? "Every forecast and quantity comes from the built-in engine: deterministic code, no key, no network."
          : "A hosted model writes words only. Every number still comes from the built-in engine."
      }
    >
      <span className="ds-live-dot" aria-hidden />
      <span>{builtIn ? "Built-in engine" : "External model for words"}</span>
      <span className="ds-status-pill-faint">· numbers from code</span>
    </span>
  );
}

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
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
    <div className="ss-account" ref={box}>
      <button
        type="button"
        className="ss-account-button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
        title={user ? `${user.full_name}, ${user.role_label}` : "Account"}
      >
        <span className="ss-avatar">{initials(user?.full_name ?? "Signed in")}</span>
        <span aria-hidden className="ss-account-caret">
          ▾
        </span>
        <span className="ds-sr-only">Account</span>
      </button>
      {open && (
        <div className="ss-account-menu" role="menu">
          <p className="ds-mono-label" style={{ margin: 0, color: "var(--ds-ink-faint)" }}>
            Signed in as
          </p>
          <p style={{ margin: "6px 0 0", fontWeight: 600, fontSize: 15 }}>{user?.full_name ?? "Nobody"}</p>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: "var(--ds-ink-muted)" }}>{user?.role_label}</p>
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
  const [checked, setChecked] = useState(false);

  const onSignIn = pathname === "/sign-in";
  const { data: state } = useLoad<DemoState>(onSignIn ? null : "/api/demo/state", [pathname]);

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

  const notice =
    state?.storage_is_temporary
      ? {
          text: "This copy keeps its data in temporary storage: a restart starts it empty.",
          link: null,
        }
      : state && !state.loaded && pathname !== "/"
        ? { text: "No company data is loaded yet.", link: { href: "/", label: "Load it" } }
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
      <a href="#main" className="ss-skip">
        Skip to the content
      </a>
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
        <div role="status" className="ss-notice">
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
      <ClosingBand />
      <footer className="ds-band" style={{ borderTop: "1px solid var(--ds-ink-line)" }}>
        <div className="ds-band-inner ss-footer">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <BrandMark size={26} />
            <span style={{ display: "grid", gap: 2 }}>
              <span style={{ fontSize: 14, fontWeight: 600, color: "var(--ds-ink-text)" }}>
                StockSense for Hengtai Industrial Supply
              </span>
              <span style={{ fontSize: 12.5, color: "var(--ds-ink-muted)" }}>
                Every number opens to show how it was worked out.
              </span>
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}
