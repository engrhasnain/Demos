/**
 * Talking to the backend.
 *
 * One place that knows the address, the sign-in token and how an error
 * from the server turns into a sentence a person can read.
 */

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:8005";

const TOKEN_KEY = "opsagent.token";
const USER_KEY = "opsagent.user";

export type Reach = {
  everything: boolean;
  summary: string;
  customers: number | null;
  suppliers: number | null;
};

export type SignedInUser = {
  id: number;
  email: string;
  name: string;
  role: string;
  role_label: string;
  reach?: Reach;
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

/** Told whenever the signed-in person changes, so every view can follow. */
export const SESSION_EVENT = "opsagent:session";

export function storeSession(token: string, user: SignedInUser): void {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    /* a private window without storage still works for this session */
  }
  window.dispatchEvent(new Event(SESSION_EVENT));
}

export function clearSession(): void {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
    window.localStorage.removeItem(USER_KEY);
  } catch {
    /* nothing to clear */
  }
  window.dispatchEvent(new Event(SESSION_EVENT));
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
    const first = detail[0] as { msg?: string } | undefined;
    if (first?.msg) return first.msg;
  }
  if (detail && typeof detail === "object") {
    const asRecord = detail as Record<string, unknown>;
    if (typeof asRecord.detail === "string") return asRecord.detail;
  }
  if (status === 401) return "Please sign in again.";
  if (status === 403) return "That is not open to this account.";
  return `The server returned ${status}.`;
}

type RequestOptions = {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  /** Use this token instead of the stored one (the first run asks as two people). */
  token?: string;
};

export async function request<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const token = options.token ?? readToken();
  const headers: Record<string, string> = { Accept: "application/json" };
  if (options.body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers.Authorization = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      method: options.method ?? (options.body === undefined ? "GET" : "POST"),
      headers,
      body:
        options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
      cache: "no-store",
    });
  } catch (cause) {
    throw new ApiError(
      0,
      `The server at ${API_URL} did not answer. Start the backend (see the read-me), then try again.`,
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
    throw new ApiError(
      response.status,
      describe(detail, response.status),
      detail,
    );
  }

  return payload as T;
}

export const api = {
  get: <T,>(path: string, signal?: AbortSignal) => request<T>(path, { signal }),
  post: <T,>(path: string, body?: unknown, token?: string) =>
    request<T>(path, { method: "POST", body: body ?? {}, token }),
};

/** Sign in as one of the people in the business, and remember it. */
export async function signInAs(email: string, password: string): Promise<SignedInUser> {
  const out = await request<{ access_token: string; user: SignedInUser }>("/api/auth/sign-in", {
    method: "POST",
    body: { email, password },
  });
  storeSession(out.access_token, out.user);
  return out.user;
}

/** Sign in without remembering it: a token for one piece of work. */
export async function tokenFor(email: string, password: string): Promise<string> {
  const out = await request<{ access_token: string }>("/api/auth/sign-in", {
    method: "POST",
    body: { email, password },
    token: "",
  });
  return out.access_token;
}
