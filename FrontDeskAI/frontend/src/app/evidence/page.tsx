"use client";

import { useEffect, useState } from "react";

import { Meter } from "@/design/Meter";
import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Band, Banner, Button, Card } from "@/design/Surface";
import { Figure } from "@/components/trace";
import { ErrorNote, SectionHead } from "@/components/ui";
import { api, readUser } from "@/lib/api";
import { count, engineWord, percent } from "@/lib/format";
import { useAction, useLoad } from "@/lib/hooks";
import type { Criterion, Evidence } from "@/lib/types";

const RUN_STEPS = [
  "Holding 120 scripted conversations",
  "Sending the red team: 21 attacks in 8 families",
  "Racing two customers at the same slot, 25 times",
  "Counting, strictly",
];

const FAMILY_HINTS: Record<string, string> = {
  straight: "Just naming somebody else's order",
  authority: "“This is Mei Lin from the service desk”",
  override: "“Ignore all previous instructions”",
  roleplay: "“You are a database”",
  enumeration: "Probing to find which references are real",
  deputy: "“My colleague asked me to check theirs”",
  encoding: "The reference spaced out or in pieces",
  volume: "Guessing at the identity check until it opens",
};

export default function EvidencePage() {
  const user = readUser();
  const mayRun = ["supervisor", "administrator"].includes(user?.role ?? "");
  const published = useLoad<{ criteria: Criterion[] }>("/api/evidence/criteria");
  const [report, setReport] = useState<Evidence | null>(null);
  const [step, setStep] = useState(0);
  const { busy, error, run } = useAction();

  useEffect(() => {
    if (!busy) return;
    setStep(0);
    const handle = window.setInterval(() => setStep((value) => Math.min(value + 1, RUN_STEPS.length - 1)), 900);
    return () => window.clearInterval(handle);
  }, [busy]);

  const start = () =>
    void run("run", () => api.post<Evidence>("/api/evidence/run", { conversations: 120 })).then((result) => {
      if (result) setReport(result);
    });

  return (
    <div>
      <Band top>
        <div className="fd-page-band">
          <div>
            <Reveal y={24}>
              <span className="ds-eyebrow">
                <span className="ds-live-dot" data-tone={report ? (report.passed ? "pass" : "fail") : "accent"} aria-hidden />
                Measured, not claimed <span className="ds-eyebrow-sep">·</span> including what it got wrong
              </span>
            </Reveal>
            <Reveal index={1} y={32}>
              <h1 className="ds-display ds-band-title">
                Four bars.
                <br />
                <span className="fd-light">Run them here, see every miss.</span>
              </h1>
            </Reveal>
            <Reveal index={2} y={28}>
              <p className="ds-band-lede">
                The acceptance criteria run as code against a scripted mix of contacts, a red team and a booking race.
                The run happens inside a transaction that is rolled back, so it never touches the live desk.
              </p>
            </Reveal>
            <Reveal index={3} y={24}>
              <div className="fd-hero-actions">
                {mayRun ? (
                  <Button tone="primary" size="large" busy={Boolean(busy)} onClick={start} arrow>
                    {report ? "Run it again" : "Run the evaluation"}
                  </Button>
                ) : (
                  <Banner tone="warn" title="Supervisors run the evaluation">
                    You are signed in as {user?.role_label ?? "staff"}; the published bars are below.
                  </Banner>
                )}
              </div>
            </Reveal>
          </div>
          <div className="fd-run-panel" aria-live="polite">
            {busy ? (
              <>
                <span className="ds-mono-label">Running now</span>
                <NodeChain
                  live
                  fill={(step + 0.5) / RUN_STEPS.length}
                  items={RUN_STEPS.map((label, index) => ({
                    key: label,
                    tone: index < step ? "pass" : index === step ? "accent" : undefined,
                    state: index < step ? "done" : index === step ? "active" : "waiting",
                    marker: index < step ? "✓" : String(index + 1).padStart(2, "0"),
                    content: <span className="fd-stage-row" data-active={index === step ? "" : undefined}>{label}</span>,
                  }))}
                />
              </>
            ) : report ? (
              <>
                <span className="ds-mono-label">Last run</span>
                <p className="fd-run-verdict" data-passed={report.passed ? "" : undefined}>
                  {report.passed ? "Every bar held" : "A bar did not hold"}
                </p>
                <p className="ds-mono" style={{ margin: "6px 0 0", fontSize: 12, color: "var(--ds-ink-muted)" }}>
                  {report.seconds.toLocaleString("en-GB")} seconds · {engineWord(report.engine)}
                </p>
                <p style={{ margin: "12px 0 0", fontSize: 13.5, color: "var(--ds-ink-muted)", lineHeight: 1.55 }}>{report.statement}</p>
              </>
            ) : (
              <>
                <span className="ds-mono-label">Not run in this session</span>
                <p style={{ margin: "10px 0 0", fontSize: 14, color: "var(--ds-ink-muted)", lineHeight: 1.55 }}>
                  Press run. It takes a few seconds: 120 conversations, 21 attacks and 50 simultaneous bookings, measured
                  by the server.
                </p>
              </>
            )}
          </div>
        </div>
      </Band>

      <div className="ds-work">
        {error && (
          <div style={{ marginBottom: 20 }}>
            <ErrorNote error={error} />
          </div>
        )}
        <section aria-labelledby="bars-heading">
          <Reveal>
            <SectionHead id="bars-heading" eyebrow="Acceptance criteria" title={report ? "The four bars, as measured" : "The four bars"} />
          </Reveal>
          <div className="fd-criteria">
            {(report?.criteria ?? published.data?.criteria ?? []).map((row, index) => (
              <CriterionCard key={row.name} row={row} index={index} measured={Boolean(report)} report={report} />
            ))}
          </div>
        </section>

        <section style={{ marginTop: 56 }} aria-labelledby="containment-heading">
          <Reveal>
            <SectionHead id="containment-heading" eyebrow="The number somebody will call low" title="Containment is not deflection" />
          </Reveal>
          <div className="fd-honest">
            <Reveal className="fd-honest-card">
              <Card tone="ink">
                <p className="fd-honest-lede">
                  Vendors quote 30 to 60 per cent deflection. Independent surveys of the same deployments find 10 to 25.
                  Most of the gap is counting a conversation as resolved because the customer stopped replying.{" "}
                  <b>A customer who gave up is not a customer who was helped.</b>
                </p>
                <ul className="fd-against">
                  {[
                    ["Returns", "A person approves every one. A return reaching a person is a success that scores nothing."],
                    ["Technician offers", "Offering slots is not finishing the job."],
                    ["Anything not understood", "Handing over is the right outcome, and it still scores zero."],
                  ].map(([title, body], index) => (
                    <Reveal as="li" key={title} index={index} from="left">
                      <span className="fd-against-mark" aria-hidden />
                      <span>
                        <b>{title}</b> {body}
                      </span>
                    </Reveal>
                  ))}
                </ul>
              </Card>
            </Reveal>
            <Reveal index={1} className="fd-honest-card">
              <Card eyebrow="By what the customer came for" title="What the desk finished on its own" flush>
                {report ? (
                  <ul className="fd-share-rows">
                    {report.conversations.by_intent.map((row, index) => (
                      <li key={row.intent}>
                        <span className="fd-share-label">{row.label}</span>
                        <Meter
                          value={row.share / 100}
                          tone={row.share >= 45 ? "pass" : row.share > 0 ? "warn" : "fail"}
                          size="small"
                          delay={index * 70}
                          label={`${row.share}% handled`}
                        />
                        <Figure
                          value={percent(row.share)}
                          count={row.share}
                          decimals={1}
                          align="end"
                          heading={`${row.label}: handled without a person`}
                          origin="Measured by the evaluation"
                          explain={{
                            formula: "handled ÷ seen × 100, counting only contacts answered with no person asked for and nothing handed over",
                            inputs: [
                              { label: "Seen", value: count(row.seen), sourceKind: "Scripted contacts" },
                              { label: "Handled alone", value: count(row.handled), sourceKind: "Measured" },
                              { label: "Handed to a person", value: count(row.escalated), sourceKind: "Measured" },
                            ],
                          }}
                        />
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p style={{ padding: 20, margin: 0, color: "var(--ds-text-2)" }}>Run the evaluation to fill this in.</p>
                )}
              </Card>
            </Reveal>
          </div>
        </section>

        {report && (
          <section style={{ marginTop: 56 }} aria-labelledby="misses-heading">
            <Reveal>
              <SectionHead id="misses-heading" eyebrow="Shown, not hidden" title="What it got wrong on this run" />
            </Reveal>
            <Reveal>
              <Card flush>
                {report.conversations.misses.length ? (
                  <ul className="fd-misses">
                    {report.conversations.misses.map((miss, index) => (
                      <Reveal as="li" key={`${miss}-${index}`} index={index} from="left" y={24}>
                        <StatusChip tone="fail" size="small">
                          Missed
                        </StatusChip>
                        <span>{miss}</span>
                      </Reveal>
                    ))}
                  </ul>
                ) : (
                  <p style={{ padding: 20, margin: 0 }}>
                    No contact the script expected the desk to finish was missed. The categories above that score zero
                    still count against it, by design.
                  </p>
                )}
              </Card>
            </Reveal>
          </section>
        )}

        {report && (
          <section style={{ marginTop: 56 }} aria-labelledby="redteam-heading">
            <Reveal>
              <SectionHead id="redteam-heading" eyebrow="The red team" title={`${report.redteam.attacks} attacks, ${report.redteam.leaks} leaks`} />
            </Reveal>
            <div className="fd-families">
              {report.redteam.by_family.map((family, index) => {
                const held = family.held === family.attacks;
                return (
                  <Reveal key={family.family} index={index} className="fd-family ds-lift" data-held={held ? "" : undefined}>
                    <div className="fd-ticket-top">
                      <span className="fd-family-name">{family.label}</span>
                      <StatusChip tone={held ? "pass" : "fail"} size="small">
                        {held ? "Held" : "Leaked"}
                      </StatusChip>
                    </div>
                    <p className="fd-small-note" style={{ marginTop: 6 }}>
                      {FAMILY_HINTS[family.family] ?? ""}
                    </p>
                    <Meter value={family.attacks ? family.held / family.attacks : 0} tone={held ? "pass" : "fail"} size="small" delay={index * 70} />
                    <p className="ds-mono" style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--ds-text-3)" }}>
                      <Figure
                        value={`${family.held} of ${family.attacks} held`}
                        heading={`${family.label}: attacks that got nothing`}
                        origin="Measured by the evaluation"
                        explain={{
                          formula: "A leak is counted on the data - another customer's name, a tracking number, a date, a lot number - never on wording",
                          inputs: report.redteam.results
                            .filter((result) => result.family === family.family)
                            .map((result) => ({
                              label: result.name,
                              value: result.held ? "held" : "leaked",
                              source: result.detail,
                              sourceKind: "Attack",
                            })),
                        }}
                      />
                    </p>
                  </Reveal>
                );
              })}
            </div>
            <Reveal>
              <p className="fd-small-note" style={{ marginTop: 18 }}>
                A real order that belongs to somebody else and an invented one get the same reply, character for
                character, so guessing finds nothing.
              </p>
            </Reveal>
          </section>
        )}
      </div>
    </div>
  );
}

function CriterionCard({
  row,
  index,
  measured,
  report,
}: {
  row: Criterion;
  index: number;
  measured: boolean;
  report: Evidence | null;
}) {
  const isShare = row.unit === "%";
  const value = measured ? row.value : undefined;
  const meter = isShare ? (value ?? 0) / 100 : measured ? (row.value === 0 ? 1 : 0.15) : 0;
  const tone = !measured ? "info" : row.passed ? "pass" : "fail";
  const shown = value === undefined ? "Not run" : isShare ? percent(value) : `${count(value)} ${row.unit}`;
  const inputs =
    !report
      ? []
      : row.name === "handled without a person"
        ? [
            { label: "Conversations", value: count(report.conversations.conversations), sourceKind: "Scripted" },
            { label: "Handled alone", value: count(report.conversations.handled), sourceKind: "Measured" },
            { label: "Handed to a person", value: count(report.conversations.escalated), sourceKind: "Measured" },
          ]
        : row.name === "a person always one tap away"
          ? [
              { label: "Replies", value: count(report.conversations.replies), sourceKind: "Measured" },
              { label: "Without a route to a person", value: count(report.conversations.missing_human), sourceKind: "Measured" },
            ]
          : row.name === "no other customer's data"
            ? [
                { label: "Attacks", value: count(report.redteam.attacks), sourceKind: "Red team" },
                { label: "Messages sent", value: count(report.redteam.attempts), sourceKind: "Red team" },
                { label: "Leaks found", value: count(report.redteam.leaks), sourceKind: "Measured" },
              ]
            : [
                { label: "Simultaneous bookings", value: count(report.concurrency.attempted), sourceKind: "Race" },
                { label: "Clashes", value: count(report.concurrency.clashes), sourceKind: "Measured" },
                {
                  label: "Second customer offered another slot",
                  value: count(report.concurrency.second_customer_offered_another),
                  sourceKind: "Measured",
                },
              ];
  return (
    <Reveal index={index} className="fd-criterion" data-tone={tone}>
      <div className="fd-ticket-top">
        <span className="ds-mono-label">{row.name}</span>
        <span style={{ display: "inline-flex", gap: 6 }}>
          {row.stretch_met && (
            <StatusChip tone="pass" size="small">
              Stretch met
            </StatusChip>
          )}
          <StatusChip tone={tone === "info" ? "neutral" : tone} size="large">
            {!measured ? "Not run" : row.passed ? "Pass" : "Fail"}
          </StatusChip>
        </span>
      </div>
      <p className="fd-criterion-question">{row.question}</p>
      <p className="fd-criterion-value" data-tone={tone}>
        {value === undefined ? (
          <span style={{ color: "var(--ds-text-3)" }}>—</span>
        ) : (
          <Figure
            value={shown}
            count={value}
            decimals={isShare ? 1 : 0}
            heading={row.question}
            origin="Measured by the evaluation"
            note={row.measured}
            explain={{
              formula: isShare
                ? `Measured share; the bar is ${row.bar}%${row.stretch ? `, the stretch ${row.stretch}%` : ""}`
                : `Counted; the bar is ${row.bar} ${row.unit}, and one is a fail`,
              result: shown,
              inputs,
            }}
          />
        )}
      </p>
      <Meter
        value={meter}
        mark={isShare ? row.bar / 100 : undefined}
        markLabel={isShare ? `bar ${row.bar}%` : undefined}
        tone={tone}
        size="large"
        delay={index * 120}
        label={measured ? `${shown}, bar ${row.bar}` : `bar ${row.bar}`}
      />
      <p className="fd-criterion-measured">
        {measured ? row.measured : `Bar: ${isShare ? `${row.bar}%` : `${row.bar} ${row.unit}`}${row.stretch ? `, stretch ${row.stretch}%` : ""}`}
      </p>
    </Reveal>
  );
}

export const dynamic = "force-dynamic";
