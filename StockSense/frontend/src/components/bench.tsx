"use client";

/**
 * The bench: one instrument tile per part on this week's plan. Each tile is
 * the part's real two years of weekly sales - a bar for a week that sold, a
 * dark dot for a week that did not - with the forecast band carried on past
 * today, and its readouts underneath. The tile the live card is talking
 * about is lit.
 */

import Link from "next/link";
import type { CSSProperties } from "react";

import { StatusChip } from "@/design/StatusChip";
import { useInView } from "@/design/motion";
import { Figure } from "@/components/trace";
import { decisionTone, patternTone } from "@/components/ui";
import { count, decimal } from "@/lib/format";
import type { PartDetail, PlanLine } from "@/lib/types";

export function Bench({
  lines,
  details,
  activeId,
}: {
  lines: PlanLine[];
  details: Record<number, PartDetail>;
  activeId: number | null;
}) {
  const [ref, shown] = useInView<HTMLOListElement>({ threshold: 0.05 });
  return (
    <ol ref={ref} className="ss-bench" data-shown={shown ? "" : undefined}>
      {lines.map((line, index) => (
        <Tile key={line.id} line={line} detail={details[line.part.id]} active={line.part.id === activeId} index={index} />
      ))}
    </ol>
  );
}

function Tile({ line, detail, active, index }: { line: PlanLine; detail?: PartDetail; active: boolean; index: number }) {
  const sold = detail?.demand.sold ?? [];
  const censored = new Set(detail?.demand.prepared.censored_weeks ?? []);
  const projects = new Set(detail?.demand.prepared.project_weeks ?? []);
  const rate = detail?.demand.weekly_rate ?? Number(line.weekly_rate);
  const deviation = detail?.demand.forecast.deviation ?? 0;
  const horizon = 16;
  const weeks = Math.max(sold.length, 1);
  const step = 3;
  const width = (weeks + horizon) * step;
  const height = 64;
  const base = height - 4;
  const ordinary = sold.filter((_, week) => !projects.has(week));
  const ceiling = Math.max(1, rate + deviation, ...ordinary) * 1.1;
  const y = (value: number) => base - (Math.min(value, ceiling) / ceiling) * (base - 4);
  const today = weeks * step;
  const pattern = detail?.demand.pattern;

  return (
    <li
      className="ss-tile ds-reveal"
      data-shown=""
      data-active={active ? "" : undefined}
      style={{ "--ds-d": `${Math.min(index, 23) * 45}ms` } as CSSProperties}
    >
      <div className="ss-tile-head">
        <Link href={`/parts/${line.part.id}`} className="ss-tile-code ds-mono" title={line.part.code}>
          {line.part.code}
        </Link>
        <StatusChip size="small" tone={patternTone(line.demand_pattern)}>
          {line.demand_pattern_label}
        </StatusChip>
      </div>
      <p className="ss-tile-desc">{line.part.description}</p>
      <div className="ss-chart ss-tile-chart" data-shown="">
        {sold.length ? (
          <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={`${pattern?.periods_with_demand ?? 0} of ${weeks} weeks sold, then the forecast band`}>
            <rect x={today} y={y(rate + deviation)} width={width - today} height={Math.max(1, y(Math.max(0, rate - deviation)) - y(rate + deviation))} fill="var(--ds-accent-soft)" />
            <line x1={today} x2={width} y1={y(rate)} y2={y(rate)} stroke="var(--ds-accent)" strokeWidth="1.6" />
            <line x1={today} x2={today} y1={0} y2={base} stroke="var(--ds-text-3)" strokeWidth="0.8" />
            <line x1={0} x2={width} y1={base + 0.5} y2={base + 0.5} stroke="var(--ds-line-strong)" strokeWidth="0.8" />
            {sold.map((value, week) => {
              const kind = projects.has(week) ? "project" : censored.has(week) ? "censored" : "sold";
              if (value <= 0 && kind === "sold") {
                return <circle key={week} className="ss-zweek" cx={week * step + 1.2} cy={base - 1.5} r={0.9} style={{ "--ds-d": `${week * 5}ms` } as CSSProperties} />;
              }
              const top = kind === "censored" && value <= 0 ? base - 8 : y(value);
              return (
                <rect
                  key={week}
                  className="ss-bar"
                  data-kind={kind}
                  x={week * step}
                  y={top}
                  width={2.2}
                  height={Math.max(1.5, base - top)}
                  fill={kind === "project" ? "var(--ds-warn)" : kind === "censored" ? "var(--ds-fail)" : "var(--ds-text-2)"}
                  style={{ "--ds-d": `${week * 5}ms` } as CSSProperties}
                />
              );
            })}
          </svg>
        ) : (
          <span className="ss-tile-wait ds-mono">Reading 104 weeks…</span>
        )}
      </div>
      <dl className="ss-tile-read">
        <div>
          <dt>Sold in</dt>
          <dd className="ds-num">
            {pattern ? `${pattern.periods_with_demand}/${pattern.periods}` : "…"}
            <small> weeks</small>
          </dd>
        </div>
        <div>
          <dt>A week</dt>
          <dd className="ds-num">
            <Figure value={decimal(rate, 1)} heading={`${line.part.code}: demand a week`} trace={detail?.demand.forecast.trace ?? null} />
          </dd>
        </div>
        <div>
          <dt>Order</dt>
          <dd className="ds-num" data-tone={line.decision}>
            <Figure value={count(line.quantity)} heading={`${line.part.code}: how much to order`} trace={detail?.recommendation.trace ?? null} />
          </dd>
        </div>
      </dl>
      <div className="ss-tile-foot">
        <StatusChip size="small" tone={decisionTone(line.decision)} pulse={active}>
          {line.decision_label}
        </StatusChip>
        <span className="ds-mono">{line.demand_method_label}</span>
      </div>
    </li>
  );
}
