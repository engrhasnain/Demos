"use client";

import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Band, Button } from "@/design/Surface";
import { Constellation, type ConstellationLink, type ConstellationNode } from "@/design/Constellation";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { BrandMark } from "@/components/shell";
import { ErrorNote } from "@/components/ui";
import { api, storeSession, type SignedInUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";

type Person = { email: string; name: string; role: string; role_label: string };

const PASSWORD = "demo1234";

const MAY: Record<string, string> = {
  buyer: "Reads everything, builds the week's plan",
  senior_buyer: "Also runs the replay",
  purchasing_manager: "Also reads the audit trail",
  finance_director: "Everything above",
  administrator: "Loads the catalogue",
};

/** Parts around three suppliers, joined into one order: a quiet picture of the product. */
function scene() {
  const nodes: ConstellationNode[] = [];
  const links: ConstellationLink[] = [];
  const hubs = [
    { x: 0.62, y: 0.3 },
    { x: 0.8, y: 0.55 },
    { x: 0.6, y: 0.74 },
  ];
  hubs.forEach((hub, h) => {
    nodes.push({ id: `h${h}`, x: hub.x, y: hub.y, r: 3.6, tone: h === 1 ? "warn" : "light", ring: h === 1 });
    for (let index = 0; index < 6; index += 1) {
      const angle = (index / 6) * Math.PI * 2 + h;
      const id = `p${h}-${index}`;
      nodes.push({ id, x: hub.x + Math.cos(angle) * 0.075, y: hub.y + Math.sin(angle) * 0.1, r: 2, tone: index % 3 === 0 ? "accent" : "muted", lit: index % 3 === 0 });
      links.push({ from: id, to: `h${h}`, tone: "light" });
    }
  });
  nodes.push({ id: "cash", x: 0.92, y: 0.22, r: 5, tone: "accent", ring: true, lit: true, label: "Cash cap", side: "below" });
  hubs.forEach((_, h) => links.push({ from: `h${h}`, to: "cash", tone: "accent", lit: true }));
  return {
    nodes,
    links,
    paths: [
      ["p0-0", "h0", "cash"],
      ["p1-3", "h1", "cash"],
      ["p2-0", "h2", "cash"],
      ["p0-3", "h0", "cash"],
    ],
  };
}

export default function SignIn() {
  const router = useRouter();
  const { data: people, error: peopleError, reload } = useLoad<Person[]>("/api/auth/people");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState(PASSWORD);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const picture = useMemo(scene, []);

  useEffect(() => {
    if (!email && people?.length) {
      const chosen = people.find((person) => person.role === "purchasing_manager") ?? people[0];
      setEmail(chosen.email);
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
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const empty = people !== null && people.length === 0;

  // Open only while the database is empty; the server refuses it afterwards.
  const [building, setBuilding] = useState(false);
  const build = async () => {
    setBuilding(true);
    setError(null);
    try {
      await api.post("/api/demo/load", { size: "small" });
      reload();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBuilding(false);
    }
  };

  return (
    <div className="ss-signin">
      <Band
        className="ss-signin-band"
        canvas={
          <Constellation
            nodes={picture.nodes}
            links={picture.links}
            ambient={52}
            traffic={{ paths: picture.paths, every: 1400 }}
          />
        }
      >
        <div className="ss-signin-copy">
          <Reveal y={24}>
            <span style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <BrandMark size={38} />
              <span>
                <span className="ss-brand-name" style={{ fontSize: 22 }}>
                  Stock<span>Sense</span>
                </span>
                <span className="ss-brand-sub">Hengtai Industrial Supply</span>
              </span>
            </span>
          </Reveal>
          <div>
            <Reveal index={1} y={36}>
              <h1 className="ds-display ss-signin-title">
                What to reorder,
                <br />
                how much,
                <br />
                <span className="ds-accent-text">and what being wrong costs.</span>
              </h1>
            </Reveal>
            <Reveal index={2}>
              <p className="ds-band-lede">
                Eighteen thousand parts that mostly sell nothing, suppliers that mostly run late, and a Lunar New Year that
                closes half of them for six weeks. The statistics are the easy half. Knowing when they are lying is the
                product.
              </p>
            </Reveal>
          </div>
          <Reveal index={3}>
            <div className="ss-signin-facts">
              {[
                ["Every number opens", "to its inputs, formula and sources"],
                ["Never one number", "a forecast is always a range"],
                ["Measured", "the last year replayed against the buyers"],
              ].map(([title, text]) => (
                <div key={title}>
                  <span className="ds-mono-label">{title}</span>
                  <span style={{ display: "block", marginTop: 4, fontSize: 13, color: "var(--ds-ink-muted)" }}>{text}</span>
                </div>
              ))}
            </div>
          </Reveal>
        </div>
      </Band>

      <main className="ss-signin-form">
        <form onSubmit={submit} style={{ width: "100%", maxWidth: 440 }}>
          <Reveal y={24}>
            <p className="ds-mono-label" style={{ margin: 0 }}>
              Sign in
            </p>
            <h2 className="ds-title" style={{ margin: "8px 0 0", fontSize: 30 }}>
              Who is buying today?
            </h2>
            <p style={{ margin: "8px 0 0", fontSize: 14, color: "var(--ds-text-2)" }}>The role decides what you can do.</p>
          </Reveal>

          {peopleError && (
            <div style={{ marginTop: 18 }}>
              <ErrorNote error={peopleError} />
            </div>
          )}

          {empty ? (
            <Reveal index={1}>
              <div className="ss-empty-company">
                <StatusChip tone="warn" pulse>
                  No company loaded yet
                </StatusChip>
                <p style={{ margin: "12px 0 0", fontSize: 14, lineHeight: 1.55 }}>
                  Nobody can sign in until the company is built. Build a quick one here (1,500 parts), or from the
                  project folder run:
                </p>
                <pre className="ss-command">python backend/scripts/walkthrough.py --small</pre>
                <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--ds-text-2)" }}>
                  It loads the catalogue and checks the engine end to end. Drop the flag for all eighteen thousand parts.
                </p>
                <div style={{ marginTop: 14, display: "flex", flexWrap: "wrap", gap: 10 }}>
                  <Button tone="primary" onClick={build} disabled={building}>
                    {building ? "Building the company..." : "Build the company"}
                  </Button>
                  <Button onClick={reload}>Check again</Button>
                </div>
                {error && (
                  <div style={{ marginTop: 10 }}>
                    <ErrorNote error={error} />
                  </div>
                )}
              </div>
            </Reveal>
          ) : (
            <>
              <Reveal index={1}>
                <div className="ss-people" role="radiogroup" aria-label="Who you are">
                  {(people ?? []).map((person) => (
                    <button
                      key={person.email}
                      type="button"
                      role="radio"
                      aria-checked={email === person.email}
                      className="ss-person"
                      onClick={() => setEmail(person.email)}
                    >
                      <span className="ss-avatar" aria-hidden>
                        {person.name
                          .split(/\s+/)
                          .slice(0, 2)
                          .map((part) => part[0])
                          .join("")}
                      </span>
                      <span style={{ minWidth: 0 }}>
                        <span style={{ display: "block", fontWeight: 600 }}>{person.name}</span>
                        <span style={{ display: "block", fontSize: 12.5, color: "var(--ds-text-2)" }}>{MAY[person.role] ?? person.role_label}</span>
                      </span>
                      <StatusChip size="small" tone={email === person.email ? "accent" : "neutral"}>
                        {person.role_label}
                      </StatusChip>
                    </button>
                  ))}
                  {!people && <p style={{ fontSize: 14, color: "var(--ds-text-2)" }}>Reading who can sign in…</p>}
                </div>
              </Reveal>
              <Reveal index={2}>
                <label className="ds-mono-label ds-field-label" htmlFor="password" style={{ marginTop: 18 }}>
                  Password
                </label>
                <input id="password" className="ds-input" data-mono="" type="password" value={password} onChange={(event) => setPassword(event.target.value)} />
                <div style={{ marginTop: 18 }}>
                  <Button tone="primary" size="large" type="submit" busy={busy} disabled={!email} full arrow>
                    Sign in
                  </Button>
                </div>
                {error && (
                  <div style={{ marginTop: 14 }}>
                    <ErrorNote error={error} />
                  </div>
                )}
                <p style={{ margin: "16px 0 0", fontSize: 12.5, color: "var(--ds-text-3)" }}>
                  The password is <code className="ds-mono">{PASSWORD}</code> for everyone.
                </p>
              </Reveal>
            </>
          )}
        </form>
      </main>
    </div>
  );
}
