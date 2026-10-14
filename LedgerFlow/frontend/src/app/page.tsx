"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";

import { Band, Card, LinkButton, Stat } from "@/design/Surface";
import { LiveFeedCard, type FeedItem } from "@/design/LiveFeedCard";
import { Meter } from "@/design/Meter";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { api, readUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { asNumber, clock, count, engineWords, ledgerName, money } from "@/lib/format";
import type { Dashboard, DemoState, EvaluationReport, InvoiceBrief, InvoiceDetail, Page } from "@/lib/types";
import { Figure } from "@/components/trace";
import { MatchConstellation, useBox, useMatchStage } from "@/components/match-constellation";
import { PostingJourney, type JourneyFacts } from "@/components/posting-journey";
import { FirstRun } from "@/components/first-run";
import { WalkthroughPreview } from "@/components/walkthrough";
import {
  Button,
  Empty,
  ErrorNote,
  Loading,
  MatchGlyph,
  SectionHead,
  TONE_COLOUR,
  matchState,
  severityTone,
  severityWords,
} from "@/components/ui";

export default function DeskPage() {
  const state = useLoad<DemoState>("/api/demo/state", [], { retry: true });
  const [rebuild, setRebuild] = useState(false);

  if (state.loading && !state.data) {
    return (
      <Band top>
        <Loading what="Opening the desk" />
      </Band>
    );
  }
  if (state.error) {
    return (
      <Band top>
        <div style={{ padding: "24px 0" }}>
          <ErrorNote error={state.error} />
          <div style={{ marginTop: 16 }}>
            <Button tone="secondary" onClick={state.reload}>
              Retry
            </Button>
          </div>
        </div>
      </Band>
    );
  }
  if (!state.data) return null;

  if (!state.data.loaded || rebuild) {
    return (
      <FirstRun
        needsCompany
        onFinished={() => {
          setRebuild(false);
          state.reload();
        }}
      />
    );
  }
  if (!state.data.batch_run) return <FirstRun needsCompany={false} onFinished={state.reload} />;

  return <Desk state={state.data} onRebuild={() => setRebuild(true)} />;
}

/* ------------------------------------------------------------------ */
/* Which invoices to show "in flight": a spread of real outcomes        */
/* ------------------------------------------------------------------ */
function pickFlight(invoices: InvoiceBrief[]): InvoiceBrief[] {
  const wanted = ["Posted", "Held", "Needs approval", "Stopped", "Posted", "Stopped", "Held", "Needs approval"];
  const chosen: InvoiceBrief[] = [];
  const headlines = new Set<string>();
  for (const label of wanted) {
    const candidates = invoices.filter(
      (item) => matchState(item).label === label && !chosen.includes(item) && !headlines.has(item.headline + label),
    );
    const pick = candidates.sort((a, b) => b.id - a.id)[0];
    if (pick) {
      chosen.push(pick);
      headlines.add(pick.headline + label);
    }
    if (chosen.length >= 6) break;
  }
  return chosen;
}

function amountExplain(invoice: InvoiceBrief) {
  const foreign = invoice.currency !== "TWD";
  return {
    formula: foreign
      ? `${money(invoice.total_amount)} ${invoice.currency} converted to Taiwan dollars at the rate for the invoice date`
      : "The invoice total, in Taiwan dollars",
    result: `${money(invoice.amount_in_base)} TWD`,
    inputs: [
      { label: "Invoiced", value: `${money(invoice.total_amount)} ${invoice.currency}`, source: `${invoice.reference}, as read`, sourceKind: "The invoice" },
      { label: "Payable", value: money(invoice.approved_amount), source: "The three-way match", sourceKind: "Matching code" },
      { label: "Held back", value: money(invoice.held_amount), source: invoice.headline || "Nothing held", sourceKind: "Matching code" },
    ],
  };
}

/* ------------------------------------------------------------------ */
function Desk({ state, onRebuild }: { state: DemoState; onRebuild: () => void }) {
  const board = useLoad<Dashboard>("/api/dashboard");
  const list = useLoad<Page<InvoiceBrief>>("/api/invoices?limit=200");
  const queue = useLoad<Page<InvoiceBrief>>("/api/invoices/queue");
  const invoices = useMemo(() => list.data?.items ?? [], [list.data]);

  return (
    <div>
      <Hero state={state} board={board.data} invoices={invoices} />
      <div className="ds-work">
        {board.error && <ErrorNote error={board.error} />}
        <div className="lf-desk-grid">
          <Queue queue={queue.data} loading={queue.loading} />
          <div className="lf-desk-side">
            <WhyStopped board={board.data} invoices={invoices} />
          </div>
        </div>
        <WhereEverything board={board.data} invoices={invoices} />
        <WalkthroughPreview invoices={invoices} />
      </div>
      <PostingBand invoices={invoices} />
      <Restart onRebuild={onRebuild} />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Hero: the three-way match, live                                     */
/* ------------------------------------------------------------------ */
function Hero({ state, board, invoices }: { state: DemoState; board: Dashboard | null; invoices: InvoiceBrief[] }) {
  const flight = useMemo(() => pickFlight(invoices), [invoices]);
  const [loaded, setLoaded] = useState<Record<number, InvoiceDetail>>({});
  const [index, setIndex] = useState(0);
  const [cycle, setCycle] = useState(0);
  const [stageRef, box] = useBox(620);

  useEffect(() => {
    let cancelled = false;
    flight.forEach((item) => {
      if (loaded[item.id]) return;
      api
        .get<InvoiceDetail>(`/api/invoices/${item.id}`)
        .then((detail) => !cancelled && setLoaded((previous) => ({ ...previous, [item.id]: detail })))
        .catch(() => undefined);
    });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [flight]);

  const ready = flight.filter((item) => loaded[item.id]);
  const current = ready.length ? loaded[ready[index % ready.length].id] : null;
  const onIndex = useCallback((next: number) => {
    setIndex(next);
    setCycle((value) => value + 1);
  }, []);
  const stage = useMatchStage(current ? `${current.id}-${cycle}` : null);

  const items: FeedItem[] = ready.map((item) => {
    const look = matchState(item);
    return {
      key: String(item.id),
      chip: { label: look.label, tone: look.tone },
      stamp: `${clock(item.received_at)} · ${item.reference}`,
      title: item.vendor_name,
      body: `${money(item.total_amount)} ${item.currency} · ${
        item.headline || (item.status === "posted" ? "Matched three ways and posted" : "Matched three ways")
      }`,
      meta: `Read by ${engineWords(item.read_with)} · matched and posted by code`,
      href: `/invoices/${item.id}`,
    };
  });

  const builtIn = state.reading_engine === "built-in";
  const held = invoices.filter((item) => asNumber(item.held_amount) > 0);
  const posted = invoices.filter((item) => item.status === "posted");
  const waiting = invoices.filter((item) => item.needs_a_person);

  return (
    <Band top>
      <div className="lf-hero">
        <div className="lf-hero-copy">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              LedgerFlow <span className="ds-eyebrow-sep">·</span> Hengtai Industrial Supply
            </span>
          </Reveal>
          <Reveal index={1} y={36}>
            <h1 className="ds-display lf-hero-title">
              Invoice in.
              <br />
              Matched three ways.
              <br />
              <span className="ds-accent-text">Paid once.</span>
            </h1>
          </Reveal>
          <Reveal index={2} y={30}>
            <p className="ds-band-lede" style={{ fontSize: 16.5 }}>
              Every supplier invoice read, checked against the purchase order and what actually arrived, signed
              where it must be and posted to the ledger exactly once. It stops when something is wrong, and says why.{" "}
              <strong style={{ color: "var(--ds-ink-text)" }}>Every number here opens.</strong>
            </p>
          </Reveal>
          <Reveal index={3} y={28}>
            <div className="lf-actions" style={{ marginTop: 24 }}>
              <LinkButton href="/invoices/new" tone="primary" size="large" arrow>
                Add an invoice
              </LinkButton>
              <LinkButton href="/walkthrough" tone="ink" size="large">
                Walk through it
              </LinkButton>
            </div>
          </Reveal>

          <Reveal index={4} y={28}>
            <div className="ds-band-rule" style={{ marginTop: 28 }} />
            <div className="ds-stats lf-stats">
              <Stat
                label="Invoices in"
                value={
                  <Figure
                    value={count(board?.invoices ?? 0)}
                    count={board?.invoices ?? 0}
                    decimals={0}
                    heading="Invoices received"
                    explain={{
                      formula: "Every invoice and credit note received, counted by where it is now",
                      inputs: (board?.by_status ?? []).map((row) => ({
                        label: row.label,
                        value: count(row.count),
                        source: "Live invoice records",
                        sourceKind: "Invoice state",
                      })),
                    }}
                  />
                }
              />
              <Stat
                label="Posted untouched"
                tone="accent"
                value={
                  <Figure
                    value={`${board?.untouched_share ?? 0}%`}
                    count={board?.untouched_share ?? 0}
                    decimals={board && board.untouched_share % 1 ? 1 : 0}
                    suffix="%"
                    heading="Posted with nobody touching them"
                    explain={{
                      formula: `${board?.untouched ?? 0} posted with nobody touching them ÷ ${board?.posted ?? 0} posted × 100`,
                      result: `${board?.untouched_share ?? 0}%`,
                      inputs: posted.slice(0, 14).map((item) => ({
                        label: `${item.reference} · ${item.vendor_name}`,
                        value: item.posted_untouched ? "untouched" : "a person signed",
                        source: `${money(item.approved_amount)} ${item.currency}`,
                        sourceKind: "Posted invoice",
                      })),
                    }}
                  />
                }
              />
              <Stat
                label="Need a person"
                tone={board?.waiting_for_a_person ? "warn" : "pass"}
                value={
                  <Figure
                    value={count(board?.waiting_for_a_person ?? 0)}
                    count={board?.waiting_for_a_person ?? 0}
                    decimals={0}
                    heading="Invoices waiting for a person"
                    explain={{
                      formula: "Invoices that stopped for a person, or are waiting for a signature",
                      inputs: waiting.slice(0, 14).map((item) => ({
                        label: `${item.reference} · ${item.vendor_name}`,
                        value: item.headline || item.status_label,
                        source: item.status_label,
                        sourceKind: "Invoice state",
                      })),
                    }}
                  />
                }
              />
              <Stat
                label="Held back, TWD"
                tone="warn"
                value={
                  <Figure
                    value={money(board?.held_amount ?? "0")}
                    count={asNumber(board?.held_amount)}
                    decimals={2}
                    heading="Held back, in Taiwan dollars"
                    explain={{
                      formula: "The held amount of every invoice, added up by the server",
                      result: `${money(board?.held_amount ?? "0")} TWD`,
                      inputs: held.map((item) => ({
                        label: `${item.reference} · ${item.vendor_name}`,
                        value: money(item.held_amount),
                        source: item.headline || item.status_label,
                        sourceKind: "Matching code",
                      })),
                    }}
                  />
                }
              />
              <Stat
                label="In the ledger, TWD"
                tone="pass"
                value={
                  <Figure
                    value={money(board?.posted_amount ?? "0")}
                    count={asNumber(board?.posted_amount)}
                    decimals={2}
                    heading="Posted to the ledger, in Taiwan dollars"
                    explain={{
                      formula: "The payable amount of every posted invoice, added up by the server",
                      result: `${money(board?.posted_amount ?? "0")} TWD`,
                      inputs: posted.map((item) => ({
                        label: `${item.reference} · ${item.vendor_name}`,
                        value: `${money(item.approved_amount)} ${item.currency}`,
                        source: item.posted_untouched ? "Posted untouched" : "Posted after a signature",
                        sourceKind: "Posted invoice",
                      })),
                    }}
                  />
                }
              />
            </div>
            <p className="ds-mono lf-hero-foot">
              Counted from live records when this page loaded · read by {builtIn ? "the built-in engine, no key" : "an external model"} · every figure decided by code
            </p>
          </Reveal>
        </div>

        <div className="lf-hero-stage" ref={stageRef}>
          <div className="lf-hero-canvas">
            <MatchConstellation detail={current} stage={stage} compact={box.compact} aspect={box.aspect} />
          </div>
          <div className="lf-hero-feed">
            {items.length > 0 ? (
              <LiveFeedCard title="Invoices in flight" source="live from the server" items={items} interval={7000} onIndex={onIndex} />
            ) : (
              <div className="ds-feed" style={{ padding: 18 }}>
                <span className="ds-mono-label">Invoices in flight</span>
                <div style={{ marginTop: 14, color: "var(--ds-ink-muted)", fontSize: 13.5 }}>Reading the invoices…</div>
              </div>
            )}
          </div>
        </div>
      </div>
    </Band>
  );
}

/* ------------------------------------------------------------------ */
/* Waiting for you                                                     */
/* ------------------------------------------------------------------ */
function Queue({ queue, loading }: { queue: Page<InvoiceBrief> | null; loading: boolean }) {
  const rows = queue?.items ?? [];
  return (
    <section aria-labelledby="queue-heading">
      <SectionHead
        label="Worst first · red before amber"
        title="Waiting for you"
        id="queue-heading"
        action={
          <LinkButton href="/invoices?filter=person" tone="secondary" arrow>
            Every invoice
          </LinkButton>
        }
      />
      <Card
        style={{ marginTop: 22 }}
        flush
        eyebrow={`${rows.length} ${rows.length === 1 ? "invoice" : "invoices"}`}
        title={rows.length ? "Each one says why it stopped" : "Nothing is waiting"}
        action={
          rows.length ? (
            <StatusChip tone="warn" pulse>
              {rows.length} open
            </StatusChip>
          ) : (
            <StatusChip tone="pass">Clear</StatusChip>
          )
        }
      >
        {loading && !queue ? (
          <Loading what="Loading" />
        ) : rows.length === 0 ? (
          <div style={{ padding: 20 }}>
            <Empty title="All clear.">Every invoice is posted or signed.</Empty>
          </div>
        ) : (
          <ul className="lf-rows">
            {rows.map((invoice, position) => {
              const look = matchState(invoice);
              return (
                <Reveal as="li" key={invoice.id} index={position} from="left" y={28}>
                  <div className="lf-row" style={{ "--row-tone": TONE_COLOUR[severityTone(invoice.headline_severity)] } as React.CSSProperties}>
                    <MatchGlyph state={look} posted={invoice.status === "posted"} />
                    <Link href={`/invoices/${invoice.id}`} className="lf-row-main">
                      <span className="lf-row-title">{invoice.vendor_name}</span>
                      <span className="lf-row-sub ds-mono">
                        {invoice.invoice_number || invoice.reference} · {invoice.headline}
                      </span>
                    </Link>
                    <span className="lf-row-amount">
                      <Figure value={money(invoice.amount_in_base)} heading={`${invoice.reference}: amount in Taiwan dollars`} explain={amountExplain(invoice)} />
                      <span className="lf-row-unit">TWD</span>
                    </span>
                    <StatusChip tone={look.tone} pulse={look.live}>
                      {look.label}
                    </StatusChip>
                  </div>
                </Reveal>
              );
            })}
          </ul>
        )}
      </Card>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Why things stopped                                                  */
/* ------------------------------------------------------------------ */
function WhyStopped({ board, invoices }: { board: Dashboard | null; invoices: InvoiceBrief[] }) {
  const kinds = board?.exception_kinds ?? [];
  const most = Math.max(1, ...kinds.map((row) => row.count));
  return (
    <section aria-labelledby="why-heading">
      <SectionHead label="Open exceptions, by kind" title="Why they stopped" id="why-heading" />
      <Card style={{ marginTop: 22 }}>
        {kinds.length === 0 ? (
          <Empty title="Nothing open." />
        ) : (
          <ul className="lf-why">
            {kinds.map((row, index) => {
              const tone = severityTone(row.severity);
              const examples = invoices.filter((item) => item.headline === row.label);
              return (
                <Reveal as="li" key={row.kind} index={index} className="lf-why-row">
                  <div className="lf-why-head">
                    <span className="lf-why-label">{row.label}</span>
                    <span className="lf-why-count">
                      <Figure
                        value={count(row.count)}
                        count={row.count}
                        decimals={0}
                        heading={row.label}
                        explain={{
                          formula: `Open exceptions of the kind "${row.label}". One invoice can carry more than one.`,
                          inputs: examples.map((item) => ({
                            label: `${item.reference} · ${item.vendor_name}`,
                            value: money(item.amount_in_base),
                            source: item.status_label,
                            sourceKind: "Invoice",
                          })),
                        }}
                      />
                    </span>
                  </div>
                  <Meter value={row.count / most} tone={tone === "neutral" ? "info" : tone} size="small" delay={index * 90} label={`${row.count} open`} />
                  <StatusChip tone={tone} size="small">
                    {severityWords(row.severity)}
                  </StatusChip>
                </Reveal>
              );
            })}
          </ul>
        )}
      </Card>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Where everything is: the flow of states                             */
/* ------------------------------------------------------------------ */
const FLOW = [
  { code: "received", label: "Received" },
  { code: "read", label: "Read" },
  { code: "checked", label: "Matched" },
  { code: "awaiting_approval", label: "Waiting to be signed" },
  { code: "approved", label: "Signed" },
  { code: "posted", label: "In the ledger" },
];
const SIDE = [
  { code: "exception", label: "Needs a person" },
  { code: "rejected", label: "Sent back" },
];

function WhereEverything({ board, invoices }: { board: Dashboard | null; invoices: InvoiceBrief[] }) {
  const counts = new Map((board?.by_status ?? []).map((row) => [row.code, row.count]));
  const total = Math.max(1, board?.invoices ?? 1);
  const cell = (code: string, label: string, index: number, tone?: "pass" | "warn" | "fail") => {
    const value = counts.get(code) ?? 0;
    const inState = invoices.filter((item) => item.status === code);
    return (
      <Reveal as="li" key={code} index={index} className="lf-flow-step" data-empty={value ? undefined : ""} data-tone={tone}>
        <span className="lf-flow-node" aria-hidden />
        <span className="lf-flow-count">
          <Figure
            value={count(value)}
            count={value}
            decimals={0}
            heading={`Invoices: ${label}`}
            explain={{
              formula: `Invoices whose state is now "${label}"`,
              inputs: inState.map((item) => ({
                label: `${item.reference} · ${item.vendor_name}`,
                value: `${money(item.total_amount)} ${item.currency}`,
                source: item.headline || item.status_label,
                sourceKind: "Invoice",
              })),
            }}
          />
        </span>
        <span className="lf-flow-label">{label}</span>
        <span className="lf-flow-share ds-mono">{Math.round((value / total) * 100)}%</span>
      </Reveal>
    );
  };
  return (
    <section style={{ marginTop: 64 }} aria-labelledby="where-heading">
      <SectionHead
        label="Every invoice, by state"
        title="Where everything is"
        id="where-heading"
        action={
          <LinkButton href="/invoices" tone="ghost" arrow>
            The register
          </LinkButton>
        }
      />
      <Card style={{ marginTop: 22 }}>
        <ol className="lf-flow">
          <span className="lf-flow-line" aria-hidden>
            <span />
          </span>
          <span className="lf-flow-pulse" aria-hidden />
          {FLOW.map((step, index) => cell(step.code, step.label, index, step.code === "posted" ? "pass" : step.code === "awaiting_approval" ? "warn" : undefined))}
        </ol>
        <ol className="lf-flow lf-flow-side">
          {SIDE.map((step, index) => cell(step.code, step.label, index + FLOW.length, "fail"))}
        </ol>
      </Card>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Two systems, no shared transaction                                  */
/* ------------------------------------------------------------------ */
function PostingBand({ invoices }: { invoices: InvoiceBrief[] }) {
  const posted = useMemo(() => invoices.filter((item) => item.status === "posted").slice(0, 12), [invoices]);
  const [details, setDetails] = useState<InvoiceDetail[]>([]);
  const evaluation = useLoad<EvaluationReport | null>("/api/evaluation/last");
  const ledger = useLoad<Page<{ id: number; vendor_name: string; invoice_number: string }>>("/api/ledger?limit=200");

  useEffect(() => {
    if (!posted.length) return;
    let cancelled = false;
    Promise.all(posted.map((item) => api.get<InvoiceDetail>(`/api/invoices/${item.id}`).catch(() => null))).then((rows) => {
      if (!cancelled) setDetails(rows.filter(Boolean) as InvoiceDetail[]);
    });
    return () => {
      cancelled = true;
    };
  }, [posted]);

  const recovered = details.find((detail) => (detail.postings.find((row) => row.status === "posted")?.attempts ?? 0) > 1);
  const subject = recovered ?? details[0] ?? null;
  const posting = subject?.postings.find((row) => row.status === "posted") ?? null;
  const billsForSubject = subject
    ? (ledger.data?.items ?? []).filter((bill) => bill.vendor_name === subject.vendor_name && bill.invoice_number === subject.invoice_number).length
    : 0;

  const facts: JourneyFacts = {
    reached: 2,
    approvalPending: false,
    blocked: false,
    postingKey: posting?.idempotency_key ?? "",
    billReference: posting?.external_reference ?? "",
    ledgerName: posting ? ledgerName(posting.ledger) : "The ledger",
    attempts: posting?.attempts ?? 0,
    bills: billsForSubject,
  };

  const retry = evaluation.data?.criteria.find((row) => row.name === "duplicate bills after a crash");
  const tryOn = invoices.find((item) => item.status === "approved") ?? invoices.find((item) => item.status === "awaiting_approval" && item.kind === "bill");

  return (
    <Band style={{ borderTop: "1px solid var(--ds-ink-line)" }}>
      <div className="lf-posting">
        <div className="lf-posting-copy">
          <Reveal>
            <p className="ds-mono-label" style={{ margin: 0 }}>
              The one thing a controller always asks
            </p>
          </Reveal>
          <Reveal index={1}>
            <h2 className="ds-display lf-posting-title">
              Two systems.
              <br />
              No shared transaction.
              <br />
              <span className="ds-accent-text">Paid once.</span>
            </h2>
          </Reveal>
          <Reveal index={2}>
            <p className="ds-band-lede">
              The ledger and LedgerFlow keep separate records, so posting is two writes and nothing can make them one.
              If the connection dies between them, the ledger has the bill and LedgerFlow does not know. The retry
              carries the same key, finds the bill, and writes nothing new. It cannot be made atomic, only
              recoverable, and this is the recovery.
            </p>
          </Reveal>
          <Reveal index={3}>
            <div className="lf-posting-proof">
              <span className="ds-stat-value" data-tone="pass">
                {retry ? (
                  <Figure
                    value={String(retry.value)}
                    count={retry.value}
                    decimals={0}
                    heading="Bills paid twice after a dropped connection"
                    explain={{
                      formula: retry.question,
                      result: String(retry.value),
                      inputs: [
                        { label: "Measured", value: retry.measured, source: "The last evaluation run", sourceKind: "Evaluation" },
                        { label: "The bar", value: String(retry.bar), source: "Acceptance criteria", sourceKind: "Company policy" },
                      ],
                    }}
                  />
                ) : (
                  "0"
                )}
              </span>
              <span className="lf-posting-proof-words">
                <span className="ds-mono-label">{retry ? "Bills paid twice, measured" : "The bar: bills paid twice"}</span>
                <span className="lf-posting-measured">
                  {retry ? retry.measured : "Not measured yet. The evidence page drops the connection fifty times on purpose and counts."}
                </span>
              </span>
            </div>
            <div className="lf-actions" style={{ marginTop: 24 }}>
              {tryOn && (
                <LinkButton href={`/invoices/${tryOn.id}#paid-once`} tone="primary" size="large" arrow>
                  Try it on a real invoice
                </LinkButton>
              )}
              <LinkButton href="/evidence" tone="ink" size="large">
                {retry ? "See the measurement" : "Measure it"}
              </LinkButton>
            </div>
          </Reveal>
        </div>
        <Reveal index={2} y={36} style={{ minWidth: 0 }}>
          {subject ? (
            <PostingJourney
              facts={facts}
              state={recovered ? "recovered" : "posted"}
              rehearsal
              stacked
              caption={
                recovered ? (
                  <>
                    This happened to <Link href={`/invoices/${subject.id}`}>{subject.reference}</Link>: it was recovered on
                    attempt {posting?.attempts}. Replayed here with its real key.
                  </>
                ) : (
                  <>
                    A rehearsal of the rule on <Link href={`/invoices/${subject.id}`}>{subject.reference}</Link>&apos;s real
                    key. The counters show the rehearsal; the ledger itself holds {billsForSubject || 1} bill for it.
                  </>
                )
              }
            />
          ) : (
            <Loading what="Reading the ledger" />
          )}
        </Reveal>
      </div>
    </Band>
  );
}

/* ------------------------------------------------------------------ */
/* Starting again (administrators only)                                */
/* ------------------------------------------------------------------ */
function Restart({ onRebuild }: { onRebuild: () => void }) {
  const user = readUser();
  const [asking, setAsking] = useState(false);
  if (user?.role !== "administrator") return null;
  return (
    <div className="ds-work" style={{ paddingTop: 40, paddingBottom: 40 }}>
      <div className="lf-restart">
        <div>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Administrator
          </p>
          <p style={{ margin: "6px 0 0", fontWeight: 600 }}>Rebuild the company</p>
          <p style={{ margin: "2px 0 0", fontSize: 13.5, color: "var(--ds-text-2)" }}>
            Builds Hengtai again from its fixed seed and empties the tray. Every invoice, posting and bill goes.
          </p>
        </div>
        {asking ? (
          <div className="lf-actions">
            <Button tone="danger" onClick={onRebuild}>
              Yes, rebuild it
            </Button>
            <Button tone="ghost" onClick={() => setAsking(false)}>
              Keep it
            </Button>
          </div>
        ) : (
          <Button tone="secondary" onClick={() => setAsking(true)}>
            Rebuild
          </Button>
        )}
      </div>
    </div>
  );
}

export const dynamic = "force-dynamic";
