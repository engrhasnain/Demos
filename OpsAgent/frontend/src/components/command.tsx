"use client";

/**
 * The command centre's two fixtures.
 *
 * CommandBar: the question bar in the middle of the screen, in the shape of a
 * command palette. Type a question, or move through the suggested questions
 * with the arrow keys; each suggestion says which system it reads and whether
 * the person asking may run it at all.
 *
 * SystemsRail: the five systems, with what the person asking can reach in
 * each, and what the last question did to it (read, or stopped at the ring).
 */

import { useId, useState, type ReactNode } from "react";

import type { BrainDomain, BrainStep } from "@/components/ops-brain";
import { StatusChip } from "@/design/StatusChip";
import { capabilityAllowed } from "@/lib/brain";
import type { Reach } from "@/lib/api";
import { DOMAIN_BY_ID, domainsOf, type DomainId } from "@/lib/words";

export type Suggestion = { text: string; uses: string };

export const SUGGESTED: Suggestion[] = [
  { text: "How are we doing this week?", uses: "headline_numbers" },
  { text: "Which customers have late orders?", uses: "customers_with_late_orders" },
  { text: "What is owed altogether?", uses: "money_owed_in_total" },
  { text: 'What happens if "Chang Hsing Fastener (TW)" shuts down?', uses: "customers_exposed_to_supplier" },
  { text: 'Which of "Acme Tooling Co., Ltd." orders are late?', uses: "late_orders_for_customer" },
  { text: "Which shipments are stuck?", uses: "shipments_held" },
  { text: "Which parts are running out within 4 weeks?", uses: "parts_running_out" },
  { text: "When do suppliers shut for new year?", uses: "supplier_shutdowns" },
  { text: "What were Acme's margins last quarter?", uses: "" },
];

export function CommandBar({
  value,
  onChange,
  onSubmit,
  busy = false,
  role,
  reach,
  who,
  suggestions = SUGGESTED,
  extra,
  autoFocus = false,
}: {
  value: string;
  onChange: (value: string) => void;
  onSubmit: (text: string) => void;
  busy?: boolean;
  role?: string | null;
  reach?: Reach | null;
  who?: ReactNode;
  suggestions?: Suggestion[];
  extra?: ReactNode;
  autoFocus?: boolean;
}) {
  const id = useId();
  const [active, setActive] = useState(-1);
  const list = suggestions;

  const submit = (text: string) => {
    if (!text.trim() || busy) return;
    onSubmit(text.trim());
  };

  return (
    <div className="oa-command" data-busy={busy ? "" : undefined}>
      <form
        className="oa-command-bar"
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          submit(active >= 0 ? list[active].text : value);
        }}
      >
        <span className="oa-command-prompt" aria-hidden>
          <span className="oa-command-caret" />
        </span>
        <label htmlFor={`${id}-q`} className="ds-sr-only">
          Ask a question about the business
        </label>
        <input
          id={`${id}-q`}
          className="oa-command-input"
          value={value}
          maxLength={400}
          autoComplete="off"
          autoFocus={autoFocus}
          placeholder="Ask across orders, invoices, stock, the service desk and shipments…"
          onChange={(event) => {
            onChange(event.target.value);
            setActive(-1);
          }}
          onKeyDown={(event) => {
            if (event.key === "ArrowDown") {
              event.preventDefault();
              setActive((index) => Math.min(list.length - 1, index + 1));
            } else if (event.key === "ArrowUp") {
              event.preventDefault();
              setActive((index) => Math.max(-1, index - 1));
            } else if (event.key === "Escape") {
              setActive(-1);
            }
          }}
          aria-controls={`${id}-list`}
          aria-activedescendant={active >= 0 ? `${id}-s-${active}` : undefined}
        />
        {who && <span className="oa-command-who">{who}</span>}
        <button type="submit" className="oa-command-go" disabled={busy || (!value.trim() && active < 0)}>
          {busy ? <span className="ds-spinner" aria-hidden /> : null}
          {busy ? "Asking" : "Ask"}
          <kbd aria-hidden>↵</kbd>
        </button>
      </form>
      {extra && <div className="oa-command-extra">{extra}</div>}
      <ul className="oa-command-list" id={`${id}-list`} role="listbox" aria-label="Suggested questions">
        {list.map((item, index) => {
          const open = item.uses ? capabilityAllowed(item.uses, role, reach) : false;
          const domain = item.uses ? DOMAIN_BY_ID[domainsOf(item.uses)[0] as DomainId] : null;
          return (
            <li key={item.text} role="presentation" style={{ "--ds-d": `${index * 45}ms` } as React.CSSProperties}>
              <button
                type="button"
                id={`${id}-s-${index}`}
                role="option"
                aria-selected={active === index}
                className="oa-command-item"
                data-active={active === index ? "" : undefined}
                data-closed={item.uses && role && !open ? "" : undefined}
                disabled={busy}
                onMouseEnter={() => setActive(index)}
                onFocus={() => setActive(index)}
                onClick={() => {
                  onChange(item.text);
                  submit(item.text);
                }}
              >
                <span className="oa-command-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="oa-command-text">{item.text}</span>
                <span className="oa-command-meta">
                  {domain ? domain.short : "no query"}
                  <i data-tone={!item.uses ? "warn" : !role || open ? "pass" : "fail"}>
                    {!item.uses ? "needs review" : !role ? "open" : open ? "open to you" : "closed to you"}
                  </i>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function SystemsRail({
  domains,
  last,
  title = "Systems",
}: {
  domains: BrainDomain[];
  /** What the last question did, per system. */
  last?: BrainStep[];
  title?: string;
}) {
  return (
    <div className="oa-rail-panel">
      <p className="oa-rail-title">
        <span className="ds-mono-label">{title}</span>
        <span className="oa-rail-count">05</span>
      </p>
      <ol className="oa-systems">
        {domains.map((domain, index) => {
          const touched = last?.filter((step) => step.domain === domain.id) ?? [];
          const blocked = touched.some((step) => step.blocked);
          const read = touched.some((step) => !step.blocked);
          const allowed = domain.capabilities.filter((item) => item.allowed).length;
          return (
            <li
              key={domain.id}
              className="oa-system"
              data-closed={domain.closed ? "" : undefined}
              data-blocked={blocked ? "" : undefined}
              data-read={read ? "" : undefined}
            >
              <span className="oa-system-index">{String(index + 1).padStart(2, "0")}</span>
              <span className="oa-system-body">
                <b>{domain.label}</b>
                <span>
                  {allowed} of {domain.capabilities.length} queries · {domain.sub}
                </span>
              </span>
              <StatusChip
                tone={blocked ? "fail" : read ? "accent" : domain.closed ? "neutral" : "pass"}
                surface="dark"
                size="small"
                pulse={blocked || read}
              >
                {blocked ? "Stopped" : read ? "Read" : domain.closed ? "Closed" : "Open"}
              </StatusChip>
            </li>
          );
        })}
      </ol>
    </div>
  );
}
