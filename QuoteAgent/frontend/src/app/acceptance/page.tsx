"use client";

import { useEffect, useState, type CSSProperties } from "react";

import { Banner, Button, Card, Stamp } from "@/design/Surface";
import { CountUp } from "@/design/CountUp";
import { Meter } from "@/design/Meter";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { api } from "@/lib/api";
import { useAction, useLoad, usePoll } from "@/lib/hooks";
import { dateAndTime } from "@/lib/format";
import type { AcceptanceCriterion } from "@/lib/types";
import { Figure } from "@/components/trace";
import { ErrorNote, Loading, PageBand } from "@/components/ui";

type PassBar = { key: string; name: string; bar: string; how: string };
type Run = {
  id: number;
  started_at: string;
  finished_at: string | null;
  engine: string;
  sample_size: number;
  passed: boolean;
  criteria: AcceptanceCriterion[];
  notes: string;
};
type Runs = { runs: Run[]; pass_bars: PassBar[] };
type Progress = {
  running: boolean;
  stage: string;
  done: number;
  total: number;
  percent: number;
  error: string;
  result: {
    id?: number;
    passed: boolean;
    seconds: number;
    sample_size: number;
    requests: number;
    engine: string;
    statement: string;
    started_at?: string;
    criteria: AcceptanceCriterion[];
    mistakes: Record<string, string>[];
  } | null;
};

const DETAIL_WORDS: Record<string, string> = {
  correct: "Correct at the first attempt",
  total: "Clear lines in the test set",
  wrongly_flagged: "Clear lines wrongly flagged",
  unclear_flagged: "Unclear lines flagged",
  unclear_total: "Unclear lines in the test set",
  clear_wrongly_flagged: "Clear lines wrongly flagged",
  clear_total: "Clear lines in the test set",
  checked: "Priced quotes checked",
  changes_expected: "Changes made between versions",
  changes_detected: "Changes found",
  median_seconds: "Median working time, seconds",
  slowest_seconds: "Slowest, seconds",
  engine: "Engine",
};

type MeterRow = { label: string; value: number; mark: number; markLabel: string; text: string };

function firstNumber(text: string): number {
  const match = text.match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : 0;
}

function ratio(detail: Record<string, unknown>, top: string, bottom: string): number {
  const a = Number(detail[top] ?? 0);
  const b = Number(detail[bottom] ?? 0);
  return b > 0 ? a / b : 0;
}

/** Turn a measured criterion into bars against its pass mark. */
function metersOf(criterion: AcceptanceCriterion): MeterRow[] {
  const detail = criterion.detail ?? {};
  switch (criterion.key) {
    case "line_matching": {
      const value = ratio(detail, "correct", "total");
      return [{ label: "Correct at the first attempt", value, mark: 0.92, markLabel: "bar 92%", text: `${(value * 100).toFixed(1)}%` }];
    }
    case "ambiguity_handling": {
      const flagged = ratio(detail, "unclear_flagged", "unclear_total");
      const wrong = ratio(detail, "clear_wrongly_flagged", "clear_total");
      return [
        { label: "Unclear lines flagged", value: flagged, mark: 0.95, markLabel: "bar 95%", text: `${(flagged * 100).toFixed(1)}%` },
        {
          label: "Clear lines wrongly flagged (lower is better, scale to 5%)",
          value: wrong / 0.05,
          mark: 0.03 / 0.05,
          markLabel: "at most 3%",
          text: `${(wrong * 100).toFixed(1)}%`,
        },
      ];
    }
    case "pricing_integrity": {
      const checked = Number(detail.checked ?? 0);
      const failures = Array.isArray(detail.failures) ? detail.failures.length : 0;
      const value = checked ? (checked - failures) / checked : 0;
      return [{ label: "Quotes whose every price equals the engine's", value, mark: 1, markLabel: "every one", text: `${checked - failures} of ${checked}` }];
    }
    case "revisions": {
      const value = ratio(detail, "changes_detected", "changes_expected");
      return [{ label: "Changes detected", value, mark: 1, markLabel: "every one", text: `${(value * 100).toFixed(1)}%` }];
    }
    case "speed": {
      const seconds = firstNumber(criterion.measured);
      return [
        {
          label: "Ninetieth percentile against the 15 minutes allowed",
          value: Math.max(0.012, seconds / 900),
          mark: 1,
          markLabel: "15 minutes",
          text: `${seconds} s of 900 s`,
        },
      ];
    }
    default:
      return [];
  }
}

