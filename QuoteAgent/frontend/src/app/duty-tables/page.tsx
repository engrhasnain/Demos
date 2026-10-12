"use client";

import { useId, useMemo, useState } from "react";

import { Banner, Button, Card, Stamp } from "@/design/Surface";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { StepRail } from "@/design/StepRail";
import { useInView } from "@/design/motion";
import { api } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";
import { dateOnly, money, words } from "@/lib/format";
import type { TariffTable } from "@/lib/types";
import { Figure } from "@/components/trace";
import { ErrorNote, Ledger, Loading, PageBand, Td, Th } from "@/components/ui";

type Tables = { tables: TariffTable[]; principle: string };
type Rate = { id: number; rate: string; as_of_date: string; source: string };
type Rates = { pair: string; rates: Rate[]; note: string };
type Freight = {
  rates: {
    id: number;
    lane: string;
    mode: string;
    minimum_charge: string;
    price_per_kilogram: string;
    handling_per_shipment: string;
    insurance_percent: string;
    transit_days: number;
    currency: string;
  }[];
  note: string;
};
type Flagged = {
  count: number;
  quotes: {
    case_id: number;
    reference: string;
    version: number;
    reason: string;
    grand_total: string;
    currency: string;
  }[];
};

const TABLE_WORDS: Record<string, string> = {
  active: "In force",
  draft: "Draft",
  superseded: "Replaced",
};

