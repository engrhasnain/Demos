"use client";

/**
 * Who is asking, as React state.
 *
 * The person is read from the browser's storage and followed through the
 * session event, so switching person anywhere (the header, the ask view,
 * the home page) changes what every view shows at once.
 */

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { api, ApiError, readUser, SESSION_EVENT, type SignedInUser } from "@/lib/api";

export function useSession(): { user: SignedInUser | null; checked: boolean } {
  const [user, setUser] = useState<SignedInUser | null>(null);
  const [checked, setChecked] = useState(false);

  useEffect(() => {
    const read = () => {
      setUser(readUser());
      setChecked(true);
    };
    read();
    window.addEventListener(SESSION_EVENT, read);
    window.addEventListener("storage", read);
    return () => {
      window.removeEventListener(SESSION_EVENT, read);
      window.removeEventListener("storage", read);
    };
  }, []);

  return { user, checked };
}

/** For pages that need somebody signed in: send everyone else home to choose. */
export function useSignedIn(): SignedInUser | null {
  const router = useRouter();
  const { user, checked } = useSession();
  useEffect(() => {
    if (checked && !user) router.replace("/?choose=1");
  }, [checked, user, router]);
  return user;
}

/** Backoff delays (ms) between automatic retries of a failed initial load. */
const RETRY_DELAYS = [1500, 3000, 6000];

/**
 * Load a path whenever any of `keys` change.
 *
 * Pass `retry: true` for a GET-shaped initial-state load that should not
 * just give up and show a blank page on one failed fetch: it will retry
 * automatically (roughly 1.5s/3s/6s) before surfacing `error` for good.
 * Default behaviour (no auto-retry) is unchanged for every other caller,
 * including anything that re-triggers on a mutating action.
 */
export function useLoad<T>(path: string | null, keys: unknown[] = [], options: { retry?: boolean } = {}) {
  const { retry = false } = options;
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    let cancelled = false;
    let attempt = 0;

    const run = () => {
      setLoading(true);
      api
        .get<T>(path, controller.signal)
        .then((out) => {
          if (cancelled) return;
          setData(out);
          setError("");
        })
        .catch((cause) => {
          if (controller.signal.aborted || cancelled) return;
          const message = cause instanceof ApiError ? cause.message : String(cause);
          if (retry && attempt < RETRY_DELAYS.length) {
            const delay = RETRY_DELAYS[attempt];
            attempt += 1;
            window.setTimeout(() => {
              if (!cancelled) run();
            }, delay);
            return;
          }
          setError(message);
        })
        .finally(() => {
          if (!controller.signal.aborted && !cancelled) setLoading(false);
        });
    };

    run();
    return () => {
      cancelled = true;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, retry, ...keys]);

  return { data, error, loading, reload, setData };
}
