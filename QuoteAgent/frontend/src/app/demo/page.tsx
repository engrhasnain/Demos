"use client";

import { useState } from "react";

import { Button, Card, LinkButton, Stamp } from "@/design/Surface";
import { CountUp } from "@/design/CountUp";
import { Meter } from "@/design/Meter";
import { NodeChain } from "@/design/NodeChain";
import { StatusChip } from "@/design/StatusChip";
import { api } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";
import { money, words } from "@/lib/format";
import type { CaseSummary, DemoStep } from "@/lib/types";
import { Figure } from "@/components/trace";
import { ErrorNote, Loading, PageBand } from "@/components/ui";

type Script = { steps: DemoStep[]; current_case: CaseSummary | null; note: string };

type StepResult = {
  step?: DemoStep;
  case_id?: number;
  summary?: string;
  [key: string]: unknown;
};

/** Where to look after each step, so the demonstration script flows. */
const LOOK: Record<number, { tab: string; label: string }> = {
  1: { tab: "lines", label: "See every line and why it matched" },
  2: { tab: "emails", label: "See the one consolidated email" },
  3: { tab: "lines", label: "See the lines waiting for the supplier" },
  4: { tab: "questions", label: "See the answers and the question asked again" },
  5: { tab: "lines", label: "See the supplier's lines priced" },
  6: { tab: "versions", label: "See the totals before and after" },
  7: { tab: "lines", label: "See the duty change on each line" },
  8: { tab: "approvals", label: "See what went to the sales manager" },
  9: { tab: "versions", label: "See the change log for version 2" },
  10: { tab: "timeline", label: "See the whole timeline" },
};

const ROLE_WORDS: Record<string, string> = {
  sales_engineer: "a sales engineer",
  sales_manager: "the sales manager",
  director: "a director",
  pricing_owner: "the pricing owner",
  administrator: "the administrator",
};