export default function DutyTablesPage() {
  const tables = useLoad<Tables>("/api/rates/tariff-tables");
  const rates = useLoad<Rates>("/api/rates/exchange-rates?base=TWD&quote=USD&limit=12");
  const freight = useLoad<Freight>("/api/rates/freight");
  const flagged = useLoad<Flagged>("/api/rates/quotes-needing-repricing");
  const [open, setOpen] = useState<number | null>(null);
  const detail = useLoad<TariffTable>(open ? `/api/rates/tariff-tables/${open}` : null);
  const { busy, error, note, run } = useAction();

  const activate = (id: number) =>
    void run(
      `activate-${id}`,
      async () => {
        const result = await api.post<{ quotes_flagged_for_repricing: unknown[] }>(
          `/api/rates/tariff-tables/${id}/activate`,
          {
            confirm_broker_sign_off: true,
            customs_broker: "Chen and Partners Customs Brokers, licence 04218",
          },
        );
        tables.reload();
        flagged.reload();
        return result;
      },
      "In force. Every open quote priced on an older table is flagged for re-pricing.",
    );

  const ordered = useMemo(
    () => (tables.data?.tables ?? []).slice().sort((a, b) => (a.effective_from < b.effective_from ? -1 : 1)),
    [tables.data],
  );
  const activeIndex = ordered.findIndex((table) => table.status === "active");

  return (
    <div>
      <PageBand
        eyebrow={["Duty, currency and freight", "dated, owned, signed off"]}
        title="Duty and currency"
        accent="One table in force, by date."
        lede={
          tables.data?.principle ??
          "Duty is never computed by a model. It is read from the one table in force on the quote date, and every quote records which version priced it."
        }
      >
        {ordered.length > 0 && (
          <Reveal index={4}>
            <div className="qa-case-rail">
              <p className="ds-mono-label" style={{ margin: "0 0 14px" }}>
                Duty tables for 2026, oldest first
              </p>
              <StepRail
                label="Duty tables by date"
                steps={ordered.map((table) => ({
                  key: String(table.id),
                  label: table.version,
                  sub: `${TABLE_WORDS[table.status] ?? table.status} · from ${dateOnly(table.effective_from)}`,
                }))}
                current={activeIndex < 0 ? 0 : activeIndex}
                tone="pass"
              />
            </div>
          </Reveal>
        )}
      </PageBand>

      <div className="ds-work">
        <div style={{ display: "grid", gap: 12, marginBottom: 20 }}>
          {error && <ErrorNote error={error} />}
          {note && <Banner tone="pass">{note}</Banner>}
          {flagged.data && flagged.data.count > 0 && (
            <Banner
              tone="warn"
              title={`${flagged.data.count} open quote${flagged.data.count === 1 ? " is" : "s are"} waiting to be re-priced`}
            >
              <ul style={{ margin: "6px 0 0", padding: 0, listStyle: "none", display: "grid", gap: 4 }}>
                {flagged.data.quotes.map((quote) => (
                  <li key={`${quote.case_id}-${quote.version}`}>
                    <a href={`/requests/${quote.case_id}`} className="ds-mono" style={{ color: "var(--ds-text)", fontWeight: 600 }}>
                      {quote.reference}
                    </a>{" "}
                    version {quote.version} · {money(quote.grand_total, quote.currency)} · {quote.reason}
                  </li>
                ))}
              </ul>
            </Banner>
          )}
        </div>

        <div className="qa-duty-grid">
          <Card eyebrow="Duty tables" title="Every version, with its owner and its broker" flush>
            {tables.loading && <div style={{ padding: "0 20px" }}><Loading what="Loading the duty tables" /></div>}
            {tables.error && (
              <div style={{ padding: 20 }}>
                <ErrorNote error={tables.error} />
              </div>
            )}
            <ul style={{ listStyle: "none", margin: 0, padding: 0 }}>
              {(tables.data?.tables ?? []).map((table, index) => (
                <Reveal
                  as="li"
                  key={table.id}
                  index={index}
                  y={24}
                  style={{ padding: "16px 20px", borderTop: index ? "1px solid var(--ds-line)" : undefined }}
                >
                  <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
                    <div style={{ minWidth: 0 }}>
                      <p style={{ margin: 0, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                        <Stamp>{table.version}</Stamp>
                        <StatusChip
                          tone={table.status === "active" ? "pass" : table.status === "draft" ? "warn" : "neutral"}
                          pulse={table.status === "active" || table.status === "draft"}
                        >
                          {TABLE_WORDS[table.status] ?? table.status}
                        </StatusChip>
                        <StatusChip tone={table.signed_off ? "pass" : "fail"}>
                          {table.signed_off ? "Broker signed off" : "Not signed off"}
                        </StatusChip>
                      </p>
                      <p style={{ margin: "10px 0 0", fontWeight: 600, fontSize: 14.5 }}>{table.title}</p>
                      <p style={{ margin: "4px 0 0", fontSize: 12.5, color: "var(--ds-text-3)" }}>
                        In force from{" "}
                        <Figure
                          value={dateOnly(table.effective_from)}
                          heading={`${table.version} comes into force`}
                          explain={{
                            formula: "The date this table starts to price quotes; a quote dated on or after it uses this table until the next one comes into force",
                            result: dateOnly(table.effective_from),
                            inputs: [
                              { label: "Owned by", value: table.owned_by, source: "Duty table record", sourceKind: "Duty table" },
                              { label: "Customs broker", value: table.customs_broker || "None yet", source: table.source_note || "Duty table record", sourceKind: "Duty table" },
                            ],
                          }}
                        />
                        {table.effective_to && ` to ${dateOnly(table.effective_to)}`} · {table.line_count} rates · owned by {table.owned_by}
                        {table.customs_broker && ` · ${table.customs_broker}`}
                      </p>
                    </div>
                    <div style={{ display: "flex", gap: 8, flexShrink: 0 }}>
                      <Button size="small" onClick={() => setOpen(open === table.id ? null : table.id)}>
                        {open === table.id ? "Hide the rates" : "See the rates"}
                      </Button>
                      {table.status === "draft" && (
                        <Button size="small" tone="primary" busy={busy === `activate-${table.id}`} onClick={() => activate(table.id)}>
                          Bring into force
                        </Button>
                      )}
                    </div>
                  </div>

                  {open === table.id && (
                    <div className="qa-line-detail" style={{ marginTop: 14, border: "1px solid var(--ds-line)", borderRadius: 3, overflow: "hidden" }}>
                      {detail.loading && <div style={{ padding: "0 14px" }}><Loading what="Loading the rates" /></div>}
                      {detail.data?.lines && (
                        <Ledger
                          head={
                            <>
                              <Th>Commodity code</Th>
                              <Th width="6rem">Route</Th>
                              <Th>Component</Th>
                              <Th align="right" width="5rem">
                                Rate
                              </Th>
                              <Th>Charged on</Th>
                            </>
                          }
                        >
                          {detail.data.lines
                            .filter((line) => line.destination_country === "US")
                            .slice(0, 40)
                            .map((line) => (
                              <tr key={line.id}>
                                <Td className="ds-mono" style={{ fontSize: 12 }}>
                                  {line.commodity_code}
                                </Td>
                                <Td style={{ fontSize: 12 }}>
                                  {line.origin_country} → {line.destination_country}
                                </Td>
                                <Td>
                                  <span style={{ fontSize: 12.5 }}>{words(line.component)}</span>
                                  {line.not_stacked_with && (
                                    <span style={{ display: "block", fontSize: 11, color: "var(--ds-text-3)" }}>
                                      not stacked with {words(line.not_stacked_with)}
                                    </span>
                                  )}
                                  {line.combined_cap_percent && (
                                    <span style={{ display: "block", fontSize: 11, color: "var(--ds-text-3)" }}>
                                      combined rate capped at {line.combined_cap_percent}%
                                    </span>
                                  )}
                                </Td>
                                <Td align="right">
                                  <Figure
                                    value={`${line.rate_percent}%`}
                                    heading={`${words(line.component)} on ${line.commodity_code}`}
                                    explain={{
                                      formula: `Read from duty table ${table.version}; charged on ${line.charged_on}`,
                                      result: `${line.rate_percent}%`,
                                      inputs: [
                                        { label: "Authority", value: line.authority || "—", source: table.title, sourceKind: "Duty table" },
                                        ...(line.note ? [{ label: "Note", value: line.note.slice(0, 80), source: table.version, sourceKind: "Duty table" }] : []),
                                      ],
                                    }}
                                  />
                                </Td>
                                <Td style={{ fontSize: 12, color: "var(--ds-text-2)" }}>{line.charged_on}</Td>
                              </tr>
                            ))}
                        </Ledger>
                      )}
                    </div>
                  )}
                </Reveal>
              ))}
            </ul>
          </Card>

          <div style={{ display: "grid", gap: 20, alignContent: "start" }}>
            <Card eyebrow="Exchange rates" title={rates.data?.pair ?? "Currency"}>
              {rates.loading && <Loading what="Loading the rates" />}
              {rates.data && <RateChart rates={rates.data.rates} pair={rates.data.pair} />}
              {rates.data && (
                <div style={{ marginTop: 14, border: "1px solid var(--ds-line)", borderRadius: 3, overflow: "hidden" }}>
                  <Ledger
                    head={
                      <>
                        <Th>Date</Th>
                        <Th align="right">Rate</Th>
                      </>
                    }
                  >
                    {rates.data.rates.slice(0, 6).map((rate, index) => (
                      <Reveal as="tr" key={rate.id} index={index} y={16}>
                        <Td>{dateOnly(rate.as_of_date)}</Td>
                        <Td align="right" className="ds-mono">
                          <Figure
                            value={rate.rate}
                            heading={`${rates.data?.pair} on ${dateOnly(rate.as_of_date)}`}
                            explain={{
                              formula: "The closing rate recorded for that date; a quote locks the rate in force on its quote date",
                              result: rate.rate,
                              inputs: [{ label: "Source", value: rate.source, source: rate.source, sourceKind: "Exchange rate" }],
                            }}
                          />
                        </Td>
                      </Reveal>
                    ))}
                  </Ledger>
                </div>
              )}
            </Card>

            <Card eyebrow="Freight" title="Lanes and what they cost" flush>
              {freight.loading && <div style={{ padding: "0 20px" }}><Loading what="Loading the freight table" /></div>}
              {freight.data && (
                <Ledger
                  head={
                    <>
                      <Th>Lane</Th>
                      <Th align="right">Per kilogram</Th>
                      <Th align="right">Minimum</Th>
                      <Th align="right">Days</Th>
                    </>
                  }
                >
                  {freight.data.rates.map((rate, index) => (
                    <Reveal as="tr" key={rate.id} index={index} y={16}>
                      <Td style={{ paddingLeft: 20 }}>
                        <span style={{ fontWeight: 600 }}>{rate.lane}</span>
                        <span style={{ display: "block", fontSize: 11.5, color: "var(--ds-text-3)" }}>by {rate.mode}</span>
                      </Td>
                      <Td align="right">
                        <Figure
                          value={money(rate.price_per_kilogram)}
                          heading={`${rate.lane} by ${rate.mode}, per kilogram`}
                          explain={{
                            formula: "Freight = the larger of weight × price per kilogram and the minimum charge, plus handling per shipment",
                            inputs: [
                              { label: "Minimum charge", value: money(rate.minimum_charge, rate.currency), source: "Logistics freight table", sourceKind: "Company policy" },
                              { label: "Handling per shipment", value: money(rate.handling_per_shipment, rate.currency), source: "Logistics freight table", sourceKind: "Company policy" },
                              { label: "Insurance", value: `${rate.insurance_percent}%`, source: "Logistics freight table", sourceKind: "Company policy" },
                            ],
                          }}
                        />
                      </Td>
                      <Td align="right">
                        <Figure
                          value={money(rate.minimum_charge)}
                          heading={`${rate.lane} by ${rate.mode}, minimum charge`}
                          explain={{
                            formula: "The least a shipment on this lane is charged, whatever it weighs",
                            result: money(rate.minimum_charge, rate.currency),
                            inputs: [{ label: "Lane", value: `${rate.lane} by ${rate.mode}`, source: "Logistics freight table", sourceKind: "Company policy" }],
                          }}
                        />
                      </Td>
                      <Td align="right">{rate.transit_days}</Td>
                    </Reveal>
                  ))}
                </Ledger>
              )}
            </Card>
          </div>
        </div>
      </div>
    </div>
  );
}

/** The rate over time, drawn left to right when it scrolls into view. */
function RateChart({ rates, pair }: { rates: Rate[]; pair: string }) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.3 });
  const clip = useId().replace(/:/g, "");
  const points = rates.slice().reverse();
  if (points.length < 2) return null;
  const values = points.map((rate) => Number(rate.rate));
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const width = 560;
  const height = 150;
  const pad = 12;
  const xy = points.map((rate, index) => ({
    x: pad + (index / (points.length - 1)) * (width - pad * 2),
    y: pad + (1 - (Number(rate.rate) - min) / span) * (height - pad * 2 - 18),
    rate,
  }));
  const path = xy.map((point, index) => `${index ? "L" : "M"}${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const last = xy[xy.length - 1];

  return (
    <div ref={ref} className="qa-chart" data-shown={shown ? "" : undefined}>
      <svg viewBox={`0 0 ${width} ${height}`} width="100%" height={height} role="img" aria-label={`${pair} over the last ${points.length} weeks, from ${points[0].rate} to ${last.rate.rate}`}>
        <defs>
          <clipPath id={clip}>
            <rect className="qa-chart-clip" x="0" y="0" width={width} height={height} />
          </clipPath>
        </defs>
        {[0, 0.5, 1].map((fraction) => (
          <line
            key={fraction}
            x1={pad}
            x2={width - pad}
            y1={pad + fraction * (height - pad * 2 - 18)}
            y2={pad + fraction * (height - pad * 2 - 18)}
            stroke="var(--ds-line)"
            strokeWidth="1"
          />
        ))}
        <g clipPath={`url(#${clip})`}>
          <path d={path} fill="none" stroke="var(--ds-ink)" strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
          {xy.map((point) => (
            <circle key={point.rate.id} cx={point.x} cy={point.y} r="3.2" fill="var(--ds-surface)" stroke="var(--ds-ink)" strokeWidth="1.8" />
          ))}
        </g>
        <circle className="qa-chart-last" cx={last.x} cy={last.y} r="5" fill="var(--ds-accent)" />
        <text x={pad} y={height - 2} fontSize="10.5" fill="var(--ds-text-3)" fontFamily="var(--ds-font-mono)">
          {dateOnly(points[0].as_of_date)}
        </text>
        <text x={width - pad} y={height - 2} fontSize="10.5" fill="var(--ds-text-3)" textAnchor="end" fontFamily="var(--ds-font-mono)">
          {dateOnly(last.rate.as_of_date)}
        </text>
      </svg>
    </div>
  );
}

export const dynamic = "force-dynamic";
