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

type LoadOptions = {
  /** Opt-in: auto-retry a failed initial fetch a few times with backoff before giving up. */
  retry?: boolean;
};

/** Delays, in ms, between automatic retries when `retry` is enabled. */
const RETRY_DELAYS = [1500, 3000, 6000];

/** Fetch once, with a reload handle and a readable error. */
export function useLoad<T>(path: string | null, dependencies: unknown[] = [], options?: LoadOptions): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(path));
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);
  const retryAttempt = useRef(0);
  const retryEnabled = Boolean(options?.retry);

  useEffect(() => {
    if (!path) {
      setLoading(false);
      return;
    }
    const attempt = ++latest.current;
    const controller = new AbortController();
    let retryTimer: ReturnType<typeof window.setTimeout> | undefined;
    setLoading(true);
    setError(null);

    api
      .get<T>(path, controller.signal)
      .then((value) => {
        if (attempt === latest.current) {
          setData(value);
          setLoading(false);
          retryAttempt.current = 0;
        }
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted || attempt !== latest.current) return;
        setError(cause instanceof ApiError ? cause.message : String(cause));
        setLoading(false);
        if (retryEnabled && retryAttempt.current < RETRY_DELAYS.length) {
          const delay = RETRY_DELAYS[retryAttempt.current];
          retryAttempt.current += 1;
          retryTimer = setTimeout(() => {
            if (attempt === latest.current) setNonce((value) => value + 1);
          }, delay);
        }
      });

    return () => {
      controller.abort();
      if (retryTimer) clearTimeout(retryTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, nonce, retryEnabled, ...dependencies]);

  const reload = useCallback(() => {
    retryAttempt.current = 0;
    setNonce((value) => value + 1);
  }, []);
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
