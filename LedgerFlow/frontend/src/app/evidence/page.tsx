"use client";

import { useEffect, useRef, useState } from "react";

import { Constellation } from "@/design/Constellation";
import { CountUp } from "@/design/CountUp";
import { Meter } from "@/design/Meter";
import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { api, readUser } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";
import { dateAndTime, engineWords } from "@/lib/format";
import type { Criterion, EvaluationReport } from "@/lib/types";
import { Figure } from "@/components/trace";
import { Button, Card, Empty, ErrorNote, LinkButton, Loading, PageBand, SectionHead } from "@/components/ui";

const SAMPLE = { clean_count: 120, duplicate_count: 40, bank_change_count: 20, retry_count: 50 };

/** Plain words for the measured things, as headings. */
const TITLES: Record<string, string> = {
  "header fields": "Header fields read right",
  "line items": "Line figures read right",
  "repeats caught": "Repeats caught",
  "bank changes blocked": "Bank changes blocked",
  "posted untouched": "Clean invoices posted untouched",
  "duplicate bills after a crash": "Bills paid twice after a crash",
};

/* A pipeline of nodes for the running state: documents in, verdicts out. */
const RUN_NODES = [
  ...Array.from({ length: 8 }, (_, index) => ({ id: `in-${index}`, x: 0.08, y: 0.1 + index * 0.115, r: 2, tone: "light" as const })),
  { id: "inv", x: 0.36, y: 0.3, r: 4, tone: "accent" as const, lit: true, label: "Read" },
  { id: "ord", x: 0.52, y: 0.55, r: 4, tone: "accent" as const, lit: true, label: "Matched" },
  { id: "led", x: 0.7, y: 0.35, r: 4, tone: "accent" as const, lit: true, label: "Posted or stopped" },
  { id: "score", x: 0.9, y: 0.5, r: 5, tone: "pass" as const, ring: true, lit: true, label: "Scored" },
];
const RUN_LINKS = [
  ...Array.from({ length: 8 }, (_, index) => ({ from: `in-${index}`, to: "inv", tone: "light" as const })),
  { from: "inv", to: "ord", tone: "accent" as const, lit: true },
  { from: "ord", to: "led", tone: "accent" as const, lit: true },
  { from: "led", to: "score", tone: "pass" as const, lit: true },
];
const RUN_PATHS = Array.from({ length: 8 }, (_, index) => [`in-${index}`, "inv", "ord", "led", "score"]);

