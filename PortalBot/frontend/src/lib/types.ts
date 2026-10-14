/** The shapes the backend sends. */

export type Step = {
  id: number;
  at: string | null;
  system: "bot" | "carrier" | "legacy";
  action: string;
  attempt: number;
  outcome: "ok" | "refused" | "failed" | "skipped" | "waiting";
  sent: Record<string, unknown>;
  received: Record<string, unknown>;
  note: string;
  duration_ms: number;
};

export type ShipmentBrief = {
  reference: string;
  order_number: string;
  customer: string;
  country: string;
  city: string;
  packages: number;
  weight_kg: number;
  dangerous: boolean;
  state: string;
  state_label: string;
  consignment: string;
  tracking_number: string;
  attempts: number;
  exception_kind: string;
  exception_label: string;
  exception_detail: string;
};

export type ShipmentDetail = ShipmentBrief & {
  to_name: string;
  to_line1: string;
  to_postcode: string;
  goods_description: string;
  service: string;
  lines: { part_code: string; description: string }[];
  dangerous_detail: {
    dangerous?: boolean;
    declarations?: {
      un_number: string;
      proper_name: string;
      dg_class: string;
      packing_group: string;
      note: string;
    }[];
    unknown?: string[];
    reasons?: string[];
  };
  idempotency_key: string;
  booked_at: string | null;
  written_back_at: string | null;
  label_url: string;
  steps: Step[];
};

export type Drift = {
  matches: boolean;
  severity: string;
  expected_fingerprint: string;
  found_fingerprint: string;
  missing: string[];
  added: string[];
  looks_renamed: string[][];
  summary: string;
};

export type Run = {
  id: number;
  started_at: string | null;
  finished_at: string | null;
  status: string;
  considered: number;
  completed: number;
  exceptions: number;
  skipped_already_done: number;
  seconds: number;
  halted_reason: string;
  drift: Drift | null;
  notes: string;
};

export type RunResult = {
  run: Run;
  halted: boolean;
  halt_reason: string;
  drift: Drift | null;
  completed: number;
  exceptions: number;
  already_done: number;
};

export type Challenge = {
  reference: string;
  kind: string;
  status: string;
  asked_at: string | null;
  asked_of: { name: string } | null;
  shipment: string | null;
  note: string;
};

export type Flag = {
  id: number;
  raised_at: string | null;
  script: string;
  expected_fingerprint: string;
  found_fingerprint: string;
  detail: Drift;
  status: string;
  acknowledged_by: { name: string } | null;
  note: string;
};

export type Dashboard = {
  shipments: number;
  done: number;
  automated_share: number;
  by_state: { state: string; label: string; count: number }[];
  by_exception: { kind: string; label: string; count: number }[];
  waiting_for_a_code: number;
  open_flags: number;
  latest_run: Run | null;
  minutes_saved: number;
  hours_saved: number;
  carrier: string;
};

export type Criterion = {
  name: string;
  question: string;
  bar: number;
  unit: string;
  value: number;
  measured: string;
  passed: boolean;
};

export type Evidence = {
  started_at: string;
  seconds: number;
  criteria: Criterion[];
  passed: boolean;
  statement: string;
  ordinary: {
    total: number;
    clean: number;
    clean_done: number;
    clean_share: number;
    defective: number;
    exceptions: number;
    classified: number;
    classified_share: number;
    by_kind: { kind: string; label: string; count: number; planted: boolean }[];
    seconds: number;
  };
  killing: {
    shipments: number;
    kills: number;
    bookings_made: number;
    duplicates: number;
    duplicate_detail: string[];
    unstable_keys: string[];
    finished: number;
    refused_by_the_portal: number;
  };
  drift: {
    halted: boolean;
    booked_anyway: number;
    flag_raised: boolean;
    flag: Drift | null;
    suggested_renames: string[][];
    reason: string;
    held: boolean;
  };
};

export type DemoState = {
  loaded: boolean;
  shipments: number;
  storage_is_temporary: boolean;
};

export type Page<T> = {
  total: number;
  limit: number;
  offset: number;
  items: T[];
};

export type Health = {
  service: string;
  environment: string;
  database: string;
  carrier: string;
  portal_version: string;
  serverless: boolean;
};

export type Person = { email: string; name: string; role: string; role_label: string };

export type LoadResult = {
  seconds: number;
  counts: Record<string, number>;
  state: DemoState;
};
