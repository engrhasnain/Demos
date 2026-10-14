"use client";

/**
 * Every number on screen opens.
 *
 * A figure is a button. Pressing it slides out the trace: the reviewed
 * query that produced it, exactly as it ran (permission filter and all),
 * the inputs it ran with and where each came from, the moment it was read,
 * and how the figure follows from the rows that came back.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { CountUp } from "@/design/CountUp";
import { StatusChip } from "@/design/StatusChip";
import { TraceSheet, type TraceInputView, type TraceStepView } from "@/design/TraceSheet";
import type { Evidence, Row } from "@/lib/types";
import {
  capabilityWords,
  cell,
  clock,
  columnWords,
  DOMAIN_BY_ID,
  domainsOf,
  filterShort,
  filterWords,
  grouped,
  howOld,
} from "@/lib/words";

export type TraceContent = {
  heading: string;
  figure: string;
  steps: TraceStepView[];
  intro?: ReactNode;
  extra?: ReactNode;
  origin?: string;
  originNote?: string;
};

type Opened = TraceContent & { key: string };

type TraceContextValue = {
  open: (opened: Opened) => void;
  close: () => void;
  openKey: string | null;
};

const TraceContext = createContext<TraceContextValue | null>(null);

export function TraceProvider({ children }: { children: ReactNode }) {
  const [opened, setOpened] = useState<Opened | null>(null);
  const [closing, setClosing] = useState(false);

  const open = useCallback((next: Opened) => {
    setClosing(false);
    setOpened(next);
  }, []);
  const close = useCallback(() => setClosing(true), []);
  const exited = useCallback(() => {
    setOpened(null);
    setClosing(false);
  }, []);

  useEffect(() => {
    if (!opened) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [opened, close]);

  const value = useMemo(
    () => ({ open, close, openKey: opened && !closing ? opened.key : null }),
    [open, close, opened, closing],
  );

  return (
    <TraceContext.Provider value={value}>
      {children}
      {opened && (
        <TraceSheet
          closing={closing}
          onClose={close}
          onExited={exited}
          eyebrow="Where this number came from"
          heading={opened.heading}
          figure={opened.figure}
          steps={opened.steps}
          foot={
            <>
              <StatusChip tone="accent">{opened.origin ?? "From the database"}</StatusChip>
              <span style={{ fontSize: 12, color: "var(--ds-text-3)" }}>
                {opened.originNote ?? "Computed by the database from a reviewed query. The reasoning engine never writes a number."}
              </span>
            </>
          }
        >
          {opened.intro}
          {opened.extra && <div style={{ marginBottom: 22 }}>{opened.extra}</div>}
        </TraceSheet>
      )}
    </TraceContext.Provider>
  );
}

export function useTrace(): TraceContextValue {
  const value = useContext(TraceContext);
  if (!value) throw new Error("useTrace has to be used inside the trace provider");
  return value;
}

/** A number that opens its trace. */
export function Figure({
  value,
  content,
  count,
  decimals = 0,
  className = "",
  align = "start",
}: {
  value: string;
  content: TraceContent | (() => TraceContent);
  /** Count up to this when it scrolls into view; `value` is the last frame. */
  count?: number;
  decimals?: number;
  className?: string;
  align?: "start" | "end";
}) {
  const { open, openKey } = useTrace();
  const key = useId();
  const shown =
    count !== undefined && Number.isFinite(count) ? (
      <CountUp to={count} final={value} decimals={decimals} align={align} />
    ) : (
      value
    );
  return (
    <button
      type="button"
      className={`ds-figure ${className}`}
      data-open={openKey === key ? "" : undefined}
      onClick={() => {
        const built = typeof content === "function" ? content() : content;
        open({ ...built, key });
      }}
      aria-label={`${value}. Open where this number came from.`}
    >
      {shown}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* A counted figure: the rule in words and what it was counted from     */
/* ------------------------------------------------------------------ */
export function counted(
  heading: string,
  figure: string,
  formula: string,
  inputs: TraceInputView[],
  origin = "Counted by the server",
  originNote = "Read from live records when the page loaded, not estimated.",
): TraceContent {
  return {
    heading,
    figure,
    origin,
    originNote,
    steps: [{ label: "How it is counted", formula, result: figure, inputs }],
  };
}

/* ------------------------------------------------------------------ */
/* A figure in an answer: traced to the query that produced it          */
/* ------------------------------------------------------------------ */
function rowLabel(row: Row, columns: string[]): string {
  for (const column of columns) {
    const value = row[column];
    if (typeof value === "string" && value && !/^\d{4}-\d{2}-\d{2}/.test(value)) return value;
  }
  const first = row[columns[0]];
  return first === null || first === undefined ? "row" : String(first);
}

function numericColumns(evidence: Evidence): string[] {
  return evidence.columns.filter((column) => evidence.rows.some((row) => typeof row[column] === "number"));
}

function near(a: number, b: number): boolean {
  return Math.abs(a - b) < 0.006;
}

/** How a number in a sentence follows from the rows. Deterministic, checked against the rows. */
export function explainFigure(figure: string, evidence: Evidence): { formula: string; inputs: TraceInputView[] } {
  const rows = evidence.rows;
  const columns = evidence.columns;
  const words = capabilityWords(evidence.capability);
  const source = `${words}, read at ${clock(evidence.read_at)}`;
  const take = rows.slice(0, 6);
  const isDate = /^\d{4}-\d{2}-\d{2}$/.test(figure);

  if (isDate) {
    for (const row of rows) {
      for (const column of columns) {
        if (typeof row[column] === "string" && String(row[column]).startsWith(figure)) {
          return {
            formula: `${columnWords(column)} on the row for ${rowLabel(row, columns)}`,
            inputs: columns.map((c) => ({ label: columnWords(c), value: cell(row[c]), source, sourceKind: "Row" })),
          };
        }
      }
    }
  }

  const n = Number(figure.replace(/,/g, ""));
  if (Number.isFinite(n)) {
    if (n === evidence.row_count) {
      return {
        formula: `count of rows the query returned, after the permission filter = ${evidence.row_count}`,
        inputs: take.map((row) => ({ label: rowLabel(row, columns), value: "1 row", source, sourceKind: "Row" })),
      };
    }
    for (const column of numericColumns(evidence)) {
      const values = rows.map((row) => (typeof row[column] === "number" ? (row[column] as number) : 0));
      const sum = values.reduce((total, value) => total + value, 0);
      if (rows.length > 1 && (near(Math.round(sum * 100) / 100, n) || (Number.isInteger(n) && Math.round(sum) === n && !figure.includes(".")))) {
        return {
          formula: `sum of ${columnWords(column)} over ${rows.length} rows = ${grouped(sum, figure.includes(".") ? 2 : 0)}`,
          inputs: take.map((row) => ({ label: rowLabel(row, columns), value: cell(row[column]), source, sourceKind: "Row" })),
        };
      }
    }
    for (const column of numericColumns(evidence)) {
      for (const row of rows) {
        const value = row[column];
        if (typeof value !== "number") continue;
        const decimals = figure.includes(".") ? figure.split(".")[1].length : 0;
        const matches = decimals ? near(Number(value.toFixed(decimals)), n) : Math.trunc(value) === n || near(value, n);
        if (matches) {
          return {
            formula: `${columnWords(column)} on the row for ${rowLabel(row, columns)}${decimals ? `, to ${decimals} decimal place${decimals > 1 ? "s" : ""}` : value !== n ? ", whole days" : ""}`,
            inputs: columns.map((c) => ({ label: columnWords(c), value: cell(row[c]), source, sourceKind: "Row" })),
          };
        }
      }
    }
    const cover = columns.includes("weeks_of_cover");
    if (cover) {
      const thin = rows.filter((row) => typeof row.weeks_of_cover === "number" && (row.weeks_of_cover as number) < 4);
      if (thin.length === n) {
        return {
          formula: `count of rows where weeks of cover is under 4 = ${thin.length}`,
          inputs: thin.slice(0, 6).map((row) => ({ label: rowLabel(row, columns), value: `${cell(row.weeks_of_cover)} weeks`, source, sourceKind: "Row" })),
        };
      }
    }
    const overdue = columns.includes("days_overdue");
    if (overdue) {
      const late = rows.filter((row) => typeof row.days_overdue === "number" && (row.days_overdue as number) > 0);
      if (late.length === n) {
        return {
          formula: `count of rows past their due date = ${late.length}`,
          inputs: late.slice(0, 6).map((row) => ({ label: rowLabel(row, columns), value: `${Math.trunc(row.days_overdue as number)} days`, source, sourceKind: "Row" })),
        };
      }
    }
  }
  return {
    formula: "read from the rows this query returned",
    inputs: take.map((row) => ({ label: rowLabel(row, columns), value: cell(row[columns[1] ?? columns[0]]), source, sourceKind: "Row" })),
  };
}

function parameterInputs(evidence: Evidence, index: number): TraceInputView[] {
  return Object.entries(evidence.parameters).map(([name, value]) => {
    const shown = typeof value === "string" ? value.replace(/^%|%$/g, "") : cell(value);
    const fromStep = name === "customer" || name === "supplier";
    return {
      label: name === "text" ? "name searched for" : name === "weeks" ? "weeks of cover" : name,
      value: fromStep ? `found by step ${index}` : shown,
      source: fromStep
        ? "Taken from the lookup before it, which ran under this person's own filter, never from what was typed"
        : "From the question, checked against the kind the query declared",
      sourceKind: fromStep ? "Earlier step" : "Question",
    };
  });
}

export function RowsTable({ evidence, limit = 40 }: { evidence: Evidence; limit?: number }) {
  if (!evidence.rows.length) {
    return <p style={{ margin: 0, fontSize: 13, color: "var(--ds-text-3)" }}>No rows came back.</p>;
  }
  return (
    <div className="ds-table-wrap oa-rows">
      <table className="ds-table">
        <thead>
          <tr>
            {evidence.columns.map((column) => (
              <th key={column}>{columnWords(column)}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {evidence.rows.slice(0, limit).map((row, index) => (
            <tr key={index}>
              {evidence.columns.map((column) => (
                <td key={column} data-align={typeof row[column] === "number" ? "right" : undefined}>
                  {cell(row[column])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      {evidence.rows.length > limit && (
        <p className="ds-mono" style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--ds-text-3)" }}>
          First {limit} of {evidence.rows.length} rows shown.
        </p>
      )}
    </div>
  );
}

export function evidenceTrace({
  figure,
  evidence,
  index,
  sentence,
  reading,
  engine,
}: {
  figure: string;
  evidence: Evidence;
  /** 1-based step number in the plan. */
  index: number;
  sentence?: string;
  reading?: string;
  engine?: string;
}): TraceContent {
  const how = explainFigure(figure, evidence);
  const domains = domainsOf(evidence.capability).map((id) => DOMAIN_BY_ID[id].label).join(", ");
  return {
    heading: sentence ? `“${sentence}”` : capabilityWords(evidence.capability),
    figure,
    origin: "From the database",
    originNote: `Computed by the database from a reviewed query. The ${engine === "external" ? "external model" : "built-in engine"} wrote only the words around it.`,
    intro: (
      <div className="oa-trace-intro ds-reveal" data-shown="">
        {reading && (
          <p>
            <span className="ds-mono-label">Question read as</span>
            {reading}
          </p>
        )}
        <p>
          <span className="ds-mono-label">System</span>
          {domains}
        </p>
        <p>
          <span className="ds-mono-label">Freshness</span>
          Read at {clock(evidence.read_at)}
          {typeof evidence.age_seconds === "number" ? `, ${howOld(evidence.age_seconds)}` : ""}
          {evidence.stale ? " — older than five minutes" : ""}
        </p>
      </div>
    ),
    steps: [
      {
        label: `Step ${index} · reviewed query: ${capabilityWords(evidence.capability)}`,
        formula: evidence.sql,
        result: `${grouped(evidence.row_count)} ${evidence.row_count === 1 ? "row" : "rows"}`,
        unit: `in ${evidence.duration_ms} ms`,
        note: `${evidence.asks} Written and reviewed by a person; the model only picked its name. Permission filter: ${filterWords(evidence.filter_applied)}.`,
        inputs: [
          ...parameterInputs(evidence, index - 1),
          {
            label: "permission filter",
            value: filterShort(evidence.filter_applied),
            source: "Grants for the signed-in person, read from the database at sign-in, never from the question",
            sourceKind: "Grants",
          },
        ],
      },
      {
        label: "How the number follows from the rows",
        formula: how.formula,
        result: figure,
        inputs: how.inputs,
      },
    ],
    extra: (
      <details className="oa-details">
        <summary>All {grouped(evidence.row_count)} rows this query returned</summary>
        <RowsTable evidence={evidence} />
      </details>
    ),
  };
}
