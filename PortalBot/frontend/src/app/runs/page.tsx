"use client";

import Link from "next/link";
import { useMemo, useRef } from "react";

import {
  Constellation,
  type ConstellationHandle,
  type ConstellationLink,
  type ConstellationNode,
} from "@/design/Constellation";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Band, Empty } from "@/design/Surface";
import { Figure } from "@/components/trace";
import { ErrorNote, Loading, Segments, ThesisStrip } from "@/components/ui";
import { useLoad } from "@/lib/hooks";
import type { Run } from "@/lib/types";
import { RUN_CHIP, clock, day, killedAfter, runKinds, seconds, type RunKind } from "@/lib/words";

const KIND_TONE: Record<RunKind, ConstellationNode["tone"]> = {
  finished: "pass",
  resumed: "accent",
  killed: "warn",
  halted: "fail",
  running: "accent",
};

function timelineScene(runs: Run[], kinds: Map<number, RunKind>) {
  const ordered = [...runs].sort((a, b) => a.id - b.id).slice(-12);
  const nodes: ConstellationNode[] = [];
  const links: ConstellationLink[] = [];
  const span = Math.max(1, ordered.length - 1);
  ordered.forEach((run, index) => {
    const kind = kinds.get(run.id) ?? "finished";
    const x = ordered.length === 1 ? 0.5 : 0.1 + (index / span) * 0.8;
    const y = 0.5 + Math.sin(index * 1.3) * 0.16;
    nodes.push({
      id: `run-${run.id}`,
      x,
      y,
      r: 5,
      tone: KIND_TONE[kind],
      lit: true,
      ring: kind === "halted" || kind === "killed" || index === ordered.length - 1,
      label: `Run ${run.id}`,
      sub: RUN_CHIP[kind].label,
      side: index % 2 ? "below" : "above",
      drift: 2,
    });
    // each run's work, as a small cluster of rows around it
    const many = Math.min(9, Math.max(2, Math.round(run.considered / 18)));
    for (let dot = 0; dot < many; dot += 1) {
      const angle = (dot / many) * Math.PI * 2 + index;
      const id = `run-${run.id}-${dot}`;
      nodes.push({
        id,
        x: x + Math.cos(angle) * 0.035,
        y: y + Math.sin(angle) * 0.13,
        r: 1.6,
        tone: kind === "halted" ? "fail" : dot < Math.round((run.completed / Math.max(1, run.considered)) * many) ? "pass" : "muted",
        drift: 4,
      });
      links.push({ from: `run-${run.id}`, to: id, tone: kind === "halted" ? "fail" : "light" });
    }
    if (index > 0) {
      const previous = ordered[index - 1];
      links.push({
        from: `run-${previous.id}`,
        to: `run-${run.id}`,
        tone: kind === "resumed" ? "accent" : "light",
        lit: kind === "resumed",
      });
    }
  });
  return { nodes, links, path: ordered.map((run) => `run-${run.id}`) };
}

export default function RunsPage() {
  const { data, error, loading } = useLoad<{ items: Run[] }>("/api/runs");
  const runs = useMemo(() => data?.items ?? [], [data]);
  const kinds = useMemo(() => runKinds(runs), [runs]);
  const scene = useMemo(() => timelineScene(runs, kinds), [runs, kinds]);
  const canvas = useRef<ConstellationHandle>(null);
  const ordered = [...runs].sort((a, b) => b.id - a.id);
  const tally = (kind: RunKind) => [...kinds.values()].filter((value) => value === kind).length;

  return (
    <>
      <Band top>
        <div className="pb-band-grid">
          <div>
            <Reveal y={24}>
              <span className="ds-eyebrow">
                <span className="ds-live-dot" data-tone="accent" aria-hidden />
                Runs <span className="ds-eyebrow-sep">·</span> same code, every time
              </span>
            </Reveal>
            <Reveal index={1} y={32}>
              <h1 className="ds-display ds-band-title">
                Every run,
                <br />
                <span className="ds-accent-text pb-light">checkpoint by checkpoint.</span>
              </h1>
            </Reveal>
            <Reveal index={2}>
              <p className="ds-band-lede">
                A killed run leaves every row saying how far it got. The next run reads the rows and carries on, asking the
                carrier before it books anything. A run that finds the booking form changed stops before sending anything.
              </p>
            </Reveal>
            <Reveal index={3}>
              <div className="ds-stats">
                {(
                  [
                    ["Runs", runs.length, undefined, "every run recorded today"],
                    ["Killed part way", tally("killed"), "warn", "runs whose process was killed"],
                    ["Resumed", tally("resumed"), "accent", "runs straight after a killed one"],
                    ["Stopped for a changed screen", tally("halted"), "fail", "runs halted by the form check"],
                  ] as const
                ).map(([label, value, tone, rule]) => (
                  <div key={label}>
                    <span className="ds-stat-value" data-tone={tone}>
                      <Figure
                        value={String(value)}
                        count={value}
                        heading={label}
                        explain={{
                          formula: `count of ${rule}`,
                          inputs: ordered.slice(0, 8).map((run) => ({
                            label: `Run ${run.id}`,
                            value: RUN_CHIP[kinds.get(run.id) ?? "finished"].label,
                            source: run.notes || run.halted_reason,
                            sourceKind: "Run record",
                          })),
                        }}
                      />
                    </span>
                    <span className="ds-mono-label ds-stat-label">{label}</span>
                  </div>
                ))}
              </div>
            </Reveal>
          </div>
          <div className="pb-band-canvas">
            <Constellation
              ref={canvas}
              nodes={scene.nodes}
              links={scene.links}
              ambient={34}
              traffic={scene.path.length > 1 ? { paths: [scene.path], every: 2600, tone: "accent" } : undefined}
              label={`${runs.length} runs: ${tally("killed")} killed, ${tally("resumed")} resumed, ${tally("halted")} stopped for a changed screen.`}
            />
          </div>
        </div>
      </Band>

      <div className="ds-work" style={{ display: "grid", gap: 22 }}>
        {error && <ErrorNote error={error} />}
        <div className="pb-section-head">
          <div>
            <p className="ds-mono-label" style={{ margin: 0 }}>
              Newest first
            </p>
            <h2 className="ds-title pb-section-title" style={{ marginTop: 8 }}>
              The run log
            </h2>
          </div>
          <div className="pb-legend">
            <span>
              <i style={{ background: "var(--ds-pass)" }} /> completed
            </span>
            <span>
              <i style={{ background: "var(--ds-warn)" }} /> held for a person
            </span>
            <span>
              <i style={{ background: "var(--ds-info)" }} /> already done, skipped
            </span>
            <span>
              <i style={{ background: "var(--ds-line-strong)" }} /> not reached
            </span>
          </div>
        </div>

        <section className="ds-card">
          {loading && !data ? (
            <div style={{ padding: "0 20px" }}>
              <Loading what="Reading the runs" />
            </div>
          ) : ordered.length === 0 ? (
            <div style={{ padding: 20 }}>
              <Empty title="No run yet.">Start one from the walkthrough on the control screen.</Empty>
            </div>
          ) : (
            ordered.map((run, index) => <RunRow key={run.id} run={run} kind={kinds.get(run.id) ?? "finished"} index={index} />)
          )}
        </section>
        <ThesisStrip />
      </div>
    </>
  );
}

