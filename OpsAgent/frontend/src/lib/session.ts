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

/** Load a path whenever any of `keys` change. */
export function useLoad<T>(path: string | null, keys: unknown[] = []) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [tick, setTick] = useState(0);
  const reload = useCallback(() => setTick((value) => value + 1), []);

  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setLoading(true);
    api
      .get<T>(path, controller.signal)
      .then((out) => {
        setData(out);
        setError("");
      })
      .catch((cause) => {
        if (controller.signal.aborted) return;
        setError(cause instanceof ApiError ? cause.message : String(cause));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, tick, ...keys]);

  return { data, error, loading, reload, setData };
}
