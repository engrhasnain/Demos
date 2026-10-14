/**
 * The "shipments in flight" feed, from real rows.
 *
 * A handful of shipments are opened in full (their trace says which run
 * touched them and what each screen was sent), and the latest stopped run is
 * added, so the live card and the canvas always show something that really
 * happened on this day.
 */

import type { FeedItem } from "@/design/LiveFeedCard";
import { api } from "@/lib/api";
import { scenarioFromRun, scenarioFromShipment, type DriveScenario } from "@/lib/scenario";
import type { Run, ShipmentBrief, ShipmentDetail } from "@/lib/types";
import {
  ACTION_WORDS,
  RUN_CHIP,
  clock,
  killedAfter,
  lastStep,
  runAt,
  runKinds,
  shipmentChip,
  type RunKind,
} from "@/lib/words";

export type FeedEntry = { item: FeedItem; scenario: DriveScenario };

function spread<T>(list: T[], many: number): T[] {
  if (list.length <= many) return list;
  return Array.from({ length: many }, (_, index) => list[Math.floor((index * (list.length - 1)) / Math.max(1, many - 1))]);
}

export async function openSamples(shipments: ShipmentBrief[]): Promise<ShipmentDetail[]> {
  const done = shipments.filter((s) => s.state === "done");
  const picks: ShipmentBrief[] = [];
  const add = (s: ShipmentBrief | undefined) => {
    if (s && !picks.some((p) => p.reference === s.reference)) picks.push(s);
  };
  add(done.find((s) => s.dangerous));
  spread(done, 4).forEach(add);
  const kinds = new Set<string>();
  for (const s of shipments) {
    if (s.exception_kind && !kinds.has(s.exception_kind) && kinds.size < 2) {
      kinds.add(s.exception_kind);
      add(s);
    }
  }
  add(shipments.find((s) => s.state === "booked"));
  const details = await Promise.all(
    picks.slice(0, 8).map((s) => api.get<ShipmentDetail>(`/api/shipments/${encodeURIComponent(s.reference)}`).catch(() => null)),
  );
  return details.filter(Boolean) as ShipmentDetail[];
}

/** Which run finished this shipment, and whether that run resumed a killed one. */
export function placeOf(detail: ShipmentDetail, runs: Run[], kinds: Map<number, RunKind>) {
  const last = lastStep(detail);
  const run = runAt(runs, last?.at ?? null);
  const kind = run ? kinds.get(run.id) : undefined;
  const ordered = [...runs].sort((a, b) => a.id - b.id);
  const previous = run ? ordered[ordered.findIndex((r) => r.id === run.id) - 1] ?? null : null;
  return {
    last,
    run,
    kind,
    resumedAfter: kind === "resumed" && previous ? killedAfter(previous) : null,
    previous,
  };
}

export function buildFeed(
  runs: Run[],
  details: ShipmentDetail[],
  carrier: string,
): { entries: FeedEntry[]; sample: ShipmentDetail | null } {
  const kinds = runKinds(runs);
  const written: FeedEntry[] = [];
  const resumed: FeedEntry[] = [];
  const held: FeedEntry[] = [];
  const other: FeedEntry[] = [];
  let sample: ShipmentDetail | null = null;

  for (const detail of details) {
    const place = placeOf(detail, runs, kinds);
    const isResumed = Boolean(place.resumedAfter) && detail.state === "done";
    const chip = shipmentChip(detail, isResumed);
    const scenario = scenarioFromShipment(detail, { resumedAfter: isResumed ? place.resumedAfter : null, run: place.run?.id, carrier });
    const runWords = place.run ? `run ${place.run.id}` : "not run yet";
    let body = "";
    if (detail.exception_kind) {
      body = `${detail.exception_label}. ${detail.exception_detail}`.slice(0, 170);
    } else if (isResumed) {
      body = `Run ${place.previous?.id} was killed after ${place.resumedAfter}. Run ${place.run?.id} read the row, asked the carrier first, then booked it once as ${detail.consignment} and wrote ${detail.tracking_number} back.`;
    } else if (detail.state === "done") {
      body = `Booked with ${carrier} as ${detail.consignment}. Tracking ${detail.tracking_number} written into ${detail.order_number} and read back.`;
    } else if (detail.state === "booked") {
      body = `Booked as ${detail.consignment}. The tracking number is collected on the next run; the booking stands.`;
    } else {
      body = "Waiting for the next run.";
    }
    const entry: FeedEntry = {
      item: {
        key: `s-${detail.reference}`,
        chip,
        stamp: `${clock(place.last?.at)} · ${runWords}`,
        title: `${detail.reference} · ${detail.customer}`,
        body,
        meta: `Step: ${(ACTION_WORDS[place.last?.action ?? ""] ?? "not started").toLowerCase()} · Engine: built-in script`,
        href: `/shipments/${encodeURIComponent(detail.reference)}`,
      },
      scenario,
    };
    if (detail.exception_kind) held.push(entry);
    else if (isResumed) resumed.push(entry);
    else if (detail.state === "done") {
      written.push(entry);
      if (!sample) sample = detail;
    } else other.push(entry);
  }

  const ordered = [...runs].sort((a, b) => b.id - a.id);
  const halted = ordered.find((run) => run.status === "halted");
  const haltedEntry: FeedEntry | null = halted
    ? {
        item: {
          key: `r-${halted.id}`,
          chip: { label: RUN_CHIP.halted.label, tone: "fail" },
          stamp: `${clock(halted.started_at)} · run ${halted.id}`,
          title: "The carrier changed its booking form",
          body: `${(halted.drift?.looks_renamed ?? []).map(([a, b]) => `${a} → ${b}`).join(", ")}. Nothing was sent; the script is flagged for a developer.`,
          meta: "Step: compared the form with the script · Engine: built-in script",
          href: `/runs/${halted.id}`,
        },
        scenario: scenarioFromRun(halted, "halted", null, null),
      }
    : null;

  const entries: FeedEntry[] = [];
  const take = (list: FeedEntry[]) => {
    const next = list.shift();
    if (next) entries.push(next);
  };
  take(written);
  take(resumed);
  take(held);
  if (haltedEntry) entries.push(haltedEntry);
  take(written);
  take(held);
  take(other);
  take(written);
  return { entries: entries.slice(0, 7), sample };
}

/** The scene for one run, for the guide and the run page. */
export function runScenario(runs: Run[], run: Run, sample: ShipmentDetail | null): DriveScenario {
  const kinds = runKinds(runs);
  const ordered = [...runs].sort((a, b) => a.id - b.id);
  const previous = ordered[ordered.findIndex((r) => r.id === run.id) - 1] ?? null;
  return scenarioFromRun(run, kinds.get(run.id) ?? "finished", sample, previous);
}