function RunRow({ run, kind, index }: { run: Run; kind: RunKind; index: number }) {
  const killed = killedAfter(run);
  const reachedRows = run.completed + run.exceptions + run.skipped_already_done;
  const notReached = kind === "halted" ? run.considered : Math.max(0, run.considered - reachedRows);
  const title =
    kind === "halted"
      ? "The booking form had changed. Stopped before sending anything."
      : kind === "killed"
        ? `Process killed after ${killed ?? reachedRows} shipments. Every row kept its checkpoint.`
        : kind === "resumed"
          ? "Carried on from the rows the killed run left behind."
          : "Worked through every unfinished row.";
  return (
    <Reveal index={index} y={24}>
      <div className="pb-run">
        <Link href={`/runs/${run.id}`} className="pb-run-number" style={{ textDecoration: "none" }} aria-label={`Open run ${run.id}`}>
          {run.id}
          <small>{clock(run.started_at)}</small>
        </Link>
        <span style={{ minWidth: 0 }}>
          <span style={{ display: "flex", flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <StatusChip tone={RUN_CHIP[kind].tone} pulse={kind === "halted"}>
              {RUN_CHIP[kind].label}
            </StatusChip>
            <span className="ds-mono" style={{ fontSize: 11.5, color: "var(--ds-text-3)" }}>
              {day(run.started_at)} · {seconds(run.seconds)}
            </span>
          </span>
          <p className="pb-run-title">{title}</p>
          <span className="pb-run-figures">
            {(
              [
                [run.considered, "considered", "unfinished rows the run picked up, in order"],
                [run.completed, "completed", "rows this run booked, wrote back and read back"],
                [run.exceptions, "held for a person", "rows this run stopped with a named exception"],
                [run.skipped_already_done, "already done", "rows found finished and left alone"],
              ] as const
            ).map(([value, words, rule]) => (
              <span key={words}>
                <b>
                  <Figure
                    value={String(value)}
                    heading={`Run ${run.id}: ${words}`}
                    explain={{
                      formula: `count of ${rule}`,
                      inputs: [
                        { label: "Run", value: String(run.id), source: run.notes || run.halted_reason, sourceKind: "Run record" },
                        { label: words, value: String(value), source: "Counted by the run as it went", sourceKind: "Run record" },
                      ],
                    }}
                  />
                </b>{" "}
                {words}
              </span>
            ))}
          </span>
          <Segments
            label={`${run.completed} completed, ${run.exceptions} held, ${run.skipped_already_done} skipped, ${notReached} not reached`}
            parts={[
              { value: run.completed, colour: "var(--ds-pass)", title: "Completed" },
              { value: run.exceptions, colour: "var(--ds-warn)", title: "Held for a person" },
              { value: run.skipped_already_done, colour: "var(--ds-info)", title: "Already done" },
              { value: notReached, colour: "var(--ds-line-strong)", title: "Not reached" },
            ]}
          />
        </span>
        <Link href={`/runs/${run.id}`} className="pb-run-go" style={{ textDecoration: "none" }}>
          Open the run →
        </Link>
      </div>
    </Reveal>
  );
}
