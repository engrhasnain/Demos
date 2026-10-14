"use client";

/**
 * LiveFeedCard - "LIVE ..." card that cycles through real records.
 *
 * Header: a mono title and a pulsing dot with where the data comes from.
 * Body: one record at a time - a solid status chip, a mono timestamp, a
 * title, a line of detail. Footer: one progress dash per record; the active
 * dash fills, and when it is full the next record rises in.
 *
 * The dash animation drives the timing, so pausing (pointer over the card,
 * keyboard focus inside it, card off screen) pauses both together. Under
 * reduced motion nothing advances on its own; the dashes still switch
 * records when pressed.
 */

import Link from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { StatusChip, type ChipTone } from "./StatusChip";
import { useInView } from "./motion";

export type FeedItem = {
  key: string;
  chip: { label: string; tone: ChipTone };
  stamp: string;
  title: ReactNode;
  body?: ReactNode;
  meta?: ReactNode;
  href?: string;
};

export function LiveFeedCard({
  title,
  source,
  items,
  interval = 4600,
  onIndex,
  surface = "dark",
  className = "",
  footNote,
}: {
  title: string;
  source: string;
  items: FeedItem[];
  interval?: number;
  onIndex?: (index: number) => void;
  surface?: "dark" | "light";
  className?: string;
  footNote?: ReactNode;
}) {
  const [active, setActive] = useState(0);
  const [leaving, setLeaving] = useState<number | null>(null);
  const [held, setHeld] = useState(false);
  const [ref, onScreen] = useInView<HTMLDivElement>({ once: false, threshold: 0.05, rootMargin: "0px" });

  const count = items.length;
  const safe = count ? active % count : 0;

  useEffect(() => {
    onIndex?.(safe);
  }, [safe, onIndex]);

  const go = (next: number) => {
    if (!count) return;
    const target = ((next % count) + count) % count;
    if (target === safe) return;
    setLeaving(safe);
    setActive(target);
  };

  if (!count) return null;
  const paused = held || !onScreen;

  return (
    <div
      ref={ref}
      className={`ds-feed ${className}`}
      data-surface={surface}
      onPointerEnter={() => setHeld(true)}
      onPointerLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
    >
      <div className="ds-feed-head">
        <span className="ds-mono-label ds-feed-title">{title}</span>
        <span className="ds-feed-source">
          <span className="ds-live-dot" aria-hidden />
          {source}
        </span>
      </div>

      <div className="ds-feed-body" aria-live="polite">
        {items.map((item, index) => {
          const state = index === safe ? "active" : index === leaving ? "leaving" : "waiting";
          const content = (
            <>
              <div className="ds-feed-meta">
                <StatusChip tone={item.chip.tone} surface={surface}>
                  {item.chip.label}
                </StatusChip>
                <span className="ds-feed-stamp">{item.stamp}</span>
              </div>
              <div className="ds-feed-item-title">{item.title}</div>
              {item.body && <div className="ds-feed-item-body">{item.body}</div>}
              {item.meta && <div className="ds-feed-item-meta">{item.meta}</div>}
            </>
          );
          return (
            <div
              key={item.key}
              className="ds-feed-item"
              data-state={state}
              aria-hidden={state !== "active"}
            >
              {item.href ? (
                <Link
                  href={item.href}
                  className="ds-feed-link"
                  tabIndex={state === "active" ? 0 : -1}
                >
                  {content}
                </Link>
              ) : (
                content
              )}
            </div>
          );
        })}
      </div>

      <div className="ds-feed-foot">
        <div className="ds-feed-dashes" role="tablist" aria-label={`${title}: choose a record`}>
          {items.map((item, index) => (
            <button
              key={item.key}
              type="button"
              role="tab"
              aria-selected={index === safe}
              aria-label={`Show record ${index + 1} of ${count}`}
              className="ds-feed-dash"
              data-state={index === safe ? "active" : index < safe ? "done" : "waiting"}
              data-paused={paused ? "" : undefined}
              style={{ "--ds-dash-ms": `${interval}ms` } as React.CSSProperties}
              onClick={() => go(index)}
            >
              <i
                onAnimationEnd={(event) => {
                  if (event.animationName.includes("ds-dash-fill") && index === safe) go(safe + 1);
                }}
              />
            </button>
          ))}
        </div>
        <span className="ds-feed-count">
          {String(safe + 1).padStart(2, "0")}/{String(count).padStart(2, "0")}
        </span>
      </div>
      {footNote && <div className="ds-feed-note">{footNote}</div>}
    </div>
  );
}
