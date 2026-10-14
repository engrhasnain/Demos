"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { Band, Card, LinkButton, Stat } from "@/design/Surface";
import { LiveFeedCard, type FeedItem } from "@/design/LiveFeedCard";
import { Reveal } from "@/design/Reveal";
import { DemandField, type FieldPart, type FieldSupplier } from "@/components/demand-field";
import { Bench } from "@/components/bench";
import { DecisionStrip, PatternMap, ShutdownTimeline, TourRoute, type TourStop } from "@/components/desk";
import { FirstRun } from "@/components/first-run";
import { Figure } from "@/components/trace";
import { ErrorNote, Loading, SectionHead, decisionTone } from "@/components/ui";
import { api } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import {
  BASE_CURRENCY,
  count,
  countryName,
  dateLong,
  dateTime,
  days,
  money,
  percent,
  plain,
  shortSupplier,
} from "@/lib/format";
import type { Dashboard, DemoState, Page, PartDetail, PlanLine, PlanRun, Replay, Settings, Shutdown } from "@/lib/types";

export default function DeskPage() {
  const state = useLoad<DemoState>("/api/demo/state", [], { retry: true });
  const [rebuild, setRebuild] = useState(false);

  useEffect(() => {
    setRebuild(new URLSearchParams(window.location.search).get("rebuild") === "1");
  }, []);

  const finished = useCallback(() => {
    window.location.assign("/");
  }, []);

  if (state.loading && !state.data) {
    return (
      <Band top>
        <Loading what="Loading" dark />
      </Band>
    );
  }
  if (state.error) {
    return (
      <Band top>
        <div style={{ padding: "40px 0" }}>
          <ErrorNote error={state.error} onRetry={state.reload} />
        </div>
      </Band>
    );
  }
  if (!state.data) return null;
  if (!state.data.loaded || rebuild) {
    return <FirstRun mode="load" partsLoaded={state.data.parts} onFinished={finished} />;
  }
  if (!state.data.planned) {
    return <FirstRun mode="plan" partsLoaded={state.data.parts} onFinished={finished} />;
  }
  return <Desk engine={state.data.engine} />;
}

/* ------------------------------------------------------------------ */
/* Choosing what the hero draws: real lines from this week's plan       */
/* ------------------------------------------------------------------ */
const PAST_NEW_YEARS = ["2025-01-29", "2026-02-17"]; // published dates, as the server tabulates them

function daysBetween(a: string, b: string): number {
  return Math.round((new Date(`${b}T00:00:00`).getTime() - new Date(`${a}T00:00:00`).getTime()) / 86400000);
}

function shiftIso(iso: string, offset: number): string {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + offset);
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function pickField(lines: PlanLine[]): PlanLine[] {
  const bySupplier = new Map<number, PlanLine[]>();
  lines.forEach((line) => {
    const id = line.part.supplier?.id;
    if (!id) return;
    const group = bySupplier.get(id) ?? [];
    group.push(line);
    bySupplier.set(id, group);
  });
  const ranked = Array.from(bySupplier.values()).sort((a, b) => b.length - a.length);
  const chosen: PlanLine[][] = [];
  const want = (test: (group: PlanLine[]) => boolean) => {
    const group = ranked.find((candidate) => test(candidate) && !chosen.includes(candidate));
    if (group) chosen.push(group);
  };
  want((group) => group[0].part.supplier?.country === "CN");
  want((group) => !group[0].part.supplier?.lead_time.is_reliable);
  want((group) => group.some((line) => line.decision === "prebuild"));
  for (const group of ranked) {
    if (chosen.length >= 6) break;
    if (!chosen.includes(group)) chosen.push(group);
  }
  return chosen.flatMap((group) =>
    group
      .slice()
      .sort((a, b) => (a.decision === "prebuild" ? -1 : 0) - (b.decision === "prebuild" ? -1 : 0))
      .slice(0, 4),
  );
}

