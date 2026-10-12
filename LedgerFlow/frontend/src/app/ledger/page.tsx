"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { Constellation } from "@/design/Constellation";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { api } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { asNumber, count, dateOnly, ledgerName, money } from "@/lib/format";
import type { Dashboard, InvoiceBrief, InvoiceDetail, LedgerBill, Page } from "@/lib/types";
import { Figure } from "@/components/trace";
import { PostingJourney, shortKey } from "@/components/posting-journey";
import { Card, Empty, ErrorNote, Ledger, Loading, PageBand, SectionHead, Td, Th } from "@/components/ui";

/** Two lanes of nodes: our records above, the ledger below, joined once each. */
const LANES = Array.from({ length: 7 }, (_, index) => [
  { id: `t-${index}`, x: 0.56 + index * 0.06, y: 0.3, r: 2.6, tone: "accent" as const, lit: true },
  { id: `b-${index}`, x: 0.56 + index * 0.06, y: 0.72, r: 3, tone: "light" as const, ring: index === 6 },
]).flat();
const LANE_LINKS = Array.from({ length: 7 }, (_, index) => ({ from: `t-${index}`, to: `b-${index}`, tone: "accent" as const, lit: index % 2 === 0 }));

export default function LedgerPage() {
  const { data, error, loading } = useLoad<Page<LedgerBill>>("/api/ledger?limit=200");
  const board = useLoad<Dashboard>("/api/dashboard");
  const posted = useLoad<Page<InvoiceBrief>>("/api/invoices?status=posted&limit=200");
  const bills = useMemo(() => data?.items ?? [], [data]);

  // Each bill against the posting LedgerFlow recorded for it: one each, never two.
  const [details, setDetails] = useState<Record<string, InvoiceDetail>>({});
  useEffect(() => {
    const rows = posted.data?.items ?? [];
    if (!rows.length) return;
    let cancelled = false;
    Promise.all(rows.slice(0, 40).map((row) => api.get<InvoiceDetail>(`/api/invoices/${row.id}`).catch(() => null))).then((list) => {
      if (cancelled) return;
      const next: Record<string, InvoiceDetail> = {};
      list.forEach((detail) => {
        const posting = detail?.postings.find((p) => p.status === "posted");
        if (detail && posting) next[posting.external_reference] = detail;
      });
      setDetails(next);
    });
    return () => {
      cancelled = true;
    };
  }, [posted.data]);

  const byLedger = useMemo(() => {
    const map = new Map<string, { count: number; total: number; currency: string }>();
    bills.forEach((bill) => {
      const entry = map.get(bill.ledger) ?? { count: 0, total: 0, currency: bill.currency };
      entry.count += 1;
      entry.total += asNumber(bill.amount);
      map.set(bill.ledger, entry);
    });
    return [...map.entries()];
  }, [bills]);

  const pairs = bills.map((bill) => {
    const detail = details[bill.external_reference];
    const posting = detail?.postings.find((p) => p.status === "posted");
    const twins = bills.filter((other) => other.vendor_name === bill.vendor_name && other.invoice_number === bill.invoice_number).length;
    return { bill, detail, posting, twins };
  });
  const recovered = pairs.find((pair) => (pair.posting?.attempts ?? 0) > 1);
  const subject = recovered ?? pairs.find((pair) => pair.posting) ?? null;
  const doubles = pairs.filter((pair) => pair.twins > 1).length;

  return (
    <div>
      <PageBand
        eyebrow={["The ledger", "another system", `${count(data?.total ?? 0)} bills`]}
        title="What reached the ledger."
        accent="Each bill, exactly once."
        lede="These are the bills the accounting system holds, read from it directly. Each one sits beside the posting LedgerFlow recorded for it, with the key both sides share."
        canvas={<Constellation nodes={LANES} links={LANE_LINKS} ambient={34} traffic={{ paths: LANE_LINKS.map((l) => [l.from, l.to]), every: 900 }} />}
        aside={
          <div className="lf-band-tiles">
            <div className="lf-band-tile" data-static="">
              <span className="ds-stat-value" data-tone="pass">
                <Figure
                  value={money(board.data?.posted_amount ?? "0")}
                  count={asNumber(board.data?.posted_amount)}
                  decimals={2}
                  heading="Posted to the ledger, in Taiwan dollars"
                  explain={{
                    formula: "The payable amount of every posted invoice, added up by the server",
                    result: `${money(board.data?.posted_amount ?? "0")} TWD`,
                    inputs: bills.slice(0, 30).map((bill) => ({
                      label: `${bill.external_reference} · ${bill.vendor_name}`,
                      value: `${money(bill.amount)} ${bill.currency}`,
                      source: ledgerName(bill.ledger),
                      sourceKind: "The ledger",
                    })),
                  }}
                />
              </span>
              <span className="ds-mono-label ds-stat-label">In the ledger, TWD</span>
            </div>
            {byLedger.map(([code, entry]) => (
              <div key={code} className="lf-band-tile" data-static="">
                <span className="ds-stat-value">
                  <Figure
                    value={count(entry.count)}
                    count={entry.count}
                    decimals={0}
                    heading={`Bills in the ${ledgerName(code)}`}
                    explain={{
                      formula: `Bills the ${ledgerName(code)} holds, counted from the ledger itself`,
                      inputs: bills
                        .filter((bill) => bill.ledger === code)
                        .slice(0, 30)
                        .map((bill) => ({ label: bill.external_reference, value: `${money(bill.amount)} ${bill.currency}`, source: bill.vendor_name, sourceKind: "The ledger" })),
                    }}
                  />
                </span>
                <span className="ds-mono-label ds-stat-label">{ledgerName(code)}</span>
              </div>
            ))}
            <div className="lf-band-tile" data-static="">
              <span className="ds-stat-value" data-tone={doubles ? "fail" : "pass"}>
                <Figure
                  value={count(doubles)}
                  count={doubles}
                  decimals={0}
                  heading="Invoices with more than one bill"
                  explain={{
                    formula: "Bills in the ledger that share a supplier and an invoice number with another bill",
                    result: String(doubles),
                    inputs: bills.slice(0, 30).map((bill) => ({ label: `${bill.vendor_name} · ${bill.invoice_number}`, value: bill.external_reference, source: ledgerName(bill.ledger), sourceKind: "The ledger" })),
                  }}
                />
              </span>
              <span className="ds-mono-label ds-stat-label">Paid twice</span>
            </div>
          </div>
        }
      />

      <div className="ds-work">
        {error && <ErrorNote error={error} />}

        {subject?.posting && subject.detail && (
          <section aria-labelledby="journey-heading" style={{ marginBottom: 56 }}>
            <SectionHead label="Two systems · no shared transaction" title="How a bill gets here once" id="journey-heading" />
            <Reveal style={{ marginTop: 22 }}>
              <PostingJourney
                rehearsal
                state={recovered ? "recovered" : "posted"}
                facts={{
                  reached: 2,
                  approvalPending: false,
                  blocked: false,
                  postingKey: subject.posting.idempotency_key,
                  billReference: subject.bill.external_reference,
                  ledgerName: ledgerName(subject.bill.ledger),
                  attempts: subject.posting.attempts,
                  bills: subject.twins,
                }}
                caption={
                  recovered
                    ? `${subject.detail.reference} was recovered on attempt ${subject.posting.attempts}: replayed here with its real key.`
                    : `A rehearsal of the rule on ${subject.detail.reference}'s real key, ${shortKey(subject.posting.idempotency_key)}.`
                }
              />
            </Reveal>
          </section>
        )}

        <Card flush eyebrow={`${count(data?.total ?? 0)} bills · newest first`} title="Bills in the ledger, beside our postings">
          {loading && !data ? (
            <Loading what="Reading the ledger" />
          ) : bills.length === 0 ? (
            <div style={{ padding: 20 }}>
              <Empty title="Nothing posted yet." />
            </div>
          ) : (
            <Ledger
              className="lf-ledger-table"
              head={
                <>
                  <Th>Bill in the ledger</Th>
                  <Th>Supplier</Th>
                  <Th>Invoice</Th>
                  <Th>Our posting</Th>
                  <Th>Posted</Th>
                  <Th align="right">Amount</Th>
                </>
              }
            >
              {pairs.map(({ bill, detail, posting, twins }, index) => (
                <Reveal as="tr" key={bill.id} index={index} y={20}>
                  <Td className="ds-rowmark" style={{ "--row-tone": twins > 1 ? "var(--ds-fail)" : "var(--ds-pass)" } as React.CSSProperties}>
                    <span className="ds-mono" style={{ fontWeight: 650 }}>
                      {bill.external_reference}
                    </span>
                    <span className="lf-cell-sub">{ledgerName(bill.ledger)}</span>
                  </Td>
                  <Td>{bill.vendor_name}</Td>
                  <Td>
                    {detail ? (
                      <Link href={`/invoices/${detail.id}`} className="lf-cell-link ds-mono">
                        {bill.invoice_number || "—"}
                      </Link>
                    ) : (
                      <span className="ds-mono">{bill.invoice_number || "—"}</span>
                    )}
                  </Td>
                  <Td>
                    {posting ? (
                      <span className="lf-pair">
                        <StatusChip tone={posting.attempts > 1 ? "warn" : "pass"} size="small">
                          {posting.attempts > 1 ? `Recovered, attempt ${posting.attempts}` : "One attempt"}
                        </StatusChip>
                        <span className="ds-mono lf-cell-sub" title={posting.idempotency_key}>
                          {shortKey(posting.idempotency_key)}
                        </span>
                      </span>
                    ) : (
                      <span className="lf-cell-sub">—</span>
                    )}
                  </Td>
                  <Td style={{ color: "var(--ds-text-2)", whiteSpace: "nowrap" }}>{dateOnly(bill.posted_on)}</Td>
                  <Td align="right" style={{ fontWeight: 650, whiteSpace: "nowrap" }}>
                    {detail?.trace?.steps?.length ? (
                      <Figure value={money(bill.amount)} heading={`${bill.external_reference}: the amount posted`} trace={detail.trace} />
                    ) : (
                      money(bill.amount)
                    )}
                    <span className="lf-unit">{bill.currency}</span>
                  </Td>
                </Reveal>
              ))}
            </Ledger>
          )}
        </Card>
      </div>
    </div>
  );
}

export const dynamic = "force-dynamic";
