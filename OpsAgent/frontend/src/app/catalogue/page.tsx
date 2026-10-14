"use client";

/**
 * The reviewed queries: everything this product can run, published on
 * purpose. "It can only run queries a person wrote and reviewed" is the
 * central claim, and a claim nobody can read is a slogan.
 */

import { useMemo, useState } from "react";

import { counted, Figure } from "@/components/trace";
import { CountUp } from "@/design/CountUp";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Band, Banner } from "@/design/Surface";
import { useLoad, useSignedIn } from "@/lib/session";
import type { Capability } from "@/lib/types";
import { capabilityAllowed } from "@/lib/brain";
import { capabilityWords, DOMAINS, domainsOf, roleWords } from "@/lib/words";

function scopeWords(card: Capability): string {
  if (card.whole_company) return "Whole company: only for somebody who sees every account";
  if (card.scope_column === "customer_id") return "Filtered to the asker's accounts";
  if (card.scope_column === "supplier_id") return "Filtered to the asker's suppliers";
  return "Reads nothing that belongs to anybody";
}

const PARAMETER_WORDS: Record<string, string> = {
  customer: "a customer, found by an earlier lookup",
  supplier: "a supplier, found by an earlier lookup",
  part: "a part code",
  number: "a number",
  days: "a number of days",
  date: "a date",
  text: "a name to search for",
};

export default function ReviewedQueries() {
  const user = useSignedIn();
  const { data, error } = useLoad<{ count: number; capabilities: Capability[] }>(user ? "/api/capabilities" : null, [user?.email]);
  const [open, setOpen] = useState<string | null>(null);

  const groups = useMemo(() => {
    const cards = data?.capabilities ?? [];
    return DOMAINS.map((domain) => ({
      domain,
      cards: cards.filter((card) => domainsOf(card.name)[0] === domain.id),
    })).filter((group) => group.cards.length);
  }, [data]);

  if (!user) return null;
  const cards = data?.capabilities ?? [];
  const mine = cards.filter((card) => capabilityAllowed(card.name, user.role, user.reach)).length;
  const needManager = cards.filter((card) => card.needs_role !== "viewer").length;
  const wholeCompany = cards.filter((card) => card.whole_company).length;

  const countTrace = (heading: string, value: number, formula: string, list: Capability[]) =>
    counted(
      heading,
      String(value),
      formula,
      list.slice(0, 19).map((card) => ({
        label: capabilityWords(card.name),
        value: roleWords(card.needs_role),
        source: card.asks,
        sourceKind: "Reviewed query",
      })),
      "Counted from the catalogue",
      "The catalogue is checked when the server starts: read only, scoped, grouped where it adds figures up.",
    );

  return (
    <>
      <Band top>
        <div className="oa-page-band">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              The closed list <span className="ds-eyebrow-sep">·</span> published on purpose
            </span>
          </Reveal>
          <Reveal index={1} y={32}>
            <h1 className="ds-display oa-page-title">
              {cards.length ? <CountUp to={cards.length} /> : "19"} reviewed queries.
              <br />
              <span className="oa-light ds-accent-text">Nothing else can run.</span>
            </h1>
          </Reveal>
          <Reveal index={2}>
            <p className="ds-band-lede">
              The planner picks names from this list and nothing else. A question that does not land on one is refused,
              not improvised. Adding a twentieth means somebody writes the database query and somebody reviews it: that
              is the cost of the guarantee.
            </p>
          </Reveal>
          {cards.length > 0 && (
            <Reveal index={3}>
              <div className="ds-stats">
                {[
                  { label: `Open to ${user.name.split(" ")[0]}`, value: mine, tone: "accent" as const, list: cards.filter((card) => capabilityAllowed(card.name, user.role, user.reach)), formula: "count of reviewed queries this person's role may run" },
                  { label: "Need operations manager", value: needManager, list: cards.filter((card) => card.needs_role !== "viewer"), formula: "count of reviewed queries that need the operations manager role or above" },
                  { label: "Whole-company figures", value: wholeCompany, list: cards.filter((card) => card.whole_company), formula: "count of reviewed queries that cannot be row-filtered, so need every account" },
                  { label: "Ever write anything", value: 0, list: [], formula: "count of reviewed queries containing a write; checked when the catalogue loads" },
                ].map((stat) => (
                  <div key={stat.label}>
                    <span className="ds-stat-value" data-tone={stat.tone}>
                      <Figure value={String(stat.value)} count={stat.value} content={countTrace(stat.label, stat.value, stat.formula, stat.list)} />
                    </span>
                    <span className="ds-mono-label ds-stat-label">{stat.label}</span>
                  </div>
                ))}
              </div>
            </Reveal>
          )}
        </div>
      </Band>

      <div className="ds-work">
        {error && <Banner tone="fail" title="The list did not load">{error}</Banner>}
        {groups.map((group, groupIndex) => (
          <section key={group.domain.id} className="oa-section" style={{ marginTop: groupIndex ? 44 : 0 }}>
            <Reveal>
              <div className="oa-domain-head">
                <span className="oa-domain-index">{String(groupIndex + 1).padStart(2, "0")}</span>
                <div>
                  <p className="ds-mono-label" style={{ margin: 0 }}>
                    {group.domain.system}
                  </p>
                  <h2 className="ds-title oa-section-title" style={{ marginTop: 4 }}>
                    {group.domain.label}
                  </h2>
                </div>
                <span className="oa-domain-count">
                  {group.cards.length} {group.cards.length === 1 ? "query" : "queries"}
                </span>
              </div>
            </Reveal>
            <ul className="oa-queries">
              {group.cards.map((card, index) => {
                const allowed = capabilityAllowed(card.name, user.role, user.reach);
                const isOpen = open === card.name;
                return (
                  <Reveal as="li" key={card.name} index={index} className="oa-query" data-closed={allowed ? undefined : ""}>
                    <div className="oa-query-top">
                      <StatusChip tone={allowed ? "pass" : "fail"} size="small">
                        {allowed ? "Open to you" : `Needs ${roleWords(card.needs_role).toLowerCase()}`}
                      </StatusChip>
                      {card.whole_company && (
                        <StatusChip tone="neutral" size="small">
                          Whole company
                        </StatusChip>
                      )}
                    </div>
                    <p className="oa-query-asks">{card.asks}</p>
                    <p className="oa-query-name">{capabilityWords(card.name)}</p>
                    <dl className="oa-query-facts">
                      <div>
                        <dt>Permission</dt>
                        <dd>{scopeWords(card)}</dd>
                      </div>
                      <div>
                        <dt>Takes</dt>
                        <dd>{card.parameters.length ? card.parameters.map((p) => PARAMETER_WORDS[p.kind] ?? p.name).join(", ") : "nothing from the question"}</dd>
                      </div>
                      <div>
                        <dt>Gives back</dt>
                        <dd>{card.columns.map((column) => column.replace(/_/g, " ")).join(", ")}</dd>
                      </div>
                    </dl>
                    <button
                      type="button"
                      className="oa-query-toggle"
                      aria-expanded={isOpen}
                      onClick={() => setOpen(isOpen ? null : card.name)}
                    >
                      {isOpen ? "Hide the database query" : "Show the database query"}
                      <span aria-hidden>{isOpen ? "−" : "+"}</span>
                    </button>
                    {isOpen && <pre className="oa-query-code">{card.sql}</pre>}
                  </Reveal>
                );
              })}
            </ul>
          </section>
        ))}
      </div>
    </>
  );
}
