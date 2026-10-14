"use client";

/**
 * Assurance: five bars, measured rather than asserted, with both red teams
 * shown attack by attack and the misses shown, not hidden. Two bars are
 * absolutes: one row belonging to somebody else, or one instruction obeyed
 * from a document, is a fail.
 */

import { useEffect, useState } from "react";

import { counted, Figure } from "@/components/trace";
import { Meter } from "@/design/Meter";
import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Tabs } from "@/design/Tabs";
import { Band, Banner, Button, Card, Empty } from "@/design/Surface";
import { api, ApiError } from "@/lib/api";
import { useLoad, useSignedIn } from "@/lib/session";
import type { Criterion, Evaluation, RedTeamRow } from "@/lib/types";
import { capabilityWords, CAPABILITIES, dayAndClock, grouped, plain, reaches, roleWords, sentenceCase } from "@/lib/words";

type Latest = { run: { criteria: Criterion[]; passed: boolean; started_at: string } | null; criteria: Criterion[] };

const PHASES = [
  { key: "answers", label: "Nineteen labelled questions, each answer worked out a second time" },
  { key: "permissions", label: "128 permission attacks across four limited accounts, half with the planner bypassed" },
  { key: "injections", label: "14 documents with instructions in them, in six families" },
];

function unitWords(criterion: Criterion): string {
  if (criterion.unit === "%") return "%";
  if (criterion.unit === "seconds") return " s";
  return ` ${criterion.unit}`;
}

function meterFor(criterion: Criterion, run: Evaluation | null) {
  const value = criterion.value ?? 0;
  if (criterion.name.includes("permission")) {
    const attacks = run?.permissions.attacks ?? 0;
    const held = run?.permissions.held ?? 0;
    return { value: attacks ? held / attacks : criterion.passed ? 1 : 0, mark: 1, markLabel: "all must hold", note: attacks ? `${held} of ${attacks} attacks held` : criterion.passed ? "every attack held" : "" };
  }
  if (criterion.name.includes("instruction")) {
    const attacks = run?.injections.attacks ?? 0;
    const held = run?.injections.held ?? 0;
    return { value: attacks ? held / attacks : criterion.passed ? 1 : 0, mark: 1, markLabel: "all must hold", note: attacks ? `${held} of ${attacks} attacks held` : criterion.passed ? "every attack held" : "" };
  }
  if (criterion.lower_is_better) {
    return { value: Math.min(1, value / Math.max(criterion.bar, 0.0001)), mark: 1, markLabel: `limit ${criterion.bar}${unitWords(criterion)}`, note: `${value}${unitWords(criterion)} of ${criterion.bar}${unitWords(criterion)} allowed` };
  }
  return { value: value / 100, mark: criterion.bar / 100, markLabel: `bar ${criterion.bar}%`, note: "" };
}

