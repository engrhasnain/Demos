"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Band, Banner, Button, Card, Empty, LinkButton } from "@/design/Surface";
import { ScreenDrive } from "@/components/screen-drive";
import { Figure } from "@/components/trace";
import { ErrorNote, Loading, Segments, ThesisStrip } from "@/components/ui";
import { api } from "@/lib/api";
import { runScenario } from "@/lib/feed";
import { useLoad } from "@/lib/hooks";
import { CARRIER_FIELDS, RENAMED_IN_V2 } from "@/lib/scenario";
import type { Flag, Health, Page, Run, ShipmentBrief, ShipmentDetail } from "@/lib/types";
import { RUN_CHIP, clock, day, killedAfter, runKinds, seconds } from "@/lib/words";

export default function RunPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const runId = Number(id);
  const { data, error } = useLoad<{ items: Run[] }>("/api/runs");
  const { data: flags } = useLoad<{ items: Flag[] }>("/api/flags");
  const { data: health } = useLoad<Health>("/api/health");
  const [sample, setSample] = useState<ShipmentDetail | null>(null);
  const [play, setPlay] = useState(0);
  const [compact, setCompact] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 640px)");
    const update = () => setCompact(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);

  // One real shipment, so the canvas fills the forms with real values.
  useEffect(() => {
    let cancelled = false;
    api
      .get<Page<ShipmentBrief>>("/api/shipments?state=done&limit=1")
      .then((page) => (page.items[0] ? api.get<ShipmentDetail>(`/api/shipments/${encodeURIComponent(page.items[0].reference)}`) : null))
      .then((detail) => !cancelled && setSample(detail))
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  const runs = useMemo(() => data?.items ?? [], [data]);
  const kinds = useMemo(() => runKinds(runs), [runs]);
  const run = runs.find((item) => item.id === runId) ?? null;
  const ordered = [...runs].sort((a, b) => a.id - b.id);
  const position = ordered.findIndex((item) => item.id === runId);
  const previous = position > 0 ? ordered[position - 1] : null;
  const next = position >= 0 ? ordered[position + 1] ?? null : null;
  const scenario = useMemo(() => (run ? runScenario(runs, run, sample) : null), [runs, run, sample]);

  if (error) return <div className="ds-work"><ErrorNote error={error} /></div>;
  if (!data) return <Band top><Loading what="Reading the run" dark /></Band>;
  if (!run) {
    return (
      <div className="ds-work">
        <Empty title={`There is no run ${id}.`}>
          <Link href="/runs">Back to every run</Link>
        </Empty>
      </div>
    );
  }

  const kind = kinds.get(run.id) ?? "finished";
  const chip = RUN_CHIP[kind];
  const killed = killedAfter(run);
  const flag = kind === "halted" ? (flags?.items ?? []).find((item) => item.found_fingerprint === run.drift?.found_fingerprint && Math.abs(Date.parse(item.raised_at ?? "") - Date.parse(run.started_at ?? "")) < 5000) ?? (flags?.items ?? [])[0] : null;
  const notReached = kind === "halted" ? run.considered : Math.max(0, run.considered - run.completed - run.exceptions - run.skipped_already_done);

  const figure = (value: number, heading: string, rule: string, note?: string) => (
    <Figure
      value={String(value)}
      count={value}
      heading={`Run ${run.id}: ${heading}`}
      explain={{
        formula: `count of ${rule}`,
        inputs: [
          { label: "Considered", value: String(run.considered), source: "Unfinished rows when the run started", sourceKind: "Run record" },
          { label: heading, value: String(value), source: "Counted by the run as it went", sourceKind: "Run record" },
        ],
        note,
      }}
    />
  );

  return (
    <>
      <Band top>
        <Link href="/runs" className="pb-back">
          ← Every run
        </Link>
        <div className="pb-band-grid" style={{ marginTop: 18 }}>
          <div>
            <Reveal y={24}>
              <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
                <StatusChip tone={chip.tone} surface="dark" size="large" pulse={kind === "halted"}>
                  {chip.label}
                </StatusChip>
                <span className="pb-mono-time">
                  {day(run.started_at)} · {clock(run.started_at)} to {clock(run.finished_at)} · {seconds(run.seconds)}
                </span>
              </span>
            </Reveal>
            <Reveal index={1} y={32}>
              <h1 className="ds-display ds-band-title">
                Run {run.id}
                <br />
                <span className="ds-accent-text pb-light" style={kind === "halted" ? { color: "var(--ds-fail)" } : undefined}>
                  {kind === "halted"
                    ? "stopped before sending anything."
                    : kind === "killed"
                      ? `killed after ${killed ?? run.considered}.`
                      : kind === "resumed"
                        ? "resumed from the checkpoints."
                        : "worked through the queue."}
                </span>
              </h1>
            </Reveal>
            <Reveal index={2}>
              <p className="ds-band-lede">
                {kind === "halted"
                  ? `Before touching a single row it read the carrier's booking form, compared its shape with the one the script was written against, and found ${run.drift?.looks_renamed.length ?? 0} fields renamed. It raised a flag for a developer and stopped. ${run.considered} rows were left exactly as they were.`
                  : kind === "killed"
                    ? `The process was killed after ${killed ?? "some"} shipments, as a crash or a restart would. Whatever had been committed stayed committed: every row it touched carries its own checkpoint, and the rest were never started.`
                    : kind === "resumed"
                      ? `The run before it was killed after ${previous ? killedAfter(previous) ?? "some" : "some"} shipments. This run is not a special recovery mode: it is the same code, reading each row and carrying on from wherever that row got to, asking the carrier before booking anything.`
                      : run.notes}
              </p>
            </Reveal>
            <Reveal index={3}>
              <div className="ds-stats">
                <div>
                  <span className="ds-stat-value">{figure(run.considered, "considered", "unfinished rows the run picked up, in order")}</span>
                  <span className="ds-mono-label ds-stat-label">Considered</span>
                </div>
                <div>
                  <span className="ds-stat-value" data-tone="pass">{figure(run.completed, "completed", "rows booked, written back and read back in this run")}</span>
                  <span className="ds-mono-label ds-stat-label">Completed</span>
                </div>
                <div>
                  <span className="ds-stat-value" data-tone={run.exceptions ? "warn" : undefined}>{figure(run.exceptions, "held for a person", "rows stopped with a named exception")}</span>
                  <span className="ds-mono-label ds-stat-label">Held for a person</span>
                </div>
                <div>
                  <span className="ds-stat-value" data-tone={kind === "halted" || kind === "killed" ? "fail" : undefined}>
                    {figure(notReached, "not reached", kind === "halted" ? "rows left untouched because the run stopped first" : "rows the run never reached", "Not reached is considered, less completed, held and already done.")}
                  </span>
                  <span className="ds-mono-label ds-stat-label">Not reached</span>
                </div>
              </div>
            </Reveal>
          </div>
          <div className="pb-band-canvas" style={{ height: compact ? 380 : 460 }}>
            <ScreenDrive scenario={scenario} playKey={play} compact={compact} carrier={health?.carrier} portalVersion={kind === "halted" ? "v2" : "v1"} />
            <div style={{ position: "absolute", right: 0, bottom: -6 }}>
              <Button tone="ink" size="small" onClick={() => setPlay((value) => value + 1)}>
                Replay the run
              </Button>
            </div>
          </div>
        </div>
      </Band>

      <div className="ds-work" style={{ display: "grid", gap: 24 }}>
        <Reveal>
          <Card eyebrow="What happened to the rows" title="Where this run's rows ended up">
            <Segments
              label={`${run.completed} completed, ${run.exceptions} held, ${run.skipped_already_done} skipped, ${notReached} not reached`}
              parts={[
                { value: run.completed, colour: "var(--ds-pass)", title: "Completed" },
                { value: run.exceptions, colour: "var(--ds-warn)", title: "Held for a person" },
                { value: run.skipped_already_done, colour: "var(--ds-info)", title: "Already done" },
                { value: notReached, colour: kind === "halted" ? "var(--ds-fail)" : "var(--ds-line-strong)", title: "Not reached" },
              ]}
            />
            <p className="pb-lede" style={{ marginTop: 14 }}>{run.notes}</p>
          </Card>
        </Reveal>

        {kind === "halted" && run.drift && (
          <>
            <Banner tone="fail" title="Why it stops instead of adapting">
              A bot that stops at nine in the morning costs one clerk one morning. A bot that carries on against a changed
              page, puts the postcode in the weight field and books a hundred and eighty shipments to the wrong addresses
              costs a week. Self-healing turns the first into the second, so the renames below are suggested to a
              developer and applied by nobody.
            </Banner>
            <div className="pb-grid-main">
              <Reveal>
                <Card eyebrow="Field map" title="What the script expects, against what the portal shows" flush>
                  <div className="ds-table-wrap">
                    <table className="pb-fieldmap">
                      <thead>
                        <tr>
                          <th>Field</th>
                          <th>Script expects</th>
                          <th>Portal shows now</th>
                        </tr>
                      </thead>
                      <tbody>
                        {CARRIER_FIELDS.map((field, index) => {
                          const moved = run.drift!.missing.includes(field.portal);
                          const now = moved ? run.drift!.looks_renamed.find(([gone]) => gone === field.portal)?.[1] ?? RENAMED_IN_V2[field.portal] ?? "missing" : field.portal;
                          return (
                            <Reveal as="tr" key={field.key} index={index} y={16} data-moved={moved ? "" : undefined}>
                              <td>{field.word}</td>
                              <td>{field.portal}</td>
                              <td>
                                {now}
                                {moved && <span className="ds-sr-only"> (renamed)</span>}
                              </td>
                            </Reveal>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </Card>
              </Reveal>
              <div className="pb-stack">
                <Reveal index={1}>
                  <Card eyebrow="Fingerprints" title="The shape of the form, as a hash">
                    <dl style={{ margin: 0, display: "grid", gap: 12 }}>
                      <div>
                        <dt className="ds-mono-label">Written against</dt>
                        <dd className="ds-mono" style={{ margin: "4px 0 0", fontSize: 14, fontWeight: 600 }}>{run.drift.expected_fingerprint}</dd>
                      </div>
                      <div>
                        <dt className="ds-mono-label">Found today</dt>
                        <dd className="ds-mono" style={{ margin: "4px 0 0", fontSize: 14, fontWeight: 600, color: "var(--ds-fail-ink)" }}>{run.drift.found_fingerprint}</dd>
                      </div>
                    </dl>
                    <p className="pb-lede" style={{ fontSize: 13 }}>
                      The similarity check takes the higher of a word measure and a character measure, because the two
                      kinds of rename defeat different measures. It only ever suggests.
                    </p>
                  </Card>
                </Reveal>
                <Reveal index={2}>
                  <Card eyebrow="The flag" title={flag?.status === "open" ? "Waiting for a developer" : "Acknowledged by a developer"}>
                    {flag ? (
                      <NodeChain
                        live={flag.status === "open"}
                        fill={flag.status === "open" ? 0.5 : 1}
                        items={[
                          { key: "raised", tone: "fail", state: "done", marker: "!", content: <p style={{ margin: "4px 0 0", fontSize: 13.5 }}>Raised at {clock(flag.raised_at)}</p> },
                          {
                            key: "ack",
                            tone: flag.status === "open" ? undefined : "pass",
                            state: flag.status === "open" ? "active" : "done",
                            marker: flag.status === "open" ? "02" : "✓",
                            content: (
                              <p style={{ margin: "4px 0 0", fontSize: 13.5 }}>
                                {flag.status === "open" ? "A developer reads the difference." : `${flag.acknowledged_by?.name ?? "A developer"}: ${flag.note || "acknowledged"}`}
                              </p>
                            ),
                          },
                        ]}
                      />
                    ) : (
                      <p className="pb-lede">No flag found for this run.</p>
                    )}
                    {flag?.status === "open" && (
                      <div style={{ marginTop: 14 }}>
                        <LinkButton href="/#walkthrough" tone="primary" size="small" arrow>
                          Handle it on the control screen
                        </LinkButton>
                      </div>
                    )}
                  </Card>
                </Reveal>
              </div>
            </div>
          </>
        )}

        {(kind === "killed" || kind === "resumed") && (
          <Reveal>
            <Card eyebrow="Crash and resume" title={kind === "killed" ? "What the rows said when the process died" : "How it carried on"}>
              <NodeChain
                items={[
                  {
                    key: "killed",
                    tone: "warn",
                    state: "done",
                    marker: "01",
                    content: (
                      <p style={{ margin: "4px 0 0", fontSize: 14 }}>
                        {kind === "killed" ? `This run was killed after ${killed ?? "some"} shipments.` : `Run ${previous?.id} was killed after ${previous ? killedAfter(previous) ?? "some" : "some"} shipments.`}{" "}
                        Each row it finished is done; nothing was half-written, because each checkpoint is saved only after the
                        system it describes confirmed.
                      </p>
                    ),
                  },
                  {
                    key: "resume",
                    tone: kind === "resumed" || next ? "accent" : undefined,
                    state: kind === "resumed" || next ? "done" : "active",
                    marker: "02",
                    content: (
                      <p style={{ margin: "4px 0 0", fontSize: 14 }}>
                        {kind === "resumed" || next
                          ? `Run ${kind === "resumed" ? run.id : next!.id} read every unfinished row and carried on. Before booking, it asked the carrier whether the reference was already there.`
                          : "The next run will read every row and carry on from there."}
                      </p>
                    ),
                  },
                  {
                    key: "twice",
                    tone: "pass",
                    state: "done",
                    marker: "✓",
                    content: (
                      <p style={{ margin: "4px 0 0", fontSize: 14 }}>
                        Nothing is booked twice: the key is derived from the shipment, so a retry computes the same one, and the
                        carrier is asked first. The evidence screen checks the carrier&rsquo;s own books after five kills.
                      </p>
                    ),
                  },
                ]}
              />
              <div style={{ display: "flex", flexWrap: "wrap", gap: 10, marginTop: 18 }}>
                {previous && (
                  <LinkButton href={`/runs/${previous.id}`} size="small">
                    ← Run {previous.id}
                  </LinkButton>
                )}
                {next && (
                  <LinkButton href={`/runs/${next.id}`} size="small" arrow>
                    Run {next.id}
                  </LinkButton>
                )}
                <LinkButton href="/evidence" tone="primary" size="small" arrow>
                  See the duplicates measured
                </LinkButton>
              </div>
            </Card>
          </Reveal>
        )}

        <ThesisStrip />
      </div>
    </>
  );
}
