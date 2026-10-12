"use client";

import Link from "next/link";
import { use, useState, type CSSProperties } from "react";

import { Card, Stat } from "@/design/Surface";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { TraceSteps } from "@/design/TraceSheet";
import { CoverFan, DemandChart, Deliveries } from "@/components/charts";
import { Figure } from "@/components/trace";
import { ErrorNote, Field, Key, Loading, PageBand, decisionTone, patternTone } from "@/components/ui";
import { useLoad } from "@/lib/hooks";
import {
  BASE_CURRENCY,
  count,
  countryName,
  cover,
  currencyName,
  dateLong,
  days,
  decimal,
  flagWords,
  money,
  plain,
  shortSupplier,
} from "@/lib/format";
import type { PartDetail, Trace } from "@/lib/types";

type Lie = {
  key: string;
  kind?: "censored" | "project" | "zero";
  title: string;
  text: string;
  tone: "warn" | "fail" | "accent";
};

function lies(part: PartDetail): Lie[] {
  const { demand, recommendation, supplier } = part;
  const out: Lie[] = [];
  const pattern = demand.pattern;
  if (demand.prepared.censored_weeks.length) {
    out.push({
      key: "censored",
      kind: "censored",
      tone: "fail",
      title: `${demand.prepared.censored_weeks.length === 1 ? "One zero week was" : `${count(demand.prepared.censored_weeks.length)} zero weeks were`} an empty shelf, not zero demand`,
      text:
        demand.prepared.notes.find((note) => /empty shelf/i.test(note)) ??
        "Demand in those weeks was raised to the usual rate. Fed back as zero, the forecast falls, less is ordered and the shelf empties again.",
    });
  }
  if (demand.prepared.project_weeks.length) {
    out.push({
      key: "project",
      kind: "project",
      tone: "warn",
      title: "A one-off project order would inflate the baseline",
      text:
        demand.prepared.notes.find((note) => /project/i.test(note)) ??
        "Weeks far above the usual size are recorded and kept out of the baseline.",
    });
  }
  if (pattern.kind === "intermittent" || pattern.kind === "lumpy") {
    out.push({
      key: "zero",
      kind: "zero",
      tone: "accent",
      title: `Sold in ${pattern.periods_with_demand} of ${pattern.periods} weeks: a forecast of zero would score better`,
      text: "On the usual error measure, predicting nothing beats any real forecast for a part like this, and would empty the shelf. That is why it is judged on stock-outs and money instead.",
    });
  }
  if (pattern.kind === "no_demand" || recommendation.flags.includes("dead_stock")) {
    out.push({
      key: "dead",
      tone: "warn",
      title: "Nothing is selling: a forecast that only updates on a sale would keep buying",
      text: "The classic method for occasional demand holds the rate of the last sale for ever. This one updates every week, so a part that stops selling decays towards zero.",
    });
  }
  if (demand.forecast.borrowed) {
    out.push({
      key: "borrowed",
      tone: "warn",
      title: "Too little history of its own: the forecast is borrowed",
      text: demand.forecast.notes[0] ?? "The shape of established parts in the same family, with the range widened by half again.",
    });
  }
  if (!supplier.lead_time.is_reliable || supplier.lead_time.slippage_days >= 3) {
    out.push({
      key: "late",
      tone: "fail",
      title: `The quote says ${supplier.lead_time.quoted_days} days. The record says ${decimal(supplier.lead_time.average_days, 1)}.`,
      text: `Nine deliveries in ten arrive within ${decimal(supplier.lead_time.ninetieth_percentile_days, 1)} days, the worst took ${supplier.lead_time.worst_days}. The cover is sized on what happens, not on the quote.`,
    });
  }
  return out;
}

