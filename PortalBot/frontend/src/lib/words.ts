/**
 * Plain words for everything the server sends as a code.
 *
 * The screen never shows `write_tracking` or `needs_a_person`; it shows what
 * a clerk would say. Codes stay in the code.
 */

import type { ChipTone } from "@/design/StatusChip";
import type { Run, ShipmentBrief, ShipmentDetail, Step } from "@/lib/types";

export const SYSTEM_WORDS: Record<string, string> = {
  bot: "PortalBot",
  carrier: "Carrier portal",
  legacy: "Business system",
};

export const ACTION_WORDS: Record<string, string> = {
  validate_address: "Checked and tidied the address",
  assess_dangerous_goods: "Looked the parts up in the dangerous goods table",
  book: "Booked it in the carrier portal",
  collect: "Collected the tracking number",
  write_tracking: "Wrote the tracking number into the order screen",
  verify_write: "Read the value back from the order screen",
  ask_for_code: "Asked the clerk on duty for a one-time code",
  skip: "Already done, so nothing was touched",
};

export const OUTCOME_WORDS: Record<string, { label: string; tone: ChipTone }> = {
  ok: { label: "Done", tone: "pass" },
  refused: { label: "Refused", tone: "warn" },
  failed: { label: "Failed", tone: "fail" },
  skipped: { label: "Skipped", tone: "neutral" },
  waiting: { label: "Waiting", tone: "accent" },
};

export const ROLE_WORDS: Record<string, string> = {
  viewer: "Viewer",
  clerk: "Shipping clerk",
  operations_lead: "Operations lead",
  developer: "Developer",
  administrator: "Administrator",
};

export const ROLE_RANK: Record<string, number> = {
  viewer: 0,
  clerk: 10,
  operations_lead: 20,
  developer: 30,
  administrator: 50,
};

export function mayAct(role: string | undefined, needed: keyof typeof ROLE_RANK): boolean {
  return (ROLE_RANK[role ?? ""] ?? -1) >= ROLE_RANK[needed];
}

export const COUNTRY_WORDS: Record<string, string> = {
  TW: "Taiwan",
  US: "United States",
  JP: "Japan",
  DE: "Germany",
  CN: "China",
};

export const SERVICE_WORDS: Record<string, string> = {
  STD: "Standard",
  EXP: "Express",
};

/** A code that slipped through, as words: `gross_kg` becomes "gross kg". */
export function plain(text: string | null | undefined): string {
  if (!text) return "";
  return text.replace(/\b([a-z]+(?:_[a-z0-9]+)+)\b/g, (code) => code.replace(/_/g, " "));
}

/* ------------------------------------------------------------------ */
/* Where a stopped shipment stopped                                     */
/* ------------------------------------------------------------------ */
export type Stage = "address" | "dangerous" | "book" | "collect" | "write" | "form";

export function stageOf(kind: string): Stage {
  if (kind === "bad_address" || kind === "bad_postcode") return "address";
  if (kind === "unknown_dangerous_goods" || kind === "mixed_dangerous_goods") return "dangerous";
  if (kind === "tracking_timeout") return "collect";
  if (kind.startsWith("legacy_") || kind === "truncated_write") return "write";
  if (kind === "form_changed") return "form";
  return "book";
}

/* ------------------------------------------------------------------ */
/* Runs                                                                 */
/* ------------------------------------------------------------------ */
export type RunKind = "finished" | "killed" | "resumed" | "halted" | "running";

/** What each run was: finished, killed part way, resumed after a kill, or stopped. */
export function runKinds(runs: Run[]): Map<number, RunKind> {
  const ordered = [...runs].sort((a, b) => a.id - b.id);
  const kinds = new Map<number, RunKind>();
  ordered.forEach((run, index) => {
    const before = ordered[index - 1];
    if (run.status === "halted") kinds.set(run.id, "halted");
    else if (run.status === "stopped") kinds.set(run.id, "killed");
    else if (run.status === "running") kinds.set(run.id, "running");
    else if (before && before.status === "stopped") kinds.set(run.id, "resumed");
    else kinds.set(run.id, "finished");
  });
  return kinds;
}

export const RUN_CHIP: Record<RunKind, { label: string; tone: ChipTone }> = {
  finished: { label: "Finished", tone: "pass" },
  killed: { label: "Killed part way", tone: "warn" },
  resumed: { label: "Resumed", tone: "accent" },
  halted: { label: "Stopped — screen changed", tone: "fail" },
  running: { label: "Running", tone: "accent" },
};

