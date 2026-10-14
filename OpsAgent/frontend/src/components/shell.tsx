"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";

import { Constellation, type ConstellationLink, type ConstellationNode } from "@/design/Constellation";
import { Reveal } from "@/design/Reveal";
import { ScrollHeader } from "@/design/ScrollHeader";
import { Band, LinkButton } from "@/design/Surface";
import { ApiError, clearSession, signInAs, type SignedInUser } from "@/lib/api";
import { useLoad, useSession } from "@/lib/session";
import type { DemoPerson, Health } from "@/lib/types";
import { initials, reaches, roleWords } from "@/lib/words";

const NAV: { href: string; label: string; role?: string }[] = [
  { href: "/", label: "Overview" },
  { href: "/ask", label: "Ask" },
  { href: "/catalogue", label: "Reviewed queries" },
  { href: "/proposals", label: "Proposals" },
  { href: "/register", label: "Access record", role: "manager" },
  { href: "/assurance", label: "Assurance" },
];

/** The core with five systems around it, inside a ring. */
export function BrandMark({ size = 32 }: { size?: number }) {
  const spokes = [0, 1, 2, 3, 4].map((index) => {
    const angle = -Math.PI / 2 + (index / 5) * Math.PI * 2;
    return { x: 10 + Math.cos(angle) * 6.6, y: 10 + Math.sin(angle) * 6.6 };
  });
  return (
    <span className="oa-brand-mark" style={{ width: size, height: size }} aria-hidden>
      <svg width={size * 0.66} height={size * 0.66} viewBox="0 0 20 20">
        {spokes.map((point, index) => (
          <line key={index} x1="10" y1="10" x2={point.x} y2={point.y} stroke="var(--ds-ink-muted)" strokeWidth="1" />
        ))}
        {spokes.map((point, index) => (
          <circle key={`n-${index}`} cx={point.x} cy={point.y} r="1.7" fill={index === 1 ? "var(--ds-fail)" : "var(--ds-ink-text)"} />
        ))}
        <circle cx="10" cy="10" r="3" fill="var(--ds-accent)" />
      </svg>
    </span>
  );
}

function Brand() {
  return (
    <Link href="/" className="oa-brand" aria-label="OpsAgent, overview">
      <BrandMark />
      <span>
        <span className="oa-brand-name">
          Ops<span>Agent</span>
        </span>
        <span className="oa-brand-sub">Hengtai Industrial Supply</span>
      </span>
    </Link>
  );
}

function EnginePill({ health }: { health: Health | null }) {
  if (!health) return null;
  const builtIn = health.engine === "built-in";
  return (
    <span
      className="ds-status-pill"
      title={builtIn ? "Pattern matching and the database. No key, no model." : "A hosted model picks from the reviewed queries and writes the sentence."}
    >
      <span className="ds-live-dot" aria-hidden />
      <span>{builtIn ? "Built-in engine" : "External model"}</span>
      <span className="ds-status-pill-faint">· {builtIn ? "no key needed" : "picks and phrases only"}</span>
    </span>
  );
}

/** Switch who is asking: the whole demonstration turns on it. */
export function usePeople() {
  const { data } = useLoad<{ people: DemoPerson[]; password: string }>("/api/demo/people");
  return data;
}

function Account({ user }: { user: SignedInUser | null }) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState("");
  const [trouble, setTrouble] = useState("");
  const box = useRef<HTMLDivElement>(null);
  const people = usePeople();

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

  if (!user) {
    return (
      <Link href="/?choose=1" className="ds-btn" data-tone="primary" data-size="small">
        Choose who is asking
      </Link>
    );
  }

  const become = async (email: string) => {
    if (!people) return;
    setBusy(email);
    setTrouble("");
    try {
      await signInAs(email, people.password);
      setOpen(false);
    } catch (error) {
      setTrouble(error instanceof ApiError ? error.message : String(error));
    } finally {
      setBusy("");
    }
  };

  return (
    <div className="oa-account" ref={box}>
      <button
        type="button"
        className="oa-account-button"
        aria-expanded={open}
        aria-haspopup="true"
        onClick={() => setOpen((value) => !value)}
        title={`${user.name}, ${user.role_label}`}
      >
        <span className="oa-avatar">{initials(user.name)}</span>
        <span className="oa-account-who">
          <b>{user.name}</b>
          <span>{user.role_label}</span>
        </span>
        <span aria-hidden className="oa-account-caret">
          ▾
        </span>
        <span className="ds-sr-only">Switch who is asking</span>
      </button>
      {open && (
        <div className="oa-account-menu" role="menu">
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Asking as
          </p>
          <p style={{ margin: "6px 0 0", fontWeight: 600, fontSize: 15 }}>{user.name}</p>
          <p style={{ margin: "2px 0 0", fontSize: 13, color: "var(--ds-ink-muted)" }}>
            {user.role_label} · {user.reach?.summary ?? ""}
          </p>
          <p className="ds-mono-label" style={{ margin: "16px 0 8px" }}>
            Ask as somebody else
          </p>
          <div className="oa-switch-list">
            {(people?.people ?? []).map((person) => (
              <button
                key={person.email}
                type="button"
                role="menuitem"
                className="oa-switch"
                data-current={person.email === user.email ? "" : undefined}
                disabled={busy !== "" || person.email === user.email}
                onClick={() => void become(person.email)}
              >
                <span className="oa-avatar" data-size="small">
                  {initials(person.name)}
                </span>
                <span style={{ minWidth: 0 }}>
                  <b>{person.name}</b>
                  <span>
                    {roleWords(person.role)} · {person.reach.summary}
                  </span>
                </span>
                {busy === person.email && <span className="ds-spinner" aria-hidden />}
              </button>
            ))}
          </div>
          {trouble && <p style={{ margin: "10px 0 0", fontSize: 12.5, color: "var(--ds-fail)" }}>{trouble}</p>}
          <button
            type="button"
            role="menuitem"
            className="ds-btn"
            data-tone="ink"
            data-size="small"
            data-full=""
            style={{ marginTop: 14 }}
            onClick={() => {
              clearSession();
              setOpen(false);
              router.replace("/?choose=1");
            }}
          >
            Sign out
          </button>
        </div>
      )}
    </div>
  );
}

