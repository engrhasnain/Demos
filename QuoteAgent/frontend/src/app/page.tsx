"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { Band, Card, LinkButton, Stat } from "@/design/Surface";
import { CountUp } from "@/design/CountUp";
import { LiveFeedCard, type FeedItem } from "@/design/LiveFeedCard";
import { Meter } from "@/design/Meter";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { api, readToken } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { count, dateAndTime, money } from "@/lib/format";
import type { CaseDetail, CaseEvent, CaseSummary, SystemStatus } from "@/lib/types";
import { Figure } from "@/components/trace";
import { QuoteAssembly, useAssemblyStage } from "@/components/quote-assembly";
import { MiniRail } from "@/components/case-progress";
import { FirstRun } from "@/components/first-run";
import { ClosingBand } from "@/components/closing-band";
import { ErrorNote, Loading, isLive, statusTone } from "@/components/ui";

type Queue = {
  status: string;
  label: string;
  owner: "yours" | "theirs" | "done";
  hint: string;
  count: number;
};

type Board = {
  queues: Queue[];
  needs_you: number;
  waiting_on_others: number;
  total_cases: number;
  lines_quoted: number;
  open_value: { currency: string; amount: string }[];
  sent_value: { currency: string; amount: string }[];
  won_value: { currency: string; amount: string }[];
};

type Flight = { detail: CaseDetail; engine: string };

export default function OverviewPage() {
  const router = useRouter();
  const status = useLoad<SystemStatus>("/api/system/status");
  const { reload } = status;
  // On a first run nobody is signed in: the accounts exist only now.
  const loaded = useCallback(() => {
    if (readToken()) reload();
    else router.replace("/sign-in");
  }, [reload, router]);

  if (status.loading && !status.data) {
    return (
      <Band top>
        <Loading what="Loading" />
      </Band>
    );
  }
  if (status.error) {
    return (
      <Band top>
        <ErrorNote error={status.error} />
      </Band>
    );
  }
  if (!status.data) return null;

  return status.data.data_loaded ? (
    <Dashboard status={status.data} />
  ) : (
    <FirstRun onFinished={loaded} serverless={status.data.hosting === "serverless"} />
  );
}

/* ------------------------------------------------------------------ */
/* Which requests to show "in flight": a spread of real states          */
/* ------------------------------------------------------------------ */
const FLIGHT_ORDER = [
  "awaiting_approval",
  "priced",
  "awaiting_customer",
  "sent",
  "awaiting_supplier",
  "won",
  "lost",
];

function pickFlight(cases: CaseSummary[] | undefined): CaseSummary[] {
  if (!cases) return [];
  const usable = cases.filter((item) => item.line_count > 0);
  const chosen: CaseSummary[] = [];
  for (let round = 0; round < 2 && chosen.length < 6; round += 1) {
    for (const status of FLIGHT_ORDER) {
      const candidates = usable.filter((item) => item.status === status && !chosen.includes(item));
      const pick = candidates.sort((a, b) => b.line_count - a.line_count)[0];
      if (pick && chosen.length < 6) chosen.push(pick);
    }
  }
  return chosen;
}

function engineOf(events: CaseEvent[]): string {
  const used = events.filter((event) => event.engine).map((event) => event.engine);
  if (!used.length) return "built-in";
  return used[used.length - 1];
}

