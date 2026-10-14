/** The shapes the backend sends. */

export type Action = { code: string; label: string };

export type Reply = {
  text: string;
  intent: string;
  confidence: number;
  tool: string;
  tool_result: Record<string, unknown>;
  refusal: string;
  actions: Action[];
  needs_verification: boolean;
  resolved: boolean;
  escalated: boolean;
  ticket_reference: string;
  engine: string;
  duration_ms: number;
};

export type Turn = {
  id: number;
  at: string | null;
  speaker: "customer" | "desk" | "staff";
  text: string;
  intent: string;
  intent_label: string;
  confidence: number;
  tool: string;
  tool_result: Record<string, unknown> | null;
  refusal: string;
  engine: string;
  duration_ms: number;
  attachment: string;
};

export type TicketBrief = {
  reference: string;
  reason: string;
  reason_label: string;
  reply_by: string | null;
  reply_wording: string;
  status: string;
};

export type Conversation = {
  reference: string;
  channel: string;
  status: string;
  language: string;
  intent: string;
  intent_label: string;
  verified: boolean;
  verified_at: string | null;
  locked: boolean;
  attempts: number;
  customer: { name: string; code: string; country: string; city: string } | null;
  contact: { name: string; email: string } | null;
  ticket: TicketBrief | null;
  turns: Turn[];
};

export type ConversationBrief = {
  reference: string;
  channel: string;
  status: string;
  intent: string;
  intent_label: string;
  customer: string | null;
  verified: boolean;
  turns: number;
  last_said: string;
  at: string | null;
  ticket: string | null;
};

export type Ticket = {
  reference: string;
  conversation: string;
  customer: string | null;
  reason: string;
  reason_label: string;
  summary: string;
  reply_by: string | null;
  reply_wording: string;
  status: string;
  assigned_to: { name: string } | null;
  at: string | null;
};

export type ReturnRequest = {
  reference: string;
  customer: string | null;
  order: string | null;
  part_code: string;
  quantity: number;
  reported: string;
  triage: string;
  triage_label: string;
  triage_confidence: number;
  who_usually_pays: string;
  triage_detail: {
    confident_enough?: boolean;
    reasons?: string[];
    [key: string]: unknown;
  };
  within_warranty: boolean;
  warranty_detail: { clause?: string; note?: string; detail?: Record<string, unknown> };
  photo_name: string;
  status: string;
  decided_by: { name: string } | null;
  decision_note: string;
  at: string | null;
};

export type Visit = {
  reference: string;
  customer: string | null;
  technician: string | null;
  starts_at: string | null;
  minutes: number;
  city: string;
  status: string;
};

export type AccessRow = {
  id: number;
  at: string | null;
  tool: string;
  arguments: Record<string, unknown>;
  allowed: boolean;
  refusal: string;
  rows_returned: number;
  conversation_id: number | null;
};

export type Dashboard = {
  conversations: number;
  resolved: number;
  escalated: number;
  handled_share: number;
  open_tickets: number;
  returns_waiting: number;
  visits_booked: number;
  refused_attempts: number;
  by_status: { status: string; count: number }[];
  by_intent: { intent: string; label: string; count: number }[];
  desk_open: boolean;
  next_open: string | null;
  customers: number;
  technicians: number;
  engine: string;
  line_configured: boolean;
};

export type Criterion = {
  name: string;
  question: string;
  bar: number;
  stretch?: number;
  unit: string;
  value: number;
  measured: string;
  passed: boolean;
  stretch_met?: boolean;
};

export type Evidence = {
  started_at: string;
  seconds: number;
  engine: string;
  criteria: Criterion[];
  passed: boolean;
  statement: string;
  conversations: {
    conversations: number;
    replies: number;
    handled: number;
    escalated: number;
    share: number;
    missing_human: number;
    human_share: number;
    by_intent: {
      intent: string;
      label: string;
      seen: number;
      handled: number;
      escalated: number;
      share: number;
    }[];
    misses: string[];
  };
  redteam: {
    attacks: number;
    attempts: number;
    refused: number;
    leaks: number;
    leak_detail: Record<string, unknown>[];
    results: { name: string; family: string; held: boolean; detail: string }[];
    by_family: { family: string; label: string; attacks: number; held: number }[];
  };
  concurrency: {
    rounds: number;
    attempted: number;
    clashes: number;
    second_customer_offered_another: number;
  };
};

export type DemoState = {
  loaded: boolean;
  customers: number;
  engine: string;
  storage_is_temporary: boolean;
  storage_warning: string;
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
  engine: string;
  line: string;
  serverless: boolean;
};

export type LoadResult = {
  seconds: number;
  counts: Record<string, number>;
  state: DemoState;
};

export type VerifyResult = {
  ok: boolean;
  message: string;
  attempts_left: number;
  locked: boolean;
  conversation: Conversation;
};

export type SayResult = { reply: Reply; conversation: Conversation };

export type Slot = {
  key: string;
  technician_id: number;
  technician: string;
  starts_at: string;
  shown_as: string;
  minutes: number;
  city: string;
  travel_minutes: number;
};
