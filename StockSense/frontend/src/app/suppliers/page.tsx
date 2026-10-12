"use client";

import Link from "next/link";
import { useMemo, useState, type CSSProperties } from "react";

import { Card, Empty, Stat } from "@/design/Surface";
import { StatusChip } from "@/design/StatusChip";
import { useInView } from "@/design/motion";
import { Figure } from "@/components/trace";
import { ErrorNote, Loading, PageBand } from "@/components/ui";
import { useLoad } from "@/lib/hooks";
import { count, countryName, dayMonth, days, decimal, shortSupplier } from "@/lib/format";
import type { Dashboard, Page, SupplierBrief } from "@/lib/types";

export default function Suppliers() {
  const [search, setSearch] = useState("");
  const { data, error, loading } = useLoad<Page<SupplierBrief>>(`/api/suppliers?limit=200${search ? `&search=${encodeURIComponent(search)}` : ""}`);
  const dashboard = useLoad<Dashboard>("/api/dashboard");
  const [ref, shown] = useInView<HTMLOListElement>({ threshold: 0.05 });
  const items = useMemo(() => data?.items ?? [], [data]);
  const late = items.filter((supplier) => !supplier.lead_time.is_reliable);
  const peak = Math.max(10, ...items.map((supplier) => supplier.lead_time.worst_days)) * 1.05;
  const orderBy = new Map((dashboard.data?.shutdowns ?? []).map((row) => [row.country, row]));

  return (
    <>
      <PageBand
        eyebrow={["Suppliers", data ? `${count(data.total)} on record` : "on record"]}
        title="What they quote,"
        accent="and what actually happens."
        lede="Every supplier quotes a lead time. The quote is recorded and not used: the cover is sized on the record of real deliveries. The gap between the two is the week of stock nobody budgeted for."
        actions={
          <label className="ss-band-search">
            <span className="ds-sr-only">Search suppliers</span>
            <input className="ds-input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by name or number" />
          </label>
        }
      >
        {data && (
          <div className="ds-stats" style={{ marginTop: 30 }}>
            <Stat label="Suppliers" value={<Figure value={count(data.total)} count={data.total} heading="Suppliers on record" />} />
            <Stat
              label="Run late"
              tone="fail"
              value={
                <Figure
                  value={count(late.length)}
                  count={late.length}
                  heading="Suppliers whose record does not match their quote"
                  explain={{
                    formula: "Suppliers whose real deliveries run far enough past the quote that the quote is not worth using",
                    inputs: late.slice(0, 40).map((supplier) => ({
                      label: shortSupplier(supplier.name),
                      value: `${decimal(supplier.lead_time.slippage_days, 1)} days late`,
                      source: `${count(supplier.lead_time.deliveries)} deliveries`,
                      sourceKind: "Supplier record",
                    })),
                  }}
                />
              }
            />
          </div>
        )}
      </PageBand>
      <div className="ds-work">
        {error && <ErrorNote error={error} />}
        <Card
          flush
          eyebrow="Days from order to delivery"
          title="Quote against record"
          action={
            <div className="ss-legend">
              <span className="ss-key">
                <span className="ss-key-swatch" data-ring="" style={{ borderColor: "var(--ds-pass-ink)" }} aria-hidden /> Quoted
              </span>
              <span className="ss-key">
                <span className="ss-key-swatch" style={{ background: "var(--ds-text)" }} aria-hidden /> Average delivery
              </span>
              <span className="ss-key">
                <span className="ss-key-swatch" style={{ background: "var(--ds-fail)" }} aria-hidden /> Late against the quote
              </span>
            </div>
          }
        >
          {loading && !data ? (
            <div style={{ padding: 20 }}>
              <Loading what="Reading the suppliers" />
            </div>
          ) : !items.length ? (
            <div style={{ padding: 20 }}>
              <Empty title="No suppliers match." />
            </div>
          ) : (
            <ol ref={ref} className="ss-rows ss-dumbbells" data-shown={shown ? "" : undefined}>
              {items.map((supplier, index) => {
                const lead = supplier.lead_time;
                const isLate = !lead.is_reliable;
                const shutdown = orderBy.get(supplier.country);
                const a = (lead.quoted_days / peak) * 100;
                const b = (lead.average_days / peak) * 100;
                const n = (lead.ninetieth_percentile_days / peak) * 100;
                return (
                  <li key={supplier.id} className="ss-row ss-supplier-row" style={{ "--ds-d": `${Math.min(index, 30) * 25}ms` } as CSSProperties}>
                    <Link href={`/suppliers/${supplier.id}`} className="ss-row-link">
                      <span className="ss-row-main">
                        <span className="ss-row-title">{shortSupplier(supplier.name)}</span>
                        <span className="ds-mono ss-row-sub">
                          {countryName(supplier.country)} · {count(lead.deliveries)} deliveries
                        </span>
                      </span>
                      <span className="ss-dumbbell" data-late={isLate ? "" : undefined} aria-label={`Quotes ${days(lead.quoted_days)}, averages ${days(lead.average_days)}, nine in ten within ${days(lead.ninetieth_percentile_days)}`} role="img">
                        <span className="ss-db-track" />
                        <span className="ss-db-span" style={{ left: `${Math.min(a, b)}%`, width: `${Math.abs(b - a)}%` }} />
                        <span className="ss-db-ninety" style={{ left: `${n}%` }} />
                        <span className="ss-db-quote" style={{ left: `${a}%` }} />
                        <span className="ss-db-actual" style={{ left: `${b}%` }} />
                      </span>
                      <span className="ss-row-cell">
                        <span className="ds-mono-label">Quotes / takes</span>
                        <span className="ds-num">
                          {lead.quoted_days} / <b style={{ color: isLate ? "var(--ds-fail-ink)" : undefined }}>{decimal(lead.average_days, 1)}</b> days
                        </span>
                      </span>
                      <span className="ss-row-cell" style={{ alignItems: "flex-end", gap: 6 }}>
                        {isLate ? (
                          <StatusChip tone="fail">{decimal(lead.slippage_days, 1)} days late</StatusChip>
                        ) : (
                          <StatusChip tone="pass">Keeps to it</StatusChip>
                        )}
                        {shutdown?.affects && (
                          <StatusChip tone="warn" size="small">
                            Order by {dayMonth(shutdown.order_by)}
                          </StatusChip>
                        )}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ol>
          )}
        </Card>
      </div>
    </>
  );
}
