"use client";

/**
 * Every number on screen can be opened.
 *
 * A figure is a button. Pressing it slides out the rule it was counted by and
 * every record it was counted from, as the server sent them. FrontDesk's
 * figures are counted (contacts, shares, attempts, minutes), never invented:
 * the reasoning engine picks an intent and phrases a sentence, and that is all.
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
import { plain } from "@/lib/format";

export type Explain = {
  /** The rule, in words. */
  formula: string;
  inputs: TraceInputView[];
  result?: string;
  unit?: string;
  label?: string;
  /** Further worked steps after the first. */
  more?: TraceStepView[];
};

type Opened = {
  key: string;
  heading: string;
  shown: string;
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
  if (!value) throw new Error("useTrace has to be used inside the trace provider");
  return value;
}

export function Figure({
  value,
  heading,
  explain,
  note,
  extra,
  origin,
  className = "",
  count,
  decimals = 0,
  align = "start",
}: {
  value: string;
  heading: string;
  explain?: Explain;
  note?: string;
  extra?: ReactNode;
  origin?: string;
  className?: string;
  /** Count up to this number when it scrolls into view; `value` is the last frame. */
  count?: number;
  decimals?: number;
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
      onClick={(event) => {
        event.stopPropagation();
        open({ key, heading, shown: value, explain, note, extra, origin });
      }}
      aria-label={`${heading}: ${value}. Open how it was counted.`}
    >
      {shown}
    </button>
  );
}

function toSteps(opened: Opened): TraceStepView[] {
  if (!opened.explain) return [];
  const first: TraceStepView = {
    label: opened.explain.label ?? "How it is counted",
    formula: plain(opened.explain.formula),
    result: opened.explain.result ?? opened.shown,
    unit: opened.explain.unit,
    inputs: opened.explain.inputs.map((input) => ({
      ...input,
      label: plain(input.label),
      value: plain(input.value),
      source: input.source ? plain(input.source) : input.source,
    })),
  };
  return [first, ...(opened.explain.more ?? [])];
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
  return (
    <TraceSheet
      closing={closing}
      onClose={onClose}
      onExited={onExited}
      eyebrow="How this was counted"
      heading={opened.heading}
      figure={opened.shown}
      steps={steps}
      foot={
        <>
          <StatusChip tone="accent">{opened.origin ?? "Counted by the server"}</StatusChip>
          <span style={{ fontSize: 12, color: "var(--ds-text-3)" }}>
            Deterministic code, from live records. The reasoning engine never writes a number.
          </span>
        </>
      }
    >
      {opened.note && <p className="fd-trace-note">{plain(opened.note)}</p>}
      {steps.length === 0 && !opened.extra && (
        <p style={{ fontSize: 14, color: "var(--ds-text-2)" }}>
          This figure was read straight from a record and was not calculated.
        </p>
      )}
      {opened.extra && <div style={{ marginBottom: 20 }}>{opened.extra}</div>}
    </TraceSheet>
  );
}
