/** The shapes the backend sends. Money is a string; counts are numbers. */

export type TraceInput = {
  label: string;
  value: string;
  source: string;
  source_kind: string;
  source_id: string;
};

export type TraceStep = {
  label: string;
  formula: string;
  result: string;
  unit: string;
  note: string;
  inputs: TraceInput[];
};

export type Trace = { subject: string; steps: TraceStep[] };

export type LeadTime = {
  quoted_days: number;
  average_days: number;
  deviation_days: number;
  median_days: number;
  ninetieth_percentile_days: number;
  worst_days: number;
  deliveries: number;
  slippage_days: number;
  is_reliable: boolean;
};

export type Shutdown = {
  country: string;
  label: string;
  new_year: string;
  closes_on: string;
  reopens_on: string;
  back_to_normal_on: string;
  order_by: string;
  closed_days: number;
  disrupted_days: number;
  affects: boolean;
  days_until_order_by?: number;
  weeks_of_cover_needed?: number;
  parts?: number;
};

export type SupplierBrief = {
  id: number;
  code: string;
  name: string;
  country: string;
  currency: string;
  lead_time: LeadTime;
};

export type SupplierDetail = SupplierBrief & {
  minimum_order_value: string;
  container_cubic_metres: string;
  parts: number;
  shutdown: Shutdown | null;
  weeks_of_cover_needed: number;
  days_until_order_by: number | null;
  lead_time_samples: number[];
  part_list?: PartBrief[];
};

export type PartBrief = {
  id: number;
  code: string;
  description: string;
  family: string;
  abc_class: string;
  unit_cost: string;
  pack_size: number;
  minimum_order_quantity: number;
  on_hand: number;
  on_order: number;
  on_order_due: string | null;
  is_active: boolean;
  replaced_by_part_id: number | null;
  replaces_part_id: number | null;
  supplier: SupplierBrief | null;
  stock_value: string;
};

export type Pattern = {
  kind: string;
  label: string;
  description: string;
  average_demand_interval: number;
  coefficient_of_variation_squared: number;
  periods: number;
  periods_with_demand: number;
  suggested_method: string;
};

export type Forecast = {
  method: string;
  method_label: string;
  method_note: string;
  rate: number;
  deviation: number;
  probability_of_demand: number;
  typical_size: number;
  periods_used: number;
  borrowed: boolean;
  notes: string[];
  trace: Trace | null;
};

export type Prepared = {
  weeks: number;
  censored_weeks: number[];
  recovered_units: number;
  project_weeks: number[];
  project_units: number;
  was_adjusted: boolean;
  notes: string[];
};

export type DemandView = {
  part_id: number;
  prepared: Prepared;
  pattern: Pattern;
  forecast: Forecast;
  analogue_of: string[] | null;
  weekly_rate: number;
  sold: number[];
  demand: number[];
};

export type CoverDistribution = {
  windows: number;
  average: number;
  at_service_level: number;
  median: number;
  worst: number;
  cover_weeks_low: number;
  cover_weeks_high: number;
  safety_stock: number;
  method: string;
};

export type Policy = {
  demand_per_day: number;
  deviation_per_day: number;
  lead_time_days: number;
  lead_time_deviation_days: number;
  review_period_days: number;
  cover_days: number;
  service_level: number;
  z: number;
  demand_over_cover: number;
  deviation_over_cover: number;
  safety_stock: number;
  reorder_point: number;
  order_up_to: number;
  method: string;
  distribution: CoverDistribution | null;
  trace: Trace | null;
};

export type Recommendation = {
  decision: string;
  decision_label: string;
  reason: string;
  reason_label: string;
  quantity: number;
  raw_quantity: number;
  value: string;
  position: number;
  days_of_cover: number;
  urgency: number;
  shutdown_note: string;
  flags: string[];
  policy: Policy;
  trace: Trace | null;
};

export type PartDetail = PartBrief & {
  supplier: SupplierDetail;
  history_starts_on: string | null;
  demand: DemandView;
  recommendation: Recommendation;
  successor: PartBrief | null;
  predecessor: PartBrief | null;
};