/* ------------------------------------------------------------------ */
/* The working dashboard                                               */
/* ------------------------------------------------------------------ */
function Dashboard({ status }: { status: SystemStatus }) {
  const board = useLoad<Board>("/api/system/dashboard");
  const recent = useLoad<{ cases: CaseSummary[] }>("/api/cases?limit=100");
  const data = board.data;
  const cases = useMemo(() => recent.data?.cases ?? [], [recent.data]);
  const flight = useMemo(() => pickFlight(cases), [cases]);

  return (
    <div>
      <Hero status={status} board={data} cases={cases} flight={flight} />
      <div className="ds-work">
        {board.error && <ErrorNote error={board.error} />}
        <Queues board={data} cases={cases} />
        <Recent cases={cases} loading={recent.loading} total={data?.total_cases} />
      </div>
      <ClosingBand />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Hero: the quote being assembled, live                                */
/* ------------------------------------------------------------------ */
function Hero({
  status,
  board,
  cases,
  flight,
}: {
  status: SystemStatus;
  board: Board | null;
  cases: CaseSummary[];
  flight: CaseSummary[];
}) {
  const [loaded, setLoaded] = useState<Record<number, Flight>>({});
  const [index, setIndex] = useState(0);
  const [compact, setCompact] = useState(false);
  const stageBox = useRef<HTMLDivElement>(null);

  // Load the requests in flight, so the assembly is built from real lines.
  useEffect(() => {
    let cancelled = false;
    flight.forEach((item) => {
      if (loaded[item.id]) return;
      Promise.all([
        api.get<CaseDetail>(`/api/cases/${item.id}`),
        api.get<{ events: CaseEvent[] }>(`/api/cases/${item.id}/timeline`),
      ])
        .then(([detail, timeline]) => {
          if (cancelled) return;
          setLoaded((previous) => ({
            ...previous,
            [item.id]: { detail, engine: engineOf(timeline.events) },
          }));
        })
        .catch(() => undefined);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flight]);

  useEffect(() => {
    const element = stageBox.current;
    if (!element) return;
    const measure = () => setCompact(element.getBoundingClientRect().width < 620);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const ready = flight.filter((item) => loaded[item.id]);
  const current = ready.length ? loaded[ready[index % ready.length].id] : null;
  const [cycle, setCycle] = useState(0);
  const onIndex = useCallback((next: number) => {
    setIndex(next);
    setCycle((value) => value + 1);
  }, []);
  const stage = useAssemblyStage(current ? `${current.detail.case.id}-${cycle}` : null);

  const items: FeedItem[] = ready.map((item) => {
    const { detail, engine } = loaded[item.id];
    const version = detail.current_version;
    return {
      key: String(item.id),
      chip: { label: item.status_label, tone: statusTone(item.status) },
      stamp: `${dateAndTime(item.updated_at)} · ${item.reference}`,
      title: item.customer?.name ?? item.contact_email,
      body: `${item.line_count} lines · ${item.incoterm} ${item.named_place} · ${money(
        version?.totals.grand_total ?? item.grand_total,
        item.currency,
      )}`,
      meta: `Read by the ${engine === "built-in" ? "built-in engine" : `${engine} engine`} · priced by the pricing engine`,
      href: `/requests/${item.id}`,
    };
  });

  const builtIn = status.reasoning_engine.active_engine === "built-in";
  const queues = board?.queues ?? [];
  const open = board?.open_value?.[0];
  const openCases = cases.filter(
    (item) =>
      !["won", "sent", "revised", "lost", "cancelled"].includes(item.status) &&
      Number(item.grand_total) > 0 &&
      (!open || item.currency === open.currency),
  );

  return (
    <Band top>
      <div className="qa-hero">
        <div className="qa-hero-copy">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              QuoteAgent <span className="ds-eyebrow-sep">·</span> Hengtai Industrial Supply
            </span>
          </Reveal>
          <Reveal index={1} y={36}>
            <h1 className="ds-display qa-hero-title">
              Request in.
              <br />
              <span className="qa-light">Quote out.</span>
              <br />
              <span className="ds-accent-text">Same day.</span>
            </h1>
          </Reveal>
          <Reveal index={2} y={30}>
            <p className="ds-band-lede" style={{ fontSize: 17 }}>
              QuoteAgent reads a messy request for quotation for Hengtai Industrial Supply, matches every line to a
              catalogue part, asks instead of guessing, prices it to the cent and holds it for a named approver.{" "}
              <strong style={{ color: "var(--ds-ink-text)" }}>Every number here opens</strong> to show how it
              was worked out.
            </p>
          </Reveal>
          <Reveal index={3} y={28}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 28 }}>
              <LinkButton href="/requests?new=1" tone="primary" size="large" arrow>
                New request
              </LinkButton>
              <LinkButton href="/demo" tone="ink" size="large">
                Run the walkthrough
              </LinkButton>
            </div>
          </Reveal>

          <Reveal index={4} y={28}>
            <div className="ds-band-rule" style={{ marginTop: 36 }} />
            <div className="ds-stats">
              <Stat
                label="Requests in"
                value={
                  <Figure
                    value={count(board?.total_cases ?? 0)}
                    count={board?.total_cases ?? 0}
                    decimals={0}
                    heading="Requests in the inbox"
                    explain={{
                      formula: "Every request in the inbox, counted by the state it is in now",
                      inputs: queues.map((queue) => ({
                        label: queue.label,
                        value: count(queue.count),
                        source: "Live request records",
                        sourceKind: "Request state",
                      })),
                    }}
                  />
                }
              />
              <Stat
                label="Need you"
                tone="accent"
                value={
                  <Figure
                    value={count(board?.needs_you ?? 0)}
                    count={board?.needs_you ?? 0}
                    decimals={0}
                    heading="Requests waiting on someone at Hengtai"
                    explain={{
                      formula: "The requests whose next move is ours: to approve, to send, to read or to re-quote",
                      inputs: queues
                        .filter((queue) => queue.owner === "yours")
                        .map((queue) => ({
                          label: queue.label,
                          value: count(queue.count),
                          source: queue.hint,
                          sourceKind: "Request state",
                        })),
                    }}
                  />
                }
              />
              <Stat
                label="Lines quoted"
                value={
                  <Figure
                    value={count(board?.lines_quoted ?? 0)}
                    count={board?.lines_quoted ?? 0}
                    decimals={0}
                    heading="Lines on priced quotes"
                    explain={{
                      formula: "The lines on the current version of every quote with a total above zero",
                      inputs: cases
                        .filter((item) => Number(item.grand_total) > 0)
                        .slice(0, 12)
                        .map((item) => ({
                          label: `${item.reference} · ${item.customer?.name ?? item.contact_email}`,
                          value: `${item.line_count} lines`,
                          source: `Quote version ${item.current_version}`,
                          sourceKind: "Quote",
                        })),
                    }}
                  />
                }
              />
              <Stat
                label={`Open quote value${open ? `, ${open.currency}` : ""}`}
                tone="accent"
                value={
                  <Figure
                    value={open ? money(open.amount) : "0.00"}
                    count={open ? Number(open.amount) : 0}
                    decimals={2}
                    heading={`Open quote value${open ? ` in ${open.currency}` : ""}`}
                    explain={{
                      formula:
                        "The current quote total of every request that is not yet sent, won, lost or cancelled, added up in its own currency by the server",
                      result: open ? money(open.amount, open.currency) : "0.00",
                      inputs: openCases.map((item) => ({
                        label: `${item.reference} · ${item.customer?.name ?? item.contact_email}`,
                        value: money(item.grand_total, item.currency),
                        source: `${item.status_label}, quote version ${item.current_version}`,
                        sourceKind: "Quote total",
                      })),
                    }}
                  />
                }
              />
            </div>
            <p className="ds-mono" style={{ margin: "18px 0 0", fontSize: 11.5, color: "var(--ds-ink-faint)" }}>
              Counted from live records when this page loaded ·{" "}
              {builtIn ? "built-in engine, no key" : "external model"}
            </p>
          </Reveal>
        </div>

        <div className="qa-hero-stage" ref={stageBox}>
          <div className="qa-hero-canvas">
            {!compact && (
              <div className="qa-columns" aria-hidden>
                {[
                  ["Request lines", 0.12],
                  ["Matched parts", 0.49],
                  ["Priced", 0.69],
                  ["Approval", 0.895],
                ].map(([text, x]) => (
                  <span key={text as string} className="ds-mono-label" style={{ left: `${(x as number) * 100}%` }}>
                    {text}
                  </span>
                ))}
              </div>
            )}
            <QuoteAssembly detail={current?.detail ?? null} compact={compact} stage={stage} />
          </div>
          <div className="qa-hero-feed">
            {items.length > 0 ? (
              <LiveFeedCard
                title="Quotes in flight"
                source="live from the server"
                items={items}
                interval={6400}
                onIndex={onIndex}
              />
            ) : (
              <div className="ds-feed" style={{ padding: 18 }}>
                <span className="ds-mono-label">Quotes in flight</span>
                <div style={{ marginTop: 14, color: "var(--ds-ink-muted)", fontSize: 13.5 }}>
                  Reading the requests in the inbox…
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Band>
  );
}

/* ------------------------------------------------------------------ */
/* Work queues                                                         */
/* ------------------------------------------------------------------ */
const OWNER_WORDS: Record<Queue["owner"], { label: string; tone: "accent" | "warn" | "pass" }> = {
  yours: { label: "Needs you", tone: "accent" },
  theirs: { label: "Waiting on others", tone: "warn" },
  done: { label: "Done", tone: "pass" },
};

function Queues({ board, cases }: { board: Board | null; cases: CaseSummary[] }) {
  const queues = (board?.queues ?? []).filter((queue) => queue.count > 0);
  const total = Math.max(1, board?.total_cases ?? 1);

  return (
    <section aria-labelledby="queues-heading">
      <Reveal>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "end", justifyContent: "space-between", gap: 16 }}>
          <div>
            <p className="ds-mono-label" style={{ margin: 0 }}>
              Work queues
            </p>
            <h2 id="queues-heading" className="ds-title" style={{ margin: "8px 0 0", fontSize: 30 }}>
              What needs doing
            </h2>
          </div>
          <LinkButton href="/requests" tone="secondary" arrow>
            Every request
          </LinkButton>
        </div>
      </Reveal>

      <div className="qa-pipe" style={{ marginTop: 22 }}>
        {queues.map((queue, index) => {
          const owner = OWNER_WORDS[queue.owner];
          const tone = statusTone(queue.status);
          const inQueue = cases.filter((item) => item.status === queue.status);
          return (
            <Reveal key={queue.status} index={index} className="qa-queue ds-lift">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <StatusChip tone={owner.tone} size="small" pulse={queue.owner === "yours"}>
                  {owner.label}
                </StatusChip>
                <Link
                  href={`/requests?status=${queue.status}`}
                  style={{ fontSize: 12.5, fontWeight: 600, color: "var(--ds-accent-ink)", textDecoration: "none" }}
                >
                  Open the list →
                </Link>
              </div>
              <div style={{ display: "flex", alignItems: "baseline", gap: 10, marginTop: 16 }}>
                <span className="qa-queue-count">
                  <Figure
                    value={count(queue.count)}
                    count={queue.count}
                    decimals={0}
                    heading={queue.label}
                    explain={{
                      formula: `Requests whose state is now "${queue.label}"`,
                      inputs: inQueue.map((item) => ({
                        label: `${item.reference} · ${item.customer?.name ?? item.contact_email}`,
                        value: `${item.line_count} lines`,
                        source: `Last changed ${dateAndTime(item.updated_at)}`,
                        sourceKind: "Request",
                      })),
                    }}
                  />
                </span>
                <span style={{ fontWeight: 600, fontSize: 15 }}>{queue.label}</span>
              </div>
              {queue.hint && (
                <p style={{ margin: "6px 0 14px", fontSize: 13, lineHeight: 1.5, color: "var(--ds-text-2)" }}>
                  {queue.hint}
                </p>
              )}
              {!queue.hint && <div style={{ height: 14 }} />}
              <Meter
                value={queue.count / total}
                tone={tone === "neutral" ? "info" : tone}
                size="small"
                delay={index * 90}
                label={`${queue.count} of ${total} requests`}
              />
              <p className="ds-mono" style={{ margin: "8px 0 0", fontSize: 11, color: "var(--ds-text-3)" }}>
                {queue.count} of {total} requests
              </p>
            </Reveal>
          );
        })}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Recent requests                                                     */
/* ------------------------------------------------------------------ */
function Recent({
  cases,
  loading,
  total,
}: {
  cases: CaseSummary[];
  loading: boolean;
  total?: number;
}) {
  const rows = cases
    .slice()
    .sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1))
    .slice(0, 8);
  return (
    <section style={{ marginTop: 56 }} aria-labelledby="recent-heading">
      <Reveal>
        <p className="ds-mono-label" style={{ margin: 0 }}>
          Latest activity
        </p>
        <h2 id="recent-heading" className="ds-title" style={{ margin: "8px 0 0", fontSize: 30 }}>
          Recent requests
        </h2>
      </Reveal>
      <Card
        style={{ marginTop: 22 }}
        flush
        eyebrow={`${rows.length} of ${count(total ?? cases.length)}`}
        title="Moved most recently"
        action={
          <LinkButton href="/requests" tone="ghost" size="small" arrow>
            All requests
          </LinkButton>
        }
      >
        {loading && rows.length === 0 && <div style={{ padding: 20 }}>Loading…</div>}
        <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
          {rows.map((item, index) => (
            <Reveal as="li" key={item.id} index={index} from="left" y={28}>
              <Link
                href={`/requests/${item.id}`}
                className="qa-recent-row"
              >
                <span className="ds-stamp">{item.reference}</span>
                <span style={{ minWidth: 0 }}>
                  <span style={{ display: "block", fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {item.customer?.name ?? item.contact_email}
                  </span>
                  <span className="ds-mono" style={{ display: "block", fontSize: 11.5, color: "var(--ds-text-3)", marginTop: 2 }}>
                    {dateAndTime(item.updated_at)} · {item.line_count} lines · {item.incoterm}
                  </span>
                </span>
                <span className="qa-recent-rail">
                  <MiniRail status={item.status} />
                </span>
                <span className="ds-num qa-recent-total" style={{ fontWeight: 600 }}>
                  {Number(item.grand_total) > 0 ? money(item.grand_total, item.currency) : "Not priced yet"}
                </span>
                <StatusChip tone={statusTone(item.status)} pulse={isLive(item.status)}>
                  {item.status_label}
                </StatusChip>
              </Link>
            </Reveal>
          ))}
        </ul>
      </Card>
    </section>
  );
}

export const dynamic = "force-dynamic";
