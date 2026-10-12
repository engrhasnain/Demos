"use client";

import { useEffect, useState, type CSSProperties } from "react";

import { Button, Card, Empty } from "@/design/Surface";
import { Meter } from "@/design/Meter";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { useInView } from "@/design/motion";
import { Compare, PairBars } from "@/components/charts";
import { Figure } from "@/components/trace";
import { ErrorNote, Key, Loading, PageBand, SectionHead } from "@/components/ui";
import { ApiError, api, readUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import { BASE_CURRENCY, count, dateTime, decimal, millions, money, percent } from "@/lib/format";
import type { Criterion, Evidence as Report, Replay } from "@/lib/types";

const REPORT_KEY = "stocksense.evidence";
const PARTS = 1200;
const WEEKS = 52;

export default function EvidencePage() {
  const user = readUser();
  const mayRun = ["senior_buyer", "purchasing_manager", "finance_director", "administrator"].includes(user?.role ?? "");
  const published = useLoad<{ criteria: Criterion[] }>("/api/evidence/criteria");
  const latest = useLoad<Replay | null>("/api/replay");
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState<null | "evaluate" | "replay">(null);
  const [error, setError] = useState<string | null>(null);
  const [fraction, setFraction] = useState(0);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(REPORT_KEY);
      if (saved) setReport(JSON.parse(saved) as Report);
    } catch {
      /* nothing saved */
    }
  }, []);

  // The server answers once per call; the bar follows the usual time.
  useEffect(() => {
    if (!busy) return;
    const started = performance.now();
    const expected = busy === "evaluate" ? Math.max(8, (latest.data?.seconds ?? 12) * 1.45) : Math.max(6, latest.data?.seconds ?? 12);
    const base = busy === "evaluate" ? 0 : 0.58;
    const share = busy === "evaluate" ? 0.58 : 0.42;
    const handle = window.setInterval(() => {
      const t = (performance.now() - started) / 1000 / expected;
      const local = t < 0.9 ? t : 0.9 + 0.08 * (1 - Math.exp(-(t - 0.9) * 2.5));
      setFraction(base + share * Math.min(0.98, local));
    }, 200);
    return () => window.clearInterval(handle);
  }, [busy, latest.data?.seconds]);

  const replayYear = async () => {
    setError(null);
    setFraction(0);
    try {
      setBusy("evaluate");
      const result = await api.post<Report>("/api/evidence/run", { parts: PARTS, weeks: WEEKS });
      setReport(result);
      try {
        window.localStorage.setItem(REPORT_KEY, JSON.stringify(result));
      } catch {
        /* storage is a convenience */
      }
      setBusy("replay");
      await api.post<Replay>("/api/replay", { parts: PARTS, weeks: WEEKS });
      latest.reload();
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setBusy(null);
    }
  };

  const replay = latest.data;
  const criteria = report?.criteria ?? null;
  const zero = (report?.accuracy ?? replay?.accuracy)?.zero_trap;

  return (
    <>
      <PageBand
        eyebrow={["Evidence", "measured, not claimed"]}
        title="Replay the year."
        accent="Both ways."
        lede={`The last ${WEEKS} weeks run twice against the same demand, the same opening stock and the same lead times: once with the orders the buyers actually placed, once with the orders StockSense would have recommended. At any week it may only see the weeks before it.`}
        actions={
          mayRun ? (
            <Button tone="primary" size="large" busy={Boolean(busy)} onClick={replayYear} arrow>
              {replay ? "Replay the year again" : "Replay the year"}
            </Button>
          ) : (
            <span style={{ fontSize: 13.5, color: "var(--ds-ink-muted)" }}>A senior buyer or above can run the replay.</span>
          )
        }
        aside={<Verdict report={report} replay={replay} busy={busy} fraction={fraction} />}
      />

      <div className="ds-work">
        {error && (
          <div style={{ marginBottom: 20 }}>
            <ErrorNote error={error} />
          </div>
        )}

        <section aria-labelledby="bars-heading">
          <SectionHead
            id="bars-heading"
            label="Acceptance criteria"
            title="Four bars, each measured"
            lede={
              report
                ? `Measured ${dateTime(report.started_at)} on ${count(report.parts)} parts over ${report.weeks} weeks, in ${decimal(report.seconds, 1)} seconds.`
                : "Replay the year to measure them. Until then, these are the bars as published."
            }
          />
          <div className="ss-criteria">
            {criteria
              ? criteria.map((row, index) => <Criterion key={row.name} row={row} index={index} />)
              : (published.data?.criteria ?? []).map((row, index) => (
                  <Reveal key={row.name} index={index} className="ss-criterion" data-state="waiting">
                    <span className="ds-mono-label">Bar · {row.bar}</span>
                    <p className="ss-criterion-q">{row.question}</p>
                    <StatusChip tone="neutral">Not measured yet</StatusChip>
                  </Reveal>
                ))}
          </div>
        </section>

        {replay && <Misses replay={replay} report={report} />}

        {replay ? (
          <>
            <section aria-labelledby="weekly-heading" style={{ marginTop: 64 }}>
              <SectionHead
                id="weekly-heading"
                label={`Replay ${replay.id ?? ""} · ${count(replay.parts)} parts`}
                title="The year, week by week"
                lede="Same demand, same opening stock, same lead times. Only the orders differ."
              />
              <div className="ss-two" style={{ marginTop: 22 }}>
                <Reveal>
                  <Card eyebrow={`Money tied up in stock, ${BASE_CURRENCY}`} title="Less stock held" action={<CompareKey />}>
                    <Compare
                      label="Stock value, week by week: the buyers against StockSense"
                      buyers={replay.weekly.map((week) => week.buyers_inventory)}
                      stocksense={replay.weekly.map((week) => week.stocksense_inventory)}
                    />
                  </Card>
                </Reveal>
                <Reveal index={1}>
                  <Card eyebrow="Parts out of stock" title="Fewer empty shelves" action={<CompareKey />}>
                    <Compare
                      label="Parts out of stock, week by week: the buyers against StockSense"
                      buyers={replay.weekly.map((week) => week.buyers_stockouts)}
                      stocksense={replay.weekly.map((week) => week.stocksense_stockouts)}
                    />
                  </Card>
                </Reveal>
              </div>
            </section>

            <section aria-labelledby="side-heading" style={{ marginTop: 64 }}>
              <SectionHead id="side-heading" label="Side by side" title="Both axes at once" lede="Fewer stock-outs and less money is a strict improvement. Either one alone can be bought by giving up the other." />
              <div className="ss-two" style={{ marginTop: 22 }}>
                <Reveal>
                  <Card title="The totals">
                    <div className="ss-pairs">
                      <PairBars label="Stock-out weeks" buyers={replay.buyers.stockout_weeks} stocksense={replay.stocksense.stockout_weeks} buyersText={count(replay.buyers.stockout_weeks)} stocksenseText={count(replay.stocksense.stockout_weeks)} />
                      <PairBars label="Parts that ran out" buyers={replay.buyers.parts_affected} stocksense={replay.stocksense.parts_affected} buyersText={count(replay.buyers.parts_affected)} stocksenseText={count(replay.stocksense.parts_affected)} delay={120} />
                      <PairBars label="Units not shipped" buyers={replay.buyers.units_short} stocksense={replay.stocksense.units_short} buyersText={count(replay.buyers.units_short)} stocksenseText={count(replay.stocksense.units_short)} delay={240} />
                      <PairBars label={`Average stock held, ${BASE_CURRENCY}`} buyers={Number(replay.buyers.average_inventory_value)} stocksense={Number(replay.stocksense.average_inventory_value)} buyersText={millions(replay.buyers.average_inventory_value)} stocksenseText={millions(replay.stocksense.average_inventory_value)} delay={360} />
                      <PairBars label="Orders placed" buyers={replay.buyers.orders_placed} stocksense={replay.stocksense.orders_placed} buyersText={count(replay.buyers.orders_placed)} stocksenseText={count(replay.stocksense.orders_placed)} delay={480} />
                    </div>
                  </Card>
                </Reveal>
                <Reveal index={1}>
                  <Card title="By how hard the part is" subtitle="Stock-out weeks, by demand pattern. The occasional patterns are the ones a spreadsheet gets wrong.">
                    <div className="ss-pairs">
                      {replay.by_pattern.map((row, index) => (
                        <PairBars
                          key={row.pattern}
                          label={`${row.label} · ${count(row.parts)} parts`}
                          buyers={row.buyers_stockout_weeks}
                          stocksense={row.stocksense_stockout_weeks}
                          buyersText={count(row.buyers_stockout_weeks)}
                          stocksenseText={count(row.stocksense_stockout_weeks)}
                          delay={index * 120}
                        />
                      ))}
                    </div>
                  </Card>
                </Reveal>
              </div>
            </section>

            {zero && <ZeroTrap zero={zero} replayId={replay.id} />}
          </>
        ) : latest.loading ? (
          <Loading what="Reading the last replay" />
        ) : (
          <div style={{ marginTop: 40 }}>
            <Empty title="No replay yet.">Press Replay the year to run the last twelve months both ways.</Empty>
          </div>
        )}
      </div>
    </>
  );
}

