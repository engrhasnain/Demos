"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { ScrollHeader } from "@/design/ScrollHeader";
import { api, clearSession, readToken, readUser, storeSession, type SignedInUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Health, Person } from "@/lib/types";
import { ROLE_WORDS } from "@/lib/words";

const NAV = [
  { href: "/", label: "Control" },
  { href: "/shipments", label: "Shipments" },
  { href: "/runs", label: "Runs" },
  { href: "/evidence", label: "Evidence" },
];

/** The six products of the suite, for the footer. */
const SUITE = [
  { name: "QuoteAgent", colour: "#f86f11" },
  { name: "LedgerFlow", colour: "#10b981" },
  { name: "StockSense", colour: "#2f6bff" },
  { name: "FrontDeskAI", colour: "#ff6b4a" },
  { name: "PortalBot", colour: "#8b5cf6", here: true },
  { name: "OpsAgent", colour: "#14b8a6" },
];

/** The shared sign-in password of the sample staff, shown on the sign-in screen too. */
export const STAFF_PASSWORD = "demo1234";

export function BrandMark({ size = 32 }: { size?: number }) {
  // Two screens, one bot between them, one line underneath: the checkpoints.
  return (
    <span className="pb-brand-mark" style={{ width: size, height: size }} aria-hidden>
      <svg width={size * 0.66} height={size * 0.66} viewBox="0 0 22 22">
        <rect x="1" y="4" width="7" height="9" rx="1" fill="none" stroke="var(--ds-ink-text)" strokeWidth="1.4" />
        <rect x="14" y="4" width="7" height="9" rx="1" fill="none" stroke="var(--ds-ink-text)" strokeWidth="1.4" />
        <path d="M8 8.5 H14" stroke="var(--ds-accent)" strokeWidth="1.6" />
        <circle cx="11" cy="8.5" r="2.2" fill="var(--ds-accent)" />
        <path d="M3 18 H19" stroke="var(--ds-accent)" strokeWidth="1.4" />
        <circle cx="5" cy="18" r="1.5" fill="var(--ds-ink-text)" />
        <circle cx="11" cy="18" r="1.5" fill="var(--ds-ink-text)" />
        <circle cx="17" cy="18" r="1.5" fill="var(--ds-accent)" />
      </svg>
    </span>
  );
}

function Brand() {
  return (
    <Link href="/" className="pb-brand" aria-label="PortalBot, control">
      <BrandMark />
      <span>
        <span className="pb-brand-name">
          Portal<span>Bot</span>
        </span>
        <span className="pb-brand-sub">Hengtai Industrial Supply</span>
      </span>
    </Link>
  );
}

export function EnginePill({ health }: { health: Health | null }) {
  const moved = health?.portal_version === "v2";
  return (
    <span
      className="ds-status-pill"
      title="Every step is a recorded script. PortalBot uses no reasoning model, so no key is needed."
    >
      <span className="ds-live-dot" data-tone={moved ? "fail" : undefined} aria-hidden />
      <span>Built-in script</span>
      <span className="ds-status-pill-faint">
        · portal version {health ? (moved ? "2" : "1") : "…"}
      </span>
    </span>
  );
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

/** Sign in as another of the sample staff, for the steps that need their role. */
export async function switchTo(email: string): Promise<SignedInUser> {
  const body = await api.post<{ access_token: string; user: SignedInUser }>("/api/auth/sign-in", {
    email,
    password: STAFF_PASSWORD,
  });
  storeSession(body.access_token, body.user);
  window.dispatchEvent(new Event("portalbot:session"));
  return body.user;
}

function Account({ user, onSignOut }: { user: SignedInUser | null; onSignOut: () => void }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  const { data: people } = useLoad<Person[]>(open ? "/api/auth/people" : null);

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
    <div className="pb-account" ref={box}>
      <button
        type="button"
        className="pb-account-button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
        title={user ? `${user.full_name}, ${user.role_label}` : "Account"}
      >
        <span className="pb-avatar">{initials(user?.full_name ?? "Signed in")}</span>
        <span aria-hidden style={{ fontSize: 10, color: "var(--ds-ink-muted)", paddingRight: 4 }}>
          ▾
        </span>
        <span className="ds-sr-only">Account</span>
      </button>
      {open && (
        <div className="pb-account-menu" role="menu">
          <p className="ds-mono-label" style={{ margin: 0, color: "var(--ds-ink-faint)" }}>
            Signed in as
          </p>
          <p style={{ margin: "6px 0 0", fontWeight: 600, fontSize: 15 }}>{user?.full_name ?? "—"}</p>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: "var(--ds-ink-muted)" }}>
            {ROLE_WORDS[user?.role ?? ""] ?? user?.role_label}
          </p>
          {people && people.length > 0 && (
            <div className="pb-switch">
              <span className="ds-mono-label" style={{ color: "var(--ds-ink-faint)" }}>
                Switch to
              </span>
              {people
                .filter((person) => person.email !== user?.email)
                .map((person) => (
                  <button
                    key={person.email}
                    type="button"
                    role="menuitem"
                    onClick={() =>
                      void switchTo(person.email).then(() => {
                        setOpen(false);
                        window.location.reload();
                      })
                    }
                  >
                    <span>{person.name}</span>
                    <span>{ROLE_WORDS[person.role] ?? person.role_label}</span>
                  </button>
                ))}
            </div>
          )}
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
  const { data: health } = useLoad<Health>("/api/health", [pathname]);

  useEffect(() => {
    const sync = () => setUser(readUser());
    sync();
    setChecked(true);
    if (!readToken() && !onSignIn) router.replace("/sign-in");
    window.addEventListener("portalbot:session", sync);
    return () => window.removeEventListener("portalbot:session", sync);
  }, [onSignIn, router, pathname]);

  if (onSignIn) return <>{children}</>;
  if (!checked || !user) return null;

  const signOut = () => {
    clearSession();
    router.replace("/sign-in");
  };

  const nav = NAV.map((item) => ({
    ...item,
    active: item.href === "/" ? pathname === "/" : pathname.startsWith(item.href),
  }));

  return (
    <div>
      <ScrollHeader
        brand={<Brand />}
        nav={nav}
        status={<EnginePill health={health} />}
        actions={<Account user={user} onSignOut={signOut} />}
        menuFooter={
          <div style={{ display: "grid", gap: 12 }}>
            <EnginePill health={health} />
            <button type="button" className="ds-btn" data-tone="ink" onClick={signOut}>
              Sign out {user ? `(${user.full_name})` : ""}
            </button>
          </div>
        }
      />
      <div className="ds-header-spacer" aria-hidden />
      <main id="main" style={{ minHeight: "70vh" }}>
        {children}
      </main>
      <footer className="ds-band" style={{ borderTop: "1px solid var(--ds-ink-line)" }}>
        <div
          className="ds-band-inner"
          style={{
            paddingTop: 28,
            paddingBottom: 28,
            display: "flex",
            flexWrap: "wrap",
            gap: "18px 32px",
            alignItems: "center",
            justifyContent: "space-between",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <BrandMark size={26} />
            <span style={{ fontSize: 13, color: "var(--ds-ink-muted)" }}>
              Fictional company, generated data, real logic. Every number opens.
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