function explainOf(criterion: AcceptanceCriterion, runLabel: string) {
  const detail = criterion.detail ?? {};
  const inputs = Object.entries(detail)
    .filter(([, value]) => typeof value === "number" || typeof value === "string")
    .filter(([key]) => DETAIL_WORDS[key] || key === "how" || key === "note")
    .map(([key, value]) => ({
      label: DETAIL_WORDS[key] ?? (key === "how" ? "How it is checked" : "Note"),
      value: String(value).length > 90 ? `${String(value).slice(0, 88)}…` : String(value),
      source: runLabel,
      sourceKind: "Evaluation run",
    }));
  return {
    formula: `${criterion.name}, measured on ${criterion.sample}. Pass bar: ${criterion.pass_bar}.`,
    result: criterion.measured,
    inputs,
  };
}

export default function AcceptancePage() {
  const runs = useLoad<Runs>("/api/evaluation/runs?limit=5");
  const { busy, error, run } = useAction();
  const [watching, setWatching] = useState(false);
  const progress = usePoll<Progress>("/api/evaluation/progress", watching, 600);
  const [showAll, setShowAll] = useState(false);

  const latest = progress?.result ?? null;
  const previous = runs.data?.runs[0] ?? null;
  const criteria = latest?.criteria ?? previous?.criteria ?? [];
  const runLabel = latest ? `Run just now, ${latest.engine} engine` : previous ? `Run ${previous.id}, ${dateAndTime(previous.started_at)}` : "Evaluation run";

  const start = (requests: number) =>
    void run("run", async () => {
      await api.post("/api/evaluation/run", {
        request_count: requests,
        lines_per_request: 25,
        revision_pairs: 30,
      });
      setWatching(true);
      return null;
    });

  useEffect(() => {
    if (progress && watching && !progress.running && progress.result) {
      setWatching(false);
      runs.reload();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [progress, watching]);

  const measured = criteria.filter((criterion) => criterion.passed !== null);
  const met = measured.filter((criterion) => criterion.passed).length;
  const allMet = measured.length > 0 && met === measured.length;
  const running = Boolean(progress?.running);
  // The run just made carries its full list of misses; an earlier run keeps
  // the examples inside each criterion, so those are shown instead.
  const mistakes: Record<string, string>[] =
    latest?.mistakes ??
    criteria.flatMap((criterion) =>
      Array.isArray(criterion.detail?.examples) ? (criterion.detail.examples as Record<string, string>[]) : [],
    );

  return (
    <div>
      <PageBand
        eyebrow={["Acceptance criteria", "run as code, not read off a slide"]}
        title="Pass or fail, measured."
        accent="Misses shown in full."
        lede="Six bars, run against a labelled test set built from the catalogue. Every figure below came from the latest run, and every line it got wrong is listed. The last bar needs a pilot, so it says not measured."
        actions={
          <>
            <Button tone="primary" size="large" busy={busy === "run" || running} onClick={() => start(60)} arrow>
              Run it now
            </Button>
            <Button tone="ink" size="large" busy={busy === "run" || running} onClick={() => start(200)} title="200 requests, about 5,000 lines">
              Run the full set
            </Button>
          </>
        }
        aside={
          running && progress ? (
            <div className="qa-verdict">
              <span className="ds-mono-label">Running</span>
              <p className="ds-display" style={{ margin: "12px 0 0", fontSize: 64, color: "var(--ds-accent)" }}>
                <CountUp to={Math.round(progress.percent)} duration={500} suffix="%" />
              </p>
              <div style={{ marginTop: 14 }}>
                <Meter value={progress.percent / 100} size="large" label={`${progress.percent} per cent`} />
              </div>
              <p style={{ margin: "12px 0 0", fontWeight: 600 }}>{progress.stage || "Starting"}</p>
              <p className="ds-mono" style={{ margin: "4px 0 0", fontSize: 12, color: "var(--ds-ink-muted)" }}>
                {progress.done.toLocaleString("en-GB")} of {progress.total.toLocaleString("en-GB")}
              </p>
            </div>
          ) : criteria.length ? (
            <div className="qa-verdict">
              <span className="ds-mono-label">Latest run</span>
              <p className="ds-display" style={{ margin: "12px 0 0", fontSize: 64, lineHeight: 1 }}>
                <span style={{ color: allMet ? "var(--ds-pass)" : "var(--ds-fail)" }}>
                  <CountUp to={met} />
                </span>
                <span style={{ color: "var(--ds-ink-faint)", fontSize: 32 }}> of {measured.length}</span>
              </p>
              <p style={{ margin: "6px 0 0", color: "var(--ds-ink-muted)", fontSize: 14 }}>measured bars met</p>
              <div className="qa-verdict-dots" aria-hidden>
                {criteria.map((criterion, index) => (
                  <span
                    key={criterion.key}
                    data-tone={criterion.passed === true ? "pass" : criterion.passed === false ? "fail" : "none"}
                    style={{ "--ds-d": `${300 + index * 120}ms` } as CSSProperties}
                    title={criterion.name}
                  />
                ))}
              </div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 16 }}>
                <StatusChip tone={allMet ? "pass" : "fail"} surface="dark" size="large">
                  {allMet ? "All measured bars met" : "Below a bar"}
                </StatusChip>
                <StatusChip tone="neutral" surface="dark" size="large">
                  {(latest?.engine ?? previous?.engine ?? "built-in") === "built-in" ? "Built-in engine" : `${latest?.engine ?? previous?.engine} engine`}
                </StatusChip>
              </div>
              <p className="ds-mono" style={{ margin: "12px 0 0", fontSize: 11.5, color: "var(--ds-ink-faint)" }}>
                {latest
                  ? `${latest.requests} requests · ${latest.sample_size.toLocaleString("en-GB")} lines · ${latest.seconds} s`
                  : previous
                    ? `${previous.sample_size.toLocaleString("en-GB")} lines · ${dateAndTime(previous.started_at)}`
                    : ""}
              </p>
            </div>
          ) : (
            <div className="qa-verdict">
              <span className="ds-mono-label">No run yet</span>
              <p style={{ margin: "12px 0 0", fontSize: 15, color: "var(--ds-ink-muted)" }}>
                Press &ldquo;Run it now&rdquo;: sixty requests of twenty-five lines, about a minute.
              </p>
            </div>
          )
        }
      />

      <div className="ds-work">
        <div style={{ display: "grid", gap: 12, marginBottom: 20 }}>
          {error && <ErrorNote error={error} />}
          {progress?.error && <ErrorNote error={progress.error} />}
          {latest && (
            <Banner tone={latest.passed ? "pass" : "fail"} title={latest.statement}>
              {latest.requests} requests, {latest.sample_size.toLocaleString("en-GB")} lines, in {latest.seconds} seconds, with the{" "}
              {latest.engine === "built-in" ? "built-in" : latest.engine} engine.
            </Banner>
          )}
        </div>

        {runs.loading && !criteria.length && <Loading what="Loading the last run" />}

        <div style={{ display: "grid", gap: 16 }}>
          {(runs.data?.pass_bars ?? []).map((bar, index) => {
            const result = criteria.find((criterion) => criterion.key === bar.key);
            const tone = result?.passed === true ? "pass" : result?.passed === false ? "fail" : "neutral";
            const meters = result ? metersOf(result) : [];
            return (
              <Reveal key={bar.key} index={index} y={32}>
                <Card className="qa-criterion">
                  <div className="qa-criterion-grid" data-tone={tone}>
                    <div style={{ minWidth: 0 }}>
                      <p className="ds-mono-label" style={{ margin: 0 }}>
                        Bar {String(index + 1).padStart(2, "0")}
                      </p>
                      <h2 className="ds-card-title" style={{ fontSize: 19, marginTop: 6 }}>
                        {bar.name}
                      </h2>
                      <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--ds-text-2)" }}>Pass bar: {bar.bar}</p>
                      <p style={{ margin: "4px 0 0", fontSize: 12.5, color: "var(--ds-text-3)" }}>{bar.how}</p>
                    </div>
                    <div style={{ minWidth: 0 }}>
                      {result ? (
                        <>
                          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
                            <StatusChip tone={tone === "neutral" ? "neutral" : tone} size="large">
                              {result.passed === true ? "Pass" : result.passed === false ? "Below the bar" : "Not measured"}
                            </StatusChip>
                            {result.passed !== null && (
                              <span className="ds-title" style={{ fontSize: 20 }}>
                                <Figure value={result.measured} heading={bar.name} explain={explainOf(result, runLabel)} origin="Measured by the evaluation" />
                              </span>
                            )}
                          </div>
                          {result.passed !== null && (
                            <p className="ds-mono" style={{ margin: "6px 0 0", fontSize: 11.5, color: "var(--ds-text-3)" }}>
                              measured on {result.sample}
                            </p>
                          )}
                          {meters.map((meter, position) => (
                            <div key={meter.label} style={{ marginTop: 26 }}>
                              <Meter
                                value={meter.value}
                                mark={meter.mark}
                                markLabel={meter.markLabel}
                                tone={tone === "fail" ? "fail" : "pass"}
                                delay={position * 200}
                                label={`${meter.label}: ${meter.text}, ${meter.markLabel}`}
                              />
                              <p style={{ margin: "8px 0 0", display: "flex", justifyContent: "space-between", gap: 10, fontSize: 12.5 }}>
                                <span style={{ color: "var(--ds-text-2)" }}>{meter.label}</span>
                                <span className="ds-mono ds-num" style={{ fontWeight: 600 }}>
                                  {meter.text}
                                </span>
                              </p>
                            </div>
                          ))}
                          {result.key === "edits" && (
                            <p className="qa-not-measured">{String(result.detail?.why ?? "")}</p>
                          )}
                        </>
                      ) : (
                        <p style={{ margin: 0, fontSize: 13.5, color: "var(--ds-text-3)" }}>Run it to measure this bar.</p>
                      )}
                    </div>
                  </div>
                </Card>
              </Reveal>
            );
          })}
        </div>

        {mistakes.length > 0 && (
          <div style={{ marginTop: 28 }}>
            <Card
              eyebrow="Misses, in full"
              title={
                <>
                  Every line it got wrong: <CountUp to={mistakes.length} />
                </>
              }
              subtitle="Shown so a reader can judge them, not hidden behind a percentage."
            >
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10 }}>
                {(showAll ? mistakes : mistakes.slice(0, 20)).map((mistake, index) => (
                  <Reveal as="li" key={index} index={index} y={20} from="left" className="qa-miss">
                    <p style={{ margin: 0, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                      <StatusChip tone="fail" size="small">
                        {mistake.kind}
                      </StatusChip>
                      {mistake.style && <Stamp tone="light">{mistake.style.replace(/_/g, " ")}</Stamp>}
                    </p>
                    <p className="ds-mono" style={{ margin: "8px 0 0", fontSize: 13 }}>
                      {mistake.text}
                    </p>
                    <p style={{ margin: "4px 0 0", fontSize: 12.5, color: "var(--ds-text-2)" }}>
                      {mistake.expected && `expected ${mistake.expected}`}
                      {mistake.got && ` · got ${mistake.got}`}
                      {mistake.why_unclear && `unclear because: ${mistake.why_unclear}`}
                      {mistake.reason && ` · ${mistake.reason}`}
                    </p>
                  </Reveal>
                ))}
              </ul>
              {mistakes.length > 20 && (
                <div style={{ marginTop: 14 }}>
                  <Button size="small" onClick={() => setShowAll((value) => !value)}>
                    {showAll ? "Show the first twenty" : `Show all ${mistakes.length}`}
                  </Button>
                </div>
              )}
            </Card>
          </div>
        )}

        {runs.data && runs.data.runs.length > 0 && (
          <div style={{ marginTop: 28 }}>
            <Card eyebrow="History" title="Earlier runs" flush>
              <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {runs.data.runs.map((item, index) => (
                  <Reveal
                    as="li"
                    key={item.id}
                    index={index}
                    y={16}
                    style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 12, padding: "12px 20px", borderTop: index ? "1px solid var(--ds-line)" : undefined, fontSize: 13 }}
                  >
                    <StatusChip tone={item.passed ? "pass" : "fail"}>{item.passed ? "All bars met" : "Below a bar"}</StatusChip>
                    <span className="ds-mono" style={{ color: "var(--ds-text-2)" }}>
                      {dateAndTime(item.started_at)}
                    </span>
                    <span style={{ color: "var(--ds-text-3)" }}>{item.notes}</span>
                    <span style={{ marginLeft: "auto" }}>
                      <Stamp tone="light">{item.engine === "built-in" ? "built-in engine" : `${item.engine} engine`}</Stamp>
                    </span>
                  </Reveal>
                ))}
              </ul>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

export const dynamic = "force-dynamic";
