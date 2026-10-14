"use client";

/**
 * Questions answered, live: real questions from the question log and the
 * access record, newest first, each with who asked (and their role), what
 * they asked, which systems it touched, what became of it and which engine
 * read it.
 *
 * Somebody's own questions come from their question log. A manager or above
 * also sees everybody else's reads from the access record, which is where the
 * refusals of other people show up.
 */

import { useCallback, useEffect, useRef, useState } from "react";

import type { BrainStep } from "@/components/ops-brain";
import { LiveFeedCard, type FeedItem } from "@/design/LiveFeedCard";
import { api, type SignedInUser } from "@/lib/api";
import { stepsFromPlan } from "@/lib/brain";
import type { AccessEntry, DemoPerson, QuestionDetail, QuestionRow } from "@/lib/types";
import {
  CAPABILITIES,
  clock,
  DOMAIN_BY_ID,
  domainsOf,
  filterShort,
  OUTCOME,
  outcomeOf,
  parseTime,
  plain,
  reaches,
  refusalCause,
  roleWords,
  type DomainId,
} from "@/lib/words";

export type LiveEntry = FeedItem & { steps: BrainStep[]; at: number };

function domainLine(names: string[]): string {
  const ids = Array.from(new Set(names.flatMap((name) => domainsOf(name)))) as DomainId[];
  return ids.map((id) => DOMAIN_BY_ID[id].label).join(" + ") || "No system reached";
}

const ASKS: Record<string, string> = {
  late_orders_for_customer: "Which of a customer's orders are late?",
  why_an_order_is_late: "What is holding one order up?",
  orders_waiting_on_a_part: "Which orders are waiting on a particular part?",
  supplier_lead_time: "How long does a supplier actually take?",
  parts_from_supplier: "Which parts come from a supplier?",
  customers_exposed_to_supplier: "If a supplier stops, which customers are hit?",
  cover_if_supplier_stops: "How many weeks of cover is there on a supplier's parts?",
  customer_overview: "How is one customer doing overall?",
  customers_with_late_orders: "Which customers have late orders at the moment?",
  unpaid_invoices_for_customer: "What does a customer owe?",
  money_owed_in_total: "How much is owed altogether?",
  shipments_held: "Which shipments are held up, and why?",
  stock_for_part: "How much of a part is there, and what is on order?",
  parts_running_out: "What is about to run out?",
  open_tickets: "What is the service desk holding?",
  find_customer: "Which customer is this?",
  find_supplier: "Which supplier is this?",
  supplier_shutdowns: "When do suppliers shut, and for how long?",
  headline_numbers: "How is the business doing this week?",
};

