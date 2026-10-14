"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import { Constellation, type ConstellationLink, type ConstellationNode } from "@/design/Constellation";
import { Reveal } from "@/design/Reveal";
import { ScrollHeader } from "@/design/ScrollHeader";
import { Band, LinkButton } from "@/design/Surface";
import { clearSession, readToken, readUser, type SignedInUser } from "@/lib/api";
import { initials, taipeiClock } from "@/lib/format";
import { useLoad } from "@/lib/hooks";
import type { DemoState, Health } from "@/lib/types";

const STAFF_NAV = [
  { href: "/", label: "Overview" },
  { href: "/chat", label: "Website chat" },
  { href: "/line", label: "LINE chat" },
  { href: "/desk", label: "The desk" },
  { href: "/evidence", label: "Evidence" },
];

const CUSTOMER_NAV = [
  { href: "/chat", label: "Chat on the website" },
  { href: "/line", label: "Chat on LINE" },
];

/** Customer pages need no sign-in: the chat window is the front door. */
const PUBLIC = ["/chat", "/line", "/sign-in"];

export function BrandMark({ size = 32 }: { size?: number }) {
  // Two channels meeting at one ringed assistant.
  return (
    <span className="fd-brand-mark" style={{ width: size, height: size }} aria-hidden>
      <svg width={size * 0.66} height={size * 0.66} viewBox="0 0 20 20">
        <path d="M3 5 L10 10 M3 15 L10 10" stroke="var(--ds-ink-text)" strokeWidth="1.3" />
        <circle cx="3" cy="5" r="2" fill="var(--ds-ink-text)" />
        <circle cx="3" cy="15" r="2" fill="var(--fd-line)" />
        <circle cx="12.5" cy="10" r="4.6" fill="none" stroke="var(--ds-accent)" strokeWidth="1.6" />
        <circle cx="12.5" cy="10" r="1.9" fill="var(--ds-accent)" />
      </svg>
    </span>
  );
}

function Brand({ href }: { href: string }) {
  return (
    <Link href={href} className="fd-brand" aria-label="FrontDesk, home">
      <BrandMark />
      <span>
        <span className="fd-brand-name">
          Front<span>Desk</span>
        </span>
        <span className="fd-brand-sub">Hengtai Industrial Supply</span>
      </span>
    </Link>
  );
}

function TaipeiTime() {
  const [now, setNow] = useState<string>("");
  useEffect(() => {
    const tick = () => setNow(taipeiClock());
    tick();
    const handle = window.setInterval(tick, 20000);
    return () => window.clearInterval(handle);
  }, []);
  return <span className="ds-mono">Taipei {now || "--:--"}</span>;
}

