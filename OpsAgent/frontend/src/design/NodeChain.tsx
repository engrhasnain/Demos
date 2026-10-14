"use client";

/**
 * NodeChain - a vertical chain of nodes on one solid line.
 *
 * Used for timelines, worked calculations, guided steps. The line fills from
 * the top when the chain scrolls into view, the items rise in one after
 * another, and while `live` a glowing node travels down the line, ringing
 * each node as it passes (the timing is measured from the real positions, so
 * the ring and the pulse meet). Off screen the loop pauses.
 */

import { useEffect, useLayoutEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";

import type { ChipTone } from "./StatusChip";

export type ChainItem = {
  key: string;
  tone?: ChipTone;
  state?: "done" | "active" | "waiting";
  marker?: ReactNode;
  content: ReactNode;
};

const useIsomorphicLayoutEffect = typeof window === "undefined" ? useEffect : useLayoutEffect;

export function NodeChain({
  items,
  live = true,
  cycle,
  fill = 1,
  className = "",
  stagger = 70,
}: {
  items: ChainItem[];
  live?: boolean;
  /** One trip of the pulse plus a rest, in milliseconds. */
  cycle?: number;
  /** How much of the line is filled with the accent, 0..1. */
  fill?: number;
  className?: string;
  stagger?: number;
}) {
  const list = useRef<HTMLOListElement>(null);
  const [shown, setShown] = useState(false);
  const [onScreen, setOnScreen] = useState(true);
  const [geometry, setGeometry] = useState<{ top: number; height: number; at: number[] }>({
    top: 15,
    height: 0,
    at: [],
  });

  useEffect(() => {
    const element = list.current;
    if (!element || typeof IntersectionObserver === "undefined") {
      setShown(true);
      return;
    }
    const observer = new IntersectionObserver(
      ([entry]) => {
        setOnScreen(entry.isIntersecting);
        if (entry.isIntersecting) setShown(true);
      },
      { rootMargin: "0px 0px -6% 0px", threshold: 0.05 },
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useIsomorphicLayoutEffect(() => {
    const element = list.current;
    if (!element) return;
    const measure = () => {
      // Layout offsets, not screen boxes: the items are still translated
      // while they wait to rise in, and offsets ignore transforms.
      const rows = Array.from(element.querySelectorAll<HTMLElement>(":scope > li"));
      if (!rows.length) return;
      const centres = rows.map((row) => {
        const node = row.querySelector<HTMLElement>(":scope > .ds-chain-node");
        return row.offsetTop + (node ? node.offsetTop + node.offsetHeight / 2 : 15);
      });
      const first = centres[0];
      const height = Math.max(1, centres[centres.length - 1] - first);
      setGeometry({ top: first, height, at: centres.map((c) => (c - first) / height) });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [items.length]);

  const length = cycle ?? Math.max(3200, Math.min(9000, items.length * 520));

  return (
    <ol
      ref={list}
      className={`ds-chain ${className}`}
      data-shown={shown ? "" : undefined}
      data-live={live && items.length > 1 ? "" : undefined}
      data-paused={onScreen ? undefined : ""}
      style={
        {
          "--chain-cycle": `${length}ms`,
          "--chain-h": `${geometry.height}px`,
          "--chain-fill": fill,
        } as CSSProperties
      }
    >
      <span className="ds-chain-line" aria-hidden style={{ top: geometry.top, bottom: "auto", height: geometry.height }}>
        <span />
      </span>
      <span className="ds-chain-pulse" aria-hidden style={{ top: geometry.top }} />
      {items.map((item, index) => (
        <li
          key={item.key}
          className="ds-chain-item ds-reveal"
          data-shown={shown ? "" : undefined}
          data-tone={item.tone}
          data-state={item.state}
          style={
            {
              "--ds-d": `${Math.min(index, 16) * stagger}ms`,
              "--chain-at": geometry.at[index] ?? 0,
            } as CSSProperties
          }
        >
          <span className="ds-chain-node" aria-hidden>
            {item.marker}
          </span>
          {item.content}
        </li>
      ))}
    </ol>
  );
}
