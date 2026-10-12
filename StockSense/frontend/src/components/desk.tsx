"use client";

/**
 * The sections of the desk below the hero. Every figure here is a count the
 * server made; the bars and dots only draw it.
 */

import Link from "next/link";
import { useMemo, type CSSProperties } from "react";

import { Card, LinkButton } from "@/design/Surface";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { useInView } from "@/design/motion";
import { Figure } from "@/components/trace";
import { decisionTone } from "@/components/ui";
import { count, countryName, dateLong, dayMonth, days, decimal, monthName, percent, plural } from "@/lib/format";
import type { PlanRun, Settings, Shutdown } from "@/lib/types";

/* ------------------------------------------------------------------ */
/* 1. Where eighteen thousand decisions went                           */
/* ------------------------------------------------------------------ */
const DECISION_ORDER = ["order", "prebuild", "deferred", "watch"];
const DECISION_FILL: Record<string, string> = {
  order: "var(--ds-accent)",
  prebuild: "var(--ds-warn)",
  deferred: "var(--ds-fail)",
  watch: "var(--ds-line-strong)",
};
const DECISION_HINT: Record<string, string> = {
  order: "Below the reorder point, and the cash covered it.",
  prebuild: "Will not survive the shutdown otherwise. Bought now.",
  deferred: "Wanted, but the cash ran out or the supplier minimum was missed.",
  watch: "Covered, not moving, nothing selling, or replaced.",
};

