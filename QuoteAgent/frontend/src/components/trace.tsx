"use client";

/**
 * Every number on screen can be opened.
 *
 * A figure is rendered as a button. Pressing it slides out the arithmetic:
 * each step in order, the formula in words, and for every input the record it
 * came from. Nothing on a quote is a figure somebody has to take on trust.
 *
 * Two kinds of figure open the same panel:
 * - a priced figure carries the pricing engine's own trace (the steps the
 *   server worked out and stored with the quote);
 * - a counted figure (a total on the overview, a measured acceptance result)
 *   carries `explain`: the rule in words and the records it was counted
 *   from, all as the server sent them.
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

const SOURCE_WORDS: Record<string, string> = {
  contract: "Customer contract",
  tariff_table: "Duty table",
  foreign_exchange: "Exchange rate",
  catalogue: "Catalogue record",
  policy: "Company policy",
  request: "The customer's request",
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
        <TracePanel opened={opened} closing={closing} onClose={close} onExited={exited} />
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
  explain,
  note,
  extra,
  origin,
  className = "",
  emphasis = false,
  count,
  decimals = 2,
  align = "start",
}: {
  value: string;
  heading: string;
  trace?: Trace | null;
  explain?: Explain;
  note?: string;
  extra?: ReactNode;
  origin?: string;
  className?: string;
  emphasis?: boolean;
  /** Count up to this number when it scrolls into view; `value` is the last frame. */
  count?: number;
  decimals?: number;
  align?: "start" | "end";
}) {
  const { open, openKey } = useTrace();
  const key = useId();
  const hasDetail = Boolean((trace && trace.steps?.length) || explain || note || extra);
  const shown =
    count !== undefined && Number.isFinite(count) ? (
      <CountUp to={count} final={value} decimals={decimals} align={align} />
    ) : (
      value
    );

  if (!hasDetail) {
    return <span className={`ds-num ${className}`}>{shown}</span>;
  }

  return (
    <button
      type="button"
      className={`ds-figure ${emphasis ? "font-semibold" : ""} ${className}`}
      data-open={openKey === key ? "" : undefined}
      onClick={() =>
        open({ key, heading, shown: value, trace: trace ?? null, explain, note, extra, origin })
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
/**
 * Codes such as "key_account" sometimes ride along in the engine's own
 * wording. On screen they are words: "key account".
 */
function plain(text: string): string {
  if (!text) return text;
  return text.replace(new RegExp("(^|[^A-Za-z0-9-])([a-z]+(?:_[a-z]+)+)(?=$|[^A-Za-z0-9-])", "g"), (_all, lead: string, code: string) =>
    `${lead}${code.replace(/_/g, " ")}`,
  );
}

function toSteps(opened: Opened): TraceStepView[] {
  if (opened.trace?.steps?.length) {
    return opened.trace.steps.map((step) => ({
      label: plain(step.label),
      formula: plain(step.formula),
      result: step.result,
      unit: plain(step.unit),
      note: plain(step.note),
      inputs: step.inputs.map((input) => ({
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
            {opened.origin ?? (fromTrace ? "From the pricing engine" : "Counted by the server")}
          </StatusChip>
          <span style={{ fontSize: 12, color: "var(--ds-text-3)" }}>
            {fromTrace
              ? "Deterministic code. The reasoning engine never writes a number."
              : "Read from live records, not estimated."}
          </span>
        </>
      }
    >
      {opened.note && (
        <p
          className="ds-reveal"
          data-shown=""
          style={{
            margin: "0 0 20px",
            padding: "12px 14px",
            borderRadius: 3,
            background: "var(--ds-page)",
            border: "1px solid var(--ds-line)",
            borderLeft: "4px solid var(--ds-accent)",
            fontSize: 13.5,
            lineHeight: 1.55,
            color: "var(--ds-text-2)",
          }}
        >
          {plain(opened.note)}
        </p>
      )}
      {steps.length === 0 && !opened.extra && (
        <p style={{ fontSize: 14, color: "var(--ds-text-2)" }}>
          This figure was taken straight from a record and was not calculated.
        </p>
      )}
      {opened.extra && <div style={{ marginBottom: 20 }}>{opened.extra}</div>}
    </TraceSheet>
  );
}
