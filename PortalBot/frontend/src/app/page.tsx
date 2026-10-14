"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { LiveFeedCard } from "@/design/LiveFeedCard";
import { Meter } from "@/design/Meter";
import { useInView } from "@/design/motion";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Band, Button, Card, Empty, LinkButton, Stamp, Stat } from "@/design/Surface";
import { FirstRun } from "@/components/first-run";
import { Guide } from "@/components/guide";
import { ScreenDrive } from "@/components/screen-drive";
import { switchTo } from "@/components/shell";
import { Figure } from "@/components/trace";
import { ClosingBand, ErrorNote, Loading, ThesisStrip } from "@/components/ui";
import { api, readUser } from "@/lib/api";
import { buildFeed, openSamples, runScenario, type FeedEntry } from "@/lib/feed";
import { useLoad, withRetry } from "@/lib/hooks";
import type { DriveScenario } from "@/lib/scenario";
import type { Challenge, Dashboard, DemoState, Flag, Health, Page, Run, ShipmentBrief, ShipmentDetail } from "@/lib/types";
import { RUN_CHIP, clock, count, mayAct, runKinds } from "@/lib/words";

type Overview = {
  dashboard: Dashboard;
  runs: Run[];
  flags: Flag[];
  codes: Challenge[];
  health: Health;
  shipments: ShipmentBrief[];
  feed: FeedEntry[];
  sample: ShipmentDetail | null;
};

async function loadOverview(): Promise<Overview> {
  const [dashboard, runs, flags, codes, health, page] = await Promise.all([
    api.get<Dashboard>("/api/dashboard"),
    api.get<{ items: Run[] }>("/api/runs"),
    api.get<{ items: Flag[] }>("/api/flags"),
    api.get<{ items: Challenge[] }>("/api/challenges"),
    api.get<Health>("/api/health"),
    api.get<Page<ShipmentBrief>>("/api/shipments?limit=200"),
  ]);
  const details = await openSamples(page.items);
  const { entries, sample } = buildFeed(runs.items, details, health.carrier);
  return {
    dashboard,
    runs: runs.items,
    flags: flags.items,
    codes: codes.items,
    health,
    shipments: page.items,
    feed: entries,
    sample,
  };
}

