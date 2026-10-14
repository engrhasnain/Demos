"use client";

/**
 * Tabs with a sliding accent indicator (moved by transform only) and arrow
 * key navigation between tabs.
 */

import { useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";

export type TabItem<K extends string> = { key: K; label: string; badge?: number };

export function Tabs<K extends string>({
  tabs,
  value,
  onChange,
  label,
  idPrefix = "tab",
}: {
  tabs: TabItem<K>[];
  value: K;
  onChange: (key: K) => void;
  label: string;
  idPrefix?: string;
}) {
  const bar = useRef<HTMLDivElement>(null);
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });

  useLayoutEffect(() => {
    const element = bar.current;
    if (!element) return;
    const measure = () => {
      const active = element.querySelector<HTMLElement>('[aria-selected="true"]');
      if (active) setIndicator({ left: active.offsetLeft, width: active.offsetWidth });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [value, tabs.length]);

  const onKey = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = tabs.findIndex((tab) => tab.key === value);
    let next = -1;
    if (event.key === "ArrowRight") next = (index + 1) % tabs.length;
    if (event.key === "ArrowLeft") next = (index - 1 + tabs.length) % tabs.length;
    if (event.key === "Home") next = 0;
    if (event.key === "End") next = tabs.length - 1;
    if (next < 0) return;
    event.preventDefault();
    onChange(tabs[next].key);
    bar.current?.querySelectorAll<HTMLElement>('[role="tab"]')[next]?.focus();
  };

  return (
    <div ref={bar} className="ds-tabs" role="tablist" aria-label={label} onKeyDown={onKey}>
      {tabs.map((tab) => (
        <button
          key={tab.key}
          id={`${idPrefix}-${tab.key}`}
          type="button"
          role="tab"
          aria-selected={tab.key === value}
          aria-controls={`${idPrefix}-panel`}
          tabIndex={tab.key === value ? 0 : -1}
          className="ds-tab"
          onClick={() => onChange(tab.key)}
        >
          {tab.label}
          {tab.badge ? <span className="ds-tab-badge">{tab.badge}</span> : null}
        </button>
      ))}
      <span
        className="ds-tab-indicator"
        aria-hidden
        style={{ transform: `translateX(${indicator.left}px) scaleX(${indicator.width})` }}
      />
    </div>
  );
}
