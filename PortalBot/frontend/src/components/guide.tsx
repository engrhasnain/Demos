"use client";

/**
 * The morning, in six moments: the walkthrough a viewer is taken through.
 *
 * Each moment does the real thing against the two systems (a run, a kill, a
 * new portal version, a developer's acknowledgement) and is ticked off from
 * what the server then says, not from a button having been pressed. The
 * canvas beside it replays the latest run, so the kill, the resume and the
 * halt are seen as they happened.
 */

import { useEffect, useState } from "react";

import { NodeChain } from "@/design/NodeChain";
import { Meter } from "@/design/Meter";
import { StatusChip } from "@/design/StatusChip";
import { Button, LinkButton } from "@/design/Surface";
import { ScreenDrive } from "@/components/screen-drive";
import { switchTo } from "@/components/shell";
import { ErrorNote } from "@/components/ui";
import { api, readUser } from "@/lib/api";
import type { DriveScenario } from "@/lib/scenario";
import type { Flag, Health, Run } from "@/lib/types";
import { RUN_CHIP, mayAct, runKinds } from "@/lib/words";

export const MEASURED_KEY = "portalbot.measured";

type Moment = {
  key: string;
  title: string;
  say: string;
  done: boolean;
  needs?: "clerk" | "operations_lead" | "developer" | "administrator";
  as?: { email: string; name: string };
  action?: { label: string; tone?: "primary" | "danger"; work: () => Promise<unknown> };
  link?: { href: string; label: string };
};

const DEVELOPER = { email: "ana.silva@hengtai-industrial.example", name: "Ana Silva, developer" };
const CLERK = { email: "kai.chen@hengtai-industrial.example", name: "Kai Chen, shipping clerk" };
const LEAD = { email: "tomas.reyes@hengtai-industrial.example", name: "Tomas Reyes, operations lead" };

