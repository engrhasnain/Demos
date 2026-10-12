/**
 * Talking to the backend.
 *
 * One place that knows the address, the sign-in token and how an error from
 * the server turns into a sentence a person can read.
 */

// Local development talks to the backend on port 8000. Production builds read
// an empty value from frontend/.env.production and call /api/... on their own
// origin, which vercel.json routes to the backend: no CORS, no address to set.
export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8000";

const TOKEN_KEY = "quoteagent.token";
const USER_KEY = "quoteagent.user";

export type SignedInUser = {
  id: number;
  email: string;
  full_name: string;
  role: string;
  role_label: string;
  language: string;
};

export function readToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function readUser(): SignedInUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as SignedInUser) : null;
  } catch {
    return null;
  }
}

export function storeSession(token: string, user: SignedInUser): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    /* a private window without storage still works for this session */
  }
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  } catch {
    /* nothing to clear */
  }
}

export class ApiError extends Error {
  status: number;
  detail: unknown;

  constructor(status: number, message: string, detail: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

function describe(detail: unknown, status: number): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const first = detail[0] as { msg?: string; loc?: string[] } | undefined;
    if (first?.msg) return first.msg;
  }
  if (detail && typeof detail === "object") {
    const asRecord = detail as Record<string, unknown>;
    if (typeof asRecord.statement === "string") return asRecord.statement;
    if (typeof asRecord.detail === "string") return asRecord.detail;
  }
  if (status === 401) return "Please sign in again.";
  if (status === 403) return "You do not have permission to do that.";
  return `The server returned ${status}.`;
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
};

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const token = readToken();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? (options.body === undefined ? "GET" : "POST"),
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiError(
      0,
      API_URL
        ? `The backend at ${API_URL} did not answer. Start it with: uvicorn app.main:app --reload --app-dir backend`
        : "The backend did not answer. It may still be starting; try again in a moment.",
      cause,
    );
  }

  if (response.status === 204) return undefined as T;

  const text = await response.text();
  let payload: unknown = text;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      payload = text;
    }
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === "object" && "detail" in payload
        ? (payload as { detail: unknown }).detail
        : payload;
    throw new ApiError(response.status, describe(detail, response.status), detail);
  }

  return payload as T;
}

export const api = {
  get: <T>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: body ?? {} }),
};

export function documentUrl(path: string): string {
  return `${API_URL}${path}`;
}
