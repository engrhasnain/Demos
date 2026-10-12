/**
 * Plain words for figures, dates and codes.
 *
 * The server sends money as exact strings and counts as numbers. Nothing in
 * here works anything out: it only sets what the server sent the way a
 * person reads it. Codes (country, currency) become words, because the
 * screen never shows an abbreviation.
 */

const GROUPED = new Intl.NumberFormat("en-GB");

export function count(value: number | string | null | undefined): string {
  const number = Number(value ?? 0);
  return Number.isFinite(number) ? GROUPED.format(Math.round(number)) : "0";
}

/** A money string from the server, grouped, with its two decimals. */
export function money(value: number | string | null | undefined, decimals = 2): string {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return String(value ?? "");
  return number.toLocaleString("en-GB", {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

/** "6.00 million", for the big figures on a band; the panel shows it exact. */
export function millions(value: number | string | null | undefined, decimals = 2): string {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return String(value ?? "");
  if (Math.abs(number) >= 1_000_000) {
    return `${(number / 1_000_000).toLocaleString("en-GB", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })} million`;
  }
  return money(number, 0);
}

export function decimal(value: number | string | null | undefined, places = 1): string {
  const number = Number(value ?? 0);
  if (!Number.isFinite(number)) return "0";
  return number.toLocaleString("en-GB", {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  });
}

export function percent(share: number, places = 0): string {
  return `${(share * 100).toLocaleString("en-GB", {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  })}%`;
}

export function plural(value: number, one: string, many?: string): string {
  return `${count(value)} ${Math.round(value) === 1 ? one : many ?? `${one}s`}`;
}

export function days(value: number | string): string {
  const number = Number(value);
  if (!Number.isFinite(number)) return "";
  const rounded = Math.round(number * 10) / 10;
  const text = Number.isInteger(rounded) ? count(rounded) : decimal(rounded, 1);
  return `${text} ${rounded === 1 ? "day" : "days"}`;
}

/** Cover as words: "never runs out" when nothing is selling. */
export function cover(daysOfCover: number): string {
  if (!Number.isFinite(daysOfCover) || daysOfCover > 900) return "Never runs out";
  return days(Math.round(daysOfCover));
}

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function parse(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const date = new Date(iso.length === 10 ? `${iso}T00:00:00` : iso);
  return Number.isNaN(date.getTime()) ? null : date;
}

/** "19 December 2026" */
export function dateLong(iso: string | null | undefined): string {
  const date = parse(iso);
  if (!date) return "";
  return `${date.getDate()} ${MONTHS[date.getMonth()]} ${date.getFullYear()}`;
}

/** "19 December" */
export function dayMonth(iso: string | null | undefined): string {
  const date = parse(iso);
  if (!date) return "";
  return `${date.getDate()} ${MONTHS[date.getMonth()]}`;
}

/** "5 October 2026, 15:10" */
export function dateTime(iso: string | null | undefined): string {
  const date = parse(iso);
  if (!date) return "";
  const hours = String(date.getHours()).padStart(2, "0");
  const minutes = String(date.getMinutes()).padStart(2, "0");
  return `${dateLong(iso)}, ${hours}:${minutes}`;
}

export function monthName(index: number): string {
  return MONTHS[((index % 12) + 12) % 12];
}

/** Add whole days to an ISO date, as a Date. */
export function addDays(iso: string, offset: number): Date {
  const date = parse(iso) ?? new Date();
  const next = new Date(date);
  next.setDate(next.getDate() + offset);
  return next;
}

export function isoOf(date: Date): string {
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${date.getFullYear()}-${month}-${day}`;
}

export const COUNTRY_NAMES: Record<string, string> = {
  TW: "Taiwan",
  CN: "Mainland China",
  US: "United States",
  JP: "Japan",
  DE: "Germany",
  VN: "Vietnam",
};

export function countryName(code: string | null | undefined): string {
  if (!code) return "";
  return COUNTRY_NAMES[code] ?? code;
}

const CURRENCY_NAMES: Record<string, string> = {
  TWD: "Taiwan dollars",
  CNY: "Chinese yuan",
  USD: "United States dollars",
  JPY: "Japanese yen",
  EUR: "euros",
  VND: "Vietnamese dong",
};

export function currencyName(code: string | null | undefined): string {
  if (!code) return "";
  return CURRENCY_NAMES[code] ?? code;
}

/** The company's own currency, in words. */
export const BASE_CURRENCY = "Taiwan dollars";

/** "Chang Hsing Fastener (CN) Industrial Co." without the legal tail. */
export function shortSupplier(name: string): string {
  return name
    .replace(/\s*\((?:TW|CN|US|JP|DE|VN)\)\s*/g, " ")
    .replace(/\s*(Enterprise Co\.,? Ltd\.?|Industrial Co\.?|Co\.,? Ltd\.?|Corporation|Corp\.?|Ltd\.?|Inc\.?|GmbH|Co\.)$/i, "")
    .replace(/\s+/g, " ")
    .trim();
}

/** Flags the engine raises on a line, in words. */
export const FLAG_WORDS: Record<string, string> = {
  borrowed_forecast: "Forecast borrowed from its family",
  was_out_of_stock: "The shelf ran empty before",
  had_project_orders: "One-off project orders",
  unreliable_supplier: "Supplier runs late",
  supplier_timing_dominates: "Supplier timing dominates",
  shutdown_ahead: "Shutdown ahead",
  dead_stock: "Not moving",
};

export function flagWords(flag: string): string {
  return FLAG_WORDS[flag] ?? flag.replace(/_/g, " ");
}

/** Codes that sometimes ride along in the engine's own wording, as words. */
export function plain(text: string | null | undefined): string {
  if (!text) return "";
  return text
    .replace(/[a-z]+(?:_[a-z]+)+/g, (code) => code.replace(/_/g, " "))
    .replace(/\bTWD\b/g, "Taiwan dollars")
    .replace(/\bSKUs?\b/g, (word) => (word.endsWith("s") ? "parts" : "part"))
    .replace(/\bMOQ\b/g, "minimum order quantity")
    .replace(/\b(Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)\b/g, (month) => MONTH_WORDS[month] ?? month);
}

const MONTH_WORDS: Record<string, string> = {
  Jan: "January",
  Feb: "February",
  Mar: "March",
  Apr: "April",
  Jun: "June",
  Jul: "July",
  Aug: "August",
  Sep: "September",
  Sept: "September",
  Oct: "October",
  Nov: "November",
  Dec: "December",
};