export function DecisionStrip({ plan }: { plan: PlanRun }) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.25 });
  const total = Math.max(1, plan.parts_considered);
  const rows = DECISION_ORDER.map((decision) => plan.by_decision.find((row) => row.decision === decision)).filter(
    Boolean,
  ) as PlanRun["by_decision"];

  return (
    <div ref={ref} className="ss-strip" data-shown={shown ? "" : undefined}>
      <div className="ss-strip-bar" role="img" aria-label={rows.map((row) => `${row.label}: ${count(row.count)}`).join(", ")}>
        {rows.map((row, index) => (
          <span
            key={row.decision}
            className="ss-strip-seg"
            style={
              {
                flexGrow: row.count / total,
                background: DECISION_FILL[row.decision],
                "--ds-d": `${index * 260}ms`,
              } as CSSProperties
            }
          />
        ))}
      </div>
      <div className="ss-strip-scale ds-mono" aria-hidden>
        <span>0</span>
        <span>{count(total)} parts looked at</span>
      </div>

      <div className="ss-decisions">
        {rows.map((row, index) => {
          const reasons = plan.by_reason.filter((reason) => reason.decision === row.decision);
          return (
            <Reveal key={row.decision} index={index} className="ss-decision ds-lift">
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
                <StatusChip tone={decisionTone(row.decision)} pulse={row.decision === "order" || row.decision === "prebuild"}>
                  {row.label}
                </StatusChip>
                <span className="ds-mono ss-decision-share">{percent(row.count / total, 1)}</span>
              </div>
              <div className="ss-decision-count">
                <Figure
                  value={count(row.count)}
                  count={row.count}
                  heading={`${row.label}: lines on this week's plan`}
                  explain={{
                    formula: `Lines on plan ${plan.id} whose decision is "${row.label}", counted by reason`,
                    inputs: reasons.map((reason) => ({
                      label: reason.label,
                      value: count(reason.count),
                      source: `Plan ${plan.id}, worked out ${dateLong(plan.created_at)}`,
                      sourceKind: "Plan line",
                    })),
                  }}
                />
              </div>
              <p className="ss-decision-hint">{DECISION_HINT[row.decision]}</p>
              <ul className="ss-reasons">
                {reasons.map((reason) => (
                  <li key={reason.reason}>
                    <Link href={`/plan?decision=${reason.decision}&reason=${reason.reason}`}>
                      <span>{reason.label}</span>
                      <b className="ds-num">{count(reason.count)}</b>
                    </Link>
                  </li>
                ))}
              </ul>
            </Reveal>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 2. What the catalogue is really like                                */
/* ------------------------------------------------------------------ */
type Quadrant = {
  kind: string;
  area: "tl" | "tr" | "bl" | "br";
  /** How often a dot sparks: a steady part sells most weeks. */
  period: number;
  spark: number;
};

const QUADRANTS: Quadrant[] = [
  { kind: "erratic", area: "tl", period: 2.4, spark: 0.9 },
  { kind: "lumpy", area: "tr", period: 11, spark: 0.18 },
  { kind: "smooth", area: "bl", period: 1.6, spark: 1 },
  { kind: "intermittent", area: "br", period: 8.5, spark: 0.24 },
];

const PER_DOT = 100;

export function PatternMap({ plan, settings }: { plan: PlanRun; settings: Settings | null }) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.15 });
  const [liveRef, onScreen] = useInView<HTMLDivElement>({ once: false, threshold: 0, rootMargin: "0px" });
  const total = Math.max(1, plan.parts_considered);
  const byKind = useMemo(() => new Map(plan.by_pattern.map((row) => [row.pattern, row])), [plan.by_pattern]);
  const interval = settings?.cutoffs.average_demand_interval ?? 1.32;
  const variability = settings?.cutoffs.coefficient_of_variation_squared ?? 0.49;
  const methodFor = (kind: string) => {
    const pattern = settings?.patterns.find((row) => row.kind === kind);
    const method = settings?.methods.find((row) => row.code === pattern?.method);
    return method?.label ?? "";
  };
  const occasional = (byKind.get("intermittent")?.count ?? 0) + (byKind.get("lumpy")?.count ?? 0);
  const silent = byKind.get("no_demand")?.count ?? 0;

  return (
    <div
      ref={(node) => {
        ref(node);
        liveRef(node);
      }}
      className="ss-patterns"
      data-shown={shown ? "" : undefined}
      data-paused={onScreen ? undefined : ""}
    >
      <div className="ss-patterns-copy">
        <p className="ds-mono-label" style={{ margin: 0 }}>
          The catalogue, by how it sells
        </p>
        <p className="ss-patterns-big">
          <Figure
            value={percent(occasional / total)}
            count={Math.round((occasional / total) * 100)}
            heading="Share of parts with long gaps between sales"
            explain={{
              formula: `(Occasional + Occasional and uneven) ÷ every part looked at = (${count(
                byKind.get("intermittent")?.count ?? 0,
              )} + ${count(byKind.get("lumpy")?.count ?? 0)}) ÷ ${count(total)}`,
              result: percent(occasional / total, 1),
              inputs: plan.by_pattern.map((row) => ({
                label: row.label,
                value: count(row.count),
                source: `Plan ${plan.id}: the pattern each part was classified into`,
                sourceKind: "Plan line",
              })),
            }}
          />
        </p>
        <p className="ss-patterns-lede">
          of the parts go weeks without a sale, then sell a burst. That is why one forecasting method for everything does
          not work, and why each corner gets its own.
        </p>
        <p className="ds-mono ss-patterns-foot">
          One dot is {PER_DOT} parts. A dot lights when its kind of part usually sells.
        </p>
      </div>

      <div className="ss-quad-wrap">
        <span className="ss-axis-y ds-mono-label" aria-hidden>
          Size of each sale ↑ jumps about
        </span>
        <div className="ss-quad" role="group" aria-label="Parts by demand pattern">
          {QUADRANTS.map((quadrant, qIndex) => {
            const row = byKind.get(quadrant.kind);
            const number = row?.count ?? 0;
            const dots = Math.max(1, Math.ceil(number / PER_DOT));
            const random = mulberry(qIndex * 997 + 13);
            return (
              <div key={quadrant.kind} className="ss-quad-cell" data-area={quadrant.area} data-kind={quadrant.kind}>
                <div className="ss-quad-head">
                  <span className="ss-quad-label">{row?.label ?? quadrant.kind}</span>
                  <span className="ss-quad-count">
                    <Figure
                      value={count(number)}
                      count={number}
                      heading={`${row?.label ?? quadrant.kind}: parts`}
                      explain={{
                        formula: `Parts whose average gap between sales is ${
                          quadrant.area.endsWith("r") ? "above" : "at or below"
                        } ${decimal(interval, 2)} weeks and whose size variability is ${
                          quadrant.area.startsWith("t") ? "above" : "at or below"
                        } ${decimal(variability, 2)}`,
                        inputs: [
                          {
                            label: "Parts in this corner",
                            value: count(number),
                            source: `Plan ${plan.id}`,
                            sourceKind: "Plan line",
                          },
                          {
                            label: "Forecast with",
                            value: methodFor(quadrant.kind) || "the method for this pattern",
                            source: "The method chosen for the pattern",
                            sourceKind: "Company policy",
                          },
                        ],
                      }}
                    />
                  </span>
                </div>
                <span className="ss-quad-method ds-mono">{methodFor(quadrant.kind)}</span>
                <div className="ss-dots" aria-hidden>
                  {Array.from({ length: dots }, (_, index) => {
                    const sparks = random() < quadrant.spark;
                    return (
                      <i
                        key={index}
                        data-spark={sparks ? "" : undefined}
                        style={
                          {
                            "--ds-d": `${Math.min(index, 120) * 9 + qIndex * 80}ms`,
                            "--spark-period": `${quadrant.period * (0.8 + random() * 0.5)}s`,
                            "--spark-delay": `${random() * quadrant.period}s`,
                          } as CSSProperties
                        }
                      />
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
        <span className="ss-axis-x ds-mono-label" aria-hidden>
          Sells most weeks ← → long gaps between sales
        </span>
        <div className="ss-silent">
          <span className="ss-quad-label">{byKind.get("no_demand")?.label ?? "Nothing sold"}</span>
          <span className="ss-quad-count">
            <Figure
              value={count(silent)}
              count={silent}
              heading="Parts that sold nothing in two years"
              explain={{
                formula: "Parts with no sale anywhere in their history: nothing is forecast and nothing is bought",
                inputs: [
                  {
                    label: "Parts",
                    value: count(silent),
                    source: `Plan ${plan.id}`,
                    sourceKind: "Plan line",
                  },
                ],
              }}
            />
          </span>
          <div className="ss-dots" data-silent="" aria-hidden>
            {Array.from({ length: Math.max(1, Math.ceil(silent / PER_DOT)) }, (_, index) => (
              <i key={index} style={{ "--ds-d": `${index * 40 + 400}ms` } as CSSProperties} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function mulberry(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/* ------------------------------------------------------------------ */
/* 3. The shutdown, country by country                                 */
/* ------------------------------------------------------------------ */
const DAY = 24 * 60 * 60 * 1000;

function at(iso: string): number {
  return new Date(`${iso}T00:00:00`).getTime();
}

export function ShutdownTimeline({ shutdowns }: { shutdowns: Shutdown[] }) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.2 });
  const [liveRef, onScreen] = useInView<HTMLDivElement>({ once: false, threshold: 0, rootMargin: "0px" });
  const rows = shutdowns.filter((row) => row.affects);
  if (!rows.length) return null;

  // Today, as the server counts it: the order-by date less the days left.
  const first = rows[0];
  const today = at(first.order_by) - (first.days_until_order_by ?? 0) * DAY;
  const end = Math.max(...rows.map((row) => at(row.back_to_normal_on))) + 10 * DAY;
  const span = Math.max(DAY, end - today);
  const x = (time: number) => Math.max(0, Math.min(1, (time - today) / span));

  const months: { label: string; left: number }[] = [];
  const cursor = new Date(today);
  cursor.setDate(1);
  cursor.setMonth(cursor.getMonth() + 1);
  while (cursor.getTime() < end) {
    months.push({ label: monthName(cursor.getMonth()), left: x(cursor.getTime()) });
    cursor.setMonth(cursor.getMonth() + 1);
  }

  return (
    <div
      ref={(node) => {
        ref(node);
        liveRef(node);
      }}
      className="ss-shut"
      data-shown={shown ? "" : undefined}
      data-paused={onScreen ? undefined : ""}
    >
      <div className="ss-shut-months ds-mono" aria-hidden>
        <span style={{ left: 0 }}>Today</span>
        {months.map((month) => (
          <span key={month.label} style={{ left: `${month.left * 100}%` }}>
            {month.label}
          </span>
        ))}
      </div>
      {rows.map((row, index) => {
        const orderBy = x(at(row.order_by));
        const closes = x(at(row.closes_on));
        const reopens = x(at(row.reopens_on));
        const normal = x(at(row.back_to_normal_on));
        const newYear = x(at(row.new_year));
        const urgent = (row.days_until_order_by ?? 99) <= 75;
        return (
          <div key={row.country} className="ss-shut-row" style={{ "--ds-d": `${index * 160}ms` } as CSSProperties}>
            <div className="ss-shut-who">
              <span className="ss-shut-country">{row.label || countryName(row.country)}</span>
              <span className="ds-mono ss-shut-meta">
                {plural(row.parts ?? 0, "part")} · {decimal(row.weeks_of_cover_needed ?? 0, 1)} weeks of cover
              </span>
            </div>
            <div className="ss-shut-count" data-urgent={urgent ? "" : undefined}>
              <Figure
                value={days(row.days_until_order_by ?? 0)}
                count={row.days_until_order_by ?? 0}
                    heading={`Days left to order from ${row.label}`}
                explain={{
                  formula: "The last day these plants accept orders before the new year, less today",
                  result: days(row.days_until_order_by ?? 0),
                  inputs: [
                    { label: "Lunar New Year", value: dateLong(row.new_year), source: "Published date", sourceKind: "Shutdown calendar" },
                    { label: "Stops taking orders", value: dateLong(row.order_by), source: `${row.label} rule`, sourceKind: "Shutdown calendar" },
                    { label: "Closed", value: `${dateLong(row.closes_on)} to ${dateLong(row.reopens_on)}`, source: `${row.closed_days} days`, sourceKind: "Shutdown calendar" },
                    { label: "Back to normal output", value: dateLong(row.back_to_normal_on), source: `${row.disrupted_days} days disrupted in all`, sourceKind: "Shutdown calendar" },
                    { label: "Cover to have on the shelf", value: `${decimal(row.weeks_of_cover_needed ?? 0, 1)} weeks`, source: "Disrupted days plus the pre-build allowance", sourceKind: "Company policy" },
                  ],
                }}
              />
              <span className="ss-shut-count-label ds-mono-label">to order</span>
            </div>
            <div className="ss-shut-track" aria-label={`${row.label}: order by ${dateLong(row.order_by)}, closed ${dateLong(row.closes_on)} to ${dateLong(row.reopens_on)}, back to normal ${dateLong(row.back_to_normal_on)}`} role="img">
              <span className="ss-shut-line" />
              <span className="ss-shut-run" style={{ width: `${orderBy * 100}%` }}>
                <span className="ss-shut-fill" />
                <span className="ss-shut-pulse" />
              </span>
              <span className="ss-shut-span" data-kind="disrupted" style={{ left: `${reopens * 100}%`, width: `${(normal - reopens) * 100}%` }} />
              <span className="ss-shut-span" data-kind="closed" style={{ left: `${closes * 100}%`, width: `${(reopens - closes) * 100}%` }} />
              <span className="ss-shut-tick" style={{ left: `${newYear * 100}%` }} title={`Lunar New Year, ${dateLong(row.new_year)}`} />
              <span className="ss-shut-node" data-kind="today" style={{ left: 0 }} />
              <span className="ss-shut-node" data-kind="order" style={{ left: `${orderBy * 100}%` }}>
                <span className="ss-shut-tag ds-mono">Order by {dayMonth(row.order_by)}</span>
              </span>
              <span className="ss-shut-tag ds-mono" data-kind="closed" style={{ left: `${((closes + reopens) / 2) * 100}%` }}>
                Closed {row.closed_days} days
              </span>
            </div>
          </div>
        );
      })}
      <div className="ss-shut-key">
        <span className="ss-key">
          <span className="ss-key-swatch" style={{ background: "var(--ds-warn)" }} aria-hidden /> Plants closed
        </span>
        <span className="ss-key">
          <span className="ss-key-swatch" style={{ background: "var(--ds-warn-soft)", borderColor: "var(--ds-warn)" }} aria-hidden />{" "}
          Back but below normal output
        </span>
        <span className="ss-key">
          <span className="ss-key-swatch" style={{ background: "var(--ds-accent)" }} aria-hidden /> Time left to order
        </span>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* 4. Walk someone through it                                          */
/* ------------------------------------------------------------------ */
export type TourStop = { key: string; minutes: number; title: string; say: string; href: string; action: string };

export function TourRoute({ stops }: { stops: TourStop[] }) {
  const [ref, shown] = useInView<HTMLOListElement>({ threshold: 0.15 });
  const [liveRef, onScreen] = useInView<HTMLOListElement>({ once: false, threshold: 0, rootMargin: "0px" });
  return (
    <ol
      ref={(node) => {
        ref(node);
        liveRef(node);
      }}
      className="ss-tour"
      data-shown={shown ? "" : undefined}
      data-paused={onScreen ? undefined : ""}
      style={{ "--tour-count": stops.length } as CSSProperties}
    >
      <span className="ss-tour-line" aria-hidden>
        <span />
        <i />
      </span>
      {stops.map((stop, index) => (
        <li key={stop.key} className="ss-tour-stop ds-reveal" data-shown={shown ? "" : undefined} style={{ "--ds-d": `${index * 90}ms` } as CSSProperties}>
          <span className="ss-tour-node" aria-hidden>
            {String(index + 1).padStart(2, "0")}
          </span>
          <span className="ds-mono-label">
            Stop {index + 1} · {plural(stop.minutes, "minute")}
          </span>
          <h3 className="ss-tour-title">{stop.title}</h3>
          <p className="ss-tour-say">“{stop.say}”</p>
          <LinkButton href={stop.href} tone="secondary" size="small" arrow>
            {stop.action}
          </LinkButton>
        </li>
      ))}
    </ol>
  );
}

export { Card };
