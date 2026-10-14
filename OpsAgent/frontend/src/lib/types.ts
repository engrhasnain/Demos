/** What the backend sends. */

export type Row = Record<string, string | number | null>;

export type Evidence = {
  capability: string;
  asks: string;
  rows: Row[];
  columns: string[];
  sql: string;
  parameters: Record<string, string | number | null>;
  read_at: string;
  duration_ms: number;
  filter_applied: string;
  row_count: number;
  age_seconds: number;
  stale: boolean;
};

export type ProposalRow = {
  id: number;
  reference: string;
  raised_at: string | null;
  kind: string;
  summary: string;
  detail: Record<string, unknown>;
  needs_role: string;
  needs_role_label: string;
  status: "proposed" | "approved" | "declined";
  decided_by: string | null;
  decided_at: string | null;
  note: string;
  question_id: number | null;
};

export type Answer = {
  question: string;
  question_id: number | null;
  reading: string;
  text: string;
  evidence: Evidence[];
  refused: string;
  seconds: number;
  engine: string;
  injection_seen: boolean;
  ok: boolean;
  rows_read: number;
  queries: number;
  proposals: ProposalRow[];
  reach?: {
    everything: boolean;
    summary: string;
    customers: number | null;
    suppliers: number | null;
  };
};

export type Capability = {
  name: string;
  asks: string;
  sql: string;
  parameters: { name: string; kind: string; required: boolean; note: string }[];
  scope_column: string | null;
  columns: string[];
  needs_role: string;
  needs_role_label: string;
  whole_company: boolean;
};

export type QuestionRow = {
  id: number;
  asked_at: string | null;
  asked_by: string | null;
  text: string;
  reading: string;
  answer: string;
  refused: string;
  seconds: number;
  engine: string;
  injection_seen: boolean;
  queries: number;
};

export type AccessEntry = {
  id: number;
  occurred_at: string | null;
  who: string;
  capability: string;
  parameters: Record<string, unknown>;
  allowed: boolean;
  refusal: string;
  rows_returned: number;
  filter_applied: string;
};

export type DocumentRow = {
  id: number;
  reference: string;
  kind: string;
  subject: string;
  received_on: string | null;
  body: string;
};

export type Criterion = {
  name: string;
  question: string;
  bar: number;
  unit: string;
  lower_is_better?: boolean;
  value?: number;
  measured?: string;
  passed?: boolean;
};

export type RedTeamRow = {
  name: string;
  route?: string;
  family?: string;
  wants?: string;
  held: boolean;
  leaked?: number;
  noticed?: boolean;
  expected_unnoticed?: boolean;
  detail: string;
  account?: string;
};

export type Evaluation = {
  started_at: string;
  seconds: number;
  engine: string;
  criteria: Criterion[];
  passed: boolean;
  statement: string;
  answers: {
    asked: number;
    right: number;
    share: number;
    traceable: number;
    traceable_share: number;
    slowest_seconds: number;
    misses: string[];
  };
  permissions: {
    attacks: number;
    leaked_rows: number;
    held: number;
    accounts: {
      account: string;
      role: string;
      customers_granted: number;
      suppliers_granted: number;
      attacks: number;
      leaked: number;
    }[];
    results: RedTeamRow[];
    breaches: RedTeamRow[];
  };
  injections: {
    attacks: number;
    obeyed: number;
    held: number;
    noticed: number;
    slipped_past_the_filter: number;
    rows_written: number;
    proposals_approved_by_itself: number;
    results: RedTeamRow[];
  };
};

export type DemoPerson = {
  email: string;
  name: string;
  role: string;
  reach: {
    everything: boolean;
    summary: string;
    customers: number | null;
    suppliers: number | null;
  };
};

export type PlanStep = {
  capability: string;
  parameters: Record<string, string | number | null>;
  from_step: number | null;
  takes: string;
};

export type QuestionDetail = QuestionRow & {
  plan: PlanStep[];
  evidence: Omit<Evidence, "age_seconds" | "stale">[];
};

export type Health = {
  status: string;
  service: string;
  engine: string;
  capabilities: number;
  questions_asked: number;
  storage_is_temporary: boolean;
  warnings: string[];
};

export type DemoState = {
  loaded: boolean;
  customers: number;
  suppliers: number;
  orders: number;
  people: number;
  storage_is_temporary: boolean;
};