export type PlanLine = {
  id: number;
  part: PartBrief;
  decision: string;
  decision_label: string;
  reason: string;
  reason_label: string;
  quantity: number;
  value: string;
  demand_method: string;
  demand_method_label: string;
  demand_pattern: string;
  demand_pattern_label: string;
  weekly_rate: string;
  reorder_point: string;
  order_up_to: string;
  safety_stock: string;
  position: string;
  lead_time_days: string;
  service_level: number;
  days_of_cover: number;
  urgency: number;
  shutdown_note: string;
  flags: string[];
  trace?: Trace | null;
};

export type PlanRun = {
  id: number;
  as_of: string | null;
  created_at: string | null;
  created_by: { name: string; role_label: string } | null;
  cash_cap: string;
  cash_committed: string;
  cash_remaining: string;
  parts_considered: number;
  lines_recommended: number;
  lines_deferred: number;
  seconds: number;
  notes: string;
  by_decision: { decision: string; label: string; count: number }[];
  by_reason: { decision: string; reason: string; label: string; count: number }[];
  by_pattern: { pattern: string; label: string; count: number }[];
  allocation?: {
    cap: string;
    committed: string;
    remaining: string;
    accepted: number;
    deferred: number;
    below_minimum: string[];
    trace: Trace | null;
  };
};

export type Arm = {
  name: string;
  stockout_weeks: number;
  units_short: number;
  parts_affected: number;
  orders_placed: number;
  units_ordered: number;
  spend: string;
  average_inventory_value: string;
  closing_inventory_value: string;
  weekly_inventory: number[];
  weekly_stockouts: number[];
};

export type ZeroTrap = {
  parts_scored: number;
  parts_where_zero_wins: number;
  share: number;
  zero_mase: number;
  model_mase: number;
  verdict: string;
};

export type Replay = {
  id?: number;
  weeks: number;
  parts: number;
  seconds: number;
  buyers: Arm;
  stocksense: Arm;
  by_pattern: {
    pattern: string;
    label: string;
    intermittent: boolean;
    parts: number;
    buyers_stockout_weeks: number;
    stocksense_stockout_weeks: number;
    buyers_value: string;
    stocksense_value: string;
  }[];
  weekly: {
    week: number;
    buyers_inventory: number;
    stocksense_inventory: number;
    buyers_stockouts: number;
    stocksense_stockouts: number;
  }[];
  accuracy: {
    parts_scored: number;
    mase: number | null;
    bias: number | null;
    zero_trap: ZeroTrap;
  };
  fewer_stockouts?: boolean;
  not_more_stock?: boolean;
  passed: boolean;
  notes?: string;
};

export type Criterion = {
  name: string;
  question: string;
  bar: string;
  unit: string;
  value: number | string;
  against: number | string;
  measured: string;
  passed: boolean;
};

export type Evidence = {
  started_at: string;
  seconds: number;
  parts: number;
  weeks: number;
  criteria: Criterion[];
  passed: boolean;
  accuracy: Replay["accuracy"];
  by_pattern: Replay["by_pattern"];
  misses: string[];
  statement: string;
};

export type Dashboard = {
  parts: number;
  suppliers: number;
  stock_value: string;
  carrying_cost_low: string;
  carrying_cost_high: string;
  weekly_cash_cap: string;
  latest_plan: PlanRun | null;
  shutdowns: Shutdown[];
};

export type DemoState = {
  loaded: boolean;
  planned: boolean;
  parts: number;
  engine: string;
  storage_is_temporary: boolean;
};

export type Settings = {
  base_currency: string;
  weekly_cash_cap: number;
  carrying_cost_percent_low: number;
  carrying_cost_percent_high: number;
  review_period_days: number;
  service_levels: Record<string, number>;
  project_spike_multiple: number;
  shutdown_prebuild_weeks: number;
  history_weeks: number;
  patterns: {
    kind: string;
    label: string;
    description: string;
    method: string;
    intermittent: boolean;
  }[];
  methods: { code: string; label: string; note: string }[];
  decisions: { code: string; label: string }[];
  reasons: { code: string; label: string }[];
  roles: { code: string; label: string }[];
  cutoffs: {
    average_demand_interval: number;
    coefficient_of_variation_squared: number;
  };
};

export type Page<T> = {
  total: number;
  limit: number;
  offset: number;
  items: T[];
};
