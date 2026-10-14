"use client";

/**
 * Every number on screen can be opened.
 *
 * A figure is a button. Pressing it slides out how it was arrived at: the
 * rule in words, and every input with the record it came from. PortalBot has
 * no reasoning model at all, so every figure here is either counted by the
 * server from live rows, derived by the script, or measured by the
 * evaluation, and the foot of the sheet says which.
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

export type Explain = {
  formula: string;
  inputs: TraceInputView[];
  result?: string;
  unit?: string;
  label?: string;
  note?: string;
};

export type Origin = "counted" | "script" | "measured" | "record";

const ORIGIN_WORDS: Record<Origin, [string, string]> = {
  counted: ["Counted by the server", "Read from live rows when the page loaded, not estimated."],
  script: ["Derived by the script", "Deterministic code. No reasoning model is involved anywhere in PortalBot."],
  measured: ["Measured by the evaluation", "The acceptance suite ran it, end to end, on a fresh day."],
  record: ["Taken from the record", "Copied as it stands in the shipment record. Nothing was calculated."],
};

type Opened = {
  key: string;
  heading: string;
  shown: string;
  steps: TraceStepView[];
  note?: string;
  extra?: ReactNode;
  origin: Origin;
};

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
          heading={opened.heading}
          figure={opened.shown}
          steps={opened.steps}
          foot={
            <>
              <StatusChip tone="accent">{ORIGIN_WORDS[opened.origin][0]}</StatusChip>
              <span style={{ fontSize: 12, color: "var(--ds-text-3)" }}>{ORIGIN_WORDS[opened.origin][1]}</span>
            </>
          }
        >
          {opened.note && <p className="pb-sheet-note">{opened.note}</p>}
          {opened.extra && <div style={{ marginBottom: 20 }}>{opened.extra}</div>}
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

/** A number that opens the panel showing how it was arrived at. */
export function Figure({
  value,
  heading,
  explain,
  steps,
  note,
  extra,
  origin = "counted",
  count,
  decimals = 0,
  className = "",
  align = "start",
}: {
  value: string;
  heading: string;
  explain?: Explain;
  steps?: TraceStepView[];
  note?: string;
  extra?: ReactNode;
  origin?: Origin;
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

  const resolved: TraceStepView[] =
    steps ??
    (explain
      ? [
          {
            label: explain.label ?? "How it is counted",
            formula: explain.formula,
            result: explain.result ?? value,
            unit: explain.unit,
            note: explain.note,
            inputs: explain.inputs,
          },
        ]
      : []);

  return (
    <button
      type="button"
      className={`ds-figure ${className}`}
      data-open={openKey === key ? "" : undefined}
      onClick={() => open({ key, heading, shown: value, steps: resolved, note, extra, origin })}
      aria-label={`${heading}: ${value}. Open how it was arrived at.`}
    >
      {shown}
    </button>
  );
}
