"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Constellation } from "@/design/Constellation";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Tabs } from "@/design/Tabs";
import { useLoad } from "@/lib/hooks";
import { asNumber, clock, count, dateOnly, money } from "@/lib/format";
import type { Dashboard, InvoiceBrief, Page } from "@/lib/types";
import { Figure } from "@/components/trace";
import {
  Button,
  Card,
  Empty,
  ErrorNote,
  Ledger,
  LinkButton,
  Loading,
  MatchGlyph,
  PageBand,
  TONE_COLOUR,
  Td,
  Th,
  matchState,
} from "@/components/ui";

type FilterKey = "all" | "person" | "posted" | "sign";

const FILTERS: { key: FilterKey; label: string; query: string }[] = [
  { key: "all", label: "All", query: "" },
  { key: "person", label: "Needs a person", query: "needs_a_person=true" },
  { key: "sign", label: "Waiting to be signed", query: "status=awaiting_approval" },
  { key: "posted", label: "Posted", query: "status=posted" },
];

/** The band's picture: the three-way match, with invoices arriving at it. */
const CORNERS = [
  { id: "inv", x: 0.62, y: 0.3, r: 4.4, tone: "light" as const, lit: true },
  { id: "ord", x: 0.84, y: 0.2, r: 4.4, tone: "light" as const, lit: true },
  { id: "del", x: 0.75, y: 0.56, r: 4.4, tone: "light" as const, lit: true },
  { id: "mid", x: 0.74, y: 0.35, r: 3.2, tone: "accent" as const, ring: true, lit: true },
  { id: "led", x: 0.95, y: 0.5, r: 5, tone: "pass" as const, ring: true, lit: true },
];
const ARRIVALS = Array.from({ length: 7 }, (_, index) => ({
  id: `a-${index}`,
  x: 0.5 + (index % 3) * 0.025,
  y: 0.1 + index * 0.075,
  r: 2,
  tone: (index === 2 ? "fail" : index === 5 ? "warn" : "muted") as "fail" | "warn" | "muted",
}));
const FIELD = [...CORNERS, ...ARRIVALS];
const FIELD_LINKS = [
  { from: "inv", to: "ord", tone: "accent" as const, lit: true },
  { from: "ord", to: "del", tone: "accent" as const, lit: true },
  { from: "del", to: "inv", tone: "accent" as const, lit: true },
  { from: "inv", to: "mid", tone: "accent" as const },
  { from: "ord", to: "mid", tone: "accent" as const },
  { from: "del", to: "mid", tone: "accent" as const },
  { from: "mid", to: "led", tone: "pass" as const, lit: true },
  ...ARRIVALS.map((node) => ({ from: node.id, to: "inv", tone: "light" as const })),
];
const FIELD_PATHS = ARRIVALS.map((node, index) =>
  index === 2 ? [node.id, "inv"] : [node.id, "inv", "ord", "del", "mid", "led"],
);

