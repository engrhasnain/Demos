/**
 * Plain words for everything the server says in code.
 *
 * The server keeps capability names, role codes and filter expressions in
 * the shape the code needs. The screen shows them as a person would say
 * them. Nothing here changes a fact; it only changes how it is worded.
 */

export type DomainId = "orders" | "ledger" | "stock" | "conversations" | "shipments";

export type Domain = {
  id: DomainId;
  label: string;
  short: string;
  /** Which system the domain lives in, in words. */
  system: string;
};

/** The five systems OpsAgent reads across, around its core. */
export const DOMAINS: Domain[] = [
  { id: "orders", label: "Quotes and orders", short: "Orders", system: "Quotes, orders and customers" },
  { id: "ledger", label: "Invoices and ledger", short: "Ledger", system: "Invoices and what is owed" },
  { id: "stock", label: "Stock and reordering", short: "Stock", system: "Parts, suppliers and cover" },
  { id: "conversations", label: "Customer conversations", short: "Conversations", system: "The service desk" },
  { id: "shipments", label: "Shipments", short: "Shipments", system: "Carriers and held shipments" },
];

export const DOMAIN_BY_ID: Record<DomainId, Domain> = Object.fromEntries(
  DOMAINS.map((domain) => [domain.id, domain]),
) as Record<DomainId, Domain>;

/**
 * The nineteen reviewed queries, the domains each one reads, and its name in
 * words. The names are the catalogue's own; the list is checked against the
 * live catalogue wherever the catalogue is loaded.
 */
export const CAPABILITIES: Record<
  string,
  { words: string; domains: DomainId[]; needs: string }
> = {
  late_orders_for_customer: { words: "Late orders for one customer", domains: ["orders"], needs: "viewer" },
  why_an_order_is_late: { words: "Why one order is late", domains: ["orders", "shipments"], needs: "viewer" },
  orders_waiting_on_a_part: { words: "Orders waiting on a part", domains: ["orders", "stock"], needs: "viewer" },
  supplier_lead_time: { words: "A supplier's real delivery times", domains: ["stock"], needs: "viewer" },
  parts_from_supplier: { words: "Parts from one supplier", domains: ["stock"], needs: "viewer" },
  customers_exposed_to_supplier: { words: "Customers hit if a supplier stops", domains: ["stock", "orders"], needs: "viewer" },
  cover_if_supplier_stops: { words: "Weeks of stock if a supplier stops", domains: ["stock"], needs: "viewer" },
  customer_overview: { words: "One customer's overall position", domains: ["orders"], needs: "viewer" },
  customers_with_late_orders: { words: "Customers with late orders", domains: ["orders"], needs: "viewer" },
  unpaid_invoices_for_customer: { words: "What one customer owes", domains: ["ledger"], needs: "manager" },
  money_owed_in_total: { words: "Money owed in total", domains: ["ledger"], needs: "manager" },
  shipments_held: { words: "Shipments held up", domains: ["shipments"], needs: "viewer" },
  stock_for_part: { words: "Stock of one part", domains: ["stock"], needs: "viewer" },
  parts_running_out: { words: "Parts running out", domains: ["stock"], needs: "viewer" },
  open_tickets: { words: "Open service desk cases", domains: ["conversations"], needs: "viewer" },
  find_customer: { words: "Find a customer by name", domains: ["orders"], needs: "viewer" },
  find_supplier: { words: "Find a supplier by name", domains: ["stock"], needs: "viewer" },
  supplier_shutdowns: { words: "Supplier shutdowns", domains: ["stock"], needs: "viewer" },
  headline_numbers: { words: "Headline numbers for the week", domains: ["orders", "shipments", "conversations"], needs: "manager" },
};

export function capabilityWords(name: string): string {
  return CAPABILITIES[name]?.words ?? sentenceCase(name.replace(/_/g, " "));
}

export function domainsOf(name: string): DomainId[] {
  return CAPABILITIES[name]?.domains ?? ["orders"];
}

export function sentenceCase(text: string): string {
  if (!text) return text;
  return text.charAt(0).toUpperCase() + text.slice(1);
}

/** A column name from a query, as words: "worst_days_late" -> "worst days late". */
export function columnWords(column: string): string {
  return column.replace(/_/g, " ");
}

/* ------------------------------------------------------------------ */
/* Roles                                                               */
/* ------------------------------------------------------------------ */
export const ROLE_LABEL: Record<string, string> = {
  viewer: "Viewer",
  salesperson: "Salesperson",
  account_manager: "Account manager",
  manager: "Operations manager",
  director: "Director",
  administrator: "Administrator",
};

export const ROLE_RANK: Record<string, number> = {
  viewer: 0,
  salesperson: 10,
  account_manager: 20,
  manager: 30,
  director: 40,
  administrator: 50,
};

export function roleWords(role: string | undefined | null): string {
  if (!role) return "";
  return ROLE_LABEL[role] ?? sentenceCase(role.replace(/_/g, " "));
}

