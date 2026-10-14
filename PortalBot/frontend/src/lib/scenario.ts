/**
 * Real records into a scene for the screen-driving constellation.
 *
 * A scenario is what the canvas plays: which fields the bot filled and with
 * what values, how far the row got, where it stopped and why. Everything in
 * it is read from a shipment's own trace or a run's own record.
 */

import type { Run, ShipmentDetail } from "@/lib/types";
import { COUNTRY_WORDS, SERVICE_WORDS, stageOf, type RunKind, type Stage } from "@/lib/words";

export const CARRIER_FIELDS = [
  { key: "reference", word: "Reference", portal: "consignment_ref" },
  { key: "service", word: "Service", portal: "service_code" },
  { key: "collection", word: "Collection date", portal: "collect_on" },
  { key: "name", word: "Deliver to", portal: "deliver_name" },
  { key: "street", word: "Street", portal: "deliver_addr1" },
  { key: "city", word: "City", portal: "deliver_city" },
  { key: "postcode", word: "Postcode", portal: "deliver_post" },
  { key: "country", word: "Country", portal: "deliver_ctry" },
  { key: "packages", word: "Packages", portal: "pkg_count" },
  { key: "weight", word: "Gross weight", portal: "gross_kg" },
  { key: "goods", word: "Goods", portal: "goods_desc" },
  { key: "dangerous", word: "Dangerous goods", portal: "has_dg" },
] as const;

export type FieldKey = (typeof CARRIER_FIELDS)[number]["key"];

/** The portal's version 2 names, for the fields that moved. */
export const RENAMED_IN_V2: Record<string, string> = {
  deliver_post: "deliver_postcode",
  gross_kg: "gross_weight_kg",
};

export const BUSINESS_FIELDS = [
  { key: "order", word: "Order number" },
  { key: "status", word: "Status" },
  { key: "tracking", word: "Tracking number" },
  { key: "carrier", word: "Carrier" },
  { key: "despatched", word: "Despatched on" },
  { key: "readback", word: "Read back" },
] as const;

export type DriveScenario = {
  key: string;
  kind: "written" | "booked" | "held" | "halted" | "resumed" | "killed" | "idle";
  reference?: string;
  values?: Partial<Record<FieldKey, string>>;
  order?: string;
  tracking?: string;
  carrier?: string;
  address?: string;
  dangerous?: string;
  stage?: Stage;
  reason?: string;
  moved?: [string, string][];
  killedAfter?: number;
  run?: number;
};

function show(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value);
}

/** The values the bot typed into the booking form, from the trace if it booked. */
export function formValues(detail: ShipmentDetail): Partial<Record<FieldKey, string>> {
  const booked = [...detail.steps].reverse().find((step) => step.action === "book" && Object.keys(step.sent ?? {}).length);
  const sent = (booked?.sent ?? {}) as Record<string, unknown>;
  const pick = (portal: string, fallback: unknown) =>
    show(sent[portal] ?? sent[RENAMED_IN_V2[portal] ?? ""] ?? fallback);
  const declaration = detail.dangerous_detail?.declarations?.[0];
  return {
    reference: pick("consignment_ref", detail.reference),
    service: SERVICE_WORDS[pick("service_code", detail.service)] ?? pick("service_code", detail.service),
    collection: pick("collect_on", booked?.at?.slice(0, 10) ?? ""),
    name: pick("deliver_name", detail.to_name),
    street: pick("deliver_addr1", detail.to_line1),
    city: pick("deliver_city", detail.city),
    postcode: pick("deliver_post", detail.to_postcode),
    country: COUNTRY_WORDS[pick("deliver_ctry", detail.country)] ?? pick("deliver_ctry", detail.country),
    packages: pick("pkg_count", detail.packages),
    weight: `${pick("gross_kg", detail.weight_kg)} kilograms`,
    goods: pick("goods_desc", detail.goods_description),
    dangerous: declaration ? `Yes · ${declaration.un_number}` : pick("has_dg", detail.dangerous ? "yes" : "no") === "yes" ? "Yes" : "No",
  };
}

export function scenarioFromShipment(
  detail: ShipmentDetail,
  options: { resumedAfter?: number | null; run?: number; carrier?: string } = {},
): DriveScenario {
  const values = formValues(detail);
  const declaration = detail.dangerous_detail?.declarations?.[0];
  const base: DriveScenario = {
    key: `shipment-${detail.reference}-${detail.state}-${detail.steps.length}`,
    kind: "written",
    reference: detail.reference,
    values,
    order: detail.order_number,
    tracking: detail.tracking_number,
    carrier: options.carrier ?? "Hsinchu Logistics",
    address: `${detail.city} ${values.postcode ?? detail.to_postcode}`,
    dangerous: declaration ? `${declaration.un_number}, by part number` : "None on this order",
    run: options.run,
  };
  if (detail.exception_kind) {
    return { ...base, kind: "held", stage: stageOf(detail.exception_kind), reason: detail.exception_label };
  }
  if (detail.state === "done" || detail.state === "written_back") {
    return options.resumedAfter
      ? { ...base, kind: "resumed", killedAfter: options.resumedAfter }
      : base;
  }
  if (detail.state === "booked") return { ...base, kind: "booked" };
  return { ...base, kind: "idle" };
}

export function scenarioFromRun(
  run: Run,
  kind: RunKind,
  sample: ShipmentDetail | null,
  previous: Run | null,
): DriveScenario {
  if (kind === "halted") {
    const moved = (run.drift?.looks_renamed ?? []).map(([gone, arrived]) => [gone, arrived] as [string, string]);
    return {
      key: `run-${run.id}-halted`,
      kind: "halted",
      moved,
      reason: `${moved.length || (run.drift?.missing.length ?? 0)} fields moved`,
      run: run.id,
    };
  }
  const after = (previous && /Killed after (\d+)/.exec(previous.notes || "")?.[1]) || null;
  const own = /Killed after (\d+)/.exec(run.notes || "")?.[1] ?? null;
  const fromSample = sample ? scenarioFromShipment(sample, { run: run.id }) : null;
  if (kind === "killed") {
    return {
      ...(fromSample ?? {}),
      key: `run-${run.id}-killed`,
      kind: "killed",
      killedAfter: own ? Number(own) : run.considered,
      run: run.id,
    };
  }
  if (kind === "resumed") {
    return {
      ...(fromSample ?? {}),
      key: `run-${run.id}-resumed`,
      kind: "resumed",
      killedAfter: after ? Number(after) : 0,
      run: run.id,
    };
  }
  return { ...(fromSample ?? { kind: "written" }), key: `run-${run.id}-finished`, kind: "written", run: run.id };
}