export default function Evidence() {
  const user = readUser();
  const mayRun = ["controller", "finance_director", "administrator"].includes(user?.role ?? "");
  const published = useLoad<{ criteria: Criterion[] }>("/api/evaluation/criteria");
  const last = useLoad<EvaluationReport | null>("/api/evaluation/last");
  const [fresh, setFresh] = useState<EvaluationReport | null>(null);
  const { busy, error, run } = useAction();
  const [elapsed, setElapsed] = useState(0);
  const started = useRef(0);

  useEffect(() => {
    if (!busy) return;
    started.current = performance.now();
    const tick = window.setInterval(() => setElapsed((performance.now() - started.current) / 1000), 100);
    return () => window.clearInterval(tick);
  }, [busy]);

  const report = fresh ?? last.data ?? null;
  const held = report ? report.criteria.filter((row) => row.passed).length : 0;
  const total = report?.criteria.length ?? published.data?.criteria.length ?? 6;

  const measure = () =>
    void run("run", () => api.post<EvaluationReport>("/api/evaluation/run", SAMPLE)).then((result) => {
      if (result) {
        setFresh(result);
        last.reload();
      }
    });

  return (
    <div>
      <PageBand
        eyebrow={["Evidence", "measured, not claimed", report ? `read by ${engineWords(report.engine)}` : "not measured yet"]}
        title="Six bars,"
        accent="measured on the real pipeline."
        lede="Each measurement puts documents with a known right answer through the same code you have been watching, and reports what it got, including what it got wrong. It runs inside a savepoint and is rolled back, so it leaves nothing behind."
        actions={
          <>
            {mayRun ? (
              <Button tone="primary" size="large" busy={Boolean(busy)} onClick={measure} arrow>
                {busy ? `Measuring… ${elapsed.toFixed(1)} s` : "Measure it now"}
              </Button>
            ) : (
              <StatusChip tone="warn" surface="dark" size="large">
                A controller can run it
              </StatusChip>
            )}
            <LinkButton href="/walkthrough" tone="ink" size="large">
              Walk through it
            </LinkButton>
          </>
        }
        aside={
          <div className="lf-verdict">
            <span className="ds-mono-label">The verdict</span>
            <span className="lf-verdict-number ds-display" data-tone={report ? (report.passed ? "pass" : "fail") : undefined}>
              {report ? (
                <>
                  <CountUp to={held} duration={900} />
                  <span className="lf-verdict-of"> of {total}</span>
                </>
              ) : (
                <span className="lf-verdict-of">Not measured yet</span>
              )}
            </span>
            <span className="lf-verdict-words">{report ? (report.passed ? "bars held" : "bars held: one or more did not") : `${total} bars, each measured on the real pipeline`}</span>
            {report && (
              <>
                <StatusChip tone={report.passed ? "pass" : "fail"} surface="dark" size="large">
                  {report.passed ? "Every bar held" : "A bar did not hold"}
                </StatusChip>
                <p className="ds-mono lf-verdict-meta">
                  {dateAndTime(report.started_at)} · {report.seconds} s · {report.sample_size} documents · {engineWords(report.engine)}
                </p>
              </>
            )}
          </div>
        }
      />

      <div className="ds-work">
        {error && (
          <div style={{ marginBottom: 20 }}>
            <ErrorNote error={error} />
          </div>
        )}

        {busy && (
          <Reveal>
            <div className="lf-running">
              <div className="lf-running-canvas">
                <Constellation nodes={RUN_NODES} links={RUN_LINKS} ambient={18} traffic={{ paths: RUN_PATHS, every: 260 }} label="Documents going through the pipeline" />
              </div>
              <div className="lf-running-words">
                <StatusChip tone="accent" surface="dark" pulse>
                  Running
                </StatusChip>
                <p>
                  Putting {SAMPLE.clean_count} clean invoices, {SAMPLE.duplicate_count} planted repeats and {SAMPLE.bank_change_count} bank changes
                  through the real pipeline, and dropping the connection {SAMPLE.retry_count} times. About fifteen seconds.
                </p>
                <span className="ds-mono lf-running-clock">{elapsed.toFixed(1)} s</span>
              </div>
            </div>
          </Reveal>
        )}

        {report && (
          <Reveal>
            <p className="lf-statement">{report.statement}</p>
          </Reveal>
        )}

        <SectionHead label={report ? "Measured · pass or fail" : "The bars · not measured yet"} title="What it has to get right" />
        {last.loading && !report && !published.data ? (
          <Loading what="Loading" />
        ) : (
          <div className="lf-criteria">
            {(report?.criteria ?? published.data?.criteria ?? []).map((row, index) => (
              <Measured key={row.name} row={row} measured={Boolean(report)} index={index} />
            ))}
          </div>
        )}

        {report && (
          <section style={{ marginTop: 56 }} aria-labelledby="misses-heading">
            <SectionHead label="Shown on purpose" title="What it got wrong" id="misses-heading" />
            <Card
              style={{ marginTop: 22 }}
              eyebrow={`${shortfalls(report).length} short of perfect · ${report.misses?.length ?? 0} listed by the run`}
              title={shortfalls(report).length ? "Where it fell short, counted" : "Nothing fell short in this run"}
            >
              {shortfalls(report).length > 0 && (
                <NodeChain
                  stagger={70}
                  live={false}
                  items={shortfalls(report).map((row, index) => ({
                    key: row.name,
                    tone: row.passed ? "warn" : "fail",
                    marker: String(index + 1).padStart(2, "0"),
                    content: (
                      <div className="lf-shortfall">
                        <b>{TITLES[row.name] ?? row.name}</b>
                        <span className="ds-mono">
                          {row.missed} of {row.total} {row.passed ? "missed, still above the bar" : "missed, below the bar"}
                        </span>
                        <span className="lf-cell-sub">{row.measured}</span>
                      </div>
                    ),
                  }))}
                />
              )}
              {report.misses?.length ? (
                <div style={{ marginTop: 18 }}>
                  <p className="ds-mono-label" style={{ margin: "0 0 10px" }}>
                    The run&apos;s own list
                  </p>
                  <NodeChain
                    stagger={50}
                    live={false}
                    items={report.misses.slice(0, 40).map((miss, index) => ({
                      key: `${index}`,
                      tone: "fail",
                      marker: String(index + 1).padStart(2, "0"),
                      content: <p className="lf-miss ds-mono">{miss}</p>,
                    }))}
                  />
                </div>
              ) : (
                <p className="lf-cell-sub" style={{ marginTop: shortfalls(report).length ? 16 : 0 }}>
                  The run listed no individual misses. Every shortfall above is counted from its own measurement.
                </p>
              )}
            </Card>
          </section>
        )}
      </div>
    </div>
  );
}

