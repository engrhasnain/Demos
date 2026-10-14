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

const RETRY_DELAYS_MS = [1500, 3000, 6000];

type UseLoadOptions = {
  /** Opt-in: on initial fetch failure, auto-retry with backoff (~1.5s/3s/6s) before surfacing an error. */
  retry?: boolean;
};

/** Fetch once, with a reload handle and a readable error. */
export function useLoad<T>(
  path: string | null,
  dependencies: unknown[] = [],
  options: UseLoadOptions = {},
): Loaded<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(Boolean(path));
  const [nonce, setNonce] = useState(0);
  const latest = useRef(0);
  const retry = options.retry ?? false;

  useEffect(() => {
    if (!path) {
      setLoading(false);
      return;
    }
    const attempt = ++latest.current;
    const controller = new AbortController();
    const timeouts: number[] = [];
    setLoading(true);
    setError(null);

    const attemptFetch = (retriesLeft: number) => {
      api
        .get<T>(path, controller.signal)
        .then((value) => {
          if (attempt === latest.current) {
            setData(value);
            setLoading(false);
          }
        })
        .catch((cause: unknown) => {
          if (controller.signal.aborted || attempt !== latest.current) return;
          if (retry && retriesLeft > 0) {
            const delay = RETRY_DELAYS_MS[RETRY_DELAYS_MS.length - retriesLeft] ?? RETRY_DELAYS_MS.at(-1)!;
            const handle = window.setTimeout(() => {
              if (attempt === latest.current) attemptFetch(retriesLeft - 1);
            }, delay);
            timeouts.push(handle);
            return;
          }
          setError(cause instanceof ApiError ? cause.message : String(cause));
          setLoading(false);
        });
    };

    attemptFetch(retry ? RETRY_DELAYS_MS.length : 0);

    return () => {
      controller.abort();
      timeouts.forEach((handle) => window.clearTimeout(handle));
    };
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