const CLOSING_NODES: ConstellationNode[] = [
  { id: "core", x: 0.78, y: 0.5, r: 5, tone: "accent", ring: true, lit: true, drift: 1 },
  ...[0, 1, 2, 3, 4].map((index) => {
    const angle = -Math.PI / 2 + (index / 5) * Math.PI * 2;
    return {
      id: `d-${index}`,
      x: 0.78 + Math.cos(angle) * 0.13,
      y: 0.5 + Math.sin(angle) * 0.33,
      r: 3,
      tone: index === 1 ? ("fail" as const) : ("light" as const),
      ring: index === 1,
    };
  }),
];
const CLOSING_LINKS: ConstellationLink[] = [0, 2, 3, 4].map((index) => ({ from: "core", to: `d-${index}`, tone: "accent" }));
const CLOSING_PATHS = [0, 2, 3, 4].map((index) => ["core", `d-${index}`]);

function ClosingBand() {
  return (
    <Band
      canvas={
        <div className="oa-closing-canvas">
          <Constellation nodes={CLOSING_NODES} links={CLOSING_LINKS} ambient={36} traffic={{ paths: CLOSING_PATHS, every: 1100 }} />
        </div>
      }
      style={{ borderTop: "1px solid var(--ds-ink-line)" }}
    >
      <Reveal y={32}>
        <div className="oa-closing">
          <span className="ds-eyebrow">
            <span className="ds-live-dot" data-tone="accent" aria-hidden />
            What it does not claim
          </span>
          <h2 className="ds-display oa-closing-title">
            The planner can be fooled.
            <br />
            <span className="oa-light ds-accent-text">What it can reach is fixed.</span>
          </h2>
          <p className="ds-band-lede">
            Anything that reads text can be talked into the wrong plan. Here the worst a fooled plan can name is one of
            nineteen reviewed queries, and each one still runs under the asker&rsquo;s own role check and row filter.
            The acceptance check attacks exactly that, and shows what it found.
          </p>
          <div className="oa-closing-actions">
            <LinkButton href="/ask" tone="primary" size="large" arrow>
              Ask a question
            </LinkButton>
            <LinkButton href="/assurance" tone="ink" size="large">
              See the acceptance results
            </LinkButton>
          </div>
        </div>
      </Reveal>
    </Band>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { user } = useSession();
  const { data: health } = useLoad<Health>("/api/health", [pathname]);

  const nav = NAV.filter((item) => !item.role || reaches(user?.role, item.role)).map((item) => ({
    href: item.href,
    label: item.label,
    active: item.href === "/" ? pathname === "/" : pathname.startsWith(item.href),
  }));

  const notice = health?.storage_is_temporary
    ? "Demonstration data — resets when the server restarts."
    : null;

  return (
    <div style={notice ? ({ "--ds-header-h": "calc(var(--ds-header-top) + var(--ds-header-bar) + 36px)" } as React.CSSProperties) : undefined}>
      <a href="#main" className="oa-skip">
        Skip to the content
      </a>
      <ScrollHeader
        topLine={
          <>
            <span className="oa-top-who">
              {user ? (
                <>
                  <span className="ds-live-dot" data-tone="accent" aria-hidden />
                  Asking as <b>{user.name}</b> · {user.role_label} · {user.reach?.summary ?? ""}
                </>
              ) : (
                <>
                  <span className="ds-live-dot" data-tone="warn" aria-hidden />
                  Nobody signed in. Choose who is asking to begin.
                </>
              )}
            </span>
            <span className="oa-top-note">Hengtai Industrial Supply · generated business data, real queries</span>
          </>
        }
        brand={<Brand />}
        nav={nav}
        status={<EnginePill health={health} />}
        actions={<Account user={user} />}
        menuFooter={<EnginePill health={health} />}
      />
      {notice && (
        <div role="status" className="oa-notice">
          <span>{notice}</span>
        </div>
      )}
      <div className="ds-header-spacer" aria-hidden />
      <main id="main" style={{ minHeight: "70vh" }}>
        {children}
      </main>
      <ClosingBand />
      <footer className="ds-band" style={{ borderTop: "1px solid var(--ds-ink-line)" }}>
        <div className="ds-band-inner oa-footer">
          <div style={{ display: "grid", gap: 10 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <BrandMark size={26} />
              <span style={{ fontSize: 13, color: "var(--ds-ink-muted)" }}>
                Answers from reviewed queries, scoped to what the asker may see. Every number opens.
              </span>
            </div>
            <span className="ds-mono" style={{ fontSize: 11.5, color: "var(--ds-ink-faint)" }}>
              {health ? `${health.capabilities} reviewed queries · ${health.engine === "built-in" ? "built-in engine" : "external model"} · nothing is ever written` : "OpsAgent"}
            </span>
          </div>
        </div>
      </footer>
    </div>
  );
}

/** Used by pages that want the engine name without loading it twice. */
export function useHealth() {
  return useLoad<Health>("/api/health").data;
}