export default function Control() {
  const [data, setData] = useState<Overview | null>(null);
  const [dataError, setDataError] = useState<string | null>(null);
  const [restart, setRestart] = useState(false);
  const [nonce, setNonce] = useState(0);
  const refresh = useCallback(() => setNonce((value) => value + 1), []);

  // The whole screen hangs off this one call, so a dropped connection should not leave it
  // stuck on the placeholder forever: retry a few times with backoff before asking the person.
  const { data: state, error: stateError, reload: reloadState } = useLoad<DemoState>("/api/demo/state", [nonce], {
    retry: true,
  });

  useEffect(() => {
    if (!state || !state.loaded) return;
    let cancelled = false;
    withRetry(loadOverview, () => cancelled)
      .then((overview) => {
        if (!cancelled) {
          setData(overview);
          setDataError(null);
        }
      })
      .catch((cause: unknown) => {
        if (!cancelled) setDataError(cause instanceof Error ? cause.message : String(cause));
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, nonce]);

  if (stateError && !state) {
    return (
      <div className="ds-work">
        <ErrorNote error={stateError} />
        <div style={{ marginTop: 16 }}>
          <Button onClick={reloadState}>Retry</Button>
        </div>
      </div>
    );
  }
  if (!state) return <div className="ds-work"><Loading what="Opening the control room" /></div>;
  if (!state.loaded || restart) {
    return (
      <FirstRun
        again={restart && state.loaded}
        onFinished={() => {
          setRestart(false);
          setData(null);
          refresh();
          window.scrollTo({ top: 0 });
        }}
      />
    );
  }
  if (!data) {
    return (
      <Band top>
        {dataError ? (
          <div className="pb-hero" style={{ display: "grid", placeItems: "center", gap: 16, textAlign: "center" }}>
            <ErrorNote error={dataError} />
            <Button onClick={refresh}>Retry</Button>
          </div>
        ) : (
          <div className="pb-hero" aria-busy="true">
            <Loading what="Reading today's rows" dark />
          </div>
        )}
      </Band>
    );
  }
  return <Overview data={data} onChanged={refresh} onRestart={() => setRestart(true)} />;
}

/* ------------------------------------------------------------------ */
/* The loaded day                                                      */
/* ------------------------------------------------------------------ */
function Overview({ data, onChanged, onRestart }: { data: Overview; onChanged: () => void; onRestart: () => void }) {
  const { dashboard, runs, flags, codes, health, feed, sample } = data;
  const [index, setIndex] = useState(0);
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 640px)");
    const update = () => setCompact(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);

  const scenario = feed[index % Math.max(1, feed.length)]?.scenario ?? null;
  const ordered = useMemo(() => [...runs].sort((a, b) => b.id - a.id), [runs]);
  const latest: DriveScenario | null = ordered[0] ? runScenario(runs, ordered[0], sample) : null;
  const openFlags = flags.filter((flag) => flag.status === "open");
  const held = dashboard.by_state.find((row) => row.state === "needs_a_person")?.count ?? 0;
  const finished = dashboard.by_state
    .filter((row) => ["done", "failed", "needs_a_person"].includes(row.state))
    .reduce((sum, row) => sum + row.count, 0);
  const stateRows = dashboard.by_state.map((row) => `${row.label}: ${row.count}`);

  return (
    <>
      <Band top>
        <div className="pb-hero">
          <div className="pb-hero-copy">
            <Reveal y={24}>
              <span className="ds-eyebrow">
                <span className="ds-live-dot" data-tone={openFlags.length ? "fail" : "accent"} aria-hidden />
                Live <span className="ds-eyebrow-sep">·</span> {health.carrier}
                <span className="ds-eyebrow-sep">·</span> portal version {health.portal_version === "v2" ? "2" : "1"}
              </span>
            </Reveal>
            <Reveal index={1} y={36}>
              <h1 className="ds-display pb-hero-title">
                Every shipment booked.
                <br />
                <span className="ds-accent-text pb-light">Every tracking number written back.</span>
              </h1>
            </Reveal>
            <Reveal index={2}>
              <p className="ds-band-lede">
                The carrier has no way in for us and the business system has no way to write into it, so PortalBot drives
                both screens the way a clerk would. The row is the transaction: a crash resumes from the last checkpoint
                without booking twice, and a changed screen stops the run before anything is sent.
              </p>
            </Reveal>
            <Reveal index={3}>
              <div className="ds-stats" style={{ gap: "22px 32px" }}>
                <Stat
                  label="Shipments today"
                  value={
                    <Figure
                      value={String(dashboard.shipments)}
                      count={dashboard.shipments}
                      heading="Shipments today"
                      explain={{
                        formula: "count of every shipment row loaded for today",
                        inputs: stateRows.map((text) => ({ label: text.split(":")[0], value: text.split(": ")[1], source: "Shipment rows, grouped by state", sourceKind: "Live rows" })),
                      }}
                    />
                  }
                />
                <Stat
                  label="Through both systems"
                  tone="pass"
                  value={
                    <Figure
                      value={`${dashboard.automated_share}%`}
                      count={dashboard.automated_share}
                      decimals={1}
                      heading="Through both systems"
                      explain={{
                        formula: "done ÷ (done + needs a person + failed) × 100",
                        result: `${dashboard.automated_share}%`,
                        inputs: [
                          { label: "Done", value: String(dashboard.done), source: "Rows booked, written back and read back", sourceKind: "Live rows" },
                          { label: "Finished one way or the other", value: String(finished), source: "Done, needs a person or failed", sourceKind: "Live rows" },
                        ],
                        note: "Over every shipment that has finished, awkward ones included. The evidence screen measures clean shipments on their own.",
                      }}
                    />
                  }
                />
                <Stat
                  label="Held for a person"
                  tone={held ? "warn" : undefined}
                  value={
                    <Figure
                      value={String(held)}
                      count={held}
                      heading="Held for a person"
                      explain={{
                        formula: "count of rows in the state needs a person",
                        inputs: dashboard.by_exception.map((row) => ({ label: row.label, value: String(row.count), source: "Named exception on the row", sourceKind: "Live rows" })),
                      }}
                    />
                  }
                />
                <Stat
                  label="Clerk hours saved"
                  unit="hours"
                  value={
                    <Figure
                      value={String(dashboard.hours_saved)}
                      count={dashboard.hours_saved}
                      decimals={1}
                      heading="Clerk hours saved"
                      explain={{
                        formula: "done × 4 minutes ÷ 60",
                        result: `${dashboard.hours_saved} hours`,
                        inputs: [
                          { label: "Done", value: String(dashboard.done), source: "Rows through both systems", sourceKind: "Live rows" },
                          { label: "Minutes a clerk spends on one", value: "4", source: "Timed by hand at Hengtai: book, copy, paste back", sourceKind: "Assumption" },
                        ],
                      }}
                    />
                  }
                />
              </div>
            </Reveal>
            <Reveal index={4}>
              <div className="pb-hero-actions">
                <LinkButton href="#walkthrough" tone="primary" size="large" arrow>
                  Walk through the morning
                </LinkButton>
                <LinkButton href="/runs" tone="ink" size="large">
                  Every run
                </LinkButton>
              </div>
            </Reveal>
          </div>

          <div className="pb-hero-stage">
            <div className="pb-hero-canvas">
              <ScreenDrive
                scenario={scenario}
                compact={compact}
                carrier={health.carrier}
                portalVersion={health.portal_version}
              />
            </div>
            {feed.length > 0 && (
              <div className="pb-hero-feed">
                <LiveFeedCard
                  title="Shipments in flight"
                  source={`${health.carrier} · built-in script`}
                  items={feed.map((entry) => entry.item)}
                  interval={8200}
                  onIndex={setIndex}
                  footNote="Real rows from today. Open one for its whole trace."
                />
              </div>
            )}
          </div>
        </div>
      </Band>

      <div className="ds-work" style={{ display: "grid", gap: 28 }}>
        {openFlags.length > 0 && <FlagCard flag={openFlags[0]} runId={ordered.find((run) => run.status === "halted")?.id} onChanged={onChanged} />}
        {codes.length > 0 && <CodesCard codes={codes} onChanged={onChanged} />}

        <Reveal>
          <Guide runs={runs} flags={flags} health={health} latest={latest} onChanged={onChanged} onRestart={onRestart} />
        </Reveal>

        <Reveal>
          <StateRail dashboard={dashboard} />
        </Reveal>

        <div className="pb-grid-2">
          <Reveal>
            <WhyStopped dashboard={dashboard} />
          </Reveal>
          <Reveal index={1}>
            <RecentRuns runs={runs} />
          </Reveal>
        </div>

        <Reveal>
          <ThesisStrip />
        </Reveal>
      </div>
      <ClosingBand />
    </>
  );
}

/* ------------------------------------------------------------------ */
/* The portal moved                                                    */
/* ------------------------------------------------------------------ */
function FlagCard({ flag, runId, onChanged }: { flag: Flag; runId?: number; onChanged: () => void }) {
  const user = readUser();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const allowed = mayAct(user?.role, "developer");
  const act = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.post(`/api/flags/${flag.id}`, { note: "Read the difference. Script updated for the renamed fields." });
      await api.post("/api/portal/release", { version: "v1" });
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="ds-card" data-tone="accent" style={{ borderColor: "var(--ds-fail)" }} role="alert">
      <div className="ds-card-body" style={{ display: "grid", gap: 16 }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
          <StatusChip tone="fail" pulse>
            Stopped — screen changed
          </StatusChip>
          <span className="ds-mono" style={{ fontSize: 12, color: "var(--ds-text-3)" }}>
            Raised {clock(flag.raised_at)} · script {flag.script.replace(/_/g, " ")}
          </span>
        </div>
        <div>
          <h2 className="ds-title" style={{ margin: 0, fontSize: 24 }}>
            The carrier changed its booking form. Nothing was booked.
          </h2>
          <p className="pb-lede">
            The script stores the shape of the form it was written against and checks it before every run. These fields
            moved, so the run stopped before sending anything. A developer reads the difference; the bot never rewrites
            itself.
          </p>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10 }}>
          {flag.detail.looks_renamed.map(([gone, arrived]) => (
            <span key={gone} className="ds-mono" style={{ display: "inline-flex", alignItems: "center", gap: 8, padding: "6px 10px", background: "var(--ds-fail-soft)", color: "var(--ds-fail-ink)", fontSize: 13, fontWeight: 600, borderRadius: 3 }}>
              {gone} <span aria-hidden>→</span>
              <span className="ds-sr-only">renamed to</span> {arrived}
            </span>
          ))}
        </div>
        {error && <ErrorNote error={error} />}
        <div style={{ display: "flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
          {allowed ? (
            <Button tone="primary" busy={busy} onClick={() => void act()} arrow>
              Acknowledge and update the script
            </Button>
          ) : (
            <Button tone="primary" onClick={() => void switchTo("ana.silva@hengtai-industrial.example").then(() => window.location.reload())} arrow>
              Switch to Ana Silva, developer
            </Button>
          )}
          <LinkButton href={runId ? `/runs/${runId}` : "/runs"} tone="secondary">
            See the run that stopped
          </LinkButton>
        </div>
      </div>
    </section>
  );
}

function CodesCard({ codes, onChanged }: { codes: Challenge[]; onChanged: () => void }) {
  return (
    <Card eyebrow="Waiting on a person" title="The portal asked for a one-time code" subtitle="Pushed to the clerk on duty. The bot never tries to answer one, and image challenges are never attempted." flush>
      {codes.slice(0, 5).map((challenge) => (
        <CodeRow key={challenge.reference} challenge={challenge} onDone={onChanged} />
      ))}
    </Card>
  );
}

function CodeRow({ challenge, onDone }: { challenge: Challenge; onDone: () => void }) {
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, padding: "12px 20px", borderTop: "1px solid var(--ds-line)" }}>
      <Stamp>{challenge.shipment}</Stamp>
      <span style={{ fontSize: 13, color: "var(--ds-text-2)" }}>asked of {challenge.asked_of?.name ?? "nobody on duty"} at {clock(challenge.asked_at)}</span>
      <label className="ds-sr-only" htmlFor={`code-${challenge.reference}`}>
        One-time code
      </label>
      <input id={`code-${challenge.reference}`} className="ds-input" data-mono="" style={{ width: 120, marginLeft: "auto" }} value={code} onChange={(event) => setCode(event.target.value)} placeholder="000000" />
      <Button
        size="small"
        busy={busy}
        onClick={() => {
          setBusy(true);
          api
            .post(`/api/challenges/${challenge.reference}`, { code })
            .then(onDone)
            .catch((cause: unknown) => setError(String(cause)))
            .finally(() => setBusy(false));
        }}
      >
        Supply the code
      </Button>
      {error && <span style={{ width: "100%", color: "var(--ds-fail-ink)", fontSize: 13 }}>{error}</span>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Where every row is                                                  */
/* ------------------------------------------------------------------ */
function StateRail({ dashboard }: { dashboard: Dashboard }) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.25 });
  const by = (state: string) => dashboard.by_state.find((row) => row.state === state)?.count ?? 0;
  const rows: { state: string; label: string; note: string; tone: string; href: string }[] = [
    { state: "pending", label: "Not started", note: "waiting for a run", tone: "var(--ds-text-3)", href: "/shipments?state=pending" },
    { state: "booked", label: "Booked", note: "in the portal, not yet written back", tone: "var(--ds-accent)", href: "/shipments?state=booked" },
    { state: "written_back", label: "Written back", note: "tracking in the order screen", tone: "var(--ds-accent)", href: "/shipments?state=written_back" },
    { state: "done", label: "Done", note: "read back and closed", tone: "var(--ds-pass)", href: "/shipments?state=done" },
    { state: "needs_a_person", label: "Needs a person", note: "a named exception", tone: "var(--ds-warn)", href: "/shipments?state=needs_a_person" },
  ];
  return (
    <Card
      eyebrow="The row is the transaction"
      title="Where every row is right now"
      subtitle="Nothing spans a carrier portal and an old order screen, so each row carries its own checkpoint. Kill the process anywhere and the row says how far it got."
    >
      <div ref={ref} className="pb-states" data-shown={shown ? "" : undefined}>
        {rows.map((row, position) => {
          const value = by(row.state);
          return (
            <div
              key={row.state}
              className="pb-state"
              data-filled={value > 0 ? "" : undefined}
              style={{ "--state-tone": row.tone, "--ds-d": `${position * 140}ms` } as React.CSSProperties}
            >
              <span className="pb-state-fill" aria-hidden />
              <span className="pb-state-node" aria-hidden />
              <span className="pb-state-value">
                <Figure
                  value={String(value)}
                  count={value}
                  heading={`Rows in the state: ${row.label.toLowerCase()}`}
                  explain={{
                    formula: `count of shipment rows whose state is "${row.label.toLowerCase()}"`,
                    inputs: [
                      { label: row.label, value: String(value), source: "Shipment rows, grouped by state", sourceKind: "Live rows" },
                      { label: "All rows today", value: String(dashboard.shipments), source: "Every shipment loaded", sourceKind: "Live rows" },
                    ],
                  }}
                />
              </span>
              <Link href={row.href} className="ds-mono-label pb-state-label" style={{ textDecoration: "none" }}>
                {row.label} →
              </Link>
              <span className="pb-state-note">{row.note}</span>
            </div>
          );
        })}
      </div>
    </Card>
  );
}

