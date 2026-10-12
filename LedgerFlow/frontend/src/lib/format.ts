/**
 * Showing numbers and words.
 *
 * Money arrives from the server as an exact decimal string and is never
 * turned into a JavaScript number for display, because that is how cents go
 * missing. It is grouped by splitting the string. A number is only parsed
 * where it drives an animation (a count-up or a bar), and the last frame of
 * any count-up is always the server's own text.
 */

export function money(value: string | null | undefined, currency?: string): string {
  if (value === null || value === undefined || value === "") return "—";
  const trimmed = value.trim();
  const negative = trimmed.startsWith("-");
  const [whole, decimals = ""] = trimmed.replace("-", "").split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  const padded = (decimals + "00").slice(0, 2);
  const text = `${negative ? "-" : ""}${grouped}.${padded}`;
  return currency ? `${text} ${currency}` : text;
}

export function quantity(value: string | null | undefined): string {
  if (value === null || value === undefined || value === "") return "—";
  const [whole, decimals] = value.split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  if (!decimals || /^0+$/.test(decimals)) return grouped;
  return `${grouped}.${decimals.replace(/0+$/, "")}`;
}

/** For animation only: never shown as the final figure. */
export function asNumber(value: string | number | null | undefined): number {
  if (typeof value === "number") return value;
  if (!value) return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

export function isZero(value: string | null | undefined): boolean {
  return !value || asNumber(value) === 0;
}

export function count(value: number | undefined | null): string {
  if (value === null || value === undefined) return "—";
  return value.toLocaleString("en-GB");
}

export function dateOnly(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value.length === 10 ? `${value}T00:00:00` : value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
}

export function dateAndTime(value: string | null | undefined): string {
  if (!value) return "—";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString("en-GB", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

/** 18:04:19, for mono timestamps in feeds and timelines. */
export function clock(value: string | null | undefined): string {
  if (!value) return "--:--:--";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

export function duration(milliseconds: number): string {
  if (!milliseconds) return "instant";
  if (milliseconds < 1000) return `${milliseconds} ms`;
  return `${(milliseconds / 1000).toFixed(2)} s`;
}

export function initials(name: string): string {
  const parts = name.split(/\s+/).filter(Boolean);
  if (!parts.length) return "?";
  return (parts[0][0] + (parts.length > 1 ? parts[parts.length - 1][0] : "")).toUpperCase();
}

export function shorten(text: string, length: number): string {
  const clean = (text || "").replace(/\s+/g, " ").trim();
  return clean.length > length ? `${clean.slice(0, length - 1)}…` : clean;
}

/** Plain words for the codes the server uses internally. */
const LEDGERS: Record<string, string> = {
  taiwan_ledger: "Taiwan ledger",
  united_states_ledger: "United States ledger",
};

export function ledgerName(code: string): string {
  return LEDGERS[code] ?? code.replace(/_/g, " ");
}

export function engineWords(engine: string | null | undefined): string {
  if (!engine) return "deterministic code";
  if (engine === "built-in") return "the built-in engine";
  if (engine === "external") return "an external model";
  return `the ${engine} engine`;
}
