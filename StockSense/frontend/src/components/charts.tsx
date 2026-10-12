"use client";

/**
 * Drawing demand. Plain SVG, no charting library.
 *
 * Every chart draws in when it scrolls into view - bars grow from the
 * baseline one week after another, lines and bands are revealed left to
 * right by a clip that only ever moves by transform - and under reduced
 * motion it is simply there. A forecast is never one line: it is always a
 * band with the line inside it. No dashes anywhere: thresholds are solid
 * lines with a label.
 */

import { useId, useMemo, type CSSProperties } from "react";

import { useInView } from "@/design/motion";
import { count, dayMonth, decimal } from "@/lib/format";

const DAY = 86400000;
function weeksFrom(startsOn: string, iso: string): number {
  return (new Date(`${iso}T00:00:00`).getTime() - new Date(`${startsOn}T00:00:00`).getTime()) / DAY / 7;
}

/* ------------------------------------------------------------------ */
/* Two years of sales, then the forecast band and the shutdown          */
/* ------------------------------------------------------------------ */
export type ShutdownWindow = {
  label: string;
  closes_on: string;
  reopens_on: string;
  back_to_normal_on: string;
  order_by: string;
};

export function DemandChart({
  sold,
  censoredWeeks,
  projectWeeks,
  startsOn,
  rate,
  deviation,
  horizon = 26,
  shutdown,
  highlight,
}: {
  sold: number[];
  censoredWeeks: number[];
  projectWeeks: number[];
  startsOn: string | null;
  rate: number;
  deviation: number;
  horizon?: number;
  shutdown?: ShutdownWindow | null;
  /** Which kind of week to pick out, when a warning is being pointed at. */
  highlight?: "censored" | "project" | "zero" | null;
}) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.2 });
  const clip = useId().replace(/:/g, "");
  const weeks = sold.length;
  const step = 6;
  const width = (weeks + horizon) * step;
  const height = 230;
  const top = 26;
  const base = height - 26;
  const censored = useMemo(() => new Set(censoredWeeks), [censoredWeeks]);
  const projects = useMemo(() => new Set(projectWeeks), [projectWeeks]);
  const ordinary = sold.filter((_, index) => !projects.has(index));
  const ceiling = Math.max(1, rate + deviation * 1.2, ...ordinary) * 1.12;
  const y = (value: number) => base - (Math.min(value, ceiling) / ceiling) * (base - top);
  const todayX = weeks * step;
  const future = (week: number) => todayX + week * step;

  const shut = useMemo(() => {
    if (!shutdown || !startsOn) return null;
    const closes = weeksFrom(startsOn, shutdown.closes_on);
    const reopens = weeksFrom(startsOn, shutdown.reopens_on);
    const normal = weeksFrom(startsOn, shutdown.back_to_normal_on);
    const orderBy = weeksFrom(startsOn, shutdown.order_by);
    const clampX = (week: number) => Math.max(todayX, Math.min(width, week * step));
    return {
      closes: clampX(closes),
      reopens: clampX(reopens),
      normal: clampX(normal),
      orderBy: clampX(orderBy),
      label: shutdown.label,
      orderByText: dayMonth(shutdown.order_by),
    };
  }, [shutdown, startsOn, todayX, width]);

  const low = Math.max(0, rate - deviation);
  const high = rate + deviation;
  const months = useMemo(() => {
    if (!startsOn) return [] as { x: number; label: string }[];
    const start = new Date(`${startsOn}T00:00:00`);
    const marks: { x: number; label: string }[] = [];
    const cursor = new Date(start);
    cursor.setDate(1);
    cursor.setMonth(cursor.getMonth() + 1);
    const end = new Date(start.getTime() + (weeks + horizon) * 7 * DAY);
    while (cursor < end) {
      if (cursor.getMonth() === 0 || cursor.getMonth() === 6) {
        const x = ((cursor.getTime() - start.getTime()) / DAY / 7) * step;
        marks.push({ x, label: `${cursor.getMonth() === 0 ? "January" : "July"} ${cursor.getFullYear()}` });
      }
      cursor.setMonth(cursor.getMonth() + 1);
    }
    return marks;
  }, [startsOn, weeks, horizon]);

  return (
    <div ref={ref} className="ss-chart" data-shown={shown ? "" : undefined} data-highlight={highlight ?? undefined}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${weeks} weeks of sales, then ${horizon} weeks of forecast`} preserveAspectRatio="none" style={{ height }}>
        <defs>
          <clipPath id={`${clip}-future`}>
            <rect className="ss-clip" x={todayX} y={0} width={width - todayX} height={height} />
          </clipPath>
        </defs>

        {/* the shutdown, behind everything */}
        {shut && shut.normal > shut.closes && (
          <g className="ss-chart-shutdown">
            <rect x={shut.reopens} y={top - 14} width={Math.max(0, shut.normal - shut.reopens)} height={base - top + 14} fill="var(--ds-warn-soft)" />
            <rect x={shut.closes} y={top - 14} width={Math.max(0, shut.reopens - shut.closes)} height={base - top + 14} fill="var(--ds-warn)" opacity="0.32" />
            <line x1={shut.closes} x2={shut.closes} y1={top - 14} y2={base} stroke="var(--ds-warn)" strokeWidth="1.5" />
          </g>
        )}

        {/* gridlines */}
        {[0.25, 0.5, 0.75, 1].map((share) => (
          <line key={share} x1={0} x2={width} y1={y(ceiling * share / 1.12)} y2={y(ceiling * share / 1.12)} stroke="var(--ds-line)" strokeWidth="1" />
        ))}
        <line x1={0} x2={width} y1={base + 0.5} y2={base + 0.5} stroke="var(--ds-line-strong)" strokeWidth="1" />

        {/* the weeks: a bar when something sold, a dark dot when nothing did */}
        {sold.map((value, index) => {
          const isProject = projects.has(index);
          const isCensored = censored.has(index);
          const x = index * step + 1;
          const delay = `${index * 9}ms`;
          if (value <= 0 && !isCensored) {
            return (
              <circle key={index} className="ss-zweek" cx={x + 2} cy={base - 3} r={1.4} style={{ "--ds-d": delay } as CSSProperties}>
                <title>{`Week ${index + 1}: nothing sold`}</title>
              </circle>
            );
          }
          const barTop = isCensored && value <= 0 ? base - 10 : y(value);
          const fill = isProject ? "var(--ds-warn)" : isCensored ? "var(--ds-fail)" : "var(--ds-text-2)";
          const kind = isProject ? "project" : isCensored ? "censored" : "sold";
          return (
            <g key={index}>
              <rect
                className="ss-bar"
                data-kind={kind}
                x={x}
                y={barTop}
                width={4}
                height={Math.max(2, base - barTop)}
                fill={fill}
                style={{ "--ds-d": delay } as CSSProperties}
              >
                <title>
                  {`Week ${index + 1}: ${count(value)} sold`}
                  {isCensored ? " (the shelf was empty: demand unknown, not zero)" : ""}
                  {isProject ? " (a one-off project order, kept out of the baseline)" : ""}
                </title>
              </rect>
              {isProject && value > ceiling && (
                <text x={x + 2} y={top - 4} textAnchor="middle" className="ss-chart-flag">
                  ↑ {count(value)}
                </text>
              )}
            </g>
          );
        })}

        {/* today, and the forecast band after it */}
        <line x1={todayX} x2={todayX} y1={top - 14} y2={base} stroke="var(--ds-text)" strokeWidth="1.5" />
        <g clipPath={`url(#${clip}-future)`}>
          <rect x={todayX} y={y(high)} width={width - todayX} height={Math.max(1, y(low) - y(high))} fill="var(--ds-accent-soft)" />
          <line x1={todayX} x2={width} y1={y(high)} y2={y(high)} stroke="var(--ds-accent-line)" strokeWidth="1" />
          <line x1={todayX} x2={width} y1={y(low)} y2={y(low)} stroke="var(--ds-accent-line)" strokeWidth="1" />
          <line x1={todayX} x2={width} y1={y(rate)} y2={y(rate)} stroke="var(--ds-accent)" strokeWidth="2.5" />
          {Array.from({ length: Math.floor(horizon / 4) }, (_, index) => (
            <circle key={index} className="ss-band-node" cx={future(index * 4 + 2)} cy={y(rate)} r={2.6} fill="var(--ds-accent)" style={{ "--ds-d": `${1500 + index * 120}ms` } as CSSProperties} />
          ))}
        </g>
        {shut && shut.orderBy > todayX && (
          <g className="ss-chart-orderby">
            <line x1={shut.orderBy} x2={shut.orderBy} y1={top - 14} y2={base} stroke="var(--ds-fail-ink)" strokeWidth="1.5" />
            <circle cx={shut.orderBy} cy={top - 14} r={3.5} fill="var(--ds-fail)" />
          </g>
        )}
        {months.map((month) => (
          <text key={month.label} x={month.x} y={height - 8} className="ss-chart-axis">
            {month.label}
          </text>
        ))}
        <text x={todayX - 4} y={top - 18} textAnchor="end" className="ss-chart-axis" style={{ fontWeight: 700 }}>
          Today
        </text>
      </svg>
      {shut && (
        <div className="ss-chart-tags" aria-hidden>
          {shut.orderBy > todayX && (
            <span className="ss-chart-tag" data-kind="order" style={{ left: `${(shut.orderBy / width) * 100}%` }}>
              Order by {shut.orderByText}
            </span>
          )}
          {shut.reopens > shut.closes && (
            <span className="ss-chart-tag" data-kind="closed" style={{ left: `${(((shut.closes + shut.reopens) / 2) / width) * 100}%` }}>
              {shut.label} closed
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* What happens over the cover period                                   */
/* ------------------------------------------------------------------ */
export function CoverFan({
  coverDays,
  median,
  high,
  average,
  reorderPoint,
  position,
  ordered,
}: {
  coverDays: number;
  median: number;
  high: number;
  average: number;
  reorderPoint: number;
  position: number;
  ordered: number;
}) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.25 });
  const clip = useId().replace(/:/g, "");
  const width = 640;
  const height = 210;
  const left = 4;
  const right = width - 4;
  const top = 16;
  const base = height - 24;
  const after = position + ordered;
  const peak = Math.max(1, high, average, reorderPoint, after, position) * 1.12;
  const x = (share: number) => left + share * (right - left);
  const y = (value: number) => base - (Math.max(0, value) / peak) * (base - top);
  const steps = 24;
  const upper: string[] = [];
  const lower: string[] = [];
  const middle: string[] = [];
  for (let index = 0; index <= steps; index += 1) {
    const t = index / steps;
    const centre = average * t;
    const spreadUp = (high - average) * Math.sqrt(t);
    const spreadDown = Math.max(0, average - median) * Math.sqrt(t);
    upper.push(`${x(t)},${y(centre + Math.max(0, spreadUp))}`);
    lower.unshift(`${x(t)},${y(Math.max(0, centre - spreadDown))}`);
    middle.push(`${x(t)},${y(centre)}`);
  }
  const lines = [
    { value: reorderPoint, colour: "var(--ds-fail-ink)", label: `Order at ${count(reorderPoint)}` },
    { value: position, colour: "var(--ds-pass-ink)", label: `What we have, ${count(position)}` },
    ...(ordered > 0 ? [{ value: after, colour: "var(--ds-accent-ink)", label: `After this order, ${count(after)}` }] : []),
  ];

  return (
    <div ref={ref} className="ss-chart" data-shown={shown ? "" : undefined}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Demand over the cover period, with its range" preserveAspectRatio="none" style={{ height }}>
        <defs>
          <clipPath id={`${clip}-fan`}>
            <rect className="ss-clip" x={0} y={0} width={width} height={height} />
          </clipPath>
        </defs>
        {[0.25, 0.5, 0.75].map((share) => (
          <line key={share} x1={left} x2={right} y1={y(peak * share)} y2={y(peak * share)} stroke="var(--ds-line)" strokeWidth="1" />
        ))}
        <line x1={left} x2={right} y1={base + 0.5} y2={base + 0.5} stroke="var(--ds-line-strong)" />
        <g clipPath={`url(#${clip}-fan)`}>
          <polygon points={[...upper, ...lower].join(" ")} fill="var(--ds-accent-soft)" />
          <polyline points={upper.join(" ")} fill="none" stroke="var(--ds-accent-line)" strokeWidth="1.2" />
          <polyline points={middle.join(" ")} fill="none" stroke="var(--ds-accent)" strokeWidth="2.5" />
        </g>
        {lines.map((line, index) => (
          <g key={line.label} className="ss-fan-line" style={{ "--ds-d": `${900 + index * 220}ms` } as CSSProperties}>
            <line x1={left} x2={right} y1={y(line.value)} y2={y(line.value)} stroke={line.colour} strokeWidth="1.75" />
            <circle cx={right - 3} cy={y(line.value)} r={3.5} fill={line.colour} />
          </g>
        ))}
        <text x={left} y={height - 6} className="ss-chart-axis">
          Today
        </text>
        <text x={right} y={height - 6} textAnchor="end" className="ss-chart-axis">
          {decimal(coverDays, 0)} days: the lead time plus the wait to the next order
        </text>
      </svg>
      <div className="ss-fan-labels" aria-hidden>
        {lines.map((line) => (
          <span key={line.label} style={{ top: `${(y(line.value) / height) * 100}%`, color: line.colour }}>
            {line.label}
          </span>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Every delivery on record against the quote                           */
/* ------------------------------------------------------------------ */
export function Deliveries({ samples, quoted }: { samples: number[]; quoted: number }) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.3 });
  if (!samples.length) {
    return <p style={{ fontSize: 13, color: "var(--ds-text-3)", margin: 0 }}>No deliveries on record yet.</p>;
  }
  const width = 480;
  const height = 92;
  const peak = Math.max(quoted, ...samples) * 1.15;
  const low = Math.min(quoted, ...samples) * 0.8;
  const y = (value: number) => height - 10 - ((value - low) / Math.max(1, peak - low)) * (height - 22);
  return (
    <div ref={ref} className="ss-chart" data-shown={shown ? "" : undefined}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`${samples.length} deliveries against a quote of ${quoted} days`} preserveAspectRatio="none" style={{ height }}>
        <line x1={0} x2={width} y1={y(quoted)} y2={y(quoted)} stroke="var(--ds-pass-ink)" strokeWidth="1.5" />
        <text x={4} y={y(quoted) - 6} className="ss-chart-axis" style={{ fill: "var(--ds-pass-ink)" }}>
          Quoted {quoted} days
        </text>
        {samples.map((value, index) => {
          const cx = (index / Math.max(1, samples.length - 1)) * (width - 16) + 8;
          const late = value > quoted;
          return (
            <g key={index}>
              {late && <line className="ss-late-stem" x1={cx} x2={cx} y1={y(quoted)} y2={y(value)} stroke="var(--ds-fail)" strokeWidth="1.5" style={{ "--ds-d": `${index * 60}ms` } as CSSProperties} />}
              <circle className="ss-delivery" cx={cx} cy={y(value)} r={4} fill={late ? "var(--ds-fail)" : "var(--ds-pass)"} style={{ "--ds-d": `${index * 60}ms` } as CSSProperties}>
                <title>{`${value} days${late ? `, ${value - quoted} late` : ""}`}</title>
              </circle>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* The buyers against StockSense, week by week                          */
/* ------------------------------------------------------------------ */
export function Compare({
  buyers,
  stocksense,
  height = 170,
  label,
}: {
  buyers: number[];
  stocksense: number[];
  height?: number;
  label: string;
}) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.25 });
  const clip = useId().replace(/:/g, "");
  const width = 640;
  const weeks = Math.max(buyers.length, stocksense.length, 2);
  const peak = Math.max(1, ...buyers, ...stocksense) * 1.08;
  const x = (week: number) => 4 + (week / (weeks - 1)) * (width - 12);
  const y = (value: number) => height - 8 - (value / peak) * (height - 20);
  const path = (series: number[]) => series.map((value, index) => `${x(index)},${y(value)}`).join(" ");
  const lastB = buyers[buyers.length - 1] ?? 0;
  const lastS = stocksense[stocksense.length - 1] ?? 0;
  return (
    <div ref={ref} className="ss-chart" data-shown={shown ? "" : undefined}>
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label} preserveAspectRatio="none" style={{ height }}>
        <defs>
          <clipPath id={`${clip}-c`}>
            <rect className="ss-clip" x={0} y={0} width={width} height={height} />
          </clipPath>
        </defs>
        {[0.25, 0.5, 0.75].map((share) => (
          <line key={share} x1={0} x2={width} y1={y(peak * share)} y2={y(peak * share)} stroke="var(--ds-line)" strokeWidth="1" />
        ))}
        <g clipPath={`url(#${clip}-c)`}>
          <polyline points={path(buyers)} fill="none" stroke="var(--ds-text-3)" strokeWidth="1.75" />
          <polyline points={path(stocksense)} fill="none" stroke="var(--ds-accent)" strokeWidth="2.5" />
        </g>
        <circle className="ss-end-node" cx={x(buyers.length - 1)} cy={y(lastB)} r={3.5} fill="var(--ds-text-3)" />
        <circle className="ss-end-node ss-end-live" cx={x(stocksense.length - 1)} cy={y(lastS)} r={4.5} fill="var(--ds-accent)" />
      </svg>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Two bars, the buyers and StockSense, for one measure                 */
/* ------------------------------------------------------------------ */
export function PairBars({
  label,
  buyers,
  stocksense,
  buyersText,
  stocksenseText,
  lowerIsBetter = true,
  delay = 0,
}: {
  label: string;
  buyers: number;
  stocksense: number;
  buyersText: React.ReactNode;
  stocksenseText: React.ReactNode;
  lowerIsBetter?: boolean;
  delay?: number;
}) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.3 });
  const peak = Math.max(1, buyers, stocksense);
  const better = lowerIsBetter ? stocksense < buyers : stocksense > buyers;
  const worse = lowerIsBetter ? stocksense > buyers : stocksense < buyers;
  return (
    <div ref={ref} className="ss-pair" data-shown={shown ? "" : undefined} data-verdict={better ? "better" : worse ? "worse" : "same"}>
      <span className="ss-pair-label">{label}</span>
      <span className="ss-pair-row">
        <span className="ss-pair-who ds-mono">Buyers</span>
        <span className="ss-pair-track">
          <span className="ss-pair-fill" data-who="buyers" style={{ "--w": buyers / peak, "--ds-d": `${delay}ms` } as CSSProperties} />
        </span>
        <span className="ss-pair-value ds-num">{buyersText}</span>
      </span>
      <span className="ss-pair-row">
        <span className="ss-pair-who ds-mono">StockSense</span>
        <span className="ss-pair-track">
          <span className="ss-pair-fill" data-who="stocksense" style={{ "--w": stocksense / peak, "--ds-d": `${delay + 180}ms` } as CSSProperties} />
        </span>
        <span className="ss-pair-value ds-num">{stocksenseText}</span>
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* One plan line's stock, as a bullet: have, order at, after the order  */
/* ------------------------------------------------------------------ */
export function StockBullet({
  position,
  reorderPoint,
  orderUpTo,
  quantity,
  delay = 0,
}: {
  position: number;
  reorderPoint: number;
  orderUpTo: number;
  quantity: number;
  delay?: number;
}) {
  const peak = Math.max(1, orderUpTo, reorderPoint, position + quantity) * 1.06;
  const share = (value: number) => `${(Math.max(0, value) / peak) * 100}%`;
  return (
    <span
      className="ss-bullet"
      role="img"
      aria-label={`Have ${count(position)}, order at ${count(reorderPoint)}, fill up to ${count(orderUpTo)}${quantity ? `, ordering ${count(quantity)}` : ""}`}
      style={{ "--ds-d": `${delay}ms` } as CSSProperties}
    >
      <span className="ss-bullet-zone" style={{ width: share(reorderPoint) }} />
      <span className="ss-bullet-have" style={{ width: share(position) }} />
      {quantity > 0 && <span className="ss-bullet-add" style={{ left: share(position), width: share(quantity) }} />}
      <span className="ss-bullet-mark" style={{ left: share(reorderPoint) }} />
      <span className="ss-bullet-mark" data-kind="up" style={{ left: share(orderUpTo) }} />
    </span>
  );
}
