"use client";

import { useEffect, useMemo, useState } from "react";

import { Constellation, type ConstellationLink, type ConstellationNode } from "@/design/Constellation";
import { Meter } from "@/design/Meter";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Band, Banner, Button, Card } from "@/design/Surface";
import { MEASURED_KEY } from "@/components/guide";
import { switchTo } from "@/components/shell";
import { Figure } from "@/components/trace";
import { ErrorNote, Loading, ThesisStrip } from "@/components/ui";
import { api, readUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { Criterion, Evidence } from "@/lib/types";
import { mayAct, seconds } from "@/lib/words";

const PHASES = [
  ["01", "A clean day", "Every shipment through both systems; clean ones counted apart from the awkward ones."],
  ["02", "Five kills", "The run killed at five different points, then the carrier's own books checked for a reference booked twice."],
  ["03", "The portal moves", "Version 2 released under the script. Nothing may be booked against it."],
] as const;

/** A bar is a fraction of the way to its target, for the meter. */
function meterOf(row: Criterion): { value: number; mark?: number; markLabel?: string } {
  if (row.unit === "%") return { value: row.value / 100, mark: row.bar / 100, markLabel: `bar ${row.bar}%` };
  if (row.bar === 0) return { value: row.value === 0 ? 1 : 0, markLabel: "bar: none" };
  return { value: Math.min(1, row.value / Math.max(1, row.bar)), mark: 1, markLabel: `bar ${row.bar}` };
}

function killScene(kills: number, duplicates: number) {
  const nodes: ConstellationNode[] = [];
  const links: ConstellationLink[] = [];
  const many = Math.max(1, kills);
  for (let index = 0; index < many; index += 1) {
    const x = 0.12 + (index / Math.max(1, many - 1)) * 0.76;
    nodes.push({ id: `kill-${index}`, x, y: 0.42, r: 4, tone: "warn", ring: true, lit: true, label: `Kill ${index + 1}`, side: "above" });
    nodes.push({ id: `resume-${index}`, x: x + 0.05, y: 0.66, r: 3.2, tone: "accent", lit: true });
    links.push({ from: `kill-${index}`, to: `resume-${index}`, tone: "accent", lit: true });
    if (index > 0) links.push({ from: `resume-${index - 1}`, to: `kill-${index}`, tone: "light" });
  }
  nodes.push({ id: "books", x: 0.5, y: 0.9, r: 5, tone: duplicates ? "fail" : "pass", ring: true, lit: true, label: "The carrier's own books", sub: duplicates ? `${duplicates} booked twice` : "nothing booked twice", side: "right" });
  for (let index = 0; index < many; index += 1) links.push({ from: `resume-${index}`, to: "books", tone: duplicates ? "fail" : "pass" });
  const paths = Array.from({ length: many }, (_, index) => [`kill-${index}`, `resume-${index}`, "books"]);
  return { nodes, links, paths };
}

export default function EvidencePage() {
  const user = readUser();
  const mayRun = mayAct(user?.role, "operations_lead");
  const { data: published } = useLoad<{ criteria: Criterion[] }>("/api/evidence/criteria");
  const [report, setReport] = useState<Evidence | null>(null);
  const [busy, setBusy] = useState(false);
  const [phase, setPhase] = useState(-1);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!busy) return;
    const handle = window.setInterval(() => setPhase((value) => Math.min(2, value + 1)), 1400);
    return () => window.clearInterval(handle);
  }, [busy]);

  const run = async () => {
    setBusy(true);
    setPhase(0);
    setError(null);
    try {
      const result = await api.post<Evidence>("/api/evidence/run", { shipments: 180 });
      setReport(result);
      setPhase(3);
      try {
        window.localStorage.setItem(MEASURED_KEY, "yes");
      } catch {
        /* a private window keeps the result on screen only */
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setPhase(-1);
    } finally {
      setBusy(false);
    }
  };

  const kills = useMemo(() => (report ? killScene(report.killing.kills, report.killing.duplicates) : null), [report]);
  const passed = report?.criteria.filter((row) => row.passed).length ?? 0;

  return (
    <>
      <Band top>
        <Reveal y={24}>
          <span className="ds-eyebrow">
            <span className="ds-live-dot" data-tone={report ? (report.passed ? undefined : "fail") : "accent"} aria-hidden />
            Evidence <span className="ds-eyebrow-sep">·</span> measured, not claimed
          </span>
        </Reveal>
        <Reveal index={1} y={32}>
          <h1 className="ds-display ds-band-title">
            Four bars.
            <br />
            <span className="ds-accent-text pb-light">Run them, and read the misses.</span>
          </h1>
        </Reveal>
        <Reveal index={2}>
          <p className="ds-band-lede">
            The acceptance suite builds a fresh day in its own space, runs it, kills it five times at different points and
            then checks the carrier&rsquo;s own books, and finally moves the portal under the script. The figure for clean
            shipments is measured over clean shipments only; the awkward ones are counted on their own, so a good number
            cannot hide whether the exceptions were handled or merely rare.
          </p>
        </Reveal>
        <Reveal index={3}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, alignItems: "center", marginTop: 26 }}>
            {mayRun ? (
              <Button tone="primary" size="large" busy={busy} onClick={() => void run()} arrow>
                {report ? "Run it again" : "Run the acceptance suite"}
              </Button>
            ) : (
              <Button tone="primary" size="large" onClick={() => void switchTo("tomas.reyes@hengtai-industrial.example").then(() => window.location.reload())} arrow>
                Switch to Tomas Reyes, operations lead, to run it
              </Button>
            )}
            {report && (
              <StatusChip tone={report.passed ? "pass" : "fail"} surface="dark" size="large">
                {passed} of {report.criteria.length} bars held
              </StatusChip>
            )}
          </div>
        </Reveal>
        {(busy || report) && (
          <div className="pb-phases" aria-live="polite">
            {PHASES.map(([number, title, text], index) => {
              const state = phase > index || (report && !busy) ? "done" : phase === index ? "active" : "waiting";
              return (
                <div key={number} className="pb-phase" data-state={state}>
                  <span className="ds-mono-label">{number}</span>
                  <span className="pb-phase-title">
                    {state === "active" ? <span className="ds-live-dot" data-tone="accent" aria-hidden /> : state === "done" ? <span className="ds-live-dot" aria-hidden /> : null}
                    {title}
                  </span>
                  <p style={{ margin: "6px 0 0", fontSize: 13, lineHeight: 1.5, color: "var(--ds-ink-muted)" }}>{text}</p>
                </div>
              );
            })}
          </div>
        )}
      </Band>

      <div className="ds-work" style={{ display: "grid", gap: 26 }}>
        {error && <ErrorNote error={error} />}
        {busy && !report && <Loading what="Running a day, killing it five times and moving the portal" />}

        {report ? (
          <>
            <Banner tone={report.passed ? "pass" : "fail"} title={report.passed ? "Every bar held" : "A bar did not hold"}>
              {report.statement} Measured in {seconds(report.seconds)}.
            </Banner>
            <div className="pb-criteria">
              {report.criteria.map((row, index) => {
                const meter = meterOf(row);
                return (
                  <Reveal key={row.name} index={index}>
                    <Card eyebrow={row.passed ? "Pass" : "Fail"} tone="accent" style={{ borderColor: row.passed ? "var(--ds-line)" : "var(--ds-fail)" }}>
                      <div style={{ display: "flex", justifyContent: "space-between", gap: 12, alignItems: "flex-start" }}>
                        <p className="pb-criterion-question">{row.question}</p>
                        <StatusChip tone={row.passed ? "pass" : "fail"} pulse={!row.passed}>
                          {row.passed ? "Pass" : "Fail"}
                        </StatusChip>
                      </div>
                      <span className="pb-criterion-value" data-tone={row.passed ? "pass" : "fail"}>
                        <Figure
                          value={`${row.value}${row.unit === "%" ? "%" : ""}`}
                          count={row.value}
                          decimals={row.unit === "%" && !Number.isInteger(row.value) ? 1 : 0}
                          origin="measured"
                          heading={row.question}
                          explain={{
                            formula: row.unit === "%" ? `measured share, against a bar of ${row.bar}%` : `measured count, against a bar of ${row.bar}`,
                            inputs: [
                              { label: "Measured", value: `${row.value}${row.unit === "%" ? "%" : ""}`, source: row.measured, sourceKind: "Evaluation" },
                              { label: "Bar", value: `${row.bar}${row.unit === "%" ? "%" : ""}`, source: "The acceptance criteria, published before the run", sourceKind: "Criteria" },
                            ],
                          }}
                        />
                      </span>
                      <div style={{ marginTop: 26 }}>
                        <Meter value={meter.value} mark={meter.mark} markLabel={meter.markLabel} tone={row.passed ? "pass" : "fail"} size="large" delay={index * 140} label={`${row.value} against a bar of ${row.bar}`} />
                      </div>
                      <p className="pb-criterion-measured">{row.measured}</p>
                    </Card>
                  </Reveal>
                );
              })}
            </div>

            <div className="pb-grid-2">
              <Reveal>
                <Card eyebrow="The kill test" title="Killed five times. The carrier's books, checked." flush>
                  <div style={{ position: "relative", height: 260, background: "var(--ds-ink)" }}>
                    {kills && <Constellation nodes={kills.nodes} links={kills.links} ambient={18} traffic={{ paths: kills.paths, every: 900, tone: "accent" }} label={`${report.killing.kills} kills, ${report.killing.duplicates} booked twice.`} />}
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(0, 1fr))", gap: 12, padding: "16px 20px" }}>
                    {(
                      [
                        ["Kills", report.killing.kills, "times the run was killed part way"],
                        ["Bookings made", report.killing.bookings_made, "bookings in the carrier's own books"],
                        ["Booked twice", report.killing.duplicates, "references the carrier holds more than once"],
                      ] as const
                    ).map(([label, value, rule]) => (
                      <div key={label}>
                        <span style={{ display: "block", fontFamily: "var(--ds-font-display)", fontWeight: 600, fontSize: 28, color: label === "Booked twice" ? (value ? "var(--ds-fail-ink)" : "var(--ds-pass-ink)") : undefined }}>
                          <Figure
                            value={String(value)}
                            count={value}
                            origin="measured"
                            heading={label}
                            explain={{
                              formula: `count of ${rule}`,
                              inputs: [
                                { label: "Shipments in the test", value: String(report.killing.shipments), source: "A fresh day, built for the test", sourceKind: "Evaluation" },
                                { label: "Finished", value: String(report.killing.finished), source: "Rows done after the last resume", sourceKind: "Evaluation" },
                                { label: "Unstable keys", value: String(report.killing.unstable_keys.length), source: "Keys that changed between runs", sourceKind: "Evaluation" },
                              ],
                              note: "Checking our own records would prove nothing; the whole failure is the two sides disagreeing. So the test reads the carrier's books.",
                            }}
                          />
                        </span>
                        <span className="ds-mono-label">{label}</span>
                      </div>
                    ))}
                  </div>
                </Card>
              </Reveal>
              <Reveal index={1}>
                <Card eyebrow="When the portal moved" title={report.drift.halted ? "It stopped. Nothing was booked." : "It did not stop"} tone="accent">
                  <p className="pb-lede" style={{ marginTop: 0 }}>{report.drift.reason}</p>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}>
                    {report.drift.suggested_renames.map(([gone, arrived]) => (
                      <span key={gone} className="ds-mono" style={{ padding: "6px 10px", background: "var(--ds-fail-soft)", color: "var(--ds-fail-ink)", fontSize: 12.5, fontWeight: 600, borderRadius: 3 }}>
                        {gone} → {arrived}
                      </span>
                    ))}
                  </div>
                  <div style={{ display: "flex", flexWrap: "wrap", gap: "14px 30px", marginTop: 18 }}>
                    <div>
                      <span style={{ display: "block", fontFamily: "var(--ds-font-display)", fontWeight: 600, fontSize: 28 }}>
                        <Figure
                          value={String(report.drift.booked_anyway)}
                          count={report.drift.booked_anyway}
                          origin="measured"
                          heading="Booked on a moved form"
                          explain={{ formula: "count of bookings made after version 2 was released", inputs: [{ label: "Halted", value: report.drift.halted ? "yes" : "no", source: "The run's own status", sourceKind: "Evaluation" }, { label: "Flag raised", value: report.drift.flag_raised ? "yes" : "no", source: "Script flags", sourceKind: "Evaluation" }] }}
                        />
                      </span>
                      <span className="ds-mono-label">Booked on a moved form</span>
                    </div>
                    <div>
                      <span style={{ display: "block", marginTop: 6 }}>
                        <StatusChip tone={report.drift.flag_raised ? "pass" : "fail"}>{report.drift.flag_raised ? "Flag raised" : "No flag"}</StatusChip>
                      </span>
                      <span className="ds-mono-label" style={{ display: "block", marginTop: 10 }}>
                        Suggested to a developer · applied by nobody
                      </span>
                    </div>
                  </div>
                </Card>
              </Reveal>
            </div>

            <Reveal>
              <Card eyebrow="Including what it got wrong" title="What stopped, and why" subtitle="Every exception is named and traceable. Planted means the day was built with it on purpose; anything else is the bot's own miss.">
                <ul className="pb-why">
                  {report.ordinary.by_kind.map((row, index) => (
                    <li key={row.kind} className="pb-why-row">
                      <span className="pb-why-label">
                        {row.label}{" "}
                        <StatusChip tone={row.planted ? "neutral" : "fail"} size="small">
                          {row.planted ? "Planted in the day" : "A miss"}
                        </StatusChip>
                      </span>
                      <span className="pb-why-value">
                        <Figure
                          value={String(row.count)}
                          count={row.count}
                          origin="measured"
                          heading={row.label}
                          explain={{ formula: "count of shipments stopped with this named exception", inputs: [{ label: row.label, value: String(row.count), source: row.planted ? "Planted in the generated day" : "Not planted: a miss", sourceKind: "Evaluation" }, { label: "Exceptions in all", value: String(report.ordinary.exceptions), source: "Every named exception", sourceKind: "Evaluation" }, { label: "Classified", value: String(report.ordinary.classified), source: "Exceptions with a name and the evidence", sourceKind: "Evaluation" }] }}
                        />
                      </span>
                      <Meter value={row.count / Math.max(1, ...report.ordinary.by_kind.map((item) => item.count))} tone={row.planted ? "warn" : "fail"} delay={index * 120} />
                    </li>
                  ))}
                </ul>
              </Card>
            </Reveal>
          </>
        ) : !busy && published ? (
          <div className="pb-criteria">
            {published.criteria.map((row, index) => (
              <Reveal key={row.name} index={index}>
                <Card eyebrow="Not measured yet" title={row.question}>
                  <p className="ds-mono" style={{ margin: 0, fontSize: 13, color: "var(--ds-text-2)" }}>
                    Bar: {row.bar}
                    {row.unit === "%" ? "%" : ` ${row.unit}`}
                  </p>
                  <div style={{ marginTop: 22 }}>
                    <Meter value={0} mark={row.unit === "%" ? row.bar / 100 : undefined} markLabel={row.unit === "%" ? `bar ${row.bar}%` : undefined} />
                  </div>
                </Card>
              </Reveal>
            ))}
          </div>
        ) : null}

        <Reveal>
          <Card eyebrow="Said out loud" title="What this does not claim">
            <ul className="pb-not-claimed">
              <li>
                <b>It does not claim to be robust against the portal changing.</b> It claims to notice and stop. Only the
                second claim is keepable.
              </li>
              <li>
                <b>It does not claim driving a screen is a good idea.</b> It is a last resort for systems with no other way
                in. If the carrier has a proper interface, use that.
              </li>
              <li>
                <b>It does not self-heal, and will not be made to.</b> Automatic adaptation turns a cheap failure into an
                expensive one.
              </li>
              <li>
                <b>It does not claim these figures will hold on your carrier.</b> They are against a simulated portal built
                to misbehave in the documented ways. What transfers is the structure: checkpoints on the row, a derived key,
                a form check before sending, named exceptions.
              </li>
              <li>
                <b>It does not defeat human-presence checks.</b> Image challenges stop the run and go to a clerk.
              </li>
            </ul>
          </Card>
        </Reveal>
        <ThesisStrip action={<span />} />
      </div>
    </>
  );
}
