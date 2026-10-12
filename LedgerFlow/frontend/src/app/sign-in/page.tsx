"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Banner, Button } from "@/design/Surface";
import { Constellation } from "@/design/Constellation";
import { Reveal } from "@/design/Reveal";
import { api, storeSession, type SignedInUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { initials } from "@/lib/format";
import { BrandMark } from "@/components/shell";
import { ErrorNote } from "@/components/ui";

type Person = { email: string; name: string; role: string; role_label: string };

const PASSWORD = "demo1234";

/** What each role may do, in a few words. */
const MAY: Record<string, string> = {
  clerk: "Upload, read, run the post",
  accountant: "Clear exceptions, sign, post",
  controller: "Everything, and the call-back",
  finance_director: "The second signature",
  administrator: "Builds the company data",
};

/** The picture: the three-way match, as an idea (no records before sign-in). */
const NODES = [
  { id: "doc", x: 0.12, y: 0.2, r: 2, tone: "muted" as const },
  { id: "inv", x: 0.24, y: 0.36, r: 5, tone: "light" as const, lit: true, label: "Invoice", side: "left" as const },
  { id: "ord", x: 0.62, y: 0.24, r: 5, tone: "light" as const, lit: true, label: "Purchase order", side: "above" as const },
  { id: "del", x: 0.44, y: 0.7, r: 5, tone: "light" as const, lit: true, label: "Delivery", side: "below" as const },
  { id: "mid", x: 0.43, y: 0.43, r: 3.6, tone: "accent" as const, ring: true, lit: true },
  { id: "led", x: 0.86, y: 0.6, r: 6, tone: "pass" as const, ring: true, lit: true, label: "The ledger", side: "below" as const },
  ...[0, 1, 2].flatMap((index) => [
    { id: `il${index}`, x: 0.16 - index * 0.02, y: 0.44 + index * 0.06, r: 2.2, tone: "light" as const },
    { id: `ol${index}`, x: 0.7 + index * 0.03, y: 0.16 + index * 0.05, r: 2.2, tone: "light" as const },
    { id: `dl${index}`, x: 0.38 + index * 0.06, y: 0.8 + (index % 2) * 0.04, r: 2.2, tone: "light" as const },
  ]),
];
const LINKS = [
  { from: "doc", to: "inv", tone: "light" as const },
  { from: "inv", to: "ord", tone: "accent" as const, lit: true },
  { from: "ord", to: "del", tone: "accent" as const, lit: true },
  { from: "del", to: "inv", tone: "accent" as const, lit: true },
  { from: "inv", to: "mid", tone: "accent" as const },
  { from: "ord", to: "mid", tone: "accent" as const },
  { from: "del", to: "mid", tone: "accent" as const },
  { from: "mid", to: "led", tone: "pass" as const, lit: true },
  ...[0, 1, 2].flatMap((index) => [
    { from: "inv", to: `il${index}`, tone: "light" as const },
    { from: "ord", to: `ol${index}`, tone: "light" as const },
    { from: "del", to: `dl${index}`, tone: "light" as const },
    { from: `il${index}`, to: `ol${index}`, tone: "accent" as const },
    { from: `ol${index}`, to: `dl${index}`, tone: "accent" as const },
  ]),
];
const PATHS = [
  ["doc", "inv", "ord", "del", "inv", "mid", "led"],
  ["il0", "ol0", "dl0"],
  ["il1", "ol1", "dl1"],
  ["il2", "ol2", "dl2"],
  ["mid", "led"],
];

export default function SignIn() {
  const router = useRouter();
  const { data: people, error: peopleError, loading } = useLoad<Person[]>("/api/auth/people");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState(PASSWORD);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!email && people?.length) {
      const controller = people.find((person) => person.role === "controller") ?? people[0];
      setEmail(controller.email);
    }
  }, [people, email]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = await api.post<{ access_token: string; user: SignedInUser }>("/api/auth/sign-in", { email, password });
      storeSession(body.access_token, body.user);
      router.push("/");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="lf-signin">
      <aside className="lf-signin-band">
        <div className="lf-signin-canvas">
          <Constellation nodes={NODES} links={LINKS} ambient={54} traffic={{ paths: PATHS, every: 900 }} />
        </div>
        <div className="lf-signin-copy">
          <Reveal y={20}>
            <span className="lf-brand">
              <BrandMark size={36} />
              <span>
                <span className="lf-brand-name" style={{ fontSize: 22 }}>
                  Ledger<span>Flow</span>
                </span>
                <span className="lf-brand-sub">Hengtai Industrial Supply</span>
              </span>
            </span>
          </Reveal>
          <div>
            <Reveal index={1} y={36}>
              <h1 className="ds-display lf-signin-title">
                Read. Match.
                <br />
                <span className="ds-accent-text">Post once.</span>
              </h1>
            </Reveal>
            <Reveal index={2} y={28}>
              <p className="ds-band-lede">
                Supplier invoices checked against the purchase order and what actually arrived, then posted to the ledger
                exactly once. It stops when something is wrong, and says why.
              </p>
            </Reveal>
          </div>
          <Reveal index={3} y={20}>
            <p className="ds-mono lf-signin-foot">Built-in engine · no key · every number opens</p>
          </Reveal>
        </div>
      </aside>

      <main className="lf-signin-main">
        <form onSubmit={submit} className="lf-signin-form">
          <Reveal y={24}>
            <p className="ds-mono-label" style={{ margin: 0 }}>
              Sign in
            </p>
            <h2 className="ds-title" style={{ margin: "8px 0 0", fontSize: 30 }}>
              Who are you today?
            </h2>
            <p style={{ margin: "8px 0 0", color: "var(--ds-text-2)", fontSize: 14 }}>
              What you may do depends on who you pick. The controller can do every step of the walkthrough.
            </p>
          </Reveal>

          {peopleError && (
            <div style={{ marginTop: 20 }}>
              <ErrorNote error={peopleError} />
            </div>
          )}
          {!loading && !peopleError && people && people.length === 0 && (
            <div style={{ marginTop: 20 }}>
              <Banner tone="warn" title="Nobody to sign in as yet">
                Build the company data first: <span className="ds-mono">python backend/scripts/walkthrough.py</span>
              </Banner>
            </div>
          )}

          <fieldset className="lf-people">
            <legend className="ds-sr-only">Who you are</legend>
            {(people ?? []).map((person, index) => (
              <Reveal key={person.email} index={index + 1} y={20} className="lf-person-wrap">
                <label className="lf-person" data-selected={email === person.email ? "" : undefined}>
                  <input type="radio" name="who" value={person.email} checked={email === person.email} onChange={() => setEmail(person.email)} className="ds-sr-only" />
                  <span className="lf-person-avatar">{initials(person.name)}</span>
                  <span className="lf-person-words">
                    <span className="lf-person-name">{person.name}</span>
                    <span className="lf-person-role">{person.role_label}</span>
                    <span className="lf-person-may ds-mono">{MAY[person.role] ?? ""}</span>
                  </span>
                  <span className="lf-person-dot" aria-hidden />
                </label>
              </Reveal>
            ))}
          </fieldset>

          <label className="ds-mono-label ds-field-label" htmlFor="password" style={{ marginTop: 20 }}>
            Password
          </label>
          <input id="password" type="password" className="ds-input" data-mono="" value={password} onChange={(event) => setPassword(event.target.value)} />

          <div style={{ marginTop: 18 }}>
            <Button tone="primary" type="submit" size="large" busy={busy} full arrow disabled={!email}>
              Sign in
            </Button>
          </div>

          {error && (
            <div style={{ marginTop: 16 }}>
              <ErrorNote error={error} />
            </div>
          )}

          <p className="lf-signin-hint">
            The password is <span className="ds-mono">{PASSWORD}</span> for everyone.
          </p>
        </form>
      </main>
    </div>
  );
}
