/**
 * Formatting and plain words.
 *
 * The server speaks in codes ("escalated", "find_slots"); the screen speaks in
 * words. Every code that reaches the page goes through one of these maps.
 */

import type { ChipTone } from "@/design/StatusChip";
import type { Conversation, ConversationBrief, Turn } from "@/lib/types";

export function count(value: number | null | undefined): string {
  return (value ?? 0).toLocaleString("en-GB");
}

export function percent(value: number | null | undefined, decimals = 1): string {
  const number = Number(value ?? 0);
  return `${number.toLocaleString("en-GB", {
    minimumFractionDigits: number % 1 === 0 ? 0 : decimals,
    maximumFractionDigits: decimals,
  })}%`;
}

const CURRENCY_WORDS: Record<string, string> = {
  TWD: "Taiwan dollars",
  USD: "US dollars",
  EUR: "euros",
  JPY: "yen",
};

export function money(amount: string | number, currency?: string): string {
  const number = Number(amount);
  const text = Number.isFinite(number)
    ? number.toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    : String(amount);
  if (!currency) return text;
  return `${text} ${CURRENCY_WORDS[currency] ?? currency}`;
}

/** Timestamps from the server are UTC without a zone marker. */
export function parseWhen(value: string | null | undefined): Date | null {
  if (!value) return null;
  const hasZone = /[zZ]|[+-]\d\d:?\d\d$/.test(value);
  const date = new Date(hasZone ? value : `${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function clock(value: string | null | undefined): string {
  const date = parseWhen(value);
  if (!date) return "--:--";
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" });
}

export function dayAndTime(value: string | null | undefined): string {
  const date = parseWhen(value);
  if (!date) return "";
  return date.toLocaleString("en-GB", {
    weekday: "short",
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function taipeiClock(now = new Date()): string {
  return now.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Taipei",
  });
}

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
}

export function shorten(text: string, length: number): string {
  const clean = (text || "").replace(/\s+/g, " ").trim();
  return clean.length > length ? `${clean.slice(0, length - 1)}…` : clean;
}

/* ------------------------------------------------------------------ */
/* Channels                                                            */
/* ------------------------------------------------------------------ */
export const CHANNEL_WORDS: Record<string, string> = {
  web: "Website",
  line: "LINE",
};

export function channelWord(channel: string): string {
  return CHANNEL_WORDS[channel] ?? channel;
}

/* ------------------------------------------------------------------ */
/* What the desk did, in words                                         */
/* ------------------------------------------------------------------ */
export const TOOL_WORDS: Record<string, string> = {
  ask_to_verify: "Asked who they are",
  order_status: "Looked up the order",
  quote_status: "Looked up the quotation",
  find_slots: "Searched the technician diaries",
  book_visit: "Booked a technician",
  propose_return: "Proposed a return",
  raise_ticket: "Handed to a person",
  opening_hours: "Read the office hours",
};

export function toolWord(tool: string): string {
  if (!tool) return "Replied";
  return TOOL_WORDS[tool] ?? tool.replace(/_/g, " ");
}

export function engineWord(engine: string | null | undefined): string {
  if (!engine || engine === "built-in") return "Built-in engine";
  if (engine === "external") return "Hosted model";
  return `${engine} engine`;
}

/* ------------------------------------------------------------------ */
/* Where a conversation stands                                         */
/* ------------------------------------------------------------------ */
export type Outcome = "booked" | "handed" | "verifying" | "answered" | "refused" | "open";

export const OUTCOME_WORDS: Record<Outcome, { label: string; tone: ChipTone }> = {
  booked: { label: "Booked", tone: "pass" },
  handed: { label: "Handed to a person", tone: "warn" },
  verifying: { label: "Verifying", tone: "accent" },
  answered: { label: "Answered", tone: "pass" },
  refused: { label: "Held back", tone: "fail" },
  open: { label: "Waiting", tone: "neutral" },
};

export function outcomeOf(conversation: Conversation): Outcome {
  const turns = conversation.turns ?? [];
  if (turns.some((turn) => turn.tool === "book_visit" && turn.tool_result && "reference" in turn.tool_result)) {
    return "booked";
  }
  if (conversation.status === "escalated" || conversation.ticket) return "handed";
  const desk = turns.filter((turn) => turn.speaker === "desk");
  const last = desk[desk.length - 1];
  if (!last) return "open";
  if (!conversation.verified && last.tool === "ask_to_verify") return "verifying";
  if (last.refusal) return "refused";
  return "answered";
}

export function outcomeOfBrief(brief: ConversationBrief): Outcome {
  if (brief.status === "escalated" || brief.ticket) return "handed";
  if (brief.status === "resolved") return /That is booked|已為您預約/.test(brief.last_said) ? "booked" : "answered";
  if (!brief.turns) return "open";
  if (!brief.verified && /order number and the email|訂單號碼/i.test(brief.last_said)) return "verifying";
  if (/no record of that|沒有這筆訂單/i.test(brief.last_said)) return "refused";
  return "answered";
}

export const STATUS_WORDS: Record<string, string> = {
  open: "Open",
  resolved: "Handled",
  escalated: "With a person",
};

export function lastCustomerLine(turns: Turn[]): string {
  for (let index = turns.length - 1; index >= 0; index -= 1) {
    if (turns[index].speaker === "customer") return turns[index].text;
  }
  return "";
}

/** Server codes in running text ("key_account") become words. */
export function plain(text: string): string {
  if (!text) return text;
  return text.replace(/(^|[^A-Za-z0-9-])([a-z]+(?:_[a-z]+)+)(?=$|[^A-Za-z0-9-])/g, (_all, lead: string, code: string) =>
    `${lead}${code.replace(/_/g, " ")}`,
  );
}
