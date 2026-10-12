"use client";

/**
 * Every number on screen can be opened.
 *
 * A figure is rendered as a button. Pressing it slides out the suite's trace
 * sheet: the figure on ink with a small constellation of the calculation,
 * then each step on a node chain, the formula, and for every input the
 * record it came from, lighting up in turn. Nothing that goes to the ledger
 * is a figure somebody has to take on trust.
 *
 * Two kinds of figure open the same sheet:
 * - a calculated figure carries the matching code's own trace (the steps the
 *   server worked out and stored with the invoice);
 * - a counted figure (a total on the desk, a measured result) carries
 *   `explain`: the rule in words and the records it was counted from, all as
 *   the server sent them.
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

/** Plain words for the kind of record an input came from. */
export const SOURCE_WORDS: Record<string, string> = {
  purchase_order: "Purchase order",
  goods_receipt: "Goods receipt",
  invoice: "The invoice",
  supplier: "Supplier record",
  policy: "Company policy",
  foreign_exchange: "Exchange rate",
  ledger: "The ledger",
  document: "The document",
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
      {opened && <TracePanel opened={opened} closing={closing} onClose={close} onExited={exited} />}
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
  explain,
  note,
  extra,
  origin,
  className = "",
  count,
  decimals = 2,
  align = "start",
  prefix,
  suffix,
}: {
  value: string;
  heading: string;
  trace?: Trace | null;
  explain?: Explain;
  note?: string;
  extra?: ReactNode;
  origin?: string;
  className?: string;
  /** Count up to this number when it scrolls into view; `value` is the last frame. */
  count?: number;
  decimals?: number;
  align?: "start" | "end";
  prefix?: string;
  suffix?: string;
}) {
  const { open, openKey } = useTrace();
  const key = useId();
  const hasDetail = Boolean((trace && trace.steps?.length) || explain || note || extra);
  const shown =
    count !== undefined && Number.isFinite(count) ? (
      <CountUp to={count} final={value} decimals={decimals} align={align} prefix={prefix} suffix={suffix} />
    ) : (
      value
    );

  if (!hasDetail) {
    return <span className={`ds-num ${className}`}>{shown}</span>;
  }

  return (
    <button
      type="button"
      className={`ds-figure ${className}`}
      data-open={openKey === key ? "" : undefined}
      onClick={() => open({ key, heading, shown: value, trace: trace ?? null, explain, note, extra, origin })}
      aria-label={`${heading}: ${value}. Open how it was worked out.`}
    >
      {shown}
    </button>
  );
}

/* ------------------------------------------------------------------ */
/* The panel                                                           */
/* ------------------------------------------------------------------ */
function toSteps(opened: Opened): TraceStepView[] {
  if (opened.trace?.steps?.length) {
    return opened.trace.steps.map((step) => ({
      label: step.label,
      formula: step.formula,
      result: step.result,
      unit: step.unit,
      note: step.note,
      inputs: step.inputs.map((input) => ({
        label: input.label,
        value: input.value,
        source: input.source,
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
  const steps = useMemo(() => toSteps(opened), [opened]);
  const fromTrace = Boolean(opened.trace?.steps?.length);

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
            {opened.origin ?? (fromTrace ? "From the matching code" : "Counted by the server")}
          </StatusChip>
          <span style={{ fontSize: 12, color: "var(--ds-text-3)" }}>
            {fromTrace
              ? "Deterministic code. The reading engine never writes a number."
              : "Read from live records, not estimated."}
          </span>
        </>
      }
    >
      {opened.note && <p className="lf-trace-note">{opened.note}</p>}
      {steps.length === 0 && !opened.extra && (
        <p style={{ fontSize: 14, color: "var(--ds-text-2)" }}>
          This figure was taken straight from a record and was not calculated.
        </p>
      )}
      {opened.extra && <div style={{ marginBottom: 20 }}>{opened.extra}</div>}
    </TraceSheet>
  );
}
