"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Reveal } from "@/design/Reveal";
import { Button } from "@/design/Surface";
import { ScreenDrive } from "@/components/screen-drive";
import { BrandMark, STAFF_PASSWORD } from "@/components/shell";
import { ErrorNote } from "@/components/ui";
import { api, storeSession, type SignedInUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { DriveScenario } from "@/lib/scenario";
import type { DemoState, Person } from "@/lib/types";
import { ROLE_WORDS } from "@/lib/words";

const MAY: Record<string, string> = {
  clerk: "Runs the bot, supplies one-time codes",
  operations_lead: "Also runs the evidence",
  developer: "Also acknowledges a changed form, releases a portal version",
  administrator: "Everything, and loads a fresh day",
};

export default function SignIn() {
  const router = useRouter();
  const { data: people, error: peopleError } = useLoad<Person[]>("/api/auth/people");
  const { data: state } = useLoad<DemoState>("/api/demo/state");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState(STAFF_PASSWORD);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [loop, setLoop] = useState(0);

  useEffect(() => {
    if (!email && people?.length) {
      const chosen = people.find((p) => p.role === "administrator") ?? people[0];
      setEmail(chosen.email);
    }
  }, [people, email]);

  const scenario = useMemo<DriveScenario>(
    () => ({
      key: "sign-in",
      kind: "written",
      reference: "the next shipment",
      values: {},
      carrier: "Hsinchu Logistics",
      address: "checked before the portal",
      dangerous: "looked up by part",
    }),
    [],
  );

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const body = await api.post<{ access_token: string; user: SignedInUser }>("/api/auth/sign-in", { email, password });
      storeSession(body.access_token, body.user);
      router.push("/");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="pb-signin">
      <section className="pb-signin-band">
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <BrandMark size={34} />
          <span>
            <span className="pb-brand-name" style={{ fontSize: 20 }}>
              Portal<span>Bot</span>
            </span>
            <span className="pb-brand-sub">Hengtai Industrial Supply</span>
          </span>
        </div>
        <div>
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" aria-hidden />
              Two screens <span className="ds-eyebrow-sep">·</span> no way in but the screen
            </span>
          </Reveal>
          <Reveal index={1} y={32}>
            <h1 className="ds-display" style={{ margin: "18px 0 0", fontSize: "clamp(32px, 4vw, 54px)" }}>
              Books it once.
              <br />
              <span className="ds-accent-text pb-light">Writes it back. Stops when the screen moves.</span>
            </h1>
          </Reveal>
          <div className="pb-signin-canvas" style={{ marginTop: 18 }}>
            <ScreenDrive scenario={scenario} playKey={loop} onDone={() => window.setTimeout(() => setLoop((value) => value + 1), 2200)} />
          </div>
        </div>
        <p style={{ margin: 0, maxWidth: 560, fontSize: 13.5, lineHeight: 1.6, color: "var(--ds-ink-muted)" }}>
          A carrier portal with no interface for us, and a twenty-year-old order screen with no way to write into it.
          PortalBot drives both, keeps a checkpoint on every row, and never books the same shipment twice.
        </p>
      </section>

      <main className="pb-signin-form">
        <form onSubmit={submit} style={{ width: "100%", maxWidth: 400 }}>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Sign in
          </p>
          <h2 className="ds-title" style={{ margin: "8px 0 0", fontSize: 28 }}>
            Who is at the console?
          </h2>
          {state && !state.loaded && (
            <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--ds-text-2)" }}>
              No day is loaded yet. Sign in as the administrator to load one.
            </p>
          )}
          {peopleError && (
            <div style={{ marginTop: 16 }}>
              <ErrorNote error={peopleError} />
            </div>
          )}
          {people && people.length === 0 && (
            <div style={{ marginTop: 16 }}>
              <ErrorNote error="Nobody can sign in yet. Prepare the first day once with: python backend/scripts/walkthrough.py" />
            </div>
          )}
          <div role="radiogroup" aria-label="Who you are" style={{ display: "grid", gap: 8, marginTop: 20 }}>
            {(people ?? []).map((person) => (
              <button
                key={person.email}
                type="button"
                role="radio"
                aria-checked={email === person.email}
                className="pb-person"
                onClick={() => setEmail(person.email)}
              >
                <span className="pb-avatar" style={{ gridRow: "1 / span 2" }}>
                  {person.name
                    .split(/\s+/)
                    .slice(0, 2)
                    .map((part) => part[0])
                    .join("")}
                </span>
                <span className="pb-person-name">
                  {person.name} <span style={{ fontWeight: 500, color: "var(--ds-text-3)" }}>· {ROLE_WORDS[person.role] ?? person.role_label}</span>
                </span>
                <span className="pb-person-role">{MAY[person.role] ?? ""}</span>
              </button>
            ))}
          </div>
          <label className="ds-mono-label ds-field-label" htmlFor="password" style={{ marginTop: 18 }}>
            Password
          </label>
          <input id="password" type="password" className="ds-input" data-mono="" value={password} onChange={(event) => setPassword(event.target.value)} />
          <div style={{ marginTop: 18 }}>
            <Button tone="primary" type="submit" busy={busy} full arrow>
              Sign in
            </Button>
          </div>
          {error && (
            <div style={{ marginTop: 14 }}>
              <ErrorNote error={error} />
            </div>
          )}
          <p className="ds-mono" style={{ margin: "18px 0 0", fontSize: 11.5, color: "var(--ds-text-3)" }}>
            Every sample account uses the password {STAFF_PASSWORD}. Only a developer may acknowledge a changed form.
          </p>
        </form>
      </main>
    </div>
  );
}