function EnginePill({ health }: { health: Health | null }) {
  if (!health) return null;
  const builtIn = health.engine === "built-in";
  return (
    <span
      className="ds-status-pill"
      title={
        builtIn
          ? "The built-in engine picks an intent from a fixed list and phrases the reply. No key is needed."
          : "A hosted model picks the intent and phrases the reply. It never reads a record."
      }
    >
      <span className="ds-live-dot" aria-hidden />
      <span>{builtIn ? "Built-in engine" : "Hosted model"}</span>
      <span className="ds-status-pill-faint">· {builtIn ? "no key needed" : "phrasing only"}</span>
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
    <div className="fd-account" ref={box}>
      <button
        type="button"
        className="fd-account-button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
        title={user ? `${user.full_name}, ${user.role_label}` : "Account"}
      >
        <span className="fd-avatar">{initials(user?.full_name ?? "Staff")}</span>
        <span aria-hidden style={{ fontSize: 10, color: "var(--ds-ink-muted)", paddingRight: 4 }}>
          ▾
        </span>
        <span className="ds-sr-only">Account</span>
      </button>
      {open && (
        <div className="fd-account-menu" role="menu">
          <p className="ds-mono-label" style={{ margin: 0, color: "var(--ds-ink-faint)" }}>
            Signed in as
          </p>
          <p style={{ margin: "6px 0 0", fontWeight: 600, fontSize: 15 }}>{user?.full_name ?? "—"}</p>
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

/* ------------------------------------------------------------------ */
/* The closing band: the product's own honesty, never a sales pitch     */
/* ------------------------------------------------------------------ */
const CLOSING_NODES: ConstellationNode[] = [
  { id: "a", x: 0.6, y: 0.32, r: 3, tone: "light" },
  { id: "b", x: 0.66, y: 0.62, r: 3, tone: "pass" },
  { id: "c", x: 0.76, y: 0.46, r: 5, tone: "accent", ring: true, lit: true },
  { id: "d", x: 0.88, y: 0.24, r: 3.4, tone: "warn" },
  { id: "e", x: 0.9, y: 0.7, r: 2.6, tone: "muted" },
  { id: "f", x: 0.95, y: 0.5, r: 2.6, tone: "muted" },
];
const CLOSING_LINKS: ConstellationLink[] = [
  { from: "a", to: "c", tone: "light" },
  { from: "b", to: "c", tone: "pass" },
  { from: "c", to: "d", tone: "warn", lit: true },
];
const CLOSING_PATHS = [
  ["a", "c", "d"],
  ["b", "c", "d"],
];

function ClosingBand() {
  return (
    <Band
      canvas={
        <div className="fd-closing-canvas">
          <Constellation nodes={CLOSING_NODES} links={CLOSING_LINKS} ambient={36} surface="light" traffic={{ paths: CLOSING_PATHS, every: 1600, tone: "accent" }} />
        </div>
      }
      style={{ borderTop: "1px solid var(--ds-ink-line)" }}
    >
      <Reveal y={32}>
        <div className="fd-closing">
          <span className="ds-eyebrow">
            <span className="ds-live-dot" data-tone="warn" aria-hidden />
            What FrontDesk says out loud
          </span>
          <h2 className="ds-display fd-closing-title">
            Containment is not deflection.
            <br />
            <span className="fd-light">A contained conversation is not a solved one.</span>
          </h2>
          <p className="ds-band-lede">
            A contact counts as handled only when the desk answered the question, the customer never asked for a
            person, and nothing was handed over. Returns, technician offers and anything not understood count against
            the number, on purpose. A customer who gave up is not a customer who was helped.
          </p>
          <div className="fd-closing-actions">
            <LinkButton href="/evidence" tone="primary" size="large" arrow>
              See what it got wrong
            </LinkButton>
            <LinkButton href="/chat" tone="ink" size="large">
              Talk to the desk
            </LinkButton>
          </div>
        </div>
      </Reveal>
    </Band>
  );
}

function Footer({ staff }: { staff: boolean }) {
  return (
    <footer className="ds-band" style={{ borderTop: "1px solid var(--ds-ink-line)" }}>
      <div className="ds-band-inner fd-footer">
        <div style={{ display: "grid", gap: 10 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <BrandMark size={26} />
            <span style={{ fontSize: 13, color: "var(--ds-ink-muted)" }}>
              {staff
                ? "Answers from live records, for the right customer only. Every number opens."
                : "Your records are shown to you only, and only after you prove who you are."}
            </span>
          </div>
          <span className="ds-mono" style={{ fontSize: 11, color: "var(--ds-ink-faint)" }}>
            Hengtai Industrial Supply is a fictional company · generated records, real logic
          </span>
        </div>
      </div>
    </footer>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname() || "/";
  const router = useRouter();
  const [user, setUser] = useState<SignedInUser | null>(null);
  const [checked, setChecked] = useState(false);
  const isPublic = PUBLIC.some((path) => pathname === path || pathname.startsWith(`${path}/`));
  const onSignIn = pathname === "/sign-in";
  const { data: health } = useLoad<Health>(onSignIn ? null : "/api/health", [pathname]);
  const { data: demo, error: demoError } = useLoad<DemoState>(onSignIn ? null : "/api/demo/state", [pathname]);

  // The staff accounts are created by loading the company, so on a brand new
  // database nobody can sign in yet. Until it is loaded the guided first run
  // on "/" is open without signing in; the server allows the load only then
  // (see `administrator_unless_first_run` in the backend).
  const firstRun = demo ? !demo.loaded : demoError ? false : null;

  useEffect(() => {
    const token = readToken();
    setUser(token ? readUser() : null);
    setChecked(true);
    if (token || isPublic || firstRun === null) return;
    if (!firstRun) router.replace(`/sign-in?next=${encodeURIComponent(pathname)}`);
    else if (pathname !== "/") router.replace("/");
  }, [isPublic, pathname, router, firstRun]);

  if (onSignIn) return <>{children}</>;
  if (!checked) return null;
  if (!user && !isPublic && !(firstRun && pathname === "/")) return null;

  const signOut = () => {
    clearSession();
    setUser(null);
    router.replace("/sign-in");
  };

  const staff = Boolean(user);
  const nav = (staff ? STAFF_NAV : CUSTOMER_NAV).map((item) => ({
    ...item,
    active: item.href === "/" ? pathname === "/" : pathname.startsWith(item.href),
  }));
  const notice = demo?.storage_warning || null;

  return (
    <div
      style={
        notice
          ? ({ "--ds-header-h": "calc(var(--ds-header-top) + var(--ds-header-bar) + 34px)" } as CSSProperties)
          : undefined
      }
    >
      <ScrollHeader
        topLine={
          <>
            <span className="fd-top-line">
              <span className="ds-live-dot" aria-hidden />
              <span>Hengtai Industrial Supply · customer service on the website and LINE, around the clock</span>
            </span>
            <span className="ds-header-top-note">
              <TaipeiTime /> · replies timed from Taipei office hours
            </span>
          </>
        }
        brand={<Brand href={staff ? "/" : "/chat"} />}
        nav={nav}
        status={<EnginePill health={health} />}
        actions={
          staff ? (
            <Account user={user} onSignOut={signOut} />
          ) : (
            <Link href={`/sign-in?next=${encodeURIComponent(pathname)}`} className="ds-btn fd-staff-link" data-tone="ink" data-size="small">
              Staff sign in
            </Link>
          )
        }
        menuFooter={
          <div style={{ display: "grid", gap: 12 }}>
            <EnginePill health={health} />
            {staff ? (
              <button type="button" className="ds-btn" data-tone="ink" onClick={signOut}>
                Sign out {user ? `(${user.full_name})` : ""}
              </button>
            ) : (
              <Link href="/sign-in" className="ds-btn" data-tone="ink">
                Staff sign in
              </Link>
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
            height: 34,
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
          <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{notice}</span>
        </div>
      )}
      <div className="ds-header-spacer" aria-hidden />
      <main id="main" style={{ minHeight: "70vh" }}>
        {children}
      </main>
      {staff && <ClosingBand />}
      <Footer staff={staff} />
    </div>
  );
}
