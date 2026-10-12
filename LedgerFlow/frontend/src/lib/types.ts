/** The shapes the backend sends. Money is always a string, never a number. */

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

export type VendorBrief = {
  id: number;
  code: string;
  name: string;
  country: string;
  currency: string;
  bank_change_pending: boolean;
};

export type BankAccount = {
  id: number;
  bank: string;
  account_number: string;
  shown_as: string;
  account_name: string;
  is_current: boolean;
  verified_by: string;
  verified_at: string | null;
};

export type CallBack = {
  id: number;
  vendor_id: number;
  vendor_name: string;
  invoice_id: number | null;
  telephone_on_file: string;
  requested_change: {
    account_on_invoice?: string;
    accounts_on_file?: { bank: string; number: string }[];
    invoice_reference?: string;
  };
  status: string;
  created_at: string | null;
  completed_at: string | null;
  completed_by: UserBrief | null;
  outcome: string;
  note: string;
};

export type UserBrief = {
  id: number;
  name: string;
  email: string;
  role: string;
  role_label: string;
};

export type VendorDetail = VendorBrief & {
  name_on_invoices: string;
  entity_code: string;
  email: string;
  telephone: string;
  tax_identifier: string;
  tax_identifier_kind: string;
  payment_terms_days: number;
  tolerance_percent: string;
  tolerance_absolute: string;
  unordered_allowance: string;
  bank_accounts: BankAccount[];
  call_backs: CallBack[];
  invoices?: InvoiceBrief[];
};

export type InvoiceBrief = {
  id: number;
  reference: string;
  kind: string;
  vendor: VendorBrief | null;
  vendor_name: string;
  invoice_number: string;
  invoice_date: string | null;
  due_date: string | null;
  currency: string;
  total_amount: string;
  amount_in_base: string;
  approved_amount: string;
  held_amount: string;
  status: string;
  status_label: string;
  posted_untouched: boolean;
  touched_by_a_person: boolean;
  needs_a_person: boolean;
  exception_count: number;
  headline: string;
  headline_severity: string;
  received_at: string | null;
  read_with: string;
};

export type InvoiceLine = {
  id: number;
  line_number: number;
  page: number;
  part_code: string;
  description: string;
  quantity: string;
  unit: string;
  unit_price: string;
  line_total: string;
  match_result: string;
  match_label: string;
  order_line_id: number | null;
  received_to_date: string;
  billed_before: string;
  payable_quantity: string;
  payable_amount: string;
  held_amount: string;
  note: string;
  trace: Trace | null;
};

export type ExceptionRow = {
  id: number;
  kind: string;
  label: string;
  severity: string;
  summary: string;
  detail: Record<string, unknown>;
  raised_at: string | null;
  resolved_at: string | null;
  resolved_by: UserBrief | null;
  resolution: string;
};

export type ApprovalRow = {
  id: number;
  rule_code: string;
  title: string;
  reason: string;
  required_role: string;
  required_role_label: string;
  step: number;
  status: string;
  detail: Record<string, unknown>;
  requested_at: string | null;
  decided_by: UserBrief | null;
  decided_at: string | null;
  comment: string;
};

export type EventRow = {
  id: number;
  occurred_at: string | null;
  actor_type: string;
  actor_name: string;
  kind: string;
  summary: string;
  detail: Record<string, unknown>;
  duration_ms: number;
  engine: string;
};

export type PostingRow = {
  id: number;
  ledger: string;
  status: string;
  attempts: number;
  external_reference: string;
  amount: string;
  currency: string;
  last_error: string;
  posted_at: string | null;
  idempotency_key: string;
};

export type OrderLine = {
  id: number;
  line_number: number;
  part_code: string;
  description: string;
  quantity_ordered: string;
  unit: string;
  unit_price: string;
  line_total: string;
};

export type PurchaseOrder = {
  id: number;
  number: string;
  vendor: VendorBrief | null;
  entity_code: string;
  currency: string;
  ordered_on: string | null;
  status: string;
  lines: OrderLine[];
};

export type InvoiceDetail = InvoiceBrief & {
  as_read: {
    vendor_name: string;
    invoice_number: string;
    buyer_tax_identifier: string;
    seller_tax_identifier: string;
    purchase_order_number: string;
    bank_account: string;
    confidence: Record<string, number>;
  };
  net_amount: string;
  tax_amount: string;
  exchange_rate: string | null;
  entity_code: string | null;
  purchase_order: PurchaseOrder | null;
  document: {
    id: number;
    filename: string;
    content_type: string;
    size_bytes: number;
    page_count: number;
    kind: string;
    received_from: string;
    received_at: string | null;
    has_barcode: boolean;
  } | null;
  lines: InvoiceLine[];
  exceptions: ExceptionRow[];
  approvals: ApprovalRow[];
  events: EventRow[];
  postings: PostingRow[];
  blocking_reasons: string[];
  may_post_untouched: boolean;
  may_post_untouched_reason: string;
  hold_reason: string;
  trace: Trace | null;
  credits_invoice_id: number | null;
};

export type Dashboard = {
  invoices: number;
  posted: number;
  untouched: number;
  untouched_share: number;
  waiting_for_a_person: number;
  held_amount: string;
  posted_amount: string;
  open_call_backs: number;
  duplicates_stopped: number;
  by_status: { code: string; label: string; count: number }[];
  exception_kinds: {
    kind: string;
    label: string;
    severity: string;
    count: number;
  }[];
};

export type LedgerBill = {
  id: number;
  ledger: string;
  external_reference: string;
  vendor_name: string;
  invoice_number: string;
  amount: string;
  currency: string;
  posted_on: string | null;
};

export type Settings = {
  base_currency: string;
  business_tax_percent: number;
  auto_post_ceiling: number;
  two_step_approval: number;
  default_tolerance_percent: number;
  default_tolerance_absolute: number;
  default_unordered_allowance: number;
  late_arrival_days: number;
  reading_engine: string;
  statuses: { code: string; label: string; description: string }[];
  exception_kinds: { kind: string; label: string; severity: string }[];
  roles: { code: string; label: string }[];
};

export type DemoState = {
  loaded: boolean;
  batch_run: boolean;
  vendors: number;
  invoices: number;
  reading_engine: string;
  storage_is_temporary: boolean;
};

export type BatchItem = {
  key: string;
  title: string;
  what_it_tests: string;
  filename: string;
  expect: string;
  pages: number;
};

export type BatchResult = {
  seconds: number;
  processed: number;
  untouched: number;
  items: {
    key: string;
    title: string;
    what_it_tests: string;
    expect: string;
    error?: string;
    invoice: InvoiceBrief;
  }[];
  dashboard: Dashboard;
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

export type EvaluationReport = {
  id?: number;
  started_at: string;
  seconds: number;
  engine: string;
  sample_size: number;
  criteria: Criterion[];
  passed: boolean;
  misses: string[];
  statement: string;
};

export type Page<T> = {
  total: number;
  limit: number;
  offset: number;
  items: T[];
};
