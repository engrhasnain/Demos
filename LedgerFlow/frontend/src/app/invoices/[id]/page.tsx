"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

import { Band, Banner, Button, Card, Empty, Stamp } from "@/design/Surface";
import { Meter } from "@/design/Meter";
import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip, type ChipTone } from "@/design/StatusChip";
import { StepRail } from "@/design/StepRail";
import { useInView } from "@/design/motion";
import { api, readUser } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";
import { asNumber, clock, dateAndTime, dateOnly, duration, engineWords, ledgerName, money, quantity } from "@/lib/format";
import type { ExceptionRow, InvoiceDetail, InvoiceLine, LedgerBill, Page } from "@/lib/types";
import { Figure, type Explain } from "@/components/trace";
import { MatchConstellation, liveApprovals, useBox, useMatchStage, verdictOf, type Stage } from "@/components/match-constellation";
import { PostingJourney, type JourneyFacts, type JourneyState, type Script } from "@/components/posting-journey";
import { ErrorNote, Field, Ledger, Loading, Td, Th, matchState, severityTone, severityWords } from "@/components/ui";

export default function OneInvoice({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, loading, reload, setData } = useLoad<InvoiceDetail>(`/api/invoices/${id}`);
  const ledger = useLoad<Page<LedgerBill>>("/api/ledger?limit=200");
  const action = useAction();
  const [play, setPlay] = useState<{ script: Script; nonce: number } | null>(null);
  const [replay, setReplay] = useState(0);

  // Arriving from "Try it on a real invoice": bring the posting journey into view.
  useEffect(() => {
    if (!data || window.location.hash !== "#paid-once") return;
    const handle = window.setTimeout(() => document.getElementById("paid-once")?.scrollIntoView({ block: "start" }), 450);
    return () => window.clearTimeout(handle);
  }, [data]);

  if (error)
    return (
      <Band top>
        <div style={{ padding: "24px 0" }}>
          <ErrorNote error={error} />
        </div>
      </Band>
    );
  if (loading && !data)
    return (
      <Band top>
        <Loading what="Opening the invoice" />
      </Band>
    );
  if (!data) return null;

  const after = (next: InvoiceDetail | null) => {
    if (next) setData(next);
    else reload();
    ledger.reload();
  };
  const bills = (ledger.data?.items ?? []).filter(
    (bill) => bill.vendor_name === data.vendor_name && bill.invoice_number === data.invoice_number,
  );
  const openExceptions = data.exceptions.filter((row) => !row.resolved_at);
  const blockingExceptions = openExceptions.filter((row) => row.severity === "block");

  return (
    <div>
      <InvoiceBand data={data} replay={replay} onReplay={() => setReplay((value) => value + 1)} />
      <div className="ds-work">
        {blockingExceptions.length > 0 && (
          <Reveal>
            <Banner tone="fail" title="Nothing is paid">
              {data.blocking_reasons.join(" · ")}
            </Banner>
          </Reveal>
        )}
        {action.error && (
          <div style={{ marginTop: 16 }}>
            <ErrorNote error={action.error} />
          </div>
        )}
        <div className="lf-invoice-grid">
          <div className="lf-invoice-main">
            {openExceptions.length > 0 && <Exceptions invoice={data} rows={openExceptions} onChanged={after} action={action} />}
            <PaidOnce invoice={data} bills={bills} action={action} onChanged={after} play={play} setPlay={setPlay} />
            <Lines invoice={data} />
            {liveApprovals(data).length > 0 && <Signatures invoice={data} onChanged={after} action={action} />}
            <History invoice={data} />
          </div>
          <aside className="lf-invoice-side">
            <AsRead invoice={data} />
            {data.purchase_order && <Order invoice={data} />}
            {data.credits_invoice_id && (
              <Card eyebrow="Credit note" title="Applied against an earlier bill">
                <p style={{ margin: 0, fontSize: 13.5, color: "var(--ds-text-2)" }}>
                  A credit is not matched three ways: there is nothing to match it against. It is linked to the bill it credits.
                </p>
                <div style={{ marginTop: 12 }}>
                  <Link className="ds-btn" data-tone="secondary" data-size="small" href={`/invoices/${data.credits_invoice_id}`}>
                    Open the bill it credits →
                  </Link>
                </div>
              </Card>
            )}
            <DocumentCard invoice={data} />
          </aside>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* The band: who, how much, where it is, and the match itself          */
/* ------------------------------------------------------------------ */
function railOf(invoice: InvoiceDetail): { current: number; tone: "accent" | "pass" | "warn" | "fail"; complete: boolean } {
  const verdict = verdictOf(invoice);
  switch (invoice.status) {
    case "received":
      return { current: 0, tone: "accent", complete: false };
    case "read":
      return { current: 1, tone: "accent", complete: false };
    case "checked":
      return { current: 3, tone: "accent", complete: false };
    case "exception":
      return { current: 2, tone: verdict.kind === "stopped" ? "fail" : "warn", complete: false };
    case "awaiting_approval":
      return { current: 3, tone: "warn", complete: false };
    case "approved":
      return { current: 4, tone: "accent", complete: false };
    case "posted":
      return { current: 4, tone: "pass", complete: true };
    case "rejected":
      return { current: 2, tone: "fail", complete: false };
    default:
      return { current: 0, tone: "accent", complete: false };
  }
}

function invoicedExplain(invoice: InvoiceDetail): Explain {
  const foreign = invoice.currency !== "TWD";
  const inputs = [
    { label: "Net", value: money(invoice.net_amount), source: `${invoice.document?.filename ?? "The document"}, as read`, sourceKind: "The invoice" },
    { label: "Business tax", value: money(invoice.tax_amount), source: `${invoice.document?.filename ?? "The document"}, as read`, sourceKind: "The invoice" },
  ];
  if (foreign && invoice.exchange_rate) {
    inputs.push({ label: "Rate on the invoice date", value: invoice.exchange_rate, source: `${invoice.currency} to TWD, ${invoice.invoice_date ?? ""}`, sourceKind: "Exchange rate" });
    inputs.push({ label: "In Taiwan dollars", value: money(invoice.amount_in_base), source: "Both figures are kept", sourceKind: "The ledger" });
  }
  return {
    label: "What the invoice asks for",
    formula: `${money(invoice.net_amount)} net + ${money(invoice.tax_amount)} business tax = ${money(invoice.total_amount)} ${invoice.currency}`,
    result: `${money(invoice.total_amount)} ${invoice.currency}`,
    inputs,
  };
}

function heldExplain(invoice: InvoiceDetail): Explain {
  const held = invoice.lines.filter((line) => asNumber(line.held_amount) > 0);
  return {
    label: "What is held back",
    formula: held.length
      ? held.map((line) => money(line.held_amount)).join(" + ") + ` = ${money(invoice.held_amount)}`
      : "Nothing on any line is held",
    result: money(invoice.held_amount),
    inputs: held.map((line) => ({
      label: `Line ${line.line_number}: ${line.part_code || line.description.slice(0, 24)}`,
      value: money(line.held_amount),
      source: line.note || line.match_label,
      sourceKind: "Matching code",
    })),
  };
}

function InvoiceBand({ data, replay, onReplay }: { data: InvoiceDetail; replay: number; onReplay: () => void }) {
  const look = matchState(data);
  const rail = railOf(data);
  const [viewRef, inView] = useInView<HTMLDivElement>({ threshold: 0.2 });
  const [boxRef, box] = useBox(520);
  const stage = useMatchStage(inView ? `${data.id}-${data.status}-${replay}` : null);
  const verdict = verdictOf(data);
  const credit = data.kind === "credit_note";

  const figures: { label: string; value: string; tone?: "pass" | "warn" | "fail"; count: number; heading: string; trace?: InvoiceDetail["trace"]; explain?: Explain; hint?: string }[] = [
    {
      label: credit ? "Credit" : "Invoiced",
      value: `${money(data.total_amount)} ${data.currency}`,
      count: asNumber(data.total_amount),
      heading: "What the invoice asks for",
      explain: invoicedExplain(data),
      hint: data.currency !== "TWD" ? `${money(data.amount_in_base)} TWD at ${data.exchange_rate}` : `net ${money(data.net_amount)} + tax ${money(data.tax_amount)}`,
    },
    {
      label: "Payable",
      value: money(data.approved_amount),
      tone: "pass",
      count: asNumber(data.approved_amount),
      heading: "What is payable",
      trace: data.trace,
      hint: data.status === "posted" ? "in the ledger" : "after the three-way match",
    },
    {
      label: "Held back",
      value: money(data.held_amount),
      tone: asNumber(data.held_amount) > 0 ? "warn" : undefined,
      count: asNumber(data.held_amount),
      heading: "What is held back",
      explain: heldExplain(data),
      hint: data.hold_reason || (asNumber(data.held_amount) > 0 ? "waiting for the goods or a person" : "nothing held"),
    },
  ];

  return (
    <Band top>
      <div className="lf-invoice-band">
        <div style={{ minWidth: 0 }}>
          <Reveal y={16}>
            <Link href="/invoices" className="lf-back">
              ← Every invoice
            </Link>
          </Reveal>
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone={look.tone === "fail" ? "fail" : look.tone === "warn" ? "warn" : "accent"} aria-hidden />
              {credit ? "Credit note" : "Invoice"} <span className="ds-eyebrow-sep">·</span> {data.reference}{" "}
              <span className="ds-eyebrow-sep">·</span> read by {engineWords(data.read_with)}
            </span>
          </Reveal>
          <Reveal index={1} y={32}>
            <h1 className="ds-display lf-invoice-title">{data.vendor_name || "Unidentified supplier"}</h1>
          </Reveal>
          <div className="lf-stamp-row">
            <span className="lf-stamp" data-tone={look.tone} role="status">
              {look.label}
              {data.posted_untouched && <small>untouched</small>}
            </span>
            <Reveal index={2} y={24}>
              <div className="lf-chips" style={{ marginTop: 0 }}>
                {data.status_label.toLowerCase() !== look.label.toLowerCase() && (
                  <StatusChip tone="neutral" surface="dark">
                    {data.status_label}
                  </StatusChip>
                )}
                <span className="ds-stamp">{data.invoice_number || "no number read"}</span>
                {data.invoice_date && <span className="ds-stamp">{dateOnly(data.invoice_date)}</span>}
              </div>
            </Reveal>
          </div>
          <Reveal index={3} y={28}>
            <div className="lf-figures">
              {figures.map((figure) => (
                <div key={figure.label} className="lf-figure">
                  <span className="ds-mono-label">{figure.label}</span>
                  <span className="lf-figure-value" data-tone={figure.tone}>
                    <Figure
                      value={figure.value}
                      count={figure.count}
                      decimals={2}
                      heading={figure.heading}
                      trace={figure.trace}
                      explain={figure.trace?.steps?.length ? undefined : figure.explain}
                      note={figure.label === "Held back" ? data.hold_reason || undefined : undefined}
                    />
                  </span>
                  {figure.hint && <span className="lf-figure-hint">{figure.hint}</span>}
                </div>
              ))}
            </div>
          </Reveal>
          <Reveal index={4} y={24}>
            <div className="lf-invoice-rail">
              <StepRail
                label="Where this invoice is"
                current={rail.current}
                tone={rail.tone}
                complete={rail.complete}
                steps={[
                  { key: "received", label: "Received", sub: clock(data.received_at) },
                  { key: "read", label: "Read", sub: data.read_with === "built-in" ? "built-in engine" : engineWords(data.read_with) },
                  { key: "matched", label: credit ? "Recognised as a credit" : "Matched three ways", sub: verdict.word },
                  { key: "signed", label: "Signed", sub: liveApprovals(data).length ? `${liveApprovals(data).filter((a) => a.status === "approved").length} of ${liveApprovals(data).length}` : "not needed" },
                  { key: "ledger", label: "In the ledger", sub: data.postings.find((p) => p.status === "posted")?.external_reference || "not yet" },
                ]}
              />
            </div>
          </Reveal>
        </div>

        <Reveal index={2} y={36} style={{ minWidth: 0 }}>
          <div className="lf-invoice-stage" ref={viewRef}>
            <div className="lf-invoice-canvas" ref={boxRef}>
              <MatchConstellation detail={data} stage={stage as Stage} compact={box.compact} aspect={box.aspect} ambient={box.compact ? 20 : 34} />
            </div>
            <div className="lf-invoice-stage-foot">
              <span className="ds-mono-label">The three-way match, from this invoice&apos;s own lines</span>
              <button type="button" className="ds-btn" data-tone="ink" data-size="small" onClick={onReplay}>
                Replay it
              </button>
            </div>
          </div>
        </Reveal>
      </div>
    </Band>
  );
}

/* ------------------------------------------------------------------ */
/* Paid once: the posting journey, on this invoice                     */
/* ------------------------------------------------------------------ */
function PaidOnce({
  invoice,
  bills,
  action,
  onChanged,
  play,
  setPlay,
}: {
  invoice: InvoiceDetail;
  bills: LedgerBill[];
  action: ReturnType<typeof useAction>;
  onChanged: (next: InvoiceDetail | null) => void;
  play: { script: Script; nonce: number } | null;
  setPlay: (play: { script: Script; nonce: number }) => void;
}) {
  const user = readUser();
  const posting = invoice.postings[invoice.postings.length - 1] ?? null;
  const posted = invoice.status === "posted";
  const dropped = !posted && invoice.postings.some((row) => row.status === "failed");
  const verdict = verdictOf(invoice);
  const open = invoice.exceptions.filter((row) => !row.resolved_at && row.severity !== "note");
  const blocked = open.length > 0;
  const state: JourneyState = posted ? ((posting?.attempts ?? 1) > 1 ? "recovered" : "posted") : dropped ? "dropped" : "waiting";
  const [note, setNote] = useState<string | null>(null);

  const reached = posted || dropped ? 3 : ["approved", "checked"].includes(invoice.status) ? 2 : invoice.status === "awaiting_approval" ? 1 : blocked ? 0 : 1;
  const facts: JourneyFacts = {
    reached,
    approvalPending: invoice.status === "awaiting_approval",
    blocked,
    blockedReason: verdict.reason,
    postingKey: posting?.idempotency_key ?? "",
    billReference: posting?.external_reference || bills[0]?.external_reference || "",
    ledgerName: posting ? ledgerName(posting.ledger) : invoice.entity_code === "US" ? "United States ledger" : "Taiwan ledger",
    attempts: posting?.attempts ?? 0,
    bills: bills.length,
  };
  const mayPost = !blocked && invoice.blocking_reasons.length === 0;
  const mayDrop = mayPost && !posted && !dropped && user?.role !== "clerk";

  const doPost = () =>
    action.run("post", () => api.post<InvoiceDetail>(`/api/invoices/${invoice.id}/post`)).then((next) => {
      if (next) {
        setNote(null);
        setPlay({ script: dropped ? "retry" : "post", nonce: Date.now() });
      }
      onChanged(next);
    });

  const doDrop = () =>
    action
      .run("drop", () =>
        api.post<{ dropped: boolean; message: string; bills_in_the_ledger: number; invoice: InvoiceDetail }>(
          `/api/invoices/${invoice.id}/post-with-a-dropped-connection`,
          { mode: "after_ledger_write" },
        ),
      )
      .then((result) => {
        if (result) {
          setNote(`${result.message} Bills in the ledger: ${result.bills_in_the_ledger}.`);
          setPlay({ script: result.dropped ? "drop" : "post", nonce: Date.now() });
          onChanged(result.invoice);
        } else onChanged(null);
      });

  return (
    <section id="paid-once" className="lf-anchor">
      <Card
        eyebrow="Two systems · no shared transaction"
        title={posted ? (state === "recovered" ? "Paid once, after a dropped connection" : "Paid once") : dropped ? "Interrupted half way" : "Posting"}
        subtitle="LedgerFlow's records and the ledger are separate systems. Posting writes the bill there, then records it here. The key makes a retry land on the same bill."
        action={
          <StatusChip tone={posted ? "pass" : dropped ? "fail" : blocked ? "fail" : "warn"} pulse={!posted}>
            {posted ? (state === "recovered" ? "Recovered" : "Posted") : dropped ? "Not confirmed" : blocked ? "Stopped" : "Not posted"}
          </StatusChip>
        }
      >
        <PostingJourney
          facts={facts}
          state={state}
          play={play}
          caption={
            posting ? (
              <>
                Key <span className="ds-mono">{posting.idempotency_key}</span>: a fingerprint of the company, the supplier,
                the invoice number, the amount and the currency. The same invoice always makes the same key.
              </>
            ) : (
              "The key is made from the company, the supplier, the invoice number, the amount and the currency the first time it is posted."
            )
          }
          footer={
            state === "recovered" ? (
              <button type="button" className="ds-btn" data-tone="ink" data-size="small" onClick={() => setPlay({ script: "replay", nonce: Date.now() })}>
                Replay what happened
              </button>
            ) : null
          }
        />
        {!posted && (
          <div className="lf-paid-actions">
            <Button tone="primary" busy={action.busy === "post"} disabled={!mayPost || Boolean(action.busy)} onClick={() => void doPost()} arrow>
              {dropped ? "Post it again" : "Post it"}
            </Button>
            {mayDrop && (
              <Button tone="danger" busy={action.busy === "drop"} disabled={Boolean(action.busy)} onClick={() => void doDrop()}>
                Post, but drop the connection
              </Button>
            )}
            <Button
              tone="ghost"
              busy={action.busy === "recheck"}
              disabled={Boolean(action.busy)}
              onClick={() => void action.run("recheck", () => api.post<InvoiceDetail>(`/api/invoices/${invoice.id}/recheck`)).then(onChanged)}
            >
              Check again
            </Button>
          </div>
        )}
        {!posted && !mayPost && (
          <p className="lf-paid-why">{invoice.may_post_untouched_reason || invoice.blocking_reasons.join(" · ")}</p>
        )}
        {note && (
          <div style={{ marginTop: 14 }}>
            <Banner tone="warn" title="The connection dropped after the ledger took the bill">
              {note} Press Post it again: the key will find the bill.
            </Banner>
          </div>
        )}
      </Card>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Stopped by                                                          */
/* ------------------------------------------------------------------ */
type DuplicateMatch = { invoice_id: number; reference: string; invoice_number: string; status: string; total: string; currency: string; signals: string[] };

function ExceptionDetail({ row }: { row: ExceptionRow }) {
  if (row.kind === "duplicate") {
    const matches = (row.detail.matches as DuplicateMatch[] | undefined) ?? [];
    return (
      <div className="lf-exception-detail">
        {matches.map((match) => (
          <div key={match.invoice_id} className="lf-duplicate">
            <span className="ds-mono-label">The original</span>
            <Link href={`/invoices/${match.invoice_id}`} className="lf-duplicate-link">
              {match.reference} · {match.invoice_number} · {money(match.total)} {match.currency} →
            </Link>
            <span className="lf-signals">
              {match.signals.map((signal) => (
                <StatusChip key={signal} tone="fail" size="small">
                  {signal}
                </StatusChip>
              ))}
            </span>
          </div>
        ))}
      </div>
    );
  }
  if (row.kind === "wrong_buyer_tax_id") {
    return (
      <div className="lf-exception-detail lf-compare">
        <span>
          <span className="ds-mono-label">On the invoice</span>
          <b className="ds-mono" style={{ color: "var(--ds-fail-ink)" }}>{String(row.detail.on_invoice ?? "")}</b>
        </span>
        <span>
          <span className="ds-mono-label">Ours</span>
          <b className="ds-mono">{String(row.detail.ours ?? "")}</b>
        </span>
      </div>
    );
  }
  return null;
}

function Exceptions({
  invoice,
  rows,
  onChanged,
  action,
}: {
  invoice: InvoiceDetail;
  rows: ExceptionRow[];
  onChanged: (next: InvoiceDetail | null) => void;
  action: ReturnType<typeof useAction>;
}) {
  const [note, setNote] = useState<Record<number, string>>({});
  return (
    <Card eyebrow={`${rows.length} open`} title="Stopped by" className="lf-stopped">
      <ul className="lf-exceptions">
        {rows.map((row, index) => {
          const tone = severityTone(row.severity);
          return (
            <Reveal as="li" key={row.id} index={index} className="lf-exception" data-tone={tone}>
              <div className="lf-exception-head">
                <StatusChip tone={tone} pulse={row.severity === "block"}>
                  {severityWords(row.severity)}
                </StatusChip>
                <span className="lf-exception-label">{row.label}</span>
              </div>
              <p className="lf-exception-summary">{row.summary}</p>
              <ExceptionDetail row={row} />
              {row.kind === "bank_detail_change" ? (
                <Link href={`/suppliers/${invoice.vendor?.id}`} className="ds-btn" data-tone="primary" data-size="small" style={{ marginTop: 12 }}>
                  Make the call-back →
                </Link>
              ) : (
                <div className="lf-resolve">
                  <label className="ds-sr-only" htmlFor={`resolve-${row.id}`}>
                    What you did about {row.label}
                  </label>
                  <input
                    id={`resolve-${row.id}`}
                    className="ds-input"
                    value={note[row.id] ?? ""}
                    onChange={(event) => setNote((current) => ({ ...current, [row.id]: event.target.value }))}
                    placeholder="What you did about it"
                  />
                  <Button
                    size="small"
                    busy={action.busy === `resolve-${row.id}`}
                    onClick={() =>
                      void action
                        .run(`resolve-${row.id}`, () =>
                          api.post<InvoiceDetail>(`/api/invoices/${invoice.id}/exceptions/${row.id}/resolve`, { resolution: note[row.id] ?? "" }),
                        )
                        .then(onChanged)
                    }
                  >
                    Clear it
                  </Button>
                </div>
              )}
            </Reveal>
          );
        })}
      </ul>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Lines                                                               */
/* ------------------------------------------------------------------ */
function lineTone(line: InvoiceLine): ChipTone {
  switch (line.match_result) {
    case "matched":
      return "pass";
    case "partly_received":
      return "warn";
    case "not_received":
    case "over_tolerance":
      return "fail";
    case "not_ordered":
      return asNumber(line.held_amount) > 0 ? "fail" : "accent";
    default:
      return "info";
  }
}

function Lines({ invoice }: { invoice: InvoiceDetail }) {
  if (invoice.lines.length === 0) {
    return (
      <Card title="Lines">
        <Empty title="No lines could be read." />
      </Card>
    );
  }
  const lines = invoice.lines.slice().sort((a, b) => a.line_number - b.line_number);
  return (
    <Card flush eyebrow={`${lines.length} ${lines.length === 1 ? "line" : "lines"} · press a payable figure`} title="Lines, against the order and the delivery">
      <div className="lf-only-wide">
        <Ledger
          head={
            <>
              <Th width="2.5rem">#</Th>
              <Th>Part</Th>
              <Th align="right">Billed</Th>
              <Th align="right">Arrived</Th>
              <Th align="right">Price</Th>
              <Th align="right">Payable</Th>
              <Th align="right">Held</Th>
              <Th>Match</Th>
            </>
          }
        >
          {lines.map((line, index) => {
            const tone = lineTone(line);
            return (
              <Reveal as="tr" key={line.id} index={index} y={20}>
                <Td className="ds-rowmark" style={{ "--row-tone": `var(--ds-${tone === "accent" ? "accent" : tone === "info" ? "info" : tone})` } as React.CSSProperties}>
                  <span className="ds-mono" style={{ color: "var(--ds-text-3)" }}>
                    {line.line_number}
                  </span>
                </Td>
                <Td>
                  <span className="ds-stamp" data-tone="light">
                    {line.part_code || "—"}
                  </span>
                  <span className="lf-line-desc">{line.description}</span>
                </Td>
                <Td align="right">{quantity(line.quantity)}</Td>
                <Td align="right" title="Delivered to date, less what was billed before">
                  {quantity(line.received_to_date)}
                </Td>
                <Td align="right">{money(line.unit_price)}</Td>
                <Td align="right" style={{ fontWeight: 650 }}>
                  <Figure value={money(line.payable_amount)} heading={`Line ${line.line_number}: what is payable`} trace={line.trace} note={line.note || undefined} />
                </Td>
                <Td align="right" style={asNumber(line.held_amount) > 0 ? { color: "var(--ds-warn-ink)", fontWeight: 650 } : undefined}>
                  {money(line.held_amount)}
                </Td>
                <Td>
                  <StatusChip tone={tone} size="small">
                    {line.match_label}
                  </StatusChip>
                </Td>
              </Reveal>
            );
          })}
        </Ledger>
      </div>
      <ul className="lf-only-narrow lf-line-cards">
        {lines.map((line, index) => {
          const tone = lineTone(line);
          return (
            <Reveal as="li" key={line.id} index={index} className="lf-line-card">
              <div className="lf-line-card-head">
                <span className="ds-stamp" data-tone="light">
                  {line.line_number} · {line.part_code || "—"}
                </span>
                <StatusChip tone={tone} size="small">
                  {line.match_label}
                </StatusChip>
              </div>
              <p className="lf-line-desc">{line.description}</p>
              <dl className="lf-line-facts">
                <div>
                  <dt className="ds-mono-label">Billed</dt>
                  <dd>{quantity(line.quantity)}</dd>
                </div>
                <div>
                  <dt className="ds-mono-label">Arrived</dt>
                  <dd>{quantity(line.received_to_date)}</dd>
                </div>
                <div>
                  <dt className="ds-mono-label">Payable</dt>
                  <dd>
                    <Figure value={money(line.payable_amount)} heading={`Line ${line.line_number}: what is payable`} trace={line.trace} note={line.note || undefined} />
                  </dd>
                </div>
                <div>
                  <dt className="ds-mono-label">Held</dt>
                  <dd>{money(line.held_amount)}</dd>
                </div>
              </dl>
            </Reveal>
          );
        })}
      </ul>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* Signatures, as a chain                                              */
/* ------------------------------------------------------------------ */
function Signatures({
  invoice,
  onChanged,
  action,
}: {
  invoice: InvoiceDetail;
  onChanged: (next: InvoiceDetail | null) => void;
  action: ReturnType<typeof useAction>;
}) {
  const rows = liveApprovals(invoice);
  const signed = rows.filter((row) => row.status === "approved").length;
  const decide = (rowId: number, approved: boolean) =>
    void action
      .run(`${approved ? "yes" : "no"}-${rowId}`, () =>
        api.post<InvoiceDetail>(`/api/invoices/${invoice.id}/approvals/${rowId}`, { approved, comment: approved ? "" : "Refused." }),
      )
      .then(onChanged);

  return (
    <Card eyebrow={`${signed} of ${rows.length} signed`} title="Who has to sign">
      <NodeChain
        stagger={90}
        fill={rows.length ? signed / rows.length : 0}
        live={rows.some((row) => row.status === "pending")}
        items={[
          ...rows.map((row) => ({
            key: String(row.id),
            tone: (row.status === "approved" ? "pass" : row.status === "rejected" ? "fail" : "warn") as ChipTone,
            state: (row.status === "pending" ? "active" : "done") as "active" | "done",
            marker: row.status === "approved" ? "✓" : row.status === "rejected" ? "×" : String(row.step),
            content: (
              <div className="lf-sign">
                <div className="lf-sign-head">
                  <b>{row.title}</b>
                  <StatusChip tone={row.status === "approved" ? "pass" : row.status === "rejected" ? "fail" : "warn"} pulse={row.status === "pending"} size="small">
                    {row.status === "pending" ? `Waiting: ${row.required_role_label}` : row.status === "approved" ? "Signed" : "Refused"}
                  </StatusChip>
                  {row.step > 1 && <span className="ds-mono-label">Second signature, from somebody else</span>}
                </div>
                <p className="lf-sign-reason">{row.reason}</p>
                {row.decided_by && (
                  <p className="lf-sign-by ds-mono">
                    {row.decided_by.name} · {dateAndTime(row.decided_at)} · {row.comment || "no comment"}
                  </p>
                )}
                {row.status === "pending" && (
                  <div className="lf-actions" style={{ marginTop: 10 }}>
                    <Button tone="primary" size="small" busy={action.busy === `yes-${row.id}`} disabled={Boolean(action.busy)} onClick={() => decide(row.id, true)}>
                      Sign
                    </Button>
                    <Button tone="danger" size="small" busy={action.busy === `no-${row.id}`} disabled={Boolean(action.busy)} onClick={() => decide(row.id, false)}>
                      Refuse
                    </Button>
                  </div>
                )}
              </div>
            ),
          })),
          {
            key: "ledger",
            tone: (invoice.status === "posted" ? "pass" : "info") as ChipTone,
            state: (invoice.status === "posted" ? "done" : "waiting") as "done" | "waiting",
            marker: "L",
            content: (
              <div className="lf-sign">
                <b>Then the ledger</b>
                <p className="lf-sign-reason">{invoice.status === "posted" ? "Posted." : "Posted once every signature is in."}</p>
              </div>
            ),
          },
        ]}
      />
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* History                                                             */
/* ------------------------------------------------------------------ */
type Check = { check: string; passed: boolean; detail: string };

function History({ invoice }: { invoice: InvoiceDetail }) {
  const events = invoice.events.filter((event) => event.kind !== "status_changed");
  const moves = invoice.events.length - events.length;
  return (
    <Card eyebrow={`${events.length} steps · ${moves} moves between states`} title="What happened, in order">
      <NodeChain
        stagger={70}
        items={events.map((event) => {
          const checks = (event.detail?.checks as Check[] | undefined) ?? [];
          const tone: ChipTone =
            event.kind === "posted" ? "pass" : event.kind === "stopped_for_a_person" ? "warn" : event.actor_type === "person" ? "accent" : "info";
          return {
            key: String(event.id),
            tone,
            marker: event.actor_type === "person" ? "P" : event.actor_type === "supplier" ? "S" : event.kind === "posted" ? "✓" : "·",
            content: (
              <div className="lf-event">
                <p className="lf-event-summary">{event.summary}</p>
                <p className="lf-event-meta ds-mono">
                  {clock(event.occurred_at)} · {event.actor_name}
                  {event.duration_ms > 0 && ` · ${duration(event.duration_ms)}`}
                </p>
                <div className="lf-event-chips">
                  {event.engine ? (
                    <StatusChip tone="accent" size="small">
                      Read by {engineWords(event.engine)}
                    </StatusChip>
                  ) : event.actor_type === "agent" || event.actor_type === "system" ? (
                    <StatusChip tone="neutral" size="small">
                      Deterministic code
                    </StatusChip>
                  ) : null}
                </div>
                {checks.length > 0 && <Checks checks={checks} />}
              </div>
            ),
          };
        })}
      />
    </Card>
  );
}

function Checks({ checks }: { checks: Check[] }) {
  const passed = checks.filter((check) => check.passed).length;
  return (
    <div className="lf-checks">
      <p className="ds-mono-label" style={{ margin: 0 }}>
        {passed} of {checks.length} checks passed
      </p>
      <ul>
        {checks.map((check, index) => (
          <li key={`${check.check}-${index}`} data-passed={check.passed ? "" : undefined}>
            <StatusChip tone={check.passed ? "pass" : "warn"} size="small">
              {check.passed ? "Pass" : "Note"}
            </StatusChip>
            <span className="lf-check-name">{check.check.charAt(0).toUpperCase() + check.check.slice(1)}</span>
            <span className="lf-check-detail">{check.detail}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* The side: as read, the order, the document                          */
/* ------------------------------------------------------------------ */
function AsRead({ invoice }: { invoice: InvoiceDetail }) {
  const confidence = invoice.as_read.confidence ?? {};
  const rows: [string, string, string][] = [
    ["Number", "invoice_number", invoice.as_read.invoice_number],
    ["Date", "invoice_date", invoice.invoice_date ?? ""],
    ["Purchase order", "purchase_order_number", invoice.as_read.purchase_order_number],
    ["Our business number", "buyer_tax_identifier", invoice.as_read.buyer_tax_identifier],
    ["Their business number", "seller_tax_identifier", invoice.as_read.seller_tax_identifier],
    ["Bank account", "bank_account", invoice.as_read.bank_account],
  ];
  return (
    <Card eyebrow={`Read by ${engineWords(invoice.read_with)}`} title="As read from the page">
      <dl className="lf-read">
        {rows.map(([label, name, value], index) => {
          const sure = confidence[name];
          const percent = sure !== undefined ? Math.round(sure * 100) : null;
          return (
            <div key={name} className="lf-read-row">
              <dt className="ds-mono-label">{label}</dt>
              <dd className="ds-mono">{value || "—"}</dd>
              {percent !== null && value && (
                <div className="lf-read-sure">
                  <Meter value={sure} size="small" tone={sure >= 0.99 ? "pass" : sure >= 0.9 ? "accent" : "warn"} delay={index * 80} label={`${percent} per cent sure`} />
                  <span className="lf-read-percent">
                    <Figure
                      value={`${percent}%`}
                      heading={`How sure the reading was: ${label.toLowerCase()}`}
                      explain={{
                        formula: `The reading engine's confidence in this field, as a share of certain (1.0 = 100%)`,
                        result: `${percent}%`,
                        inputs: [
                          { label: "Field", value: label, source: invoice.document?.filename ?? "The document", sourceKind: "The document" },
                          { label: "Read as", value: value, source: `Read by ${engineWords(invoice.read_with)}`, sourceKind: "Reading engine" },
                          { label: "Confidence", value: String(sure), source: "Stored with the invoice", sourceKind: "Reading engine" },
                        ],
                      }}
                    />
                  </span>
                </div>
              )}
            </div>
          );
        })}
      </dl>
      <p className="lf-read-note">A barcode, when there is one, outranks the page and is read at full confidence. The figures are checked by code either way.</p>
    </Card>
  );
}

function Order({ invoice }: { invoice: InvoiceDetail }) {
  const order = invoice.purchase_order!;
  return (
    <Card eyebrow="Purchase order" title={order.number} action={<Stamp tone="light">{order.entity_code}</Stamp>}>
      <dl>
        <Field label="Placed">{dateOnly(order.ordered_on)}</Field>
        <Field label="Currency">{order.currency}</Field>
      </dl>
      <ul className="lf-order-lines">
        {order.lines.map((line) => (
          <li key={line.id}>
            <span className="ds-stamp" data-tone="light">
              {line.part_code}
            </span>
            <span className="lf-order-line-desc">{line.description}</span>
            <span className="ds-mono lf-order-line-sum">
              {quantity(line.quantity_ordered)} × {money(line.unit_price)} = {money(line.line_total)}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function DocumentCard({ invoice }: { invoice: InvoiceDetail }) {
  const [show, setShow] = useState(false);
  const document = invoice.document;
  return (
    <Card
      eyebrow="As it arrived"
      title="The document"
      action={
        <Button size="small" tone="secondary" onClick={() => setShow((value) => !value)}>
          {show ? "Hide it" : "Show it"}
        </Button>
      }
    >
      <dl>
        <Field label="File">{document?.filename ?? "—"}</Field>
        <Field label="Pages">{document?.page_count ?? 1}</Field>
        <Field label="From">{document?.received_from || "—"}</Field>
        <Field label="Received">{dateAndTime(document?.received_at)}</Field>
        <Field label="Read by">{engineWords(invoice.read_with)}</Field>
        {document?.has_barcode && (
          <Field label="Barcode">
            <StatusChip tone="pass" size="small">
              Decoded, used as the truth
            </StatusChip>
          </Field>
        )}
      </dl>
      {show && <DocumentText id={invoice.id} />}
    </Card>
  );
}

function DocumentText({ id }: { id: number }) {
  const { data } = useLoad<{ text: string; barcode_payload: string }>(`/api/invoices/${id}/document`);
  const text = useMemo(() => (data ? `${data.text}${data.barcode_payload ? `\n\n[barcode] ${data.barcode_payload}` : ""}` : ""), [data]);
  if (!data) return <Loading what="Loading the document" />;
  return <pre className="lf-document">{text}</pre>;
}

export const dynamic = "force-dynamic";
