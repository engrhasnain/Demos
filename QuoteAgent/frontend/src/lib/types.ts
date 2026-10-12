/** The shapes the backend sends. Money always arrives as a string. */

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

export type AttributeCheck = {
  attribute: string;
  label: string;
  requested: string;
  catalogue: string;
  agrees: boolean;
  severity: "must_agree" | "advisory";
};

export type Product = {
  id: number;
  sku: string;
  family: string;
  description: string;
  description_chinese: string;
  standard: string;
  attributes: Record<string, string>;
  attributes_in_words: string[];
  selling_unit: string;
  pack_size: number;
  weight_grams: string;
  commodity_code: string;
  country_of_origin: string;
  list_price: string;
  standard_cost: string;
  is_stocked: boolean;
  replenishment_lead_time_days: number;
  supplier: {
    id: number;
    name: string;
    country: string;
    lead_time_days: number;
    minimum_order_quantity: number;
  } | null;
};

export type DutyComponent = {
  component: string;
  label: string;
  rate_percent: string;
  published_rate_percent?: string;
  basis?: string;
  basis_value?: string;
  amount: string;
  authority?: string;
  note?: string;
};

export type FulfilmentOption = {
  code: string;
  label: string;
  detail: string;
  ready_date: string;
  lead_time_days: number;
  warehouse: string;
  split: boolean;
};

export type QuoteLine = {
  id: number;
  line_number: number;
  request_text: string;
  original_request_text: string;
  was_clarified: boolean;
  customer_reference: string;
  source_reference: string;
  requested_quantity: string;
  requested_unit: string;
  requested_attributes: Record<string, string>;
  settled_by_the_customer: Record<string, string>;
  status: string;
  status_label: string;
  blocking_reason: string;
  product: Product | null;
  match: {
    method: string;
    method_label: string;
    confidence: string;
    confidence_percent: string;
    reasons: string[];
    attribute_check: {
      family?: string;
      requested?: Record<string, string>;
      checks?: AttributeCheck[];
      notes?: string[];
    };
    alternatives: { sku: string; description: string; score: string; method: string }[];
    proposed_by: string;
    verified_by: string;
  };
  pricing: {
    quantity_billed: string;
    unit_of_sale: string;
    rounding_note: string;
    unit_price: string;
    price_source: string;
    price_source_label: string;
    price_source_reference: string;
    discount_percent: string;
    line_total: string;
    unit_cost: string;
    margin_percent: string;
    below_margin_floor: boolean;
    freight_share: string;
    insurance_share: string;
    import_duty: string;
    duty_breakdown: DutyComponent[];
    landed_total: string;
  };
  supply: { lead_time_days: number; options: FulfilmentOption[]; chosen: string };
  calculation_trace: Trace;
};

export type QuoteVersion = {
  id: number;
  version_number: number;
  status: string;
  currency: string;
  incoterm: string;
  incoterm_name: string;
  incoterm_explained: string;
  named_place: string;
  destination_country: string;
  valid_until: string | null;
  totals: {
    goods: string;
    freight: string;
    insurance: string;
    import_duty: string;
    grand_total: string;
    total_cost: string;
    margin_percent: string;
  };
  requested_discount_percent: string;
  needs_repricing: boolean;
  repricing_reason: string;
  change_log: ChangeLogEntry[];
  totals_trace: Trace;
  pricing_checksum: string;
  sent_at: string | null;
  document_format: string;
  exchange_rate: {
    id: number;
    pair: string;
    rate: string;
    as_of_date: string;
    source: string;
    locked_at: string | null;
  } | null;
  tariff_table: {
    id: number;
    version: string;
    title: string;
    signed_off: boolean;
    customs_broker: string;
  } | null;
  lines?: QuoteLine[];
  line_counts?: Record<string, number>;
};

export type ChangeLogEntry = {
  kind: string;
  line_number: number;
  description: string;
  before: Record<string, string>;
  after: Record<string, string>;
  note: string;
};

export type CaseSummary = {
  id: number;
  reference: string;
  subject: string;
  customer: { id: number; name: string; country: string } | null;
  contact_email: string;
  contact_name: string;
  language: string;
  status: string;
  status_label: string;
  status_description: string;
  is_waiting: boolean;
  incoterm: string;
  named_place: string;
  currency: string;
  owner: string;
  created_at: string;
  updated_at: string;
  version_count: number;
  current_version: number;
  line_count: number;
  grand_total: string;
};