function Desk({ engine }: { engine: string }) {
  const dashboard = useLoad<Dashboard>("/api/dashboard");
  const plan = useLoad<PlanRun | null>("/api/plan");
  const settings = useLoad<Settings>("/api/settings");
  const replay = useLoad<Replay | null>("/api/replay");
  const run = plan.data;
  const orders = useLoad<Page<PlanLine>>(run ? `/api/plan/${run.id}/lines?decision=order&limit=160` : null, [run?.id]);
  const prebuilds = useLoad<Page<PlanLine>>(run ? `/api/plan/${run.id}/lines?decision=prebuild&limit=40` : null, [run?.id]);
  const deferred = useLoad<Page<PlanLine>>(run ? `/api/plan/${run.id}/lines?decision=deferred&limit=12` : null, [run?.id]);
  const [details, setDetails] = useState<Record<number, PartDetail>>({});

  const bought = useMemo(
    () => [...(prebuilds.data?.items ?? []), ...(orders.data?.items ?? [])],
    [orders.data, prebuilds.data],
  );
  const fieldLines = useMemo(() => pickField(bought), [bought]);

  // The real two years of sales behind each part the hero draws.
  useEffect(() => {
    let cancelled = false;
    const queue = fieldLines.map((line) => line.part.id).filter((id) => !details[id]);
    const work = async () => {
      while (queue.length && !cancelled) {
        const batch = queue.splice(0, 6);
        const results = await Promise.all(
          batch.map((id) => api.get<PartDetail>(`/api/parts/${id}`).catch(() => null)),
        );
        if (cancelled) return;
        setDetails((previous) => {
          const next = { ...previous };
          results.forEach((detail) => {
            if (detail) next[detail.id] = detail;
          });
          return next;
        });
      }
    };
    void work();
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fieldLines]);

  const shutdowns = dashboard.data?.shutdowns ?? [];
  const startsOn = Object.values(details)[0]?.history_starts_on ?? null;

  const fieldSuppliers: FieldSupplier[] = useMemo(() => {
    const seen = new Map<number, FieldSupplier>();
    fieldLines.forEach((line) => {
      const supplier = line.part.supplier;
      if (!supplier || seen.has(supplier.id)) return;
      const rule = shutdowns.find((row) => row.country === supplier.country);
      const closed: [number, number][] = [];
      if (rule && startsOn) {
        const from = daysBetween(rule.new_year, rule.closes_on);
        const to = daysBetween(rule.new_year, rule.reopens_on);
        PAST_NEW_YEARS.forEach((newYear) => {
          const a = Math.floor(daysBetween(startsOn, shiftIso(newYear, from)) / 7);
          const b = Math.floor(daysBetween(startsOn, shiftIso(newYear, to)) / 7);
          if (b >= 0) closed.push([Math.max(0, a), b]);
        });
      }
      seen.set(supplier.id, {
        id: supplier.id,
        name: shortSupplier(supplier.name),
        place: countryName(supplier.country),
        late: !supplier.lead_time.is_reliable,
        slipDays: supplier.lead_time.slippage_days,
        closed,
      });
    });
    return Array.from(seen.values());
  }, [fieldLines, shutdowns, startsOn]);

  const fieldParts: FieldPart[] = useMemo(
    () =>
      fieldLines
        .map((line) => ({
          id: line.part.id,
          code: line.part.code,
          supplierId: line.part.supplier?.id ?? 0,
          sold: details[line.part.id]?.demand.sold ?? null,
          value: Number(line.value),
          bought: line.quantity > 0,
          prebuild: line.decision === "prebuild",
          decisionWords: `${line.decision_label} · ${count(line.quantity)} units`,
          urgency: line.urgency,
        }))
        // Most good per dollar first: the engine's own rule for the cash.
        .sort((a, b) => b.urgency / Math.max(1, b.value) - a.urgency / Math.max(1, a.value)),
    [fieldLines, details],
  );

  const feedLines = useMemo(() => {
    const picks: PlanLine[] = [];
    const add = (line?: PlanLine) => {
      if (line && !picks.some((item) => item.id === line.id)) picks.push(line);
    };
    const inField = (line: PlanLine) => fieldLines.some((item) => item.id === line.id);
    const fieldOrders = fieldLines.filter((line) => line.decision === "order");
    const fieldPre = fieldLines.filter((line) => line.decision === "prebuild");
    add(fieldOrders.find((line) => line.flags.includes("had_project_orders")));
    add(fieldPre[0]);
    add(fieldOrders.find((line) => line.flags.includes("unreliable_supplier")));
    add(deferred.data?.items.find((line) => line.reason === "no_cash"));
    add(fieldOrders.find((line) => line.flags.includes("was_out_of_stock") && !picks.includes(line)));
    add(deferred.data?.items.find((line) => line.reason === "below_minimum"));
    add(fieldPre[1]);
    fieldOrders.forEach((line) => picks.length < 8 && add(line));
    return picks.slice(0, 8).map((line) => ({ line, inField: inField(line) }));
  }, [fieldLines, deferred.data]);

  const [activeIndex, setActiveIndex] = useState(0);
  const onIndex = useCallback((index: number) => setActiveIndex(index), []);
  const activeLine = feedLines[activeIndex]?.line;

  const builtIn = engine === "built-in";
  const items: FeedItem[] = feedLines.map(({ line }) => ({
    key: String(line.id),
    chip: { label: line.decision_label, tone: decisionTone(line.decision) },
    stamp: `${run ? dateTime(run.created_at) : ""} · plan ${run?.id ?? ""}`,
    title: line.part.description,
    body: (
      <>
        <span className="ss-feed-figures">
          <b>{line.quantity ? `${count(line.quantity)} units` : "Nothing bought"}</b>
          {line.quantity ? (
            <>
              {" · "}
              <b>{money(line.value)}</b> {BASE_CURRENCY}
            </>
          ) : null}
          {" · "}
          {shortSupplier(line.part.supplier?.name ?? "")}
        </span>
        <span className="ss-feed-reason">
          {line.reason_label}
          {line.shutdown_note ? ` · ${plain(line.shutdown_note)}` : ""}
        </span>
      </>
    ),
    meta: `${line.part.code} · forecast by ${line.demand_method_label.toLowerCase()} · ${
      builtIn ? "built-in engine" : "external model for words"
    }`,
    href: `/parts/${line.part.id}`,
  }));

  const data = dashboard.data;
  const cn = shutdowns.find((row) => row.country === "CN") ?? shutdowns[0];

  const tourPart =
    bought.find((line) => line.flags.includes("had_project_orders") && line.flags.includes("was_out_of_stock")) ??
    bought.find((line) => line.flags.includes("had_project_orders")) ??
    bought[0];
  const stops: TourStop[] = [
    {
      key: "desk",
      minutes: 1,
      title: "The desk",
      say: `${count(run?.parts_considered ?? 0)} parts looked at this morning, ${count(
        run?.lines_recommended ?? 0,
      )} worth buying inside the cash cap.`,
      href: "#top",
      action: "Back to the top",
    },
    {
      key: "catalogue",
      minutes: 1,
      title: "What the catalogue is like",
      say: "Four parts in five sell nothing most weeks. Each corner gets a different method.",
      href: "#patterns",
      action: "The pattern map",
    },
    {
      key: "part",
      minutes: 2,
      title: "One part, end to end",
      say: "Empty shelves are not zero demand. A project order is kept out. Never one number: always the range.",
      href: tourPart ? `/parts/${tourPart.part.id}` : "/plan",
      action: tourPart ? tourPart.part.code.split("-").slice(0, 2).join(" ") : "Open a part",
    },
    {
      key: "dead",
      minutes: 1,
      title: "The dead stock",
      say: "Nobody flagged these. The engine found them: stock on the shelf, nothing sold in six months.",
      href: "/plan?decision=watch&reason=dead_stock",
      action: "Not moving",
    },
    {
      key: "evidence",
      minutes: 2,
      title: "The evidence",
      say: "The last year replayed twice. And on the usual accuracy measure, a forecast of zero beats ours.",
      href: "/evidence",
      action: "Replay the year",
    },
    {
      key: "cash",
      minutes: 1,
      title: "The cash cap",
      say: "Not the cheapest lines held over: the ones that do least good per dollar.",
      href: "/plan?decision=deferred",
      action: "Held over",
    },
  ];

  const zero = replay.data?.accuracy?.zero_trap;

  return (
    <div id="top">
      <Band top>
        <div className="ss-hero">
          <div className="ss-hero-copy">
            <Reveal y={24}>
              <span className="ds-eyebrow">
                <span className="ds-live-dot" data-tone="accent" aria-hidden />
                StockSense <span className="ds-eyebrow-sep">·</span> Forecast lab <span className="ds-eyebrow-sep">·</span> Hengtai
              </span>
            </Reveal>
            <Reveal index={1} y={36}>
              <h1 className="ds-display ss-hero-title">
                Eighteen thousand parts. Most sell nothing.
                <br />
                <span className="ds-accent-text">Know when the numbers lie.</span>
              </h1>
            </Reveal>
            <Reveal index={2} y={30}>
              <p className="ds-band-lede" style={{ fontSize: 16.5 }}>
                StockSense forecasts every part with the method its pattern needs, sizes the cover from what suppliers
                actually deliver, plans around the Lunar New Year shutdown and fits the week&apos;s orders inside the cash
                cap. <strong style={{ color: "var(--ds-ink-text)" }}>Every number opens</strong> to show how it was
                worked out.
              </p>
            </Reveal>
            <Reveal index={3} y={28}>
              <div className="ss-actions" style={{ marginTop: 26 }}>
                <LinkButton href="/plan" tone="primary" size="large" arrow>
                  This week&apos;s orders
                </LinkButton>
                <LinkButton href="/evidence" tone="ink" size="large">
                  Replay the year
                </LinkButton>
              </div>
            </Reveal>

            <Reveal index={4} y={28}>
              <div className="ds-band-rule" style={{ marginTop: 34 }} />
              {!data || !run ? (
                <Loading what="Counting" dark />
              ) : (
                <div className="ds-stats ss-hero-stats">
                  <Stat
                    label="Parts looked at"
                    value={
                      <Figure
                        value={count(run.parts_considered)}
                        count={run.parts_considered}
                        heading="Parts the engine looked at this week"
                        explain={{
                          formula: "Every part in the catalogue goes through the engine, and every one gets a decision",
                          inputs: run.by_decision.map((row) => ({
                            label: row.label,
                            value: count(row.count),
                            source: `Plan ${run.id}, worked out ${dateTime(run.created_at)}`,
                            sourceKind: "Plan line",
                          })),
                        }}
                      />
                    }
                  />
                  <Stat
                    label="Lines to order"
                    tone="accent"
                    value={
                      <Figure
                        value={count(run.lines_recommended)}
                        count={run.lines_recommended}
                        heading="Lines bought this week"
                        explain={{
                          formula: "Lines whose decision is to order, now or before the shutdown, and that fitted in the cash",
                          inputs: run.by_reason
                            .filter((row) => row.decision === "order" || row.decision === "prebuild")
                            .map((row) => ({
                              label: row.label,
                              value: count(row.count),
                              source: `Plan ${run.id}`,
                              sourceKind: "Plan line",
                            })),
                        }}
                      />
                    }
                  />
                  <Stat
                    label={`Committed, of ${count(Number(run.cash_cap))}`}
                    value={
                      <Figure
                        value={money(run.cash_committed, 0)}
                        count={Number(run.cash_committed)}
                        heading={`Cash committed this week, in ${BASE_CURRENCY}`}
                        explain={{
                          formula: "The cost of every line bought, added by the server, taken most good per dollar first until the cap",
                          result: `${money(run.cash_committed)} ${BASE_CURRENCY}`,
                          inputs: [
                            { label: "Cash cap for the week", value: money(run.cash_cap), source: "Weekly cash cap setting", sourceKind: "Company policy" },
                            { label: "Committed", value: money(run.cash_committed), source: `${count(run.lines_recommended)} lines`, sourceKind: "This week's cash" },
                            { label: "Left unspent", value: money(run.cash_remaining), source: "Cap less committed", sourceKind: "This week's cash" },
                            ...run.by_reason
                              .filter((row) => row.decision === "deferred")
                              .map((row) => ({ label: `Held over: ${row.label.toLowerCase()}`, value: count(row.count), source: `Plan ${run.id}`, sourceKind: "Plan line" })),
                          ],
                        }}
                      />
                    }
                  />
                  {cn && (
                    <Stat
                      label={`Days to order from ${cn.label}`}
                      tone="warn"
                      value={
                        <Figure
                          value={String(cn.days_until_order_by ?? 0)}
                          count={cn.days_until_order_by ?? 0}
                          heading={`Days left to order from ${cn.label} before the new year`}
                          explain={{
                            formula: "The day these plants stop accepting orders for before the holiday, less today",
                            result: days(cn.days_until_order_by ?? 0),
                            inputs: [
                              { label: "Lunar New Year", value: dateLong(cn.new_year), source: "Published date", sourceKind: "Shutdown calendar" },
                              { label: "Last day to order", value: dateLong(cn.order_by), source: `${cn.label} rule`, sourceKind: "Shutdown calendar" },
                              { label: "Parts from there", value: count(cn.parts ?? 0), source: "Suppliers by country", sourceKind: "Supplier record" },
                            ],
                          }}
                        />
                      }
                    />
                  )}
                </div>
              )}
              <p className="ds-mono ss-hero-note">
                {run ? `From plan ${run.id}, worked out ${dateTime(run.created_at)}` : "Reading the latest plan"} ·{" "}
                {builtIn ? "built-in engine, no key" : "external model for words, numbers from code"}
              </p>
            </Reveal>
          </div>

          <div className="ss-hero-stage">
            <div className="ss-hero-canvas">
              {run && (
                <DemandField
                  suppliers={fieldSuppliers}
                  parts={fieldParts}
                  cap={Number(run.cash_cap)}
                  committed={Number(run.cash_committed)}
                  linesBought={run.lines_recommended}
                  startsOn={startsOn}
                  activeId={activeLine && feedLines[activeIndex]?.inField ? activeLine.part.id : null}
                  label={`${fieldParts.length} parts from this week's plan around ${fieldSuppliers.length} suppliers, sparking in the weeks they sold; their orders fill the cash cap to ${percent(
                    Number(run.cash_committed) / Math.max(1, Number(run.cash_cap)),
                  )}.`}
                />
              )}
            </div>
            <div className="ss-hero-feed">
              {items.length > 0 ? (
                <LiveFeedCard
                  title="Reorders in flight"
                  source="live from this week's plan"
                  items={items}
                  interval={5600}
                  onIndex={onIndex}
                />
              ) : (
                <div className="ds-feed" style={{ padding: 18 }}>
                  <span className="ds-mono-label">Reorders in flight</span>
                  <div style={{ marginTop: 14, color: "var(--ds-ink-muted)", fontSize: 13.5 }}>
                    Reading this week&apos;s plan…
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      </Band>

      <div className="ds-work">
        {dashboard.error && <ErrorNote error={dashboard.error} />}

        {fieldLines.length > 0 && (
          <section aria-labelledby="bench-heading" style={{ marginBottom: 64 }}>
            <SectionHead
              id="bench-heading"
              label={`On the bench · ${fieldLines.length} parts from plan ${run?.id ?? ""}`}
              title="Two years of sales, part by part"
              lede="A bar for every week a part sold, a dark dot for every week it did not, and after today the forecast as a band. Mostly dots: that is the catalogue. Red is an empty shelf, amber a one-off project order."
              action={
                <LinkButton href="/plan" tone="secondary" arrow>
                  Every line
                </LinkButton>
              }
            />
            <div style={{ marginTop: 22 }}>
              <Bench
                lines={fieldLines}
                details={details}
                activeId={activeLine && feedLines[activeIndex]?.inField ? activeLine.part.id : null}
              />
            </div>
          </section>
        )}

        {run && (
          <section aria-labelledby="week-heading">
            <SectionHead
              id="week-heading"
              label="This week"
              title="Where eighteen thousand decisions went"
              lede="Every part gets a decision, including the ones that cost nothing. A buyer needs to know the engine looked at all of them."
              action={
                <LinkButton href="/plan" tone="secondary" arrow>
                  Every line
                </LinkButton>
              }
            />
            <Card style={{ marginTop: 22 }}>
              <DecisionStrip plan={run} />
            </Card>
          </section>
        )}

        {run && (
          <section id="patterns" aria-labelledby="patterns-heading" style={{ marginTop: 64 }}>
            <SectionHead
              id="patterns-heading"
              label="What the catalogue is really like"
              title="Most parts sell nothing, most weeks"
              lede="Two numbers off each part's history: how long the gaps between sales are, and how much the size of a sale jumps. The published cut-offs split the catalogue into four, and each gets its own method."
            />
            <Reveal style={{ marginTop: 22 }}>
              <PatternMap plan={run} settings={settings.data} />
            </Reveal>
          </section>
        )}

        {shutdowns.length > 0 && (
          <section aria-labelledby="shutdown-heading" style={{ marginTop: 64 }}>
            <SectionHead
              id="shutdown-heading"
              label="Lunar New Year"
              title="The order you cannot place late"
              lede="An order placed after a country's cut-off does not ship late. It does not ship. The test is whether what is on the shelf on the last day to order carries the part through the shutdown."
            />
            <Card style={{ marginTop: 22 }}>
              <ShutdownTimeline shutdowns={shutdowns as Shutdown[]} />
            </Card>
          </section>
        )}

        <section aria-labelledby="honest-heading" style={{ marginTop: 64 }}>
          <Reveal>
            <div className="ss-honest">
              <div>
                <p className="ds-mono-label" style={{ margin: 0, color: "var(--ds-warn-ink)" }}>
                  The uncomfortable part
                </p>
                <h2 id="honest-heading" className="ds-title ss-honest-title">
                  {zero ? (
                    <>
                      A forecast of zero beats ours on{" "}
                      <Figure
                        value={percent(zero.share)}
                        count={Math.round(zero.share * 100)}
                        heading="Parts where a forecast of zero scores better"
                        explain={{
                          formula: "Parts where a flat zero has a lower scaled error than the real forecast ÷ parts scored",
                          result: percent(zero.share, 1),
                          inputs: [
                            { label: "Parts where zero wins", value: count(zero.parts_where_zero_wins), source: `Replay ${replay.data?.id ?? ""}`, sourceKind: "The replay" },
                            { label: "Parts scored", value: count(zero.parts_scored), source: "Parts that sold in the replayed year", sourceKind: "The replay" },
                          ],
                        }}
                      />{" "}
                      of parts.
                    </>
                  ) : (
                    "A forecast of zero beats ours on the usual measure."
                  )}
                </h2>
                <p className="ss-honest-text">
                  The usual error measure is smallest at the median, and the median of a part that sells nothing four weeks
                  in five is zero. A forecast of nothing would also empty the warehouse. That is why StockSense is graded on
                  stock-outs and money, by replaying the year, and not on accuracy.
                </p>
              </div>
              <LinkButton href="/evidence" tone="primary" arrow>
                See the evidence
              </LinkButton>
            </div>
          </Reveal>
        </section>

        <section aria-labelledby="tour-heading" style={{ marginTop: 64 }}>
          <SectionHead
            id="tour-heading"
            label="Eight minutes"
            title="Walk someone through it"
            lede="Six stops, in the order that makes the argument. Each one opens the real screen."
          />
          <div style={{ marginTop: 26 }}>
            <TourRoute stops={stops} />
          </div>
        </section>
      </div>
    </div>
  );
}
