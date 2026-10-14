"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";

type Loaded<T> = {
  data: T | null;
  error: string | null;
  loading: boolean;
  reload: () => void;
  setData: (value: T) => void;
};

/** Backoff schedule for a retried initial load: ~1.5s, 3s, 6s before giving up. */
const RETRY_DELAYS_MS = [1500, 3000, 6000];

/** Retry a GET-shaped attempt with backoff before finally rejecting. */
export async function withRetry<T>(attempt: () => Promise<T>, aborted: () => boolean): Promise<T> {
  for (let tryIndex = 0; ; tryIndex += 1) {
    try {
      return await attempt();
    } catch (cause) {
      if (aborted() || tryIndex >= RETRY_DELAYS_MS.length) throw cause;
      await new Promise((resolve) => setTimeout(resolve, RETRY_DELAYS_MS[tryIndex]));
      if (aborted()) throw cause;
    }
  }
}

/**
 * Fetch once, with a reload handle and a readable error.
 * Pass `{ retry: true }` to auto-retry a failed GET with backoff (~1.5s/3s/6s)
 * before surfacing the error — opt-in only, so existing (including mutating) callers are unaffected.
 */
export function useLoad<T>(
  path: string | null,
  dependencies: unknown[] = [],
  options: { retry?: boolean } = {},
): Loaded<T> {
  const { retry = false } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(path));
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);

  useEffect(() => {
    if (!path) {
      setLoading(false);
      return;
    }
    const attempt = ++latest.current;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    const isStale = () => controller.signal.aborted || attempt !== latest.current;
    const fetchOnce = () => api.get<T>(path, controller.signal);

    (retry ? withRetry(fetchOnce, isStale) : fetchOnce())
      .then((value) => {
        if (attempt === latest.current) {
          setData(value);
          setLoading(false);
        }
      })
      .catch((cause: unknown) => {
        if (isStale()) return;
        setError(cause instanceof ApiError ? cause.message : String(cause));
        setLoading(false);
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, nonce, retry, ...dependencies]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { data, error, loading, reload, setData };
}

/** Run a write, keeping track of which one is in flight. */
export function useAction() {
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const run = useCallback(
    async <T,>(key: string, work: () => Promise<T>, message?: string): Promise<T | null> => {
      setBusy(key);
      setError(null);
      setNote(null);
      try {
        const result = await work();
        if (message) setNote(message);
        return result;
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : String(cause));
        return null;
      } finally {
        setBusy(null);
      }
    },
    [],
  );

  return { busy, error, note, run, setError, setNote };
}

/** Poll while a condition holds, for the loading and evaluation screens. */
export function usePoll<T>(
  path: string | null,
  active: boolean,
  everyMilliseconds = 700,
): T | null {
  const [value, setValue] = useState<T | null>(null);

  useEffect(() => {
    if (!path || !active) return;
    let cancelled = false;

    const tick = async () => {
      try {
        const next = await api.get<T>(path);
        if (!cancelled) setValue(next);
      } catch {
        /* a missed poll is not worth interrupting the screen for */
      }
    };

    void tick();
    const handle = window.setInterval(tick, everyMilliseconds);
    return () => {
      cancelled = true;
      window.clearInterval(handle);
    };
  }, [path, active, everyMilliseconds]);

  return value;
}
