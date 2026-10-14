"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState, type FormEvent } from "react";

import { Reveal } from "@/design/Reveal";
import { Button } from "@/design/Surface";
import { DeskScene, type SceneCustomer } from "@/components/desk-scene";
import { BrandMark } from "@/components/shell";
import { ErrorNote } from "@/components/ui";
import { api, storeSession, type SignedInUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

type Person = { email: string; name: string; role: string; role_label: string };

const PASSWORD = "demo1234";

const SCENE: SceneCustomer[] = [
  { id: "a", channel: "web", owner: "Huang Automation", outcome: "answered" },
  { id: "b", channel: "web", owner: null, outcome: "verifying" },
  { id: "c", channel: "web", owner: null, outcome: "handed" },
  { id: "d", channel: "line", owner: "Granite Technologies", outcome: "booked" },
  { id: "e", channel: "line", owner: null, outcome: "verifying" },
];

export default function SignIn() {
  const router = useRouter();
  const { data: people, error: peopleError } = useLoad<Person[]>("/api/auth/people");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState(PASSWORD);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const owners = useMemo(() => ["Huang Automation", "Granite Technologies", "Bluefin Automation", "Wang Automation"], []);

  useEffect(() => {
    if (!email && people?.length) {
      const chosen = people.find((p) => p.role === "administrator") ?? people[0];
      setEmail(chosen.email);
    }
  }, [people, email]);

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = await api.post<{ access_token: string; user: SignedInUser }>("/api/auth/sign-in", { email, password });
      storeSession(body.access_token, body.user);
      const next = new URLSearchParams(window.location.search).get("next");
      router.push(next && next.startsWith("/") && !next.startsWith("//") ? next : "/");
      router.refresh();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fd-signin">
      <aside className="fd-signin-art">
        <div className="fd-signin-canvas">
          <DeskScene customers={SCENE} owners={owners} labels={false} initiallyLit="Huang Automation" seed={9} />
        </div>
        <div className="fd-signin-copy">
          <Reveal y={24}>
            <Link href="/chat" className="fd-brand" aria-label="FrontDesk">
              <BrandMark size={36} />
              <span>
                <span className="fd-brand-name" style={{ fontSize: 22 }}>
                  Front<span>Desk</span>
                </span>
                <span className="fd-brand-sub">Hengtai Industrial Supply</span>
              </span>
            </Link>
          </Reveal>
          <Reveal index={1} y={32}>
            <h1 className="ds-display fd-signin-title">
              The staff side
              <br />
              <span className="fd-light">of the front desk.</span>
            </h1>
          </Reveal>
          <Reveal index={2} y={28}>
            <p className="ds-band-lede">
              Handovers with the conversation already written down, returns waiting for a named approver, the
              technician diary and the evidence. Customers never sign in here: they talk to the desk.
            </p>
          </Reveal>
        </div>
      </aside>

      <main className="fd-signin-main">
        <form onSubmit={submit} className="fd-signin-form">
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Staff sign in
          </p>
          <h2 className="ds-title" style={{ margin: "8px 0 0", fontSize: 28 }}>
            Who is at the desk?
          </h2>

          <label className="ds-mono-label ds-field-label" style={{ marginTop: 26 }} htmlFor="who">
            Who you are
          </label>
          <select id="who" value={email} onChange={(event) => setEmail(event.target.value)} className="ds-input">
            {(people ?? []).map((person) => (
              <option key={person.email} value={person.email}>
                {person.name} · {person.role_label}
              </option>
            ))}
          </select>

          <label className="ds-mono-label ds-field-label" style={{ marginTop: 18 }} htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            className="ds-input"
            data-mono=""
          />

          <div style={{ marginTop: 24 }}>
            <Button tone="primary" size="large" type="submit" busy={busy} full arrow>
              Sign in
            </Button>
          </div>

          {(error || peopleError) && (
            <div style={{ marginTop: 16 }}>
              <ErrorNote error={error ?? peopleError ?? ""} />
            </div>
          )}

          <p style={{ margin: "22px 0 0", fontSize: 13, color: "var(--ds-text-2)", lineHeight: 1.55 }}>
            Password <code className="ds-mono">{PASSWORD}</code> for everyone; the role decides what you can do. The
            administrator builds the company, a supervisor runs the evidence, an agent works the queue.
          </p>
          <p style={{ margin: "16px 0 0", fontSize: 13 }}>
            <Link href="/chat" style={{ color: "var(--ds-accent-ink)", fontWeight: 600 }}>
              Open the customer chat instead →
            </Link>
          </p>
        </form>
      </main>
    </div>
  );
}
