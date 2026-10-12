"use client";

/**
 * Every number on screen can be opened.
 *
 * A figure is rendered as a button. Pressing it slides out the suite's trace
 * sheet: the figure on ink, a small constellation of the calculation, then
 * each step on a node chain with its formula, its result and, for every
 * input, the record it came from.
 *
 * Three kinds of figure open the same sheet:
 * - a worked figure carries the forecasting engine's own trace;
 * - a line on the plan fetches its trace when it is opened (`load`), because
 *   eighteen thousand traces are not worth sending until somebody asks;
 * - a counted figure (a total on the desk, a measured result) carries
 *   `explain`: the rule in words and the records it was counted from.
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
import { Spinner } from "@/design/Surface";
import { plain } from "@/lib/format";
import type { Trace } from "@/lib/types";

export type Explain = {
  formula: string;
  inputs: TraceInputView[];
  result?: string;
  unit?: string;
  label?: string;
};

type Opened = {
  key: string;
  heading: string;
  shown: string;
  trace: Trace | null;
  load?: () => Promise<Trace | null | undefined>;
  explain?: Explain;
  note?: string;
  extra?: ReactNode;
  origin?: string;
};

type TraceContextValue = {
  open: (opened: Opened) => void;
  close: () => void;
  openKey: string | null;
};

const TraceContext = createContext<TraceContextValue | null>(null);

const SOURCE_WORDS: Record<string, string> = {
  history: "Sales history",
  supplier: "Supplier record",
  policy: "Company policy",
  catalogue: "Part record",
  forecast: "The forecast",
  calendar: "Shutdown calendar",
  cash: "This week's cash",
};

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
        <TracePanel
          key={opened.key + opened.heading}
          opened={opened}
          closing={closing}
          onClose={close}
          onExited={exited}
        />
      )}
    </TraceContext.Provider>
  );
}

export function useTrace(): TraceContextValue {
  const value = useContext(TraceContext);
  if (!value) {
    throw new Error("useTrace has to be used inside the trace provider");
  }
  return value;
}

/* ------------------------------------------------------------------ */
/* The figure button                                                   */
/* ------------------------------------------------------------------ */
export function Figure({
  value,
  heading,
  trace,
  load,
  explain,
  note,
  extra,
  origin,
  className = "",
  count,
  decimals = 0,
  align = "start",
  display,
}: {
  /** The exact text of the figure: the last frame of any count-up. */
  value: string;
  heading: string;
  trace?: Trace | null;
  load?: () => Promise<Trace | null | undefined>;
  explain?: Explain;
  note?: string;
  extra?: ReactNode;
  origin?: string;
  className?: string;
  /** Count up to this number when it scrolls into view. */
  count?: number;
  decimals?: number;
  align?: "start" | "end";
  /** Shown instead of `value` on the page (the panel always shows `value`). */
  display?: ReactNode;
}) {
  const { open, openKey } = useTrace();
  const key = useId();
  const hasDetail = Boolean((trace && trace.steps?.length) || load || explain || note || extra);
  const shown =
    display ??
    (count !== undefined && Number.isFinite(count) ? (
      <CountUp to={count} final={value} decimals={decimals} align={align} />
    ) : (
      value
    ));

  if (!hasDetail) {
    return <span className={`ds-num ${className}`}>{shown}</span>;
  }

  return (
    <button
      type="button"
      className={`ds-figure ${className}`}
      data-open={openKey === key ? "" : undefined}
      onClick={() =>
        open({ key, heading, shown: value, trace: trace ?? null, load, explain, note, extra, origin })
      }
      aria-label={`${heading}: ${value}. Open how it was worked out.`}
    >
      {shown}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* The panel                                                           */
/* ------------------------------------------------------------------ */
function toSteps(trace: Trace | null, opened: Opened): TraceStepView[] {
  if (trace?.steps?.length) {
    return trace.steps.map((step) => ({
      label: plain(step.label),
      formula: plain(step.formula),
      result: plain(step.result),
      unit: plain(step.unit),
      note: plain(step.note),
      inputs: (step.inputs ?? []).map((input) => ({
        label: plain(input.label),
        value: plain(input.value),
        source: plain(input.source),
        sourceKind: input.source ? SOURCE_WORDS[input.source_kind] ?? "From" : undefined,
      })),
    }));
  }
  if (opened.explain) {
    return [
      {
        label: opened.explain.label ?? "How it is counted",
        formula: opened.explain.formula,
        result: opened.explain.result ?? opened.shown,
        unit: opened.explain.unit,
        inputs: opened.explain.inputs,
      },
    ];
  }
  return [];
}

function TracePanel({
  opened,
  closing,
  onClose,
  onExited,
}: {
  opened: Opened;
  closing: boolean;
  onClose: () => void;
  onExited: () => void;
}) {
  const [loaded, setLoaded] = useState<Trace | null>(opened.trace);
  const [loading, setLoading] = useState(Boolean(opened.load && !opened.trace));
  const [failed, setFailed] = useState<string | null>(null);

  useEffect(() => {
    if (!opened.load || opened.trace) return;
    let cancelled = false;
    opened
      .load()
      .then((trace) => {
        if (cancelled) return;
        setLoaded(trace ?? null);
        setLoading(false);
      })
      .catch((cause: unknown) => {
        if (cancelled) return;
        setFailed(cause instanceof Error ? cause.message : String(cause));
        setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [opened]);

  const steps = useMemo(() => toSteps(loaded, opened), [loaded, opened]);
  const fromTrace = Boolean(loaded?.steps?.length);

  return (
    <TraceSheet
      closing={closing}
      onClose={onClose}
      onExited={onExited}
      heading={opened.heading}
      figure={opened.shown}
      steps={steps}
      foot={
        <>
          <StatusChip tone="accent">
            {opened.origin ?? (fromTrace ? "From the forecasting engine" : "Counted by the server")}
          </StatusChip>
          <span style={{ fontSize: 12, color: "var(--ds-text-3)" }}>
            {fromTrace
              ? "Built-in engine, deterministic code. The reasoning engine never writes a number."
              : "Read from live records, not estimated."}
          </span>
        </>
      }
    >
      {opened.note && (
        <p className="ss-trace-note ds-reveal" data-shown="">
          {opened.note}
        </p>
      )}
      {loading && (
        <div className="ss-trace-loading" role="status">
          <Spinner /> Fetching the working for this line…
        </div>
      )}
      {failed && <p style={{ color: "var(--ds-fail-ink)", fontSize: 14 }}>{failed}</p>}
      {!loading && !failed && steps.length === 0 && !opened.extra && (
        <p style={{ fontSize: 14, color: "var(--ds-text-2)" }}>
          This figure was taken straight from a record and was not calculated.
        </p>
      )}
      {opened.extra && <div style={{ marginBottom: 20 }}>{opened.extra}</div>}
    </TraceSheet>
  );
}