export default function OnePart({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, loading } = useLoad<PartDetail>(`/api/parts/${id}`);
  const [highlight, setHighlight] = useState<Lie["kind"] | null>(null);

  if (error) {
    return (
      <PageBand eyebrow={["Part"]} title="This part could not be opened." back={{ href: "/plan", label: "To order" }}>
        <div style={{ paddingBottom: 30 }}>
          <ErrorNote error={error} />
        </div>
      </PageBand>
    );
  }
  if (loading || !data) {
    return (
      <PageBand eyebrow={["Part", `number ${id}`]} title="Opening the part…" back={{ href: "/plan", label: "To order" }}>
        <Loading what="Working out its forecast" dark />
      </PageBand>
    );
  }

  const { demand, recommendation: order, supplier } = data;
  const policy = order.policy;
  const distribution = policy.distribution;
  const warnings = lies(data);
  const forecastTrace = demand.forecast.trace;
  const orderTrace = order.trace;
  const policyTrace = policy.trace;
  const shutdown = supplier.shutdown?.affects ? supplier.shutdown : null;

  return (
    <>
      <PageBand
        back={{ href: "/plan", label: "To order" }}
        eyebrow={[data.family, `Class ${data.abc_class}`, countryName(supplier.country)]}
        title={data.description}
        lede={
          <>
            <span className="ds-stamp" style={{ marginRight: 10 }}>
              {data.code}
            </span>
            {plain(demand.pattern.description)} Forecast by {demand.forecast.method_label.toLowerCase()}, on the built-in
            engine: {plain(demand.forecast.method_note).toLowerCase()}
          </>
        }
        actions={
          <div className="ss-part-chips">
            <StatusChip tone={patternTone(demand.pattern.kind)} surface="dark" size="large">
              {demand.pattern.label}
            </StatusChip>
            <StatusChip tone={decisionTone(order.decision)} surface="dark" size="large" pulse={order.quantity > 0}>
              {order.decision_label}
            </StatusChip>
            <StatusChip tone="neutral" surface="dark" size="large">
              {order.reason_label}
            </StatusChip>
          </div>
        }
        aside={
          warnings.length ? (
            <div className="ss-lies" role="list" aria-label="Where the statistics lie for this part">
              <p className="ds-mono-label ss-lies-head">
                <span className="ds-live-dot" data-tone="warn" aria-hidden /> Where the statistics lie · {warnings.length}
              </p>
              {warnings.map((lie, index) => (
                <button
                  key={lie.key}
                  type="button"
                  role="listitem"
                  className="ss-lie"
                  data-tone={lie.tone}
                  data-active={highlight && highlight === lie.kind ? "" : undefined}
                  disabled={!lie.kind}
                  style={{ "--ds-d": `${500 + index * 160}ms` } as CSSProperties}
                  onClick={() => {
                    if (!lie.kind) return;
                    setHighlight(highlight === lie.kind ? null : lie.kind);
                    document.getElementById("history")?.scrollIntoView({ behavior: "smooth", block: "center" });
                  }}
                >
                  <span className="ss-lie-index ds-mono">{String(index + 1).padStart(2, "0")}</span>
                  <span className="ss-lie-title">{lie.title}</span>
                  <span className="ss-lie-text">{plain(lie.text)}</span>
                  {lie.kind && <span className="ss-lie-link ds-mono">Show it on the chart →</span>}
                </button>
              ))}
            </div>
          ) : (
            <div className="ss-lies" data-clean="">
              <p className="ds-mono-label ss-lies-head">
                <span className="ds-live-dot" aria-hidden /> Nothing unusual
              </p>
              <p style={{ margin: "10px 0 0", color: "var(--ds-ink-muted)", fontSize: 14 }}>
                Steady sales, a supplier that keeps to its quote and a full history: the ordinary statistics hold for this
                part.
              </p>
            </div>
          )
        }
      >
        <div className="ds-stats ss-part-stats">
          <Stat
            label="Order"
            tone="accent"
            value={
              order.quantity > 0 ? (
                <Figure value={count(order.quantity)} count={order.quantity} heading={`${data.code}: how much to order`} trace={orderTrace} />
              ) : (
                <Figure value="Nothing" heading={`${data.code}: why nothing is ordered`} trace={orderTrace} />
              )
            }
            unit={order.quantity > 0 ? "units" : undefined}
          />
          <Stat
            label={`Costs, ${BASE_CURRENCY}`}
            value={<Figure value={money(order.value)} count={Number(order.value)} decimals={2} heading={`${data.code}: what the order costs`} trace={orderTrace} />}
          />
          <Stat
            label="Have, on hand and coming"
            value={
              <Figure
                value={count(order.position)}
                count={order.position}
                heading={`${data.code}: what we have`}
                explain={{
                  formula: "On the shelf + already on order",
                  result: count(order.position),
                  inputs: [
                    { label: "On the shelf", value: count(data.on_hand), source: "Stock record", sourceKind: "Part record" },
                    { label: "On order", value: count(data.on_order), source: data.on_order_due ? `Due ${dateLong(data.on_order_due)}` : "Nothing due", sourceKind: "Part record" },
                  ],
                }}
              />
            }
          />
          <Stat
            label="Lasts"
            tone={order.days_of_cover < 14 ? "fail" : undefined}
            value={<Figure value={cover(order.days_of_cover)} heading={`${data.code}: how long what we have lasts`} trace={orderTrace} />}
          />
          <Stat
            label="Demand a week"
            value={<Figure value={decimal(demand.weekly_rate, 1)} heading={`${data.code}: weekly demand`} trace={forecastTrace} />}
          />
          <Stat
            label="Order when it falls to"
            value={<Figure value={count(policy.reorder_point)} count={policy.reorder_point} heading={`${data.code}: the reorder point`} trace={policyTrace} />}
          />
        </div>
      </PageBand>

      <div className="ds-work">
        {order.shutdown_note && (
          <Reveal>
            <div className="ss-shutnote">
              <span className="ds-live-dot" data-tone="warn" aria-hidden />
              <span>{plain(order.shutdown_note)}</span>
              {shutdown && (
                <span className="ds-mono" style={{ marginLeft: "auto" }}>
                  Order by {dateLong(shutdown.order_by)} · {decimal(supplier.weeks_of_cover_needed, 1)} weeks of cover needed
                </span>
              )}
            </div>
          </Reveal>
        )}

        <Reveal>
          <Card
            id="history"
            eyebrow={`${demand.pattern.periods_with_demand} of ${demand.pattern.periods} weeks sold something`}
            title="Two years of sales, and what comes next"
            subtitle="A bar for each week that sold, a dark dot for each week that did not. After today, the forecast as a band with the expected week inside it."
            action={
              <div className="ss-legend">
                <Key colour="var(--ds-text-2)" label="Sold" />
                <Key colour="var(--ds-fail)" label="Shelf empty" />
                <Key colour="var(--ds-warn)" label="Project order" />
                <Key colour="var(--ds-accent)" label="Forecast range" />
              </div>
            }
          >
            <DemandChart
              sold={demand.sold}
              censoredWeeks={demand.prepared.censored_weeks}
              projectWeeks={demand.prepared.project_weeks}
              startsOn={data.history_starts_on}
              rate={demand.weekly_rate}
              deviation={demand.forecast.deviation}
              shutdown={shutdown}
              highlight={highlight}
            />
            <dl className="ss-facts">
              <Field label="Sells every">{decimal(demand.pattern.average_demand_interval, 1)} weeks on average</Field>
              <Field label="Size varies">{decimal(demand.pattern.coefficient_of_variation_squared, 2)} (above 0.49 is uneven)</Field>
              <Field label="Chance of a sale">{decimal(demand.forecast.probability_of_demand * 100, 0)}% a week</Field>
              <Field label="Typical sale">{count(demand.forecast.typical_size)} units</Field>
            </dl>
            {demand.prepared.notes.length > 0 && (
              <ul className="ss-notes">
                {demand.prepared.notes.map((note) => (
                  <li key={note}>{plain(note)}</li>
                ))}
              </ul>
            )}
          </Card>
        </Reveal>

        <div className="ss-part-grid">
          <div style={{ display: "grid", gap: 24, minWidth: 0, alignContent: "start" }}>
            <Reveal>
              <Card
                eyebrow="Never one number"
                title="What happens next, and how sure we are"
                subtitle={
                  distribution
                    ? `The band is what the last two years actually did over ${distribution.cover_weeks_low}${
                        distribution.cover_weeks_high !== distribution.cover_weeks_low ? ` to ${distribution.cover_weeks_high}` : ""
                      } weeks, taken from ${count(distribution.windows)} runs of the history, not from a bell curve.`
                    : "The band comes from the usual weekly spread, because there is too little history to take it from the past."
                }
              >
                <CoverFan
                  coverDays={policy.cover_days}
                  median={distribution ? distribution.median : policy.demand_over_cover * 0.8}
                  high={distribution ? distribution.at_service_level : policy.reorder_point}
                  average={distribution ? distribution.average : policy.demand_over_cover}
                  reorderPoint={policy.reorder_point}
                  position={order.position}
                  ordered={order.quantity}
                />
              </Card>
            </Reveal>
            <Reveal>
              <Card eyebrow={`${orderTrace?.steps.length ?? 0} steps, each with its arithmetic`} title="How the quantity was reached" subtitle="From the forecast to something a buyer can send: the supplier's real lead time, the shutdown, the pack size and the cash.">
                {orderTrace?.steps?.length ? <TraceSteps steps={toSteps(orderTrace)} /> : <p>Nothing to work out.</p>}
              </Card>
            </Reveal>
          </div>

          <div style={{ display: "grid", gap: 24, alignContent: "start", minWidth: 0 }}>
            <Reveal>
              <Card eyebrow={`${countryName(supplier.country)} · pays in ${currencyName(supplier.currency)}`} title={shortSupplier(supplier.name)} action={<Link href={`/suppliers/${supplier.id}`} className="ss-textlink">Open →</Link>}>
                <Deliveries samples={supplier.lead_time_samples} quoted={supplier.lead_time.quoted_days} />
                <dl style={{ margin: "12px 0 0" }}>
                  <Field label="Quotes">{days(supplier.lead_time.quoted_days)}</Field>
                  <Field label="Actually takes">
                    <span style={{ fontWeight: 600, color: supplier.lead_time.slippage_days >= 3 ? "var(--ds-fail-ink)" : undefined }}>
                      {days(supplier.lead_time.average_days)}
                    </span>
                  </Field>
                  <Field label="Nine in ten within">{days(supplier.lead_time.ninetieth_percentile_days)}</Field>
                  <Field label="Deliveries seen">{count(supplier.lead_time.deliveries)}</Field>
                  {shutdown && <Field label="Last day to order">{dateLong(shutdown.order_by)}</Field>}
                </dl>
              </Card>
            </Reveal>
            <Reveal>
              <Card eyebrow={`Sized from ${policy.method === "history" ? "this part's own past" : "the textbook formula"}`} title="Cover">
                <dl style={{ margin: 0 }}>
                  <Field label="Service level">{Math.round(policy.service_level * 100)}% for class {data.abc_class}</Field>
                  <Field label="Lead time used">{days(policy.lead_time_days)}</Field>
                  <Field label="Safety stock">
                    <Figure value={count(policy.safety_stock)} heading={`${data.code}: safety stock`} trace={policyTrace} />
                  </Field>
                  <Field label="Order at">
                    <Figure value={count(policy.reorder_point)} heading={`${data.code}: the reorder point`} trace={policyTrace} />
                  </Field>
                  <Field label="Fill up to">
                    <Figure value={count(policy.order_up_to)} heading={`${data.code}: fill up to`} trace={policyTrace} />
                  </Field>
                </dl>
              </Card>
            </Reveal>
            <Reveal>
              <Card title="On the part record">
                <dl style={{ margin: 0 }}>
                  <Field label="Cost">{money(data.unit_cost)} {BASE_CURRENCY}</Field>
                  <Field label="Packs of">{count(data.pack_size)}</Field>
                  {data.minimum_order_quantity > 0 && <Field label="Minimum order quantity">{count(data.minimum_order_quantity)}</Field>}
                  <Field label="Stock worth">{money(data.stock_value)}</Field>
                  {data.predecessor && (
                    <Field label="Replaces">
                      <Link className="ss-textlink" href={`/parts/${data.predecessor.id}`}>{data.predecessor.code}</Link>
                    </Field>
                  )}
                  {data.successor && (
                    <Field label="Replaced by">
                      <Link className="ss-textlink" href={`/parts/${data.successor.id}`}>{data.successor.code}</Link>
                    </Field>
                  )}
                </dl>
                {order.flags.length > 0 && (
                  <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 14 }}>
                    {order.flags.map((flag) => (
                      <StatusChip key={flag} tone="warn" size="small">
                        {flagWords(flag)}
                      </StatusChip>
                    ))}
                  </div>
                )}
              </Card>
            </Reveal>
          </div>
        </div>
      </div>
    </>
  );
}

function toSteps(trace: Trace) {
  return trace.steps.map((step) => ({
    label: plain(step.label),
    formula: plain(step.formula),
    result: plain(step.result),
    unit: plain(step.unit),
    note: plain(step.note),
    inputs: (step.inputs ?? []).map((input) => ({
      label: plain(input.label),
      value: plain(input.value),
      source: plain(input.source),
      sourceKind: input.source ? "From" : undefined,
    })),
  }));
}