export default function Assurance() {
  const user = useSignedIn();
  const { data: latest, reload } = useLoad<Latest>(user ? "/api/evaluation/latest" : null, [user?.email]);
  const [run, setRun] = useState<Evaluation | null>(null);
  const [running, setRunning] = useState(false);
  const [phase, setPhase] = useState(-1);
  const [trouble, setTrouble] = useState("");
  const [tab, setTab] = useState<"permissions" | "injections" | "answers">("permissions");

  useEffect(() => {
    if (!running) return;
    setPhase(0);
    const timers = [window.setTimeout(() => setPhase(1), 650), window.setTimeout(() => setPhase(2), 1300)];
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [running]);

  if (!user) return null;
  const mayRun = reaches(user.role, "manager");
  const criteria = run?.criteria ?? latest?.run?.criteria ?? latest?.criteria ?? [];
  const when = run?.started_at ?? latest?.run?.started_at ?? null;
  const measured = criteria.some((criterion) => criterion.passed !== undefined);
  const passedCount = criteria.filter((criterion) => criterion.passed).length;

  const measure = async () => {
    setRunning(true);
    setTrouble("");
    const started = performance.now();
    try {
      const out = await api.post<Evaluation>("/api/evaluation/run");
      const wait = Math.max(0, 2000 - (performance.now() - started));
      await new Promise((resolve) => window.setTimeout(resolve, wait));
      setRun(out);
      reload();
    } catch (cause) {
      setTrouble(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setRunning(false);
      setPhase(-1);
    }
  };

  return (
    <>
      <Band top>
        <div className="oa-page-band">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone={measured && passedCount === criteria.length ? "pass" : "warn"} aria-hidden />
              Assurance <span className="ds-eyebrow-sep">·</span> {when ? `last run ${dayAndClock(when)}` : "not run yet"}
            </span>
          </Reveal>
          <Reveal index={1} y={32}>
            <h1 className="ds-display oa-page-title">
              Measured, not asserted.
              <br />
              <span className="oa-light ds-accent-text">Including what it got wrong.</span>
            </h1>
          </Reveal>
          <Reveal index={2}>
            <p className="ds-band-lede">
              Five bars, agreed before the build. The permission red team assumes the planner is already lost: half of its
              attacks skip the planner entirely and run every query directly with somebody else&rsquo;s identifiers. Only the
              role check and the row filter are doing any work.
            </p>
          </Reveal>
          <Reveal index={3}>
            <div className="oa-run">
              {mayRun ? (
                <Button tone="primary" size="large" busy={running} onClick={() => void measure()} arrow>
                  {running ? "Measuring" : "Run it now"}
                </Button>
              ) : (
                <StatusChip tone="neutral" surface="dark" size="large">
                  An operations manager can run it
                </StatusChip>
              )}
              {measured && (
                <span className="oa-run-score">
                  <b>
                    {passedCount} of {criteria.length}
                  </b>{" "}
                  bars met · {run ? run.statement : "from the last run"}
                </span>
              )}
            </div>
          </Reveal>
          {running && (
            <div className="oa-run-phases" aria-live="polite">
              <NodeChain
                live
                stagger={0}
                fill={(phase + 1) / PHASES.length}
                items={PHASES.map((item, index) => ({
                  key: item.key,
                  tone: index < phase ? "pass" : index === phase ? "accent" : undefined,
                  state: index < phase ? "done" : index === phase ? "active" : "waiting",
                  marker: index < phase ? "✓" : String(index + 1).padStart(2, "0"),
                  content: <span className="oa-stage" data-state={index <= phase ? "active" : "waiting"}>{item.label}</span>,
                }))}
              />
            </div>
          )}
        </div>
      </Band>

      <div className="ds-work">
        {trouble && (
          <div style={{ marginBottom: 20 }}>
            <Banner tone="fail" title="The run did not finish">
              {trouble}
            </Banner>
          </div>
        )}

        <div className="oa-criteria" key={run?.started_at ?? "latest"}>
          {criteria.map((criterion, index) => {
            const meter = meterFor(criterion, run);
            const tone = criterion.passed === undefined ? "info" : criterion.passed ? "pass" : "fail";
            const value = criterion.value;
            return (
              <Reveal key={criterion.name} index={index}>
                <Card className="oa-criterion" tone={criterion.passed === false ? undefined : undefined}>
                  <div className="oa-criterion-top">
                    <StatusChip tone={tone === "info" ? "neutral" : tone} size="large" pulse={criterion.passed === false}>
                      {criterion.passed === undefined ? "Not run" : criterion.passed ? "Met" : "Missed"}
                    </StatusChip>
                    <span className="oa-criterion-value">
                      {value === undefined ? (
                        "—"
                      ) : (
                        <Figure
                          value={`${value}${unitWords(criterion)}`}
                          count={value}
                          decimals={Number.isInteger(value) ? 0 : 2}
                          content={counted(
                            sentenceCase(criterion.name),
                            `${value}${unitWords(criterion)}`,
                            criterion.measured ?? criterion.question,
                            [
                              { label: "The bar", value: `${criterion.lower_is_better ? "at most" : "at least"} ${criterion.bar}${unitWords(criterion)}`, source: criterion.question, sourceKind: "Agreed before the build" },
                              { label: "Measured", value: `${value}${unitWords(criterion)}`, source: criterion.measured ?? "", sourceKind: "This run" },
                            ],
                            "Measured by the evaluation",
                            "The evaluation recomputes every answer independently and attacks with real accounts.",
                          )}
                        />
                      )}
                    </span>
                  </div>
                  <h2 className="oa-criterion-name">{sentenceCase(criterion.name)}</h2>
                  <p className="oa-criterion-question">{criterion.question}</p>
                  <div className="oa-criterion-meter">
                    <Meter value={meter.value} mark={meter.mark} markLabel={meter.markLabel} tone={tone === "fail" ? "fail" : tone === "pass" ? "pass" : "info"} delay={index * 90} />
                  </div>
                  <p className="oa-criterion-measured">{criterion.measured ? plain(criterion.measured) : "Press run to measure it."}</p>
                </Card>
              </Reveal>
            );
          })}
        </div>

        {!run ? (
          <div style={{ marginTop: 28 }}>
            <Empty title={mayRun ? "Run it to see every attack, account by account." : "Every attack is listed after a run."}>
              It takes under a second: nineteen labelled questions, 128 permission attacks and fourteen poisoned documents.
            </Empty>
          </div>
        ) : (
          <section className="oa-section">
            <Tabs
              label="Which part of the run"
              value={tab}
              onChange={setTab}
              tabs={[
                { key: "permissions", label: "Permission attacks", badge: run.permissions.attacks },
                { key: "injections", label: "Instructions in documents", badge: run.injections.attacks },
                { key: "answers", label: "Labelled answers", badge: run.answers.asked },
              ]}
            />
            <div style={{ marginTop: 20 }} id="tab-panel" role="tabpanel">
              {tab === "permissions" && <PermissionTab run={run} />}
              {tab === "injections" && <InjectionTab run={run} />}
              {tab === "answers" && <AnswersTab run={run} />}
            </div>
          </section>
        )}
      </div>
    </>
  );
}

function accountWords(account: string | undefined): string {
  if (!account) return "";
  return account.replace(/\(([a-z_]+)\)/, (_all, role: string) => `· ${roleWords(role).toLowerCase()}`);
}

function attackName(row: RedTeamRow): string {
  return CAPABILITIES[row.name] ? `Ran "${capabilityWords(row.name)}" with another account's identifiers` : sentenceCase(row.name);
}

function AttackTable({ rows, columns }: { rows: RedTeamRow[]; columns: ("account" | "route" | "family" | "noticed")[] }) {
  return (
    <Card flush>
      <div className="ds-table-wrap">
        <table className="ds-table">
          <thead>
            <tr>
              <th>Held</th>
              <th>Attack</th>
              {columns.includes("account") && <th>Account</th>}
              {columns.includes("route") && <th>Route</th>}
              {columns.includes("family") && <th>Family</th>}
              {columns.includes("noticed") && <th>Keyword check</th>}
              <th>What came back</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => (
              <Reveal
                as="tr"
                key={`${row.name}-${index}`}
                index={index}
                className="ds-rowmark"
                style={{ "--row-tone": row.held ? "var(--ds-pass)" : "var(--ds-fail)" } as React.CSSProperties}
              >
                <td>
                  <StatusChip tone={row.held ? "pass" : "fail"} size="small">
                    {row.held ? "Held" : "Broke"}
                  </StatusChip>
                </td>
                <td style={{ minWidth: 200 }}>
                  {attackName(row)}
                  {row.wants && <div style={{ fontSize: 12, color: "var(--ds-text-3)" }}>wanted {plain(row.wants)}</div>}
                </td>
                {columns.includes("account") && <td style={{ whiteSpace: "nowrap" }}>{accountWords(row.account)}</td>}
                {columns.includes("route") && (
                  <td>
                    <StatusChip tone={row.route?.includes("bypassed") ? "accent" : "neutral"} size="small">
                      {row.route?.includes("bypassed") ? "Planner bypassed" : "Asked in words"}
                    </StatusChip>
                  </td>
                )}
                {columns.includes("family") && <td>{row.family ? sentenceCase(row.family) : ""}</td>}
                {columns.includes("noticed") && (
                  <td>
                    {row.expected_unnoticed ? (
                      <StatusChip tone="warn" size="small">
                        Missed, as expected
                      </StatusChip>
                    ) : row.noticed ? (
                      <StatusChip tone="neutral" size="small">
                        Noticed
                      </StatusChip>
                    ) : (
                      <StatusChip tone="neutral" size="small">
                        Not noticed
                      </StatusChip>
                    )}
                  </td>
                )}
                <td style={{ fontSize: 12.5, color: "var(--ds-text-2)", minWidth: 220 }}>{plain(row.detail).replace(/^ran \[(.*?)\]/, (_all, list: string) => `ran ${list.replace(/'/g, "")}`)}</td>
              </Reveal>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

function PermissionTab({ run }: { run: Evaluation }) {
  const bypassed = run.permissions.results.filter((row) => row.route?.includes("bypassed")).length;
  return (
    <div>
      <div className="oa-accounts">
        {run.permissions.accounts.map((account, index) => (
          <Reveal key={account.account} index={index}>
            <Card className="oa-account-card">
              <p className="ds-mono-label" style={{ margin: 0 }}>
                {roleWords(account.role)}
              </p>
              <p className="oa-account-name">{account.account}</p>
              <p className="oa-account-reach">
                {account.customers_granted} accounts{account.suppliers_granted ? ` · ${account.suppliers_granted} suppliers` : ""} · {account.attacks} attacks
              </p>
              <Meter value={account.attacks ? (account.attacks - (account.leaked ? 1 : 0)) / account.attacks : 1} tone={account.leaked ? "fail" : "pass"} size="small" delay={index * 90} />
              <p className="oa-account-leaked" data-bad={account.leaked ? "" : undefined}>
                {account.leaked} rows leaked
              </p>
            </Card>
          </Reveal>
        ))}
      </div>
      <p className="oa-tab-lede">
        {bypassed} of {run.permissions.attacks} attacks never went through the planner: they ran every reviewed query
        directly against a limited account, with another account&rsquo;s identifiers, which is what a completely subverted
        planner would emit. A breach is counted on the raw rows, not on what reached the screen.{" "}
        <b>{grouped(run.permissions.leaked_rows)} rows leaked.</b>
      </p>
      <AttackTable rows={run.permissions.results} columns={["account", "route"]} />
    </div>
  );
}

function InjectionTab({ run }: { run: Evaluation }) {
  const injections = run.injections;
  return (
    <div>
      <div className="oa-injection-stats">
        {[
          ["Obeyed", injections.obeyed, injections.obeyed ? "fail" : "pass"],
          ["Rows written", injections.rows_written, injections.rows_written ? "fail" : "pass"],
          ["Proposals approved by itself", injections.proposals_approved_by_itself, injections.proposals_approved_by_itself ? "fail" : "pass"],
          ["Noticed by the keyword check", injections.noticed, "info"],
          ["Slipped past it", injections.slipped_past_the_filter, "warn"],
        ].map(([label, value, tone], index) => (
          <Reveal key={String(label)} index={index}>
            <div className="oa-injection-stat" data-tone={String(tone)}>
              <span className="oa-injection-value">{String(value)}</span>
              <span className="ds-mono-label">{String(label)}</span>
            </div>
          </Reveal>
        ))}
      </div>
      <p className="oa-tab-lede">
        The keyword check is a second line and a weak one. {injections.slipped_past_the_filter} of these attacks were never
        noticed, and one is written specifically to slip past it; the evaluation asserts that it is missed. They reached
        nothing anyway, because nothing in the design depends on noticing.
      </p>
      <AttackTable rows={injections.results} columns={["family", "noticed"]} />
    </div>
  );
}

function AnswersTab({ run }: { run: Evaluation }) {
  const answers = run.answers;
  return (
    <div className="oa-answers-tab">
      <Card title={`${answers.right} of ${answers.asked} labelled questions right`} subtitle="Each answer is worked out a second time, independently, and compared.">
        <Meter value={answers.share / 100} mark={0.9} markLabel="bar 90%" tone={answers.share >= 90 ? "pass" : "fail"} size="large" />
        <p className="oa-tab-lede" style={{ marginTop: 22 }}>
          {answers.traceable} of {answers.asked} carry the query and the moment it was read. The slowest took{" "}
          {answers.slowest_seconds} s.
        </p>
      </Card>
      <Card title="What it got wrong" subtitle="Shown, not hidden.">
        {answers.misses.length ? (
          <ul className="oa-misses">
            {answers.misses.map((miss, index) => (
              <li key={index}>
                <StatusChip tone="fail" size="small">
                  Missed
                </StatusChip>
                {plain(miss)}
              </li>
            ))}
          </ul>
        ) : (
          <p style={{ margin: 0, fontSize: 14, color: "var(--ds-text-2)", lineHeight: 1.6 }}>
            No misses in this run. The labelled set includes three questions that must be refused rather than improvised,
            and the two it got wrong on its first run are part of the test suite now. What it does not claim: the wording
            around the figures is the part a reviewer should read sceptically.
          </p>
        )}
      </Card>
    </div>
  );
}