export function useLiveQuestions(user: SignedInUser | null, people: DemoPerson[] | undefined, engine: string, refresh = 0) {
  const [entries, setEntries] = useState<LiveEntry[] | null>(null);
  const peopleRef = useRef(people);
  peopleRef.current = people;
  const peopleKey = (people ?? []).map((person) => `${person.name}:${person.role}`).join("|");
  const userKey = user ? `${user.email}:${user.role}` : "";

  useEffect(() => {
    if (!user) {
      setEntries(null);
      return;
    }
    let cancelled = false;
    const engineWords = engine === "external" ? "External model" : "Built-in engine";
    const roleOf = (name: string) => peopleRef.current?.find((person) => person.name === name)?.role ?? "";

    (async () => {
      const out: LiveEntry[] = [];
      try {
        const mine = await api.get<{ questions: QuestionRow[] }>("/api/questions?limit=8");
        const details = await Promise.all(
          mine.questions.map((question) =>
            api.get<QuestionDetail>(`/api/questions/${question.id}`).catch(() => null),
          ),
        );
        mine.questions.forEach((question, index) => {
          const detail = details[index];
          const outcome = outcomeOf(question.refused, question.injection_seen);
          const plan = detail?.plan ?? [];
          const ran = detail?.evidence?.length ?? 0;
          const status =
            question.injection_seen && outcome === "answered"
              ? { label: "Needs review", tone: "warn" as const }
              : OUTCOME[outcome];
          const at = parseTime(question.asked_at)?.getTime() ?? 0;
          out.push({
            key: `q-${question.id}`,
            at,
            chip: status,
            stamp: `${clock(question.asked_at)} · ${question.engine === "external" ? "External model" : "Built-in engine"}`,
            title: question.text,
            body: question.refused
              ? `${plain(question.refused)} ${refusalCause(question.refused)}.`
              : question.injection_seen
                ? `${question.answer} The attached document held instructions; they were read as text and nothing was done.`
                : question.answer,
            meta: `${roleWords(user.role)} · ${user.name} · ${domainLine(plan.map((step) => step.capability))}`,
            steps: stepsFromPlan(plan, ran, question.refused),
          });
        });
      } catch {
        /* the log is a convenience; the page still works without it */
      }

      if (reaches(user.role, "manager")) {
        try {
          const log = await api.get<{ entries: AccessEntry[] }>("/api/access-log?limit=120");
          // One question can read several queries a moment apart: group them.
          const groups: AccessEntry[][] = [];
          for (const entry of log.entries) {
            if (entry.who === user.name) continue;
            const last = groups[groups.length - 1];
            const near =
              last &&
              last[0].who === entry.who &&
              Math.abs((parseTime(last[0].occurred_at)?.getTime() ?? 0) - (parseTime(entry.occurred_at)?.getTime() ?? 0)) < 2500;
            if (near) last.push(entry);
            else groups.push([entry]);
          }
          groups.slice(0, 8).forEach((group) => {
            const ordered = [...group].reverse();
            const final = ordered[ordered.length - 1];
            const refused = ordered.find((entry) => !entry.allowed);
            const emptyLookup = !refused && ordered.some((entry) => entry.capability.startsWith("find_") && entry.rows_returned === 0);
            const role = roleOf(final.who);
            const chip = refused || emptyLookup ? OUTCOME["not-permitted"] : OUTCOME.answered;
            const rows = ordered.reduce((total, entry) => total + (entry.allowed ? entry.rows_returned : 0), 0);
            out.push({
              key: `a-${final.id}`,
              at: parseTime(final.occurred_at)?.getTime() ?? 0,
              chip,
              stamp: `${clock(final.occurred_at)} · ${engineWords}`,
              title: ASKS[final.capability] ?? CAPABILITIES[final.capability]?.words ?? final.capability,
              body: refused
                ? `${plain(refused.refusal)} ${refusalCause(refused.refusal)}.`
                : emptyLookup
                  ? "Nothing on this account matches that name. The refusal does not confirm the name exists."
                  : `${rows.toLocaleString("en-GB")} ${rows === 1 ? "row" : "rows"} read · filter: ${filterShort(final.filter_applied)}`,
              meta: `${roleWords(role) || "Someone"} · ${final.who} · ${domainLine(ordered.map((entry) => entry.capability))}`,
              steps: ordered.map((entry) => ({
                capability: entry.capability,
                domain: domainsOf(entry.capability)[0],
                blocked: !entry.allowed,
              })),
            });
          });
        } catch {
          /* not open to this account */
        }
      }

      out.sort((a, b) => b.at - a.at);
      if (!cancelled) setEntries(out.slice(0, 10));
    })();

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userKey, peopleKey, engine, refresh]);

  return entries;
}

export function LiveQuestions({
  entries,
  onShow,
  title = "Questions answered live",
  source,
}: {
  entries: LiveEntry[];
  onShow?: (entry: LiveEntry) => void;
  title?: string;
  source: string;
}) {
  const latest = useRef({ entries, onShow });
  latest.current = { entries, onShow };
  const onIndex = useCallback((index: number) => {
    const entry = latest.current.entries[index];
    if (entry) latest.current.onShow?.(entry);
  }, []);
  return (
    <LiveFeedCard
      title={title}
      source={source}
      items={entries}
      interval={4800}
      onIndex={onIndex}
      footNote="Real records from the question log and the access record."
    />
  );
}