function CompareKey() {
  return (
    <div className="ss-legend">
      <Key colour="var(--ds-text-3)" label="The buyers" />
      <Key colour="var(--ds-accent)" label="StockSense" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* The verdict on the band                                             */
/* ------------------------------------------------------------------ */
function Verdict({
  report,
  replay,
  busy,
  fraction,
}: {
  report: Report | null;
  replay: Replay | null;
  busy: null | "evaluate" | "replay";
  fraction: number;
}) {
  const passed = report?.criteria.filter((row) => row.passed).length ?? 0;
  return (
    <div className="ss-verdict" aria-live="polite">
      {busy ? (
        <>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Replaying
          </p>
          <p className="ss-verdict-title">
            {busy === "evaluate" ? "Both ways, and checking every recommendation" : "Recording the year week by week"}
          </p>
          <div className="ss-replay-lanes" aria-hidden>
            {["The buyers", "StockSense"].map((who, lane) => (
              <div key={who} className="ss-lane" data-lane={lane}>
                <span className="ds-mono">{who}</span>
                <span className="ss-lane-track">
                  {Array.from({ length: 26 }, (_, index) => (
                    <i key={index} style={{ "--ds-d": `${index * 90 + lane * 45}ms` } as CSSProperties} />
                  ))}
                </span>
              </div>
            ))}
          </div>
          <Meter value={fraction} size="large" label={`${Math.round(fraction * 100)} per cent`} />
          <p className="ds-mono" style={{ margin: "10px 0 0", fontSize: 11.5, color: "var(--ds-ink-faint)" }}>
            The server answers when it has finished; this bar follows the usual time.
          </p>
        </>
      ) : report ? (
        <>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Last measured {dateTime(report.started_at)}
          </p>
          <p className="ss-verdict-title">
            {report.passed ? "Every bar held." : "A bar did not hold."}{" "}
            <span style={{ color: report.passed ? "var(--ds-pass)" : "var(--ds-fail)" }}>
              {passed} of {report.criteria.length}
            </span>
          </p>
          <div className="ss-verdict-dots">
            {report.criteria.map((row, index) => (
              <span key={row.name} data-tone={row.passed ? "pass" : "fail"} title={`${row.name}: ${row.passed ? "pass" : "fail"}`} style={{ "--ds-d": `${300 + index * 140}ms` } as CSSProperties} />
            ))}
          </div>
          <p style={{ margin: "14px 0 0", fontSize: 13.5, color: "var(--ds-ink-muted)" }}>{report.statement}</p>
        </>
      ) : (
        <>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            {replay ? `Replay ${replay.id ?? ""} on record` : "Nothing measured yet"}
          </p>
          <p className="ss-verdict-title">
            {replay ? `${count(replay.parts)} parts, ${replay.weeks} weeks.` : "Press replay to measure."}
          </p>
          <p style={{ margin: "10px 0 0", fontSize: 13.5, color: "var(--ds-ink-muted)" }}>
            The pass and fail of each bar comes from the acceptance run; replay the year to see it.
          </p>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* One acceptance criterion                                            */
/* ------------------------------------------------------------------ */
function Criterion({ row, index }: { row: Criterion; index: number }) {
  const value = Number(row.value);
  const against = Number(row.against);
  const isShare = row.unit === "%";
  const isCount = row.name === "occasional parts";
  const isMoney = row.unit === "TWD";
  const format = (number: number) => (isMoney ? millions(number) : isShare ? `${decimal(number, 1)}%` : count(number));
  return (
    <Reveal index={index} className="ss-criterion" data-state={row.passed ? "pass" : "fail"}>
      <div className="ss-criterion-top">
        <span className="ds-mono-label">Bar · {row.bar}</span>
        <StatusChip tone={row.passed ? "pass" : "fail"} size="large" pulse={!row.passed}>
          {row.passed ? "Pass" : "Fail"}
        </StatusChip>
      </div>
      <p className="ss-criterion-q">{row.question}</p>
      <div className="ss-criterion-figure">
        <Figure
          value={format(value)}
          count={isMoney ? undefined : value}
          decimals={isShare ? 1 : 0}
          heading={`${row.name}: measured`}
          explain={{
            formula: row.measured,
            result: format(value),
            inputs: [
              { label: "StockSense", value: isMoney ? money(value) : format(value), source: "The replay", sourceKind: "Measured" },
              { label: isCount ? "Parts replayed" : isShare ? "The bar" : "The buyers", value: isMoney ? money(against) : format(against), source: isCount || isShare ? "The run" : "Their own orders, replayed", sourceKind: "Measured" },
            ],
          }}
        />
        {!isCount && !isShare && <span className="ss-criterion-against ds-mono">against {format(against)}</span>}
      </div>
      {isShare || isCount ? (
        <Meter value={against ? value / against : 0} tone={row.passed ? "pass" : "fail"} delay={200 + index * 120} label={row.measured} />
      ) : (
        <div className="ss-pairs">
          <PairBars label="" buyers={against} stocksense={value} buyersText={format(against)} stocksenseText={format(value)} delay={200 + index * 120} />
        </div>
      )}
      <p className="ss-criterion-m">{row.measured}</p>
    </Reveal>
  );
}

/* ------------------------------------------------------------------ */
/* What it got wrong                                                    */
/* ------------------------------------------------------------------ */
function Misses({ replay, report }: { replay: Replay; report: Report | null }) {
  const worse = replay.by_pattern.filter((row) => row.stocksense_stockout_weeks > row.buyers_stockout_weeks);
  const moreOrders = replay.stocksense.orders_placed > replay.buyers.orders_placed;
  const unexplained = report?.misses ?? [];
  const bias = replay.accuracy.bias;
  return (
    <section aria-labelledby="misses-heading" style={{ marginTop: 64 }}>
      <SectionHead
        id="misses-heading"
        label="What it got wrong"
        title="The misses, said out loud"
        lede="A measured product that hides its misses is a brochure. These come from the same replay."
      />
      <div className="ss-misses">
        {worse.map((row, index) => (
          <Reveal key={row.pattern} index={index} className="ss-miss">
            <span className="ds-mono-label" style={{ color: "var(--ds-fail-ink)" }}>Worse than the buyers</span>
            <p className="ss-miss-title">
              {row.label}: {count(row.stocksense_stockout_weeks)} stock-out weeks against the buyers&apos; {count(row.buyers_stockout_weeks)}.
            </p>
            <p className="ss-miss-text">
              {row.pattern === "no_demand"
                ? `Parts with no sales in their history are not bought on a forecast, so when one does sell, the shelf is empty. The buyers keep a little of everything; on these ${count(row.parts)} parts that habit wins.`
                : `On these ${count(row.parts)} parts the buyers' own orders kept the shelf fuller than the engine's did.`}
            </p>
          </Reveal>
        ))}
        {moreOrders && (
          <Reveal index={worse.length} className="ss-miss" data-tone="warn">
            <span className="ds-mono-label" style={{ color: "var(--ds-warn-ink)" }}>A real cost</span>
            <p className="ss-miss-title">
              {count(replay.stocksense.orders_placed)} orders placed against the buyers&apos; {count(replay.buyers.orders_placed)}.
            </p>
            <p className="ss-miss-text">Smaller, more frequent orders are how it holds less stock. Each one is a purchase order somebody has to send.</p>
          </Reveal>
        )}
        {bias !== null && bias !== undefined && (
          <Reveal index={worse.length + 1} className="ss-miss" data-tone="warn">
            <span className="ds-mono-label" style={{ color: "var(--ds-warn-ink)" }}>Leans high</span>
            <p className="ss-miss-title">The forecast runs {decimal(bias, 2)} units a week above what sold, on average.</p>
            <p className="ss-miss-text">On purpose, slightly: under-forecasting an occasional part costs a stock-out, over-forecasting costs a little shelf space.</p>
          </Reveal>
        )}
        {unexplained.length > 0 ? (
          <Reveal className="ss-miss">
            <span className="ds-mono-label" style={{ color: "var(--ds-fail-ink)" }}>Recommendations that could not explain themselves</span>
            <ul className="ss-miss-list">
              {unexplained.map((miss) => (
                <li key={miss} className="ds-mono">
                  {miss}
                </li>
              ))}
            </ul>
          </Reveal>
        ) : report ? (
          <Reveal className="ss-miss" data-tone="pass">
            <span className="ds-mono-label" style={{ color: "var(--ds-pass-ink)" }}>Checked</span>
            <p className="ss-miss-title">Every recommendation named its demand model, its lead time and its cash.</p>
            <p className="ss-miss-text">{report.criteria.find((row) => row.name === "every recommendation explains itself")?.measured}</p>
          </Reveal>
        ) : null}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Why it is not graded on accuracy                                     */
/* ------------------------------------------------------------------ */
function ZeroTrap({ zero, replayId }: { zero: Replay["accuracy"]["zero_trap"]; replayId?: number }) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.2 });
  const wins = Math.round(zero.share * 100);
  const peak = Math.max(zero.zero_mase, zero.model_mase) * 1.1;
  return (
    <section aria-labelledby="zero-heading" style={{ marginTop: 64 }}>
      <div ref={ref} className="ss-zero" data-shown={shown ? "" : undefined}>
        <div className="ss-zero-copy">
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Why this is not graded on accuracy
          </p>
          <h2 id="zero-heading" className="ds-display ss-zero-title">
            A forecast of zero wins on{" "}
            <span className="ss-zero-big">
              <Figure
                value={percent(zero.share)}
                count={wins}
                heading="Parts where a forecast of zero scores better"
                explain={{
                  formula: "Parts where a flat zero has the lower scaled error ÷ parts scored",
                  result: percent(zero.share, 1),
                  inputs: [
                    { label: "Parts where zero wins", value: count(zero.parts_where_zero_wins), source: `Replay ${replayId ?? ""}`, sourceKind: "The replay" },
                    { label: "Parts scored", value: count(zero.parts_scored), source: "Parts that sold in the replayed year", sourceKind: "The replay" },
                  ],
                }}
              />
            </span>{" "}
            of parts.
          </h2>
          <p className="ds-band-lede">{zero.verdict}</p>
          <p className="ds-band-lede" style={{ marginTop: 10 }}>
            The usual error measure is smallest at the median. The median of a part that sells nothing four weeks in five is zero. So the measure rewards
            the forecast that would empty the warehouse, and the replay grades what matters instead: stock-outs and money.
          </p>
          <div className="ss-zero-bars">
            <p className="ds-mono-label" style={{ margin: "0 0 10px" }}>
              Scaled error across all {count(zero.parts_scored)} parts · lower scores better
            </p>
            {[
              { who: "A forecast of zero, every week", value: zero.zero_mase, tone: "warn" },
              { who: "StockSense", value: zero.model_mase, tone: "accent" },
            ].map((row, index) => (
              <div key={row.who} className="ss-zero-bar">
                <span>{row.who}</span>
                <span className="ss-zero-track">
                  <span data-tone={row.tone} style={{ "--w": row.value / peak, "--ds-d": `${600 + index * 200}ms` } as CSSProperties} />
                </span>
                <b className="ds-num">{decimal(row.value, 3)}</b>
              </div>
            ))}
          </div>
        </div>
        <div className="ss-waffle-wrap">
          <div className="ss-waffle" role="img" aria-label={`${wins} of every 100 parts: a forecast of zero scores better on the usual measure`}>
            {Array.from({ length: 100 }, (_, index) => (
              <i key={index} data-zero={index < wins ? "" : undefined} style={{ "--ds-d": `${index * 22}ms` } as CSSProperties} />
            ))}
          </div>
          <div className="ss-waffle-key">
            <span>
              <i data-zero="" /> zero scores better · {count(zero.parts_where_zero_wins)} parts
            </span>
            <span>
              <i /> StockSense scores better · {count(zero.parts_scored - zero.parts_where_zero_wins)} parts
            </span>
          </div>
        </div>
      </div>
    </section>
  );
}
