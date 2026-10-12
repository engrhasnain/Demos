"use client";

import Link from "next/link";
import { use, type CSSProperties } from "react";

import { Card, Empty, Stat } from "@/design/Surface";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Deliveries } from "@/components/charts";
import { ShutdownTimeline } from "@/components/desk";
import { Figure } from "@/components/trace";
import { ErrorNote, Field, Loading, PageBand, SectionHead } from "@/components/ui";
import { useLoad } from "@/lib/hooks";
import { BASE_CURRENCY, count, countryName, currencyName, days, decimal, money, shortSupplier } from "@/lib/format";
import type { SupplierDetail } from "@/lib/types";

export default function OneSupplier({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, loading } = useLoad<SupplierDetail>(`/api/suppliers/${id}`);

  if (error) {
    return (
      <PageBand eyebrow={["Supplier"]} title="This supplier could not be opened." back={{ href: "/suppliers", label: "Suppliers" }}>
        <div style={{ paddingBottom: 30 }}>
          <ErrorNote error={error} />
        </div>
      </PageBand>
    );
  }
  if (loading || !data) {
    return (
      <PageBand eyebrow={["Supplier"]} title="Opening the supplier…" back={{ href: "/suppliers", label: "Suppliers" }}>
        <Loading what="Reading the delivery record" dark />
      </PageBand>
    );
  }

  const lead = data.lead_time;
  const late = !lead.is_reliable;
  const shutdown = data.shutdown?.affects ? data.shutdown : null;
  const samples = data.lead_time_samples;

  return (
    <>
      <PageBand
        back={{ href: "/suppliers", label: "Suppliers" }}
        eyebrow={[countryName(data.country), `pays in ${currencyName(data.currency)}`, `${count(data.parts)} parts`]}
        title={shortSupplier(data.name)}
        lede={
          late
            ? `Runs ${decimal(lead.slippage_days, 1)} days late on average. The cover for its parts is sized on what it does, not on what it quotes.`
            : "Close enough to its quote that the quote is worth something."
        }
        actions={
          <div className="ss-part-chips">
            <span className="ds-stamp">{data.code}</span>
            <StatusChip tone={late ? "fail" : "pass"} surface="dark" size="large" pulse={late}>
              {late ? "Runs late" : "Keeps to its quote"}
            </StatusChip>
          </div>
        }
        aside={
          <div className="ss-verdict">
            <p className="ds-mono-label" style={{ margin: 0 }}>
              Every delivery on record
            </p>
            <div style={{ marginTop: 12 }} className="ss-dark-chart">
              <Deliveries samples={samples} quoted={lead.quoted_days} />
            </div>
          </div>
        }
      >
        <div className="ds-stats">
          <Stat label="Quotes" value={<Figure value={days(lead.quoted_days)} heading="Quoted lead time" />} />
          <Stat
            label="Actually takes"
            tone={late ? "fail" : undefined}
            value={
              <Figure
                value={days(lead.average_days)}
                count={lead.average_days}
                decimals={1}
                heading="Average real lead time"
                explain={{
                  formula: "The average of every delivery on record, from order to arrival",
                  result: days(lead.average_days),
                  inputs: samples.map((value, index) => ({ label: `Delivery ${index + 1}`, value: days(value), source: data.name, sourceKind: "Supplier record" })),
                }}
              />
            }
          />
          <Stat label="Nine in ten within" value={<Figure value={days(lead.ninetieth_percentile_days)} heading="Ninetieth percentile lead time" />} />
          <Stat label="Worst" tone="warn" value={<Figure value={days(lead.worst_days)} heading="Slowest delivery on record" />} />
        </div>
      </PageBand>

      <div className="ds-work">
        {shutdown && (
          <section aria-labelledby="sup-shut">
            <SectionHead id="sup-shut" label="Lunar New Year" title={`${shutdown.label} closes ${shutdown.closed_days} days`} lede={`${decimal(data.weeks_of_cover_needed, 1)} weeks of cover have to be on the shelf before the last day to order.`} />
            <Card style={{ marginTop: 22 }}>
              <ShutdownTimeline
                shutdowns={[
                  {
                    ...shutdown,
                    days_until_order_by: data.days_until_order_by ?? 0,
                    weeks_of_cover_needed: data.weeks_of_cover_needed,
                    parts: data.parts,
                  },
                ]}
              />
            </Card>
          </section>
        )}

        <div className="ss-part-grid" style={{ marginTop: shutdown ? 48 : 0 }}>
          <Reveal>
            <Card flush eyebrow={`First ${count(data.part_list?.length ?? 0)} of ${count(data.parts)}`} title="Their parts">
              {!data.part_list?.length ? (
                <div style={{ padding: 20 }}>
                  <Empty title="No parts." />
                </div>
              ) : (
                <ol className="ss-rows">
                  {data.part_list.map((part, index) => (
                    <li key={part.id} className="ss-row ds-reveal" data-shown="" style={{ "--ds-d": `${Math.min(index, 14) * 35}ms` } as CSSProperties}>
                      <Link href={`/parts/${part.id}`} className="ss-row-link ss-mini-row">
                        <span className="ss-row-main">
                          <span className="ds-stamp">{part.code}</span>
                          <span className="ss-row-sub">{part.description}</span>
                        </span>
                        <span className="ss-row-cell">
                          <span className="ds-mono-label">On the shelf</span>
                          <span className="ds-num">{count(part.on_hand)}</span>
                        </span>
                        <span className="ss-row-cell">
                          <span className="ds-mono-label">Worth</span>
                          <span className="ds-num" style={{ fontWeight: 600 }}>{money(part.stock_value)}</span>
                        </span>
                      </Link>
                    </li>
                  ))}
                </ol>
              )}
            </Card>
          </Reveal>
          <Reveal index={1}>
            <Card title="Ordering terms">
              <dl style={{ margin: 0 }}>
                <Field label="Parts">{count(data.parts)}</Field>
                <Field label="Minimum order value">
                  {Number(data.minimum_order_value) > 0 ? `${money(data.minimum_order_value)} ${BASE_CURRENCY}` : "None"}
                </Field>
                <Field label="Container">
                  {Number(data.container_cubic_metres) > 0 ? `${decimal(data.container_cubic_metres, 0)} cubic metres` : "Not consolidated"}
                </Field>
                <Field label="Deliveries seen">{count(lead.deliveries)}</Field>
                <Field label="Spread">{days(lead.deviation_days)} either way</Field>
              </dl>
              <p style={{ margin: "14px 0 0", fontSize: 13, color: "var(--ds-text-2)", lineHeight: 1.55 }}>
                A supplier whose lines this week do not reach its minimum order value is dropped from the week whole: half a minimum order is not a cheaper order, it is a rejected one.
              </p>
            </Card>
          </Reveal>
        </div>
      </div>
    </>
  );
}