/** Each measurement that was not perfect, with how far short it was. */
function shortfalls(report: EvaluationReport) {
  return report.criteria
    .map((row) => {
      const match = /([\d,]+) of ([\d,]+)/.exec(row.measured);
      const got = match ? Number(match[1].replace(/,/g, "")) : NaN;
      const total = match ? Number(match[2].replace(/,/g, "")) : NaN;
      if (row.unit === "%") return { ...row, missed: total - got, total };
      return { ...row, missed: row.value, total: Number.isFinite(total) ? total : row.value };
    })
    .filter((row) => Number.isFinite(row.missed) && row.missed > 0);
}

function Measured({ row, measured, index }: { row: Criterion; measured: boolean; index: number }) {
  const percent = row.unit === "%";
  const tone = !measured ? "info" : row.passed ? "pass" : "fail";
  const title = TITLES[row.name] ?? row.name;
  const shown = percent ? `${row.value}%` : String(row.value);
  return (
    <Reveal index={index} className="lf-criterion ds-lift" data-tone={tone}>
      <div className="lf-criterion-head">
        <span className="ds-mono-label">{title}</span>
        {measured ? (
          <StatusChip tone={row.passed ? "pass" : "fail"} pulse={!row.passed}>
            {row.passed ? "Pass" : "Below the bar"}
          </StatusChip>
        ) : (
          <StatusChip tone="neutral">Not measured</StatusChip>
        )}
      </div>
      <p className="lf-criterion-question">{row.question}</p>
      <div className="lf-criterion-figure">
        <span className="lf-criterion-value" data-tone={tone}>
          {measured ? (
            <Figure
              value={shown}
              count={row.value}
              decimals={percent && row.value % 1 ? 1 : 0}
              suffix={percent ? "%" : ""}
              heading={title}
              explain={{
                formula: row.question,
                result: shown,
                inputs: [
                  { label: "Measured", value: row.measured, source: "The last evaluation run", sourceKind: "Evaluation" },
                  { label: "The bar", value: `${percent ? "at least" : "at most"} ${row.bar}${percent ? "%" : ""}`, source: "The acceptance criteria", sourceKind: "Company policy" },
                  { label: "Verdict", value: row.passed ? "pass" : "below the bar", source: "Compared by code", sourceKind: "Evaluation" },
                ],
              }}
            />
          ) : (
            <span className="lf-criterion-pending">Not yet</span>
          )}
        </span>
        {!percent && <span className="lf-criterion-bar ds-mono">bar = {row.bar}</span>}
      </div>
      {percent ? (
        <Meter
          value={measured ? row.value / 100 : 0}
          mark={row.bar / 100}
          markLabel={`bar ${row.bar}%`}
          tone={tone === "info" ? "info" : tone}
          delay={index * 90}
          label={`${shown} against a bar of ${row.bar}%`}
        />
      ) : (
        <div className="lf-zero" data-tone={tone}>
          <span className="lf-zero-dot" aria-hidden />
          <span>{measured ? (row.value === 0 ? "Not one second bill" : `${row.value} second bills`) : "Measured by dropping the connection on purpose"}</span>
        </div>
      )}
      {measured && <p className="lf-criterion-measured ds-mono">{row.measured}</p>}
    </Reveal>
  );
}

export const dynamic = "force-dynamic";
