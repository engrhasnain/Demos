"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";

import { Button } from "@/design/Surface";
import { Constellation, type ConstellationLink, type ConstellationNode } from "@/design/Constellation";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { ApiError, api, storeSession, type SignedInUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { initials } from "@/lib/format";
import { BrandMark } from "@/components/shell";
import { ErrorNote, Loading } from "@/components/ui";

type DemoAccount = {
  email: string;
  full_name: string;
  role: string;
  role_label: string;
  what_they_can_do: string;
  available: boolean;
};

type DemoAccounts = { password: string; note: string; accounts: DemoAccount[] };

const PROMISES: string[] = [
  "Asks instead of guessing",
  "Never invents a price",
  "Every number opens",
  "Nothing leaves unsigned",
];

/** Four request lines converging on one gate, with the promises as tags. */
const NODES: ConstellationNode[] = [
  ...PROMISES.map((promise, index) => ({
    id: `p-${index}`,
    x: 0.18 + (index % 2) * 0.12,
    y: 0.2 + index * 0.18,
    r: 3,
    tone: "light" as const,
    label: promise,
    side: "right" as const,
  })),
  { id: "gate", x: 0.82, y: 0.48, r: 6, tone: "accent", ring: true, lit: true, label: "Approved quote", side: "below" },
  { id: "engine", x: 0.62, y: 0.3, r: 3.4, tone: "accent", lit: true },
  { id: "price", x: 0.64, y: 0.68, r: 3.4, tone: "accent", lit: true },
];
const LINKS: ConstellationLink[] = [
  { from: "p-0", to: "engine", tone: "light" },
  { from: "p-1", to: "engine", tone: "light" },
  { from: "p-2", to: "price", tone: "light" },
  { from: "p-3", to: "price", tone: "light" },
  { from: "engine", to: "gate", tone: "accent", lit: true },
  { from: "price", to: "gate", tone: "accent", lit: true },
];
const PATHS = [
  ["p-0", "engine", "gate"],
  ["p-1", "engine", "gate"],
  ["p-2", "price", "gate"],
  ["p-3", "price", "gate"],
];

export default function SignInPage() {
  return (
    <Suspense fallback={null}>
      <SignIn />
    </Suspense>
  );
}

function SignIn() {
  const router = useRouter();
  const search = useSearchParams();
  const { data, loading } = useLoad<DemoAccounts>("/api/auth/demo-accounts");
  const [email, setEmail] = useState("admin@hengtai-industrial.example");
  const [password, setPassword] = useState("demo1234");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const autoTried = useRef(false);

  const signIn = useCallback(
    async (withEmail: string, withPassword: string) => {
      setBusy(withEmail);
      setError(null);
      try {
        const response = await api.post<{ access_token: string; user: SignedInUser }>("/api/auth/sign-in", {
          email: withEmail,
          password: withPassword,
        });
        storeSession(response.access_token, response.user);
        router.replace("/");
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : String(cause));
      } finally {
        setBusy(null);
      }
    },
    [router],
  );

  useEffect(() => {
    if (data?.password) setPassword(data.password);
  }, [data?.password]);

  // "?as=paul.lee@hengtai-industrial.example" opens straight into a role, which
  // is how a walkthrough is linked to. It only ever accepts one of the
  // demonstration accounts the backend publishes.
  useEffect(() => {
    if (autoTried.current || !data) return;
    const asEmail = search.get("as");
    if (!asEmail) return;
    autoTried.current = true;
    if (data.accounts.some((account) => account.email === asEmail)) {
      void signIn(asEmail, data.password);
    } else {
      setError(`${asEmail} is not one of the demonstration accounts.`);
    }
  }, [data, search, signIn]);

  return (
    <div className="qa-signin">
      <section className="ds-band qa-signin-band">
        <div className="ds-band-canvas">
          <Constellation nodes={NODES} links={LINKS} ambient={54} traffic={{ paths: PATHS, every: 1000 }} />
        </div>
        <div className="qa-signin-copy">
          <Reveal y={20}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <BrandMark size={40} />
              <span>
                <span className="qa-brand-name" style={{ fontSize: 24 }}>
                  Quote<span>Agent</span>
                </span>
                <span className="qa-brand-sub">Hengtai Industrial Supply</span>
              </span>
            </div>
          </Reveal>
          <div>
            <Reveal index={1} y={36}>
              <h1 className="ds-display" style={{ margin: 0, fontSize: "clamp(34px, 4.2vw, 58px)" }}>
                Three and a half hours of quoting.
                <br />
                <span className="qa-light">Same day </span>
                <span className="ds-accent-text">instead.</span>
              </h1>
            </Reveal>
            <Reveal index={2}>
              <p className="ds-band-lede">
                A request for quotation, read line by line, matched to the catalogue, priced to the cent by deterministic
                code and held for a named approver.
              </p>
            </Reveal>
          </div>
          <Reveal index={3}>
            <p className="ds-mono" style={{ margin: 0, fontSize: 11.5, color: "var(--ds-ink-faint)" }}>
              Fictional company · 18,000 parts generated here · no key needed
            </p>
          </Reveal>
        </div>
      </section>

      <section className="qa-signin-form">
        <div style={{ width: "100%", maxWidth: 440 }}>
          <Reveal>
            <p className="ds-mono-label" style={{ margin: 0 }}>
              Sign in
            </p>
            <h2 className="ds-title" style={{ margin: "8px 0 0", fontSize: 30 }}>
              Pick up where the team left off
            </h2>
          </Reveal>
          <form
            style={{ marginTop: 22, display: "grid", gap: 14 }}
            onSubmit={(event) => {
              event.preventDefault();
              void signIn(email, password);
            }}
          >
            <label>
              <span className="ds-mono-label ds-field-label">Email</span>
              <input value={email} onChange={(event) => setEmail(event.target.value)} autoComplete="username" className="ds-input" data-mono="" />
            </label>
            <label>
              <span className="ds-mono-label ds-field-label">Password</span>
              <input
                value={password}
                type="password"
                onChange={(event) => setPassword(event.target.value)}
                autoComplete="current-password"
                className="ds-input"
                data-mono=""
              />
            </label>
            {error && <ErrorNote error={error} />}
            <Button type="submit" tone="primary" size="large" busy={busy === email} full arrow>
              Sign in
            </Button>
          </form>

          <div style={{ marginTop: 32 }}>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12 }}>
              <p className="ds-mono-label" style={{ margin: 0 }}>
                Or sign in as
              </p>
              <p style={{ margin: 0, fontSize: 12, color: "var(--ds-text-3)" }}>
                password <span className="ds-mono" style={{ fontWeight: 600, color: "var(--ds-text)" }}>{data?.password ?? "demo1234"}</span>
              </p>
            </div>

            {loading && <Loading what="Loading the accounts" />}
            {!loading && !data && (
              <p style={{ marginTop: 12, fontSize: 13.5, color: "var(--ds-text-2)" }}>
                The backend is not answering yet. Start it, then reload this page.
              </p>
            )}
            {data && data.accounts.length > 0 && data.accounts.every((account) => !account.available) && (
              <p style={{ marginTop: 12, fontSize: 13.5, color: "var(--ds-text-2)" }}>
                There is no demonstration data yet, so these accounts do not exist.{" "}
                <Link href="/" style={{ color: "var(--ds-accent-ink)", fontWeight: 600 }}>
                  Load the demonstration data
                </Link>{" "}
                first, then sign in here.
              </p>
            )}

            <ul style={{ listStyle: "none", margin: "12px 0 0", padding: 0, display: "grid", gap: 8 }}>
              {(data?.accounts ?? []).map((account, index) => (
                <Reveal as="li" key={account.email} index={index} y={20}>
                  <button
                    type="button"
                    onClick={() => void signIn(account.email, password)}
                    disabled={Boolean(busy)}
                    className="qa-account-row ds-lift"
                  >
                    <span className="qa-avatar" style={{ width: 36, height: 36, borderRadius: 3, fontSize: 12 }}>
                      {initials(account.full_name)}
                    </span>
                    <span style={{ minWidth: 0, flex: 1 }}>
                      <span style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                        <span style={{ fontWeight: 600, fontSize: 14 }}>{account.full_name}</span>
                        <StatusChip tone={account.role === "administrator" ? "accent" : "neutral"} size="small">
                          {account.role_label}
                        </StatusChip>
                      </span>
                      <span style={{ display: "block", marginTop: 3, fontSize: 12.5, lineHeight: 1.45, color: "var(--ds-text-2)" }}>
                        {account.what_they_can_do}
                      </span>
                    </span>
                    {busy === account.email ? <span className="ds-spinner" aria-hidden /> : <span aria-hidden>→</span>}
                  </button>
                </Reveal>
              ))}
            </ul>
          </div>
        </div>
      </section>
    </div>
  );
}

export const dynamic = "force-dynamic";