export type CaseEvent = {
  id: number;
  occurred_at: string;
  actor_type: string;
  actor_name: string;
  kind: string;
  summary: string;
  detail: Record<string, unknown>;
  duration_ms: number;
  engine: string;
  model: string;
  input_tokens: number;
  output_tokens: number;
  cost_usd: string;
};

export type CaseMessage = {
  id: number;
  direction: "inbound" | "outbound";
  kind: string;
  sender: string;
  recipients: string[];
  subject: string;
  body: string;
  language: string;
  occurred_at: string;
  sent_at: string | null;
  awaiting_approval: boolean;
  attachments: {
    id: number;
    filename: string;
    content_type: string;
    size_bytes: number;
    read_with: string;
    note: string;
    row_count: number;
  }[];
};

export type Clarification = {
  id: number;
  line_number: number;
  round_number: number;
  kind: string;
  attribute: string;
  question: string;
  question_chinese: string;
  options: string[];
  status: string;
  answer: string;
  answer_understood_as: Record<string, unknown>;
  answered_at: string | null;
};

export type Approval = {
  id: number;
  rule_code: string;
  title: string;
  reason: string;
  required_role: string;
  required_role_label: string;
  status: string;
  detail: Record<string, unknown>;
  requested_at: string;
  decided_at: string | null;
  decided_by: string;
  comment: string;
};

export type SupplierRequest = {
  id: number;
  reference: string;
  supplier: { id: number; name: string; country: string; email: string };
  line_numbers: number[];
  status: string;
  sent_at: string;
  responded_at: string | null;
  response: Record<string, unknown>;
};

export type CaseDetail = {
  case: CaseSummary;
  status: {
    code: string;
    label: string;
    description: string;
    is_waiting: boolean;
    is_terminal: boolean;
    next_options: string[];
  };
  current_version: QuoteVersion | null;
  versions: QuoteVersion[];
  messages: CaseMessage[];
  questions: {
    rounds: {
      round_number: number;
      asked: number;
      answered: number;
      questions: Clarification[];
    }[];
    emails_sent: number;
    questions_asked: number;
    statement: string;
  };
  approvals: Approval[];
  outstanding_approvals: number;
  supplier_requests: SupplierRequest[];
  blocking_reasons: string[];
  elapsed: Record<string, string | number>;
};

export type SystemStatus = {
  application: string;
  environment: string;
  database: string;
  hosting?: string;
  storage_is_temporary?: boolean;
  storage_warning?: string;
  recommended_product_target?: number;
  data_loaded: boolean;
  counts: Record<string, number>;
  reasoning_engine: {
    active_engine: string;
    model: string;
    endpoint_configured: boolean;
    api_key_present: boolean;
    budget_usd_per_case: number;
    explanation: string;
    guarantee: string;
  };
  company: {
    name: string;
    description: string;
    warehouses: string[];
    base_currency: string;
  };
  policies: Record<string, number>;
};

export type LoadProgress = {
  running: boolean;
  stage: string;
  stage_label: string;
  stage_number: number;
  stage_count: number;
  done: number;
  total: number;
  percent: number;
  completed_stages: string[];
  finished_at: string | null;
  error: string;
  counts: Record<string, number>;
  stages: { key: string; label: string; done: boolean }[];
};

export type DemoStep = {
  number: number;
  title: string;
  what_we_do: string;
  what_you_see: string;
  needs_role: string;
};

export type AcceptanceCriterion = {
  key: string;
  name: string;
  pass_bar: string;
  measured: string;
  passed: boolean | null;
  sample: string;
  detail: Record<string, unknown>;
};

export type TariffTable = {
  id: number;
  version: string;
  title: string;
  effective_from: string;
  effective_to: string | null;
  status: string;
  owned_by: string;
  customs_broker: string;
  signed_off: boolean;
  signed_off_at: string | null;
  source_note: string;
  line_count: number;
  lines?: {
    id: number;
    commodity_code: string;
    origin_country: string;
    destination_country: string;
    component: string;
    rate_percent: string;
    charged_on: string;
    combined_cap_percent: string | null;
    not_stacked_with: string;
    authority: string;
    note: string;
  }[];
};