function WhyStopped({ dashboard }: { dashboard: Dashboard }) {
  const max = Math.max(1, ...dashboard.by_exception.map((row) => row.count));
  return (
    <Card
      eyebrow="Every exception has a name"
      title="Why things stopped"
      subtitle="Not “error”: a name, a reason and the evidence, on the row. One bad address never holds up the other hundred and seventy-nine."
    >
      {dashboard.by_exception.length === 0 ? (
        <Empty title="Nothing has stopped today." />
      ) : (
        <ul className="pb-why">
          {dashboard.by_exception.map((row, index) => (
            <li key={row.kind} className="pb-why-row">
              <Link className="pb-why-label" href={`/shipments?exception=${row.kind}`}>
                {row.label}
              </Link>
              <span className="pb-why-value">
                <Figure
                  value={String(row.count)}
                  count={row.count}
                  heading={row.label}
                  explain={{
                    formula: `count of rows whose exception is "${row.label.toLowerCase()}"`,
                    inputs: [{ label: row.label, value: String(row.count), source: "The named exception recorded on each row", sourceKind: "Live rows" }],
                  }}
                />
              </span>
              <Meter value={row.count / max} tone="warn" delay={index * 120} />
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function RecentRuns({ runs }: { runs: Run[] }) {
  const kinds = runKinds(runs);
  const ordered = [...runs].sort((a, b) => b.id - a.id).slice(0, 5);
  return (
    <Card
      eyebrow="Runs"
      title="The latest runs"
      subtitle="Each one is the same code. A second run is the recovery path."
      action={
        <LinkButton href="/runs" size="small" arrow>
          All runs
        </LinkButton>
      }
      flush
    >
      {ordered.length === 0 ? (
        <div style={{ padding: 20 }}>
          <Empty title="No run yet.">Start with the walkthrough above.</Empty>
        </div>
      ) : (
        ordered.map((run) => {
          const kind = kinds.get(run.id) ?? "finished";
          return (
            <Link key={run.id} href={`/runs/${run.id}`} className="pb-run" style={{ gridTemplateColumns: "60px minmax(0,1fr)" }}>
              <span className="pb-run-number" style={{ fontSize: 24 }}>
                {run.id}
                <small>{clock(run.started_at)}</small>
              </span>
              <span style={{ minWidth: 0 }}>
                <StatusChip tone={RUN_CHIP[kind].tone} size="small">
                  {RUN_CHIP[kind].label}
                </StatusChip>
                <span style={{ display: "block", marginTop: 6, fontSize: 13, color: "var(--ds-text-2)" }}>
                  {kind === "halted"
                    ? "Stopped before sending anything."
                    : `${count(run.completed, "completed", "completed")} · ${count(run.exceptions, "exception")} · ${count(run.considered, "considered", "considered")}`}
                </span>
              </span>
            </Link>
          );
        })
      )}
    </Card>
  );
}