export default function DemoPage() {
  const script = useLoad<Script>("/api/demo/script");
  const { busy, error, run } = useAction();
  const [results, setResults] = useState<Record<number, StepResult>>({});
  const [caseId, setCaseId] = useState<number | null>(null);
  const [showRaw, setShowRaw] = useState<number | null>(null);
  const [current, setCurrent] = useState<number | null>(null);

  const runStep = (number: number) =>
    void run(`step-${number}`, async () => {
      setCurrent(number);
      const result: StepResult = await api.post<StepResult>(`/api/demo/step/${number}`, {
        case_id: number === 1 ? null : caseId,
      });
      if (typeof result.case_id === "number") setCaseId(result.case_id);
      setResults((previous) => ({ ...previous, [number]: result }));
      setCurrent(null);
      return result;
    });

  const runAll = () =>
    void run("all", async () => {
      let currentCase: number | null = null;
      for (let stepNumber = 1; stepNumber <= 10; stepNumber += 1) {
        setCurrent(stepNumber);
        const result: StepResult = await api.post<StepResult>(`/api/demo/step/${stepNumber}`, {
          case_id: stepNumber === 1 ? null : currentCase,
        });
        if (typeof result.case_id === "number") {
          currentCase = result.case_id;
          setCaseId(result.case_id);
        }
        setResults((previous) => ({ ...previous, [stepNumber]: result }));
      }
      setCurrent(null);
      return null;
    });

  const reset = () => {
    setResults({});
    setCaseId(null);
  };

  const done = Object.keys(results).length;
  const steps = script.data?.steps ?? [];

  return (
    <div>
      <PageBand
        eyebrow={["Walkthrough", "ten steps, one real request"]}
        title="The whole job,"
        accent="one step at a time."
        lede="Each step performs the real action through the same routes the screens use: a forty line request, questions, a supplier, a reply in Traditional Chinese, new trade terms, a new duty table, a discount, a revision, and the approval that lets it go."
        actions={
          <>
            <Button tone="primary" size="large" busy={busy === "all"} onClick={runAll} arrow>
              Run every step
            </Button>
            {done > 0 && (
              <Button tone="ink" size="large" onClick={reset}>
                Start again
              </Button>
            )}
            {caseId && (
              <LinkButton href={`/requests/${caseId}`} tone="ink" size="large">
                Open the request
              </LinkButton>
            )}
          </>
        }
        aside={
          <div className="qa-verdict">
            <span className="ds-mono-label">Steps done</span>
            <p className="ds-display" style={{ margin: "12px 0 0", fontSize: 64, lineHeight: 1 }}>
              <span style={{ color: "var(--ds-accent)" }}>
                <CountUp to={done} duration={600} />
              </span>
              <span style={{ fontSize: 30, color: "var(--ds-ink-faint)" }}> of {steps.length || 10}</span>
            </p>
            <div style={{ marginTop: 16 }}>
              <Meter value={done / Math.max(1, steps.length || 10)} size="large" label={`${done} of ten steps done`} />
            </div>
            <p style={{ margin: "12px 0 0", fontSize: 13, color: "var(--ds-ink-muted)" }}>
              {current ? `Running step ${current}…` : done === 10 ? "Every step ran. Open the request to see the result." : "Run them one at a time, or all ten."}
            </p>
            <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--ds-ink-faint)" }}>
              Step seven needs the pricing owner and step ten the sales manager; the administrator can run all ten.
            </p>
          </div>
        }
      />

      <div className="ds-work">
        {error && (
          <div style={{ marginBottom: 16 }}>
            <ErrorNote error={error} />
          </div>
        )}
        {script.loading && <Loading what="Loading the walkthrough" />}
        {script.error && <ErrorNote error={script.error} />}

        {steps.length > 0 && (
          <NodeChain
            stagger={80}
            fill={done / steps.length}
            items={steps.map((step) => {
              const result = results[step.number];
              const running = current === step.number;
              return {
                key: String(step.number),
                tone: result ? "accent" : running ? "warn" : undefined,
                state: result ? "done" : running ? "active" : "waiting",
                marker: result ? "✓" : String(step.number).padStart(2, "0"),
                content: (
                  <Card className="qa-step" tone={running ? "accent" : undefined}>
                    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", gap: 16 }}>
                      <div style={{ minWidth: 0, flex: "1 1 320px" }}>
                        <p className="ds-mono-label" style={{ margin: 0 }}>
                          Step {String(step.number).padStart(2, "0")}
                        </p>
                        <h2 className="ds-card-title" style={{ fontSize: 18, marginTop: 6, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
                          {step.title}
                          {step.needs_role !== "sales_engineer" && (
                            <StatusChip tone="warn" size="small">
                              Needs {ROLE_WORDS[step.needs_role] ?? words(step.needs_role)}
                            </StatusChip>
                          )}
                          {running && (
                            <StatusChip tone="accent" size="small" pulse>
                              Running
                            </StatusChip>
                          )}
                        </h2>
                        <p style={{ margin: "6px 0 0", fontSize: 13.5, lineHeight: 1.55, color: "var(--ds-text-2)" }}>
                          {step.what_you_see}
                        </p>
                      </div>
                      <Button size="small" tone={result ? "secondary" : "primary"} busy={running} onClick={() => runStep(step.number)}>
                        {result ? "Run again" : "Run"}
                      </Button>
                    </div>

                    {result && (
                      <div className="qa-step-result">
                        <p style={{ margin: 0, fontSize: 14, fontWeight: 600, lineHeight: 1.55 }}>{result.summary ?? "Done."}</p>
                        <StepHighlights result={result} />
                        {caseId && LOOK[step.number] && (
                          <div style={{ marginTop: 12 }}>
                            <LinkButton href={`/requests/${caseId}?tab=${LOOK[step.number].tab}`} tone="secondary" size="small" arrow>
                              {LOOK[step.number].label}
                            </LinkButton>
                          </div>
                        )}
                        <button
                          type="button"
                          onClick={() => setShowRaw(showRaw === step.number ? null : step.number)}
                          className="ds-btn"
                          data-tone="ghost"
                          data-size="small"
                          style={{ marginTop: 8, paddingLeft: 0 }}
                        >
                          {showRaw === step.number ? "Hide what the server returned" : "Show what the server returned"}
                        </button>
                        {showRaw === step.number && <pre className="qa-email-body qa-line-detail">{JSON.stringify(result, null, 2)}</pre>}
                      </div>
                    )}
                  </Card>
                ),
              };
            })}
          />
        )}
      </div>
    </div>
  );
}

/** A few figures pulled out of whatever the step returned. */
function StepHighlights({ result }: { result: StepResult }) {
  const chips: [string, string, boolean?][] = [];

  const counts = result.line_counts as Record<string, number> | undefined;
  if (counts) {
    Object.entries(counts).forEach(([key, value]) => {
      if (value) chips.push([key === "total" ? "lines" : words(key).toLowerCase(), String(value)]);
    });
  }
  if (typeof result.duty_before === "string" && typeof result.duty_after === "string") {
    chips.push(["duty before", money(result.duty_before), true]);
    chips.push(["duty after", money(result.duty_after), true]);
  }
  if (typeof result.total_before === "string" && typeof result.total_after === "string") {
    chips.push(["total before", money(result.total_before), true]);
    chips.push(["total after", money(result.total_after), true]);
  }
  const changeSummary = result.change_summary as Record<string, number> | undefined;
  if (changeSummary) {
    (["added", "removed", "quantity_changed", "unchanged"] as const).forEach((key) => {
      if (changeSummary[key]) chips.push([key.replace(/_/g, " "), String(changeSummary[key])]);
    });
  }
  const elapsed = result.elapsed as Record<string, string | number> | undefined;
  if (elapsed) {
    chips.push(["steps", String(elapsed.steps ?? "")]);
    chips.push(["agent working time", `${elapsed.agent_working_seconds ?? 0} s`]);
    chips.push(["reasoning cost", `$${elapsed.model_cost_usd ?? 0}`]);
  }

  if (!chips.length) return null;
  return (
    <p style={{ margin: "10px 0 0", display: "flex", flexWrap: "wrap", gap: 6 }}>
      {chips.map(([label, value, isMoney], index) => (
        <Stamp key={`${label}-${index}`} tone="light">
          {label}:{" "}
          {isMoney ? (
            <Figure
              value={value}
              heading={`${label[0].toUpperCase()}${label.slice(1)}`}
              explain={{
                formula:
                  "As the pricing engine worked it out for this step and the server returned it. Open the request to see every line's build-up.",
                result: value,
                inputs: [{ label, value, source: "The response to this walkthrough step", sourceKind: "Server" }],
              }}
            />
          ) : (
            value
          )}
        </Stamp>
      ))}
    </p>
  );
}

export const dynamic = "force-dynamic";