/** Does this role reach that requirement? Mirrors the server, fails closed. */
export function reaches(role: string | undefined | null, needed: string): boolean {
  if (!role) return false;
  if (role === "administrator") return true;
  const mine = ROLE_RANK[role];
  const want = ROLE_RANK[needed];
  if (mine === undefined || want === undefined) return false;
  return mine >= want;
}

/* ------------------------------------------------------------------ */
/* Sentences from the server                                            */
/* ------------------------------------------------------------------ */
/** Role codes and capability names inside a server sentence, as words. */
export function plain(text: string | null | undefined): string {
  if (!text) return "";
  return text
    .replace(/\bSQL\b/g, "database query")
    .replace(/\(([a-z_]+)\)/g, (all, role: string) => (ROLE_LABEL[role] ? `(${ROLE_LABEL[role].toLowerCase()})` : all))
    .replace(/\bthe ([a-z_]+) role\b/g, (_all, role: string) => `the ${roleWords(role).toLowerCase()} role`)
    .replace(/'([a-z]+(?:_[a-z]+)+)'/g, (_all, code: string) => `"${capabilityWords(code)}"`)
    .replace(/\b([a-z]+(?:_[a-z]+)+)\b/g, (_all, code: string) =>
      CAPABILITIES[code] ? capabilityWords(code).toLowerCase() : code.replace(/_/g, " "),
    );
}

/** The permission filter the server attached, in words. */
export function filterWords(filter: string | null | undefined, allowed = true): string {
  if (!allowed) return "Nothing ran";
  if (!filter) return "No filter: this person may see every account";
  const tail = /first (\d+) rows only/.exec(filter);
  const suffix = tail ? `, first ${tail[1]} rows only` : "";
  if (/no grants/.test(filter)) {
    const what = filter.startsWith("supplier") ? "suppliers" : "accounts";
    return `No ${what} granted, so no rows can come back`;
  }
  const match = /^(customer_id|supplier_id) in \((\d+) allowed\)/.exec(filter);
  if (match) {
    const what = match[1] === "customer_id" ? "accounts" : "suppliers";
    return `Only the ${match[2]} ${what} this person is granted${suffix}`;
  }
  return plain(filter);
}

/** Short form for tight places: "4 accounts" / "every account". */
export function filterShort(filter: string | null | undefined): string {
  if (!filter) return "every account";
  if (/no grants/.test(filter)) return "no grants";
  const match = /^(customer_id|supplier_id) in \((\d+) allowed\)/.exec(filter);
  if (match) return `${match[2]} ${match[1] === "customer_id" ? "accounts" : "suppliers"}`;
  return plain(filter);
}

/* ------------------------------------------------------------------ */
/* What became of a question                                            */
/* ------------------------------------------------------------------ */
export type Outcome = "answered" | "not-permitted" | "needs-review";

export function outcomeOf(refused: string | null | undefined, injection = false): Outcome {
  if (!refused) return injection ? "answered" : "answered";
  if (/needs the .* role|whole-company|Nothing on this account matches|not open to this account/i.test(refused)) {
    return "not-permitted";
  }
  return "needs-review";
}

export const OUTCOME: Record<Outcome, { label: string; tone: "pass" | "fail" | "warn" }> = {
  answered: { label: "Answered", tone: "pass" },
  "not-permitted": { label: "Refused — not permitted", tone: "fail" },
  "needs-review": { label: "Needs review", tone: "warn" },
};

/** Why a refusal happened, in one short line. */
export function refusalCause(refused: string): string {
  if (/needs the .* role|whole-company/i.test(refused)) return "Stopped by the role check before anything ran";
  if (/Nothing on this account matches/i.test(refused)) return "The row filter found nothing in this person's reach";
  if (/do not have a way/i.test(refused)) return "No reviewed query answers this; a person can add one";
  if (/steps and the limit/i.test(refused)) return "Too many steps for one question";
  return "Stopped before an answer was written";
}

/* ------------------------------------------------------------------ */
/* Time                                                                */
/* ------------------------------------------------------------------ */
/** The server stores times in UTC, sometimes without saying so. */
export function parseTime(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const text = /[zZ]|[+-]\d\d:?\d\d$/.test(iso) ? iso : `${iso}Z`;
  const when = new Date(text);
  return Number.isNaN(when.getTime()) ? null : when;
}

export function clock(iso: string | null | undefined): string {
  const when = parseTime(iso);
  if (!when) return "—";
  return when.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function dayAndClock(iso: string | null | undefined): string {
  const when = parseTime(iso);
  if (!when) return "—";
  return `${when.toLocaleDateString("en-GB", { day: "2-digit", month: "short" })} ${clock(iso)}`;
}

export function howOld(seconds: number): string {
  if (seconds < 90) return `${Math.max(0, Math.round(seconds))} seconds ago`;
  if (seconds < 5400) return `${Math.round(seconds / 60)} minutes ago`;
  return `${Math.round(seconds / 3600)} hours ago`;
}

export function grouped(value: number, decimals = 0): string {
  return value.toLocaleString("en-GB", { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
}

export function cell(value: string | number | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "number") {
    return Number.isInteger(value) ? grouped(value) : grouped(value, 2);
  }
  return value;
}

export function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}