/** "Killed after 25 shipments." → 25 */
export function killedAfter(run: Run): number | null {
  const match = /Killed after (\d+)/.exec(run.notes || "");
  return match ? Number(match[1]) : null;
}

/** The run whose time window holds this moment. */
export function runAt(runs: Run[], at: string | null): Run | null {
  if (!at) return null;
  const t = when(at);
  let best: Run | null = null;
  for (const run of runs) {
    const start = when(run.started_at);
    const end = run.finished_at ? when(run.finished_at) : Infinity;
    if (Number.isFinite(start) && t >= start - 5 && t <= end + 5) {
      if (!best || run.id > best.id) best = run;
    }
  }
  return best;
}

/* ------------------------------------------------------------------ */
/* Shipments                                                            */
/* ------------------------------------------------------------------ */
export function shipmentChip(
  shipment: ShipmentBrief,
  resumed = false,
): { label: string; tone: ChipTone } {
  if (shipment.exception_kind) {
    return shipment.state === "failed"
      ? { label: "Stopped", tone: "fail" }
      : { label: "Needs a person", tone: "warn" };
  }
  if (shipment.state === "done" || shipment.state === "written_back") {
    return resumed ? { label: "Resumed", tone: "accent" } : { label: "Tracking written", tone: "pass" };
  }
  if (shipment.state === "booked") {
    return shipment.tracking_number
      ? { label: "Tracking collected", tone: "accent" }
      : { label: "Booked", tone: "accent" };
  }
  return { label: "Not started", tone: "neutral" };
}

/** How far along the row is: 0 not started … 4 done. */
export function reached(shipment: ShipmentBrief): number {
  if (shipment.state === "done") return 4;
  if (shipment.state === "written_back") return 3;
  if (shipment.tracking_number) return 2;
  if (shipment.consignment) return 1;
  return 0;
}

export const CHECKPOINTS = ["Checked", "Booked", "Tracking collected", "Written back", "Done"];

/** The steps of one shipment, grouped by the run that took them. */
export function stepsByRun(steps: Step[], runs: Run[]): { run: Run | null; steps: Step[] }[] {
  const groups: { run: Run | null; steps: Step[] }[] = [];
  for (const step of steps) {
    const run = runAt(runs, step.at);
    const last = groups[groups.length - 1];
    if (last && (last.run?.id ?? null) === (run?.id ?? null)) last.steps.push(step);
    else groups.push({ run, steps: [step] });
  }
  return groups;
}

/** The last step that did something, for "where it is now". */
export function lastStep(detail: ShipmentDetail): Step | null {
  for (let index = detail.steps.length - 1; index >= 0; index -= 1) {
    if (detail.steps[index].action !== "skip") return detail.steps[index];
  }
  return detail.steps[detail.steps.length - 1] ?? null;
}

/* ------------------------------------------------------------------ */
/* Time                                                                 */
/* ------------------------------------------------------------------ */
/** The server stores UTC and sometimes sends it without the zone. */
export function when(iso: string | null | undefined): number {
  if (!iso) return NaN;
  return Date.parse(/[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`);
}

export function clock(iso: string | null | undefined): string {
  if (!iso) return "--:--:--";
  const date = new Date(when(iso));
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString("en-GB", { hour12: false });
}

/** 18:43:16.347, for log lines. */
export function clockMs(iso: string | null | undefined): string {
  const base = clock(iso);
  if (!iso) return base;
  const ms = new Date(when(iso)).getMilliseconds();
  return Number.isNaN(ms) ? base : `${base}.${String(ms).padStart(3, "0")}`;
}

export const OUTCOME_TAG: Record<string, string> = {
  ok: "OK",
  refused: "HOLD",
  failed: "FAIL",
  skipped: "SKIP",
  waiting: "WAIT",
};

export function day(iso: string | null | undefined): string {
  if (!iso) return "";
  const date = new Date(when(iso));
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString("en-GB", { day: "numeric", month: "long" });
}

export function seconds(value: number): string {
  if (value < 0.01) return "under a hundredth of a second";
  if (value < 1) return `${value.toFixed(2)} seconds`;
  return `${value.toFixed(1)} seconds`;
}

export function milliseconds(value: number): string {
  if (value <= 0) return "instant";
  if (value < 1000) return `${value} milliseconds`;
  return `${(value / 1000).toFixed(1)} seconds`;
}

export function count(many: number, noun: string, plural?: string): string {
  return `${many.toLocaleString("en-GB")} ${many === 1 ? noun : plural ?? `${noun}s`}`;
}