export function Guide({
  runs,
  flags,
  health,
  latest,
  onChanged,
  onRestart,
}: {
  runs: Run[];
  flags: Flag[];
  health: Health | null;
  latest: DriveScenario | null;
  onChanged: () => void;
  onRestart: () => void;
}) {
  const user = readUser();
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [measured, setMeasured] = useState(false);
  const [play, setPlay] = useState(0);

  useEffect(() => {
    try {
      setMeasured(window.localStorage.getItem(MEASURED_KEY) === "yes");
    } catch {
      setMeasured(false);
    }
  }, []);

  const kinds = runKinds(runs);
  const kindList = [...kinds.values()];
  const openFlags = flags.filter((flag) => flag.status === "open");
  const halted = kindList.includes("halted");

  const moments: Moment[] = [
    {
      key: "first",
      title: "Release the first twenty-five shipments",
      say: "A clerk does this by hand every morning: book each shipment in the portal, copy the tracking number, paste it into the old screen. About four minutes each.",
      done: runs.length > 0,
      needs: "clerk",
      as: CLERK,
      action: { label: "Run the first 25", tone: "primary", work: () => api.post("/api/run", { limit: 25 }) },
    },
    {
      key: "kill",
      title: "Kill it part way through",
      say: "The container restarts, the network drops, somebody deploys. The process is gone after twenty-five more. Every row says how far it got.",
      done: kindList.includes("killed"),
      needs: "clerk",
      as: CLERK,
      action: { label: "Run, then kill it after 25", tone: "danger", work: () => api.post("/api/run", { stop_after: 25 }) },
    },
    {
      key: "resume",
      title: "Run again: it carries on from the row",
      say: "There is no resume mode. A second run is the recovery path, the same code exercised every run. It asks the carrier before booking, so nothing is booked twice.",
      done: kindList.includes("resumed"),
      needs: "clerk",
      as: CLERK,
      action: { label: "Run the rest of the morning", tone: "primary", work: () => api.post("/api/run", {}) },
    },
    {
      key: "moved",
      title: "The carrier changes its booking form",
      say: "Version 2 renames two fields. The run reads the form first, sees it moved, and halts before sending anything, naming the two fields.",
      done: halted,
      needs: "developer",
      as: DEVELOPER,
      action: {
        label: "Release portal version 2, then run",
        tone: "danger",
        work: async () => {
          await api.post("/api/portal/release", { version: "v2" });
          return api.post("/api/run", {});
        },
      },
    },
    {
      key: "person",
      title: "A developer reads the difference",
      say: "Nothing rewrites the script. A person decides whether the new field means what the old one did. Putting the portal back to version 1 stands in for the developer updating the script.",
      done: halted && openFlags.length === 0 && health?.portal_version === "v1",
      needs: "developer",
      as: DEVELOPER,
      action: {
        label: "Acknowledge, update the script, run",
        tone: "primary",
        work: async () => {
          for (const flag of openFlags) {
            await api.post(`/api/flags/${flag.id}`, { note: "Read the difference. Script updated for the renamed fields." });
          }
          await api.post("/api/portal/release", { version: "v1" });
          return api.post("/api/run", {});
        },
      },
    },
    {
      key: "measure",
      title: "Measure it, including what it got wrong",
      say: "The acceptance suite runs a clean day, kills the run five times and checks the carrier's own books for anything booked twice, then moves the portal.",
      done: measured,
      needs: "operations_lead",
      as: LEAD,
      link: { href: "/evidence", label: "Open the evidence" },
    },
  ];

  const activeIndex = moments.findIndex((moment) => !moment.done);
  const doneCount = moments.filter((moment) => moment.done).length;

  const perform = async (moment: Moment) => {
    if (!moment.action) return;
    setBusy(moment.key);
    setError(null);
    try {
      await moment.action.work();
      setPlay((value) => value + 1);
      onChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(null);
    }
  };

  const latestRun = [...runs].sort((a, b) => b.id - a.id)[0];
  const latestKind = latestRun ? kinds.get(latestRun.id) : undefined;

  return (
    <section className="ds-card" data-tone="accent" id="walkthrough">
      <header className="ds-card-head">
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="pb-guide-head" style={{ marginBottom: 0 }}>
            <div>
              <p className="ds-mono-label" style={{ margin: 0 }}>
                Guided walkthrough · {doneCount} of {moments.length}
              </p>
              <h2 className="ds-title" style={{ margin: "8px 0 0", fontSize: 24 }}>
                The morning, in six moments
              </h2>
              <p className="ds-card-sub" style={{ maxWidth: "62ch" }}>
                It works; you kill it and it does not book twice; the portal changes under it and it stops. Each moment
                performs the real action against both systems.
              </p>
            </div>
            <div>
              <Meter value={doneCount / moments.length} size="large" tone="accent" label={`${doneCount} of ${moments.length} moments done`} />
              <div style={{ display: "flex", justifyContent: "space-between", marginTop: 8 }}>
                <span className="ds-mono-label">{Math.round((doneCount / moments.length) * 100)}% walked</span>
                {user?.role === "administrator" && (
                  <button type="button" className="ds-btn" data-tone="ghost" data-size="small" onClick={onRestart}>
                    Start the day again
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      </header>
      <div className="ds-card-body">
        <div className="pb-grid-main" style={{ alignItems: "stretch" }}>
          <div style={{ minWidth: 0 }}>
            {error && (
              <div style={{ marginBottom: 14 }}>
                <ErrorNote error={error} />
              </div>
            )}
            <NodeChain
              stagger={80}
              fill={doneCount / moments.length}
              items={moments.map((moment, index) => {
                const active = index === activeIndex;
                const allowed = mayAct(user?.role, moment.needs ?? "clerk");
                return {
                  key: moment.key,
                  tone: moment.done ? "pass" : active ? "accent" : undefined,
                  state: moment.done ? "done" : active ? "active" : "waiting",
                  marker: moment.done ? "✓" : String(index + 1).padStart(2, "0"),
                  content: (
                    <div className="pb-guide-step" data-state={moment.done ? "done" : active ? "active" : "waiting"} style={{ paddingBottom: 4 }}>
                      <p className="pb-guide-step-title">{moment.title}</p>
                      {active && (
                        <>
                          <p className="pb-guide-say">{moment.say}</p>
                          <div className="pb-guide-actions">
                            {moment.action && allowed && (
                              <Button tone={moment.action.tone ?? "primary"} busy={busy === moment.key} onClick={() => void perform(moment)} arrow>
                                {moment.action.label}
                              </Button>
                            )}
                            {moment.action && !allowed && moment.as && (
                              <Button
                                tone="primary"
                                onClick={() => void switchTo(moment.as!.email).then(() => window.location.reload())}
                                arrow
                              >
                                Switch to {moment.as.name}
                              </Button>
                            )}
                            {moment.link && (
                              <LinkButton href={moment.link.href} tone="primary" arrow>
                                {moment.link.label}
                              </LinkButton>
                            )}
                          </div>
                        </>
                      )}
                    </div>
                  ),
                };
              })}
            />
            {activeIndex === -1 && (
              <p className="pb-guide-done">
                Every moment has been walked. Run again at any time; a run with nothing left to do books nothing.
              </p>
            )}
          </div>
          <div
            style={{
              position: "relative",
              minHeight: 380,
              background: "var(--ds-ink)",
              borderRadius: "var(--ds-radius)",
              overflow: "hidden",
            }}
          >
            <div style={{ position: "absolute", inset: "52px 0 0 0" }}>
              <ScreenDrive scenario={latest} playKey={play} compact carrier={health?.carrier} portalVersion={health?.portal_version} />
            </div>
            <div style={{ position: "absolute", top: 12, left: 14, right: 14, display: "flex", justifyContent: "space-between", gap: 10, alignItems: "center" }}>
              <span className="ds-mono-label" style={{ color: "var(--ds-ink-faint)" }}>
                {latestRun ? `Latest · run ${latestRun.id}` : "No run yet"}
              </span>
              {latestKind && (
                <StatusChip tone={RUN_CHIP[latestKind].tone} surface="dark" size="small">
                  {RUN_CHIP[latestKind].label}
                </StatusChip>
              )}
              <button type="button" className="ds-btn" data-tone="ink" data-size="small" onClick={() => setPlay((value) => value + 1)}>
                Replay
              </button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
