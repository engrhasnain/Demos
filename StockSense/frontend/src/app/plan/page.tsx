"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { Button, Card, Empty } from "@/design/Surface";
import { Meter } from "@/design/Meter";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Tabs } from "@/design/Tabs";
import { useInView } from "@/design/motion";
import { StockBullet } from "@/components/charts";
import { Figure } from "@/components/trace";
import { ErrorNote, Loading, PageBand, decisionTone, patternTone, reasonTone } from "@/components/ui";
import { ApiError, api, readUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import {
  BASE_CURRENCY,
  count,
  countryName,
  cover,
  dateTime,
  flagWords,
  millions,
  money,
  percent,
  plain,
  shortSupplier,
} from "@/lib/format";
import type { Page, PlanLine, PlanRun, Trace } from "@/lib/types";

const TABS = [
  { key: "", label: "Every line" },
  { key: "order", label: "To order" },
  { key: "prebuild", label: "Before the shutdown" },
  { key: "deferred", label: "Not this week" },
  { key: "watch", label: "Watch" },
] as const;

const PAGE = 30;

export default function PlanPage() {
  return (
    <Suspense fallback={<Loading what="Loading" />}>
      <Plan />
    </Suspense>
  );
}

function allocationKey(id: number) {
  return `stocksense.allocation.${id}`;
}

function Plan() {
  const parameters = useSearchParams();
  const [decision, setDecision] = useState(parameters.get("decision") ?? "");
  const [reason, setReason] = useState(parameters.get("reason") ?? "");
  const [pattern, setPattern] = useState(parameters.get("pattern") ?? "");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  const latest = useLoad<PlanRun | null>("/api/plan");
  const run = latest.data;

  const query = [
    decision && `decision=${decision}`,
    reason && `reason=${reason}`,
    pattern && `pattern=${pattern}`,
    search && `search=${encodeURIComponent(search)}`,
  ]
    .filter(Boolean)
    .join("&");

  const lines = useLoad<Page<PlanLine>>(
    run ? `/api/plan/${run.id}/lines?limit=${PAGE}&offset=${offset}${query ? `&${query}` : ""}` : null,
    [run?.id],
  );

  useEffect(() => {
    const next = new URLSearchParams();
    if (decision) next.set("decision", decision);
    if (reason) next.set("reason", reason);
    if (pattern) next.set("pattern", pattern);
    const text = next.toString();
    window.history.replaceState(null, "", text ? `/plan?${text}` : "/plan");
  }, [decision, reason, pattern]);

  if (latest.loading && !run) return <PageBandLoading />;
  if (!run) {
    return (
      <>
        <PageBand eyebrow={["To order"]} title="No plan yet." lede="Work out this week from the desk first." />
        <div className="ds-work">
          <Empty title="Nothing has been worked out yet.">
            <Link href="/">Go to the desk</Link>
          </Empty>
        </div>
      </>
    );
  }

  const counts = new Map(run.by_decision.map((row) => [row.decision, row.count]));
  const reasons = run.by_reason.filter((row) => !decision || row.decision === decision);
  const patternLabel = run.by_pattern.find((row) => row.pattern === pattern)?.label;

  return (
    <>
      <PageBand
        eyebrow={["To order", `Plan ${run.id}`, `worked out ${dateTime(run.created_at)}`]}
        title="This week's orders,"
        accent="inside the cash cap."
        lede="Every part got a decision. The ones that cost money were taken most good per dollar first until the cash ran out, and any supplier whose lines missed its minimum was dropped whole. Press any figure to see how it was reached."
        aside={<CashCap run={run} onReplanned={() => window.location.reload()} />}
      />

      <div className="ds-work">
        <Reveal>
          <Tabs
            label="Which lines"
            value={decision as (typeof TABS)[number]["key"]}
            onChange={(key) => {
              setDecision(key);
              setReason("");
              setOffset(0);
            }}
            tabs={TABS.map((tab) => ({
              key: tab.key,
              label: tab.label,
              badge: tab.key ? counts.get(tab.key) ?? 0 : run.parts_considered,
            }))}
          />
        </Reveal>

        <Reveal index={1}>
          <div className="ss-filters">
            <div className="ss-reason-chips" role="group" aria-label="Why">
              {reasons.map((row) => (
                <button
                  key={`${row.decision}-${row.reason}`}
                  type="button"
                  className="ss-reason-chip"
                  aria-pressed={reason === row.reason}
                  onClick={() => {
                    setDecision(row.decision);
                    setReason(reason === row.reason ? "" : row.reason);
                    setOffset(0);
                  }}
                >
                  <span className="ss-reason-dot" style={{ background: `var(--ds-${toneVar(reasonTone(row.reason))})` }} aria-hidden />
                  {row.label}
                  <b className="ds-num">{count(row.count)}</b>
                </button>
              ))}
              {pattern && (
                <button type="button" className="ss-reason-chip" aria-pressed onClick={() => setPattern("")}>
                  Pattern: {patternLabel ?? pattern} <b aria-hidden>×</b>
                </button>
              )}
            </div>
            <label className="ss-search">
              <span className="ds-sr-only">Search by part number</span>
              <input
                className="ds-input"
                value={search}
                onChange={(event) => {
                  setSearch(event.target.value);
                  setOffset(0);
                }}
                placeholder="Search by part number"
              />
            </label>
          </div>
        </Reveal>

        {lines.error && <ErrorNote error={lines.error} />}

        <Card
          flush
          style={{ marginTop: 18 }}
          eyebrow={lines.data ? `${count(lines.data.total)} lines · most urgent first` : "Lines"}
          title={TABS.find((tab) => tab.key === decision)?.label ?? "Lines"}
        >
          {lines.loading && !lines.data ? (
            <div style={{ padding: 20 }}>
              <Loading what="Reading the plan" />
            </div>
          ) : !lines.data || lines.data.items.length === 0 ? (
            <div style={{ padding: 20 }}>
              <Empty title="No lines match." />
            </div>
          ) : (
            <>
              <div className="ss-line ss-line-head" aria-hidden>
                <span>Part</span>
                <span>Demand</span>
                <span>Stock: have, order at, fill up to</span>
                <span>Lasts</span>
                <span style={{ textAlign: "right" }}>Order</span>
                <span>Why</span>
              </div>
              <ol className="ss-lines" data-loading={lines.loading ? "" : undefined}>
                {lines.data.items.map((line, index) => (
                  <LineRow key={line.id} line={line} runId={run.id} index={index} />
                ))}
              </ol>
            </>
          )}
        </Card>

        {lines.data && lines.data.total > lines.data.limit && (
          <div className="ss-pager">
            <span className="ds-mono">
              {count(offset + 1)} to {count(Math.min(offset + lines.data.limit, lines.data.total))} of {count(lines.data.total)}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <Button size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                Back
              </Button>
              <Button size="small" disabled={offset + PAGE >= lines.data.total} onClick={() => setOffset(offset + PAGE)}>
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}

function toneVar(tone: string) {
  return tone === "neutral" ? "line-strong" : tone;
}

function PageBandLoading() {
  return <PageBand eyebrow={["To order"]} title="Reading the plan…" />;
}

/* ------------------------------------------------------------------ */
/* One line of the plan                                                */
/* ------------------------------------------------------------------ */
function LineRow({ line, runId, index }: { line: PlanLine; runId: number; index: number }) {
  const load = () => api.get<PlanLine>(`/api/plan/${runId}/lines/${line.id}`).then((full) => full.trace ?? null);
  const supplier = line.part.supplier;
  const short = line.days_of_cover < 14;
  return (
    <li className="ss-line ds-reveal" data-shown="" style={{ "--ds-d": `${Math.min(index, 14) * 45}ms`, "--row-tone": `var(--ds-${toneVar(decisionTone(line.decision))})` } as CSSProperties}>
      <div className="ss-line-part">
        <Link href={`/parts/${line.part.id}`} className="ss-line-code">
          <span className="ds-stamp">{line.part.code}</span>
        </Link>
        <span className="ss-line-desc">{line.part.description}</span>
        <span className="ss-line-supplier ds-mono">
          {supplier ? `${shortSupplier(supplier.name)} · ${countryName(supplier.country)}` : ""}
        </span>
        {line.flags.length > 0 && (
          <span className="ss-line-flags">
            {line.flags.map((flag) => (
              <StatusChip key={flag} size="small" tone={flag === "dead_stock" || flag === "unreliable_supplier" || flag === "shutdown_ahead" ? "warn" : "neutral"}>
                {flagWords(flag)}
              </StatusChip>
            ))}
          </span>
        )}
      </div>
      <div className="ss-line-demand">
        <StatusChip size="small" tone={patternTone(line.demand_pattern)}>
          {line.demand_pattern_label}
        </StatusChip>
        <span className="ds-mono">{line.demand_method_label}</span>
        <span className="ds-mono ss-line-rate">
          <Figure value={`${money(line.weekly_rate, 1)} a week`} heading={`${line.part.code}: demand a week`} load={load} />
        </span>
      </div>
      <div className="ss-line-stock">
        <StockBullet
          position={Number(line.position)}
          reorderPoint={Number(line.reorder_point)}
          orderUpTo={Number(line.order_up_to)}
          quantity={line.quantity}
          delay={Math.min(index, 14) * 45 + 200}
        />
        <span className="ds-mono ss-line-stock-text">
          have {count(Number(line.position))} · at {count(Number(line.reorder_point))} · up to {count(Number(line.order_up_to))}
        </span>
      </div>
      <div className="ss-line-cover" data-short={short ? "" : undefined}>
        {cover(line.days_of_cover)}
      </div>
      <div className="ss-line-order">
        {line.quantity > 0 ? (
          <>
            <span className="ss-line-qty">
              <Figure value={count(line.quantity)} heading={`${line.part.code}: how much to order`} load={load} />
            </span>
            <span className="ss-line-cost ds-mono">
              <Figure value={money(line.value)} heading={`${line.part.code}: what the order costs, in ${BASE_CURRENCY}`} load={load} />
            </span>
          </>
        ) : (
          <span className="ss-line-none">
            <Figure value="Nothing" heading={`${line.part.code}: why nothing is bought`} load={load} />
          </span>
        )}
      </div>
      <div className="ss-line-why">
        <StatusChip tone={reasonTone(line.reason)} pulse={line.decision === "prebuild"}>
          {line.reason_label}
        </StatusChip>
        {line.shutdown_note && <span className="ss-line-note">{plain(line.shutdown_note)}</span>}
      </div>
    </li>
  );
}

/* ------------------------------------------------------------------ */
/* The cash cap: the budget filling, line by line                       */
/* ------------------------------------------------------------------ */
function CashCap({ run, onReplanned }: { run: PlanRun; onReplanned: () => void }) {
  const orders = useLoad<Page<PlanLine>>(`/api/plan/${run.id}/lines?decision=order&limit=200`, [run.id]);
  const prebuilds = useLoad<Page<PlanLine>>(`/api/plan/${run.id}/lines?decision=prebuild&limit=100`, [run.id]);
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.2 });
  const [trace, setTrace] = useState<Trace | null>(null);
  const user = readUser();
  const mayPlan = Boolean(user && user.role !== "viewer");
  const cap = Math.max(1, Number(run.cash_cap));
  const committed = Number(run.cash_committed);

  useEffect(() => {
    try {
      const saved = window.sessionStorage.getItem(allocationKey(run.id));
      if (saved) setTrace(JSON.parse(saved) as Trace);
    } catch {
      /* nothing saved */
    }
  }, [run.id]);

  // Most good per dollar first: the order the engine spent the money in.
  const segments = useMemo(() => {
    const lines = [...(prebuilds.data?.items ?? []), ...(orders.data?.items ?? [])]
      .filter((line) => Number(line.value) > 0)
      .sort((a, b) => b.urgency / Number(b.value) - a.urgency / Number(a.value));
    let left = 0;
    return lines.map((line) => {
      const width = Number(line.value) / cap;
      const segment = { line, left, width };
      left += width;
      return segment;
    });
  }, [orders.data, prebuilds.data, cap]);
  const shownValue = segments.reduce((total, segment) => total + segment.width, 0);
  const restCount = Math.max(0, run.lines_recommended - segments.length);
  const deferred = run.by_reason.filter((row) => row.decision === "deferred");

  return (
    <div className="ss-cap" ref={ref} data-shown={shown ? "" : undefined}>
      <div className="ss-cap-head">
        <span className="ds-mono-label">Cash cap · {BASE_CURRENCY}</span>
        <StatusChip tone="accent" surface="dark" pulse>
          {percent(committed / cap, 1)} spent
        </StatusChip>
      </div>
      <p className="ss-cap-figure">
        <Figure
          value={money(run.cash_committed)}
          count={committed}
          decimals={2}
          heading={`Committed this week, in ${BASE_CURRENCY}`}
          trace={trace}
          explain={{
            formula: "Each line's cost, taken most good per dollar first, until the next line would pass the cap; suppliers under their minimum dropped whole",
            result: money(run.cash_committed),
            inputs: [
              { label: "Cash cap", value: money(run.cash_cap), source: "Weekly cash cap", sourceKind: "Company policy" },
              { label: "Lines bought", value: count(run.lines_recommended), source: `Plan ${run.id}`, sourceKind: "Plan line" },
              ...deferred.map((row) => ({ label: `Held over: ${row.label.toLowerCase()}`, value: count(row.count), source: `Plan ${run.id}`, sourceKind: "Plan line" })),
              { label: "Left unspent", value: money(run.cash_remaining), source: "Cap less committed", sourceKind: "This week's cash" },
            ],
          }}
        />
      </p>
      <p className="ss-cap-of ds-mono">of {money(run.cash_cap)} · {money(run.cash_remaining)} left unspent</p>

      <div className="ss-cap-bar" role="img" aria-label={`${percent(committed / cap, 1)} of the cash cap committed by ${count(run.lines_recommended)} lines`}>
        {segments.map((segment, index) => (
          <span
            key={segment.line.id}
            className="ss-cap-seg"
            data-kind={segment.line.decision}
            title={`${segment.line.part.code}: ${money(segment.line.value)}`}
            style={{ left: `${segment.left * 100}%`, width: `${segment.width * 100}%`, "--ds-d": `${300 + index * 7}ms` } as CSSProperties}
          />
        ))}
        {restCount > 0 && (
          <span
            className="ss-cap-seg"
            data-kind="rest"
            style={{ left: `${shownValue * 100}%`, width: `${Math.max(0, committed / cap - shownValue) * 100}%`, "--ds-d": `${300 + segments.length * 7 + 120}ms` } as CSSProperties}
          />
        )}
        <span className="ss-cap-mark" aria-hidden />
      </div>
      <div className="ss-cap-key ds-mono">
        <span>
          <i style={{ background: "var(--ds-accent)" }} /> {count(segments.filter((segment) => segment.line.decision === "order").length)} most urgent orders, one block each
        </span>
        <span>
          <i style={{ background: "var(--ds-warn)" }} /> before the shutdown
        </span>
        {restCount > 0 && (
          <span>
            <i style={{ background: "var(--ds-accent-line)" }} /> the other {count(restCount)} lines
          </span>
        )}
      </div>

      <div className="ss-cap-held">
        {deferred.map((row) => (
          <Link key={row.reason} href={`/plan?decision=deferred&reason=${row.reason}`} className="ss-cap-held-item">
            <span className="ds-mono-label">Held over</span>
            <b className="ds-num">{count(row.count)}</b>
            <span>{row.label}</span>
          </Link>
        ))}
      </div>

      <Replan run={run} enabled={mayPlan} onDone={onReplanned} />
    </div>
  );
}

const PRESETS = [3_000_000, 6_000_000, 12_000_000];

function Replan({ run, enabled, onDone }: { run: PlanRun; enabled: boolean; onDone: () => void }) {
  const [value, setValue] = useState(String(Math.round(Number(run.cash_cap))));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fraction, setFraction] = useState(0);
  const started = useRef(0);

  useEffect(() => {
    if (!busy) return;
    started.current = performance.now();
    const expected = Math.max(3, run.seconds || 30);
    const handle = window.setInterval(() => {
      const t = (performance.now() - started.current) / 1000 / expected;
      setFraction(Math.min(0.97, t < 0.9 ? t : 0.9 + 0.07 * (1 - Math.exp(-(t - 0.9) * 2.5))));
    }, 200);
    return () => window.clearInterval(handle);
  }, [busy, run.seconds]);

  const go = async () => {
    const cap = Number(value.replace(/[^0-9.]/g, ""));
    if (!Number.isFinite(cap) || cap <= 0) {
      setError("Type a cash cap above zero.");
      return;
    }
    setError(null);
    setBusy(true);
    try {
      const result = await api.post<PlanRun>("/api/plan", { cash_cap: cap });
      try {
        if (result.allocation?.trace) {
          window.sessionStorage.setItem(allocationKey(result.id), JSON.stringify(result.allocation.trace));
        }
      } catch {
        /* storage is a convenience */
      }
      setFraction(1);
      onDone();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
      setBusy(false);
    }
  };

  return (
    <div className="ss-replan">
      <p className="ds-mono-label" style={{ margin: 0 }}>
        Try a different cash cap
      </p>
      <div className="ss-replan-row">
        <label style={{ flex: "1 1 160px" }}>
          <span className="ds-sr-only">Cash cap in {BASE_CURRENCY}</span>
          <input
            className="ds-input ss-replan-input"
            data-mono=""
            inputMode="numeric"
            value={value}
            onChange={(event) => setValue(event.target.value)}
            disabled={busy || !enabled}
          />
        </label>
        <Button tone="primary" onClick={go} busy={busy} disabled={!enabled}>
          Work it out again
        </Button>
      </div>
      <div className="ss-replan-presets">
        {PRESETS.map((preset) => (
          <button key={preset} type="button" className="ss-preset" disabled={busy || !enabled} aria-pressed={Number(value) === preset} onClick={() => setValue(String(preset))}>
            {millions(preset, 0)}
          </button>
        ))}
      </div>
      {busy && (
        <div style={{ marginTop: 12 }} aria-live="polite">
          <Meter value={fraction} size="small" label={`Working out the week, ${Math.round(fraction * 100)} per cent`} />
          <p className="ds-mono" style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--ds-ink-muted)" }}>
            Looking at {count(run.parts_considered)} parts. Last time this took {Math.round(run.seconds)} seconds.
          </p>
        </div>
      )}
      {!enabled && (
        <p style={{ margin: "8px 0 0", fontSize: 12.5, color: "var(--ds-ink-muted)" }}>A buyer can work out the week again.</p>
      )}
      {error && <p style={{ margin: "8px 0 0", fontSize: 13, color: "var(--ds-fail)" }}>{error}</p>}
    </div>
  );
}
