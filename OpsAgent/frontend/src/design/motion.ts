"use client";

/**
 * Motion rules, as code.
 *
 * - Entrances use expo-out [0.16, 1, 0.3, 1], 0.5 to 0.9 s, 24 to 40 px of
 *   travel and a 60 to 90 ms stagger.
 * - Loops (canvas, pulses, live cards) run only while on screen and while
 *   the tab is visible.
 * - Only transform and opacity are animated.
 * - prefers-reduced-motion: loops stop, entrances are instant, canvases draw
 *   one still frame. Every hook here checks it.
 */

import { useCallback, useEffect, useState } from "react";

export const EASE_OUT = [0.16, 1, 0.3, 1] as const;
export const STAGGER_MS = 70;
export const REVEAL_MS = 800;

/** Expo-out as a function, for JavaScript-driven tweens (count-ups, canvas). */
export function easeOutExpo(t: number): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  return 1 - Math.pow(2, -10 * t);
}

export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || !window.matchMedia) return false;
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/** Live value of prefers-reduced-motion. */
export function useReducedMotion(): boolean {
  const [reduce, setReduce] = useState(false);
  useEffect(() => {
    if (!window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    setReduce(query.matches);
    const change = () => setReduce(query.matches);
    query.addEventListener?.("change", change);
    return () => query.removeEventListener?.("change", change);
  }, []);
  return reduce;
}

/**
 * True once the element has come into view (and stays true), or while it is
 * in view when `once` is false. Elements are treated as visible straight away
 * when IntersectionObserver is missing.
 *
 * Returns a callback ref, so an element that only appears after the data has
 * loaded is still observed.
 */
export function useInView<T extends Element>(
  options: { once?: boolean; rootMargin?: string; threshold?: number } = {},
): [(node: T | null) => void, boolean] {
  const { once = true, rootMargin = "0px 0px -8% 0px", threshold = 0.12 } = options;
  const [element, setElement] = useState<T | null>(null);
  const [inView, setInView] = useState(false);
  const ref = useCallback((node: T | null) => setElement(node), []);

  useEffect(() => {
    if (!element) return;
    if (typeof IntersectionObserver === "undefined") {
      setInView(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setInView(true);
          if (once) observer.disconnect();
        } else if (!once) {
          setInView(false);
        }
      },
      { rootMargin, threshold },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, [element, once, rootMargin, threshold]);

  return [ref, inView];
}

/** True while the page is visible, so loops can rest in a background tab. */
export function usePageVisible(): boolean {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const change = () => setVisible(document.visibilityState !== "hidden");
    change();
    document.addEventListener("visibilitychange", change);
    return () => document.removeEventListener("visibilitychange", change);
  }, []);
  return visible;
}

/** Scroll position as 0..1 of the page, and whether anything is scrolled. */
export function useScrollProgress(): { progress: number; scrolled: boolean } {
  const [state, setState] = useState({ progress: 0, scrolled: false });
  useEffect(() => {
    let frame = 0;
    const measure = () => {
      frame = 0;
      const root = document.documentElement;
      const max = Math.max(1, root.scrollHeight - window.innerHeight);
      const y = window.scrollY;
      setState((previous) => {
        const progress = Math.min(1, Math.max(0, y / max));
        const scrolled = y > 8;
        if (Math.abs(previous.progress - progress) < 0.002 && previous.scrolled === scrolled) {
          return previous;
        }
        return { progress, scrolled };
      });
    };
    const onScroll = () => {
      if (!frame) frame = requestAnimationFrame(measure);
    };
    measure();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);
  return state;
}