export default function Invoices() {
  const router = useRouter();
  const [filter, setFilter] = useState<FilterKey>("all");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);

  // ?filter=person from the desk; read once, without a suspense boundary.
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("filter") as FilterKey | null;
    if (wanted && FILTERS.some((item) => item.key === wanted)) setFilter(wanted);
  }, []);

  const chosen = FILTERS.find((item) => item.key === filter) ?? FILTERS[0];
  const query = [chosen.query, search ? `search=${encodeURIComponent(search)}` : ""].filter(Boolean).join("&");
  const { data, error, loading } = useLoad<Page<InvoiceBrief>>(`/api/invoices?limit=40&offset=${offset}${query ? `&${query}` : ""}`);
  const board = useLoad<Dashboard>("/api/dashboard");

  const byStatus = new Map((board.data?.by_status ?? []).map((row) => [row.code, row.count]));
  const badges: Record<FilterKey, number> = {
    all: board.data?.invoices ?? 0,
    person: board.data?.waiting_for_a_person ?? 0,
    sign: byStatus.get("awaiting_approval") ?? 0,
    posted: byStatus.get("posted") ?? 0,
  };

  return (
    <div>
      <PageBand
        eyebrow={["Invoices", `${count(board.data?.invoices ?? 0)} received`, "read by the built-in engine"]}
        title="Every invoice,"
        accent="and where it stopped."
        lede="Each row is matched three ways: the invoice, its purchase order, and what actually arrived. The triangle beside it shows which corner agreed, which broke, and whether the bill is in the ledger."
        canvas={<Constellation nodes={FIELD} links={FIELD_LINKS} ambient={40} traffic={{ paths: FIELD_PATHS, every: 900 }} />}
        actions={
          <>
            <LinkButton href="/invoices/new" tone="primary" size="large" arrow>
              Add an invoice
            </LinkButton>
            <LinkButton href="/ledger" tone="ink" size="large">
              What reached the ledger
            </LinkButton>
          </>
        }
        aside={
          <div className="lf-band-tiles">
            {FILTERS.slice(1).map((item, index) => (
              <div key={item.key} className="lf-band-tile" data-static="" data-active={filter === item.key ? "" : undefined}>
                <span className="ds-stat-value" data-tone={item.key === "posted" ? "pass" : item.key === "person" ? "warn" : "accent"}>
                  <Figure
                    value={count(badges[item.key])}
                    count={badges[item.key]}
                    decimals={0}
                    heading={item.label}
                    explain={{
                      formula: `Invoices counted by the server as "${item.label.toLowerCase()}"`,
                      inputs: (board.data?.by_status ?? []).map((row) => ({ label: row.label, value: count(row.count), source: "Live invoice records", sourceKind: "Invoice state" })),
                    }}
                  />
                </span>
                <span className="ds-mono-label ds-stat-label">{item.label}</span>
                <span className="lf-band-tile-bar" style={{ transform: `scaleX(${Math.min(1, badges[item.key] / Math.max(1, badges.all))})`, animationDelay: `${index * 90}ms` }} />
              </div>
            ))}
          </div>
        }
      />

      <div className="ds-work">
        <div className="lf-filter-bar">
          <Tabs
            label="Which invoices"
            idPrefix="invoices"
            value={filter}
            onChange={(key) => {
              setFilter(key);
              setOffset(0);
            }}
            tabs={FILTERS.map((item) => ({ key: item.key, label: item.label, badge: badges[item.key] || undefined }))}
          />
          <label className="lf-search">
            <span className="ds-sr-only">Search invoices</span>
            <input
              className="ds-input"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
              placeholder="Search supplier, number or order"
            />
          </label>
        </div>

        {error && <ErrorNote error={error} />}

        <Card flush eyebrow={data ? `${count(data.total)} found` : "Loading"} title="The register" style={{ marginTop: 20 }} className="lf-register" id="invoices-panel">
          {loading && !data ? (
            <Loading what="Loading" />
          ) : !data || data.items.length === 0 ? (
            <div style={{ padding: 20 }}>
              <Empty title="Nothing matches.">Try another tab or a shorter search.</Empty>
            </div>
          ) : (
            <>
              <div className="lf-only-wide">
                <Ledger
                  head={
                    <>
                      <Th width="3rem">Match</Th>
                      <Th>Supplier</Th>
                      <Th>Number</Th>
                      <Th>Date</Th>
                      <Th align="right">Invoiced</Th>
                      <Th align="right">Payable</Th>
                      <Th align="right">Held</Th>
                      <Th>State</Th>
                    </>
                  }
                >
                  {data.items.map((invoice, index) => {
                    const look = matchState(invoice);
                    return (
                      <Reveal
                        as="tr"
                        key={`${filter}-${invoice.id}`}
                        index={index}
                        y={22}
                        data-clickable=""
                        onClick={() => router.push(`/invoices/${invoice.id}`)}
                      >
                        <Td className="ds-rowmark" style={{ "--row-tone": TONE_COLOUR[look.tone] } as React.CSSProperties}>
                          <MatchGlyph state={look} posted={invoice.status === "posted"} />
                        </Td>
                        <Td>
                          <Link href={`/invoices/${invoice.id}`} className="lf-cell-link" onClick={(event) => event.stopPropagation()}>
                            {invoice.vendor_name || "—"}
                          </Link>
                          <span className="lf-cell-sub ds-mono">
                            {invoice.reference} · {clock(invoice.received_at)}
                          </span>
                        </Td>
                        <Td>
                          <span className="ds-mono" style={{ fontSize: 12.5 }}>
                            {invoice.invoice_number || "—"}
                          </span>
                        </Td>
                        <Td style={{ color: "var(--ds-text-2)", whiteSpace: "nowrap" }}>{dateOnly(invoice.invoice_date)}</Td>
                        <Td align="right" style={{ whiteSpace: "nowrap" }}>
                          {money(invoice.total_amount)}
                          {invoice.currency !== "TWD" && <span className="lf-unit">{invoice.currency}</span>}
                        </Td>
                        <Td align="right" style={{ fontWeight: 650, whiteSpace: "nowrap" }}>
                          {money(invoice.approved_amount)}
                        </Td>
                        <Td align="right" style={asNumber(invoice.held_amount) > 0 ? { color: "var(--ds-warn-ink)", fontWeight: 650 } : { color: "var(--ds-text-3)" }}>
                          {money(invoice.held_amount)}
                        </Td>
                        <Td>
                          <div className="lf-state-cell">
                            <StatusChip tone={look.tone} pulse={look.live}>
                              {invoice.posted_untouched ? "Posted untouched" : look.label}
                            </StatusChip>
                            {invoice.headline && <span className="lf-cell-sub">{invoice.headline}</span>}
                          </div>
                        </Td>
                      </Reveal>
                    );
                  })}
                </Ledger>
              </div>
              <ul className="lf-only-narrow lf-invoice-cards">
                {data.items.map((invoice, index) => {
                  const look = matchState(invoice);
                  return (
                    <Reveal as="li" key={`${filter}-${invoice.id}`} index={index} from="left">
                      <Link href={`/invoices/${invoice.id}`} className="lf-invoice-card" style={{ "--row-tone": TONE_COLOUR[look.tone] } as React.CSSProperties}>
                        <span className="lf-invoice-card-top">
                          <MatchGlyph state={look} posted={invoice.status === "posted"} />
                          <StatusChip tone={look.tone} pulse={look.live} size="small">
                            {look.label}
                          </StatusChip>
                          <span className="ds-mono lf-cell-sub" style={{ marginLeft: "auto" }}>
                            {invoice.reference}
                          </span>
                        </span>
                        <span className="lf-invoice-card-title">{invoice.vendor_name}</span>
                        <span className="lf-cell-sub ds-mono">
                          {invoice.invoice_number || "—"} · {dateOnly(invoice.invoice_date)}
                        </span>
                        <span className="lf-invoice-card-money">
                          <span>
                            <span className="ds-mono-label">Invoiced</span>
                            {money(invoice.total_amount)} {invoice.currency}
                          </span>
                          <span>
                            <span className="ds-mono-label">Payable</span>
                            <b>{money(invoice.approved_amount)}</b>
                          </span>
                        </span>
                        {invoice.headline && <span className="lf-invoice-card-why">{invoice.headline}</span>}
                      </Link>
                    </Reveal>
                  );
                })}
              </ul>
            </>
          )}
        </Card>

        {data && data.total > data.limit && (
          <div className="lf-pager">
            <span className="ds-mono">
              {offset + 1}–{Math.min(offset + data.limit, data.total)} of {data.total}
            </span>
            <div className="lf-actions">
              <Button size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - data.limit))}>
                Back
              </Button>
              <Button size="small" disabled={offset + data.limit >= data.total} onClick={() => setOffset(offset + data.limit)}>
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export const dynamic = "force-dynamic";
