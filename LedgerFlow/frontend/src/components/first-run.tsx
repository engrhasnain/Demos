"use client";

/**
 * The guided first run: build Hengtai, then put the morning's post through.
 *
 * Step one asks the server to generate the company (two legal entities, the
 * finance team, 140 suppliers with their bank accounts, 220 purchase orders
 * and what has been delivered against them). The company is the ringed node
 * in the middle and each kind of record lights up as a cluster round it.
 *
 * Step two puts the nineteen documents in the morning's post through the real
 * pipeline one at a time (the server's `only` parameter), so the progress is
 * the server's own: each document leaves the tray, runs round the three-way
 * match and lands in the bucket it really ended in - posted untouched,
 * waiting for a signature, held, or stopped - while the count beside each
 * bucket ticks up.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import { Band, Banner, Button } from "@/design/Surface";
import {
  Constellation,
  type ConstellationHandle,
  type ConstellationLink,
  type ConstellationNode,
  type Tone,
} from "@/design/Constellation";
import { CountUp } from "@/design/CountUp";
import { Meter } from "@/design/Meter";
import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { prefersReducedMotion } from "@/design/motion";
import { ApiError, api, readUser } from "@/lib/api";
import { money, shorten } from "@/lib/format";
import type { BatchItem, BatchResult, InvoiceBrief } from "@/lib/types";
import { ErrorNote, matchState } from "@/components/ui";
import { useBox } from "@/components/match-constellation";

type Bucket = "posted" | "approval" | "held" | "stopped";

const BUCKETS: { key: Bucket; label: string; tone: Tone; chip: "pass" | "warn" | "fail" }[] = [
  { key: "posted", label: "Posted untouched", tone: "pass", chip: "pass" },
  { key: "approval", label: "Waiting for a signature", tone: "warn", chip: "warn" },
  { key: "held", label: "Held, part or all", tone: "warn", chip: "warn" },
  { key: "stopped", label: "Stopped dead", tone: "fail", chip: "fail" },
];

function bucketOf(invoice: InvoiceBrief): Bucket {
  if (invoice.status === "posted") return "posted";
  if (invoice.status === "awaiting_approval" || invoice.status === "approved") return "approval";
  if (invoice.headline_severity === "block" || invoice.status === "rejected") return "stopped";
  return "held";
}

type Done = { item: BatchItem; invoice: InvoiceBrief; error?: string; bucket: Bucket };

/* ------------------------------------------------------------------ */
/* Step one: the company                                               */
/* ------------------------------------------------------------------ */
const COMPANY: { key: string; label: string; dots: number }[] = [
  { key: "entities", label: "Legal entities", dots: 2 },
  { key: "users", label: "Finance team", dots: 6 },
  { key: "vendors", label: "Suppliers", dots: 12 },
  { key: "bank_accounts", label: "Bank accounts on file", dots: 8 },
  { key: "purchase_orders", label: "Purchase orders", dots: 12 },
  { key: "purchase_order_lines", label: "Order lines", dots: 9 },
  { key: "goods_receipts", label: "Deliveries", dots: 10 },
  { key: "goods_receipt_lines", label: "Delivered lines", dots: 9 },
  { key: "exchange_rates", label: "Exchange rates", dots: 6 },
  { key: "accounting_periods", label: "Accounting months", dots: 6 },
];

function companyScene(lit: number, counts: Record<string, number> | null, compact: boolean) {
  const nodes: ConstellationNode[] = [
    { id: "hub", x: 0.5, y: 0.5, r: 6, tone: "accent", ring: true, lit: true, label: "Hengtai", sub: counts ? "built" : lit > 0 ? "building" : "not built", side: "below", drift: 1 },
  ];
  const links: ConstellationLink[] = [];
  COMPANY.forEach((cluster, index) => {
    const angle = -Math.PI / 2 + (index / COMPANY.length) * Math.PI * 2;
    const cx = 0.5 + Math.cos(angle) * (compact ? 0.33 : 0.36);
    const cy = 0.5 + Math.sin(angle) * (compact ? 0.38 : 0.38);
    const on = index < lit;
    const id = `c-${cluster.key}`;
    const count = counts?.[cluster.key];
    nodes.push({
      id,
      x: cx,
      y: cy,
      r: on ? 3.6 : 3,
      tone: on ? "accent" : "muted",
      lit: on,
      ring: index === lit && !counts,
      label: compact ? undefined : cluster.label,
      sub: compact ? undefined : count !== undefined ? count.toLocaleString("en-GB") : undefined,
      side: Math.cos(angle) < -0.25 ? "left" : Math.cos(angle) > 0.25 ? "right" : Math.sin(angle) < 0 ? "above" : "below",
    });
    links.push({ from: "hub", to: id, tone: on ? "accent" : "light", lit: on });
    for (let dot = 0; dot < cluster.dots; dot += 1) {
      const spread = (dot / cluster.dots) * Math.PI * 2 + index;
      const distance = 0.04 + (dot % 3) * 0.017;
      const dotId = `d-${cluster.key}-${dot}`;
      nodes.push({
        id: dotId,
        x: cx + Math.cos(spread) * distance,
        y: cy + Math.sin(spread) * distance * 1.3,
        r: 1.5,
        tone: on ? "light" : "muted",
        visible: on,
        drift: 4,
      });
      links.push({ from: id, to: dotId, tone: "accent", lit: on });
    }
    if (index > 0) links.push({ from: `c-${COMPANY[index - 1].key}`, to: id, tone: "light", lit: on && index - 1 < lit });
  });
  return { nodes, links };
}

/* ------------------------------------------------------------------ */
/* Step two: the morning's post                                        */
/* ------------------------------------------------------------------ */
function batchScene(items: BatchItem[], done: Done[], current: number, compact: boolean) {
  const nodes: ConstellationNode[] = [];
  const links: ConstellationLink[] = [];
  const tray = compact ? 0.06 : 0.07;
  const span = items.length > 1 ? 0.84 / (items.length - 1) : 0;
  const hub = {
    inv: { x: compact ? 0.32 : 0.33, y: compact ? 0.36 : 0.4 },
    ord: { x: compact ? 0.5 : 0.5, y: compact ? 0.22 : 0.26 },
    del: { x: compact ? 0.44 : 0.45, y: compact ? 0.58 : 0.6 },
  };
  const mid = { x: (hub.inv.x + hub.ord.x + hub.del.x) / 3, y: (hub.inv.y + hub.ord.y + hub.del.y) / 3 };

  items.forEach((item, index) => {
    const result = done[index];
    const tone: Tone = result ? (BUCKETS.find((b) => b.key === result.bucket)?.tone ?? "light") : index === current ? "accent" : "muted";
    nodes.push({
      id: `doc-${item.key}`,
      x: tray + (index % 2 ? 0.025 : 0),
      y: 0.08 + index * span,
      r: index === current ? 3.2 : 2.1,
      tone,
      lit: index === current || Boolean(result),
      ring: index === current,
      label: index === current && !compact ? shorten(item.title, 34) : undefined,
      side: "right",
      drift: 2,
    });
  });

  const hubLabel = (name: string) => (compact ? undefined : name);
  nodes.push({ id: "inv", ...hub.inv, r: 4.2, tone: "light", lit: current >= 0, label: hubLabel("Invoice"), side: "left", drift: 2 });
  nodes.push({ id: "ord", ...hub.ord, r: 4.2, tone: "light", lit: current >= 0, label: hubLabel("Purchase order"), side: "above", drift: 2 });
  nodes.push({ id: "del", ...hub.del, r: 4.2, tone: "light", lit: current >= 0, label: hubLabel("Delivery"), side: "below", drift: 2 });
  nodes.push({ id: "mid", ...mid, r: 3.2, tone: "accent", ring: true, lit: true, drift: 1 });
  links.push({ from: "inv", to: "ord", tone: "accent", lit: current >= 0 });
  links.push({ from: "ord", to: "del", tone: "accent", lit: current >= 0 });
  links.push({ from: "del", to: "inv", tone: "accent", lit: current >= 0 });
  ["inv", "ord", "del"].forEach((h) => links.push({ from: h, to: "mid", tone: "light" }));

  const counts: Record<Bucket, number> = { posted: 0, approval: 0, held: 0, stopped: 0 };
  done.forEach((row) => row && (counts[row.bucket] += 1));
  BUCKETS.forEach((bucket, index) => {
    const y = 0.16 + index * (compact ? 0.23 : 0.225);
    const x = compact ? 0.84 : 0.86;
    const id = `b-${bucket.key}`;
    nodes.push({
      id,
      x,
      y,
      r: 4.6,
      tone: counts[bucket.key] ? bucket.tone : "muted",
      ring: true,
      lit: counts[bucket.key] > 0,
      label: compact ? String(counts[bucket.key]) : bucket.label,
      sub: compact ? undefined : `${counts[bucket.key]} ${counts[bucket.key] === 1 ? "invoice" : "invoices"}`,
      side: compact ? "left" : "left",
      drift: 1.5,
    });
    links.push({ from: "mid", to: id, tone: bucket.tone, lit: counts[bucket.key] > 0 });
    // one satellite per invoice that landed here
    let n = 0;
    done.forEach((row, position) => {
      if (!row || row.bucket !== bucket.key) return;
      const angle = -Math.PI / 2 + n * 0.62;
      const reach = 0.045 + (n % 2) * 0.018;
      const satId = `s-${bucket.key}-${position}`;
      nodes.push({ id: satId, x: x + Math.cos(angle) * reach * 0.8, y: y + Math.sin(angle) * reach * 1.4, r: 1.7, tone: bucket.tone, drift: 3 });
      links.push({ from: id, to: satId, tone: bucket.tone, lit: true });
      n += 1;
    });
  });
  return { nodes, links, counts };
}

/* ------------------------------------------------------------------ */
export function FirstRun({
  needsCompany,
  onFinished,
}: {
  /** Step one still to do (or an administrator asked to start again). */
  needsCompany: boolean;
  onFinished: () => void;
}) {
  const user = readUser();
  const isAdministrator = user?.role === "administrator";
  const [phase, setPhase] = useState<"company" | "batch">(needsCompany ? "company" : "batch");
  const [building, setBuilding] = useState(false);
  const [built, setBuilt] = useState<{ counts: Record<string, number>; seconds: number } | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [lit, setLit] = useState(needsCompany ? 0 : COMPANY.length);
  const [items, setItems] = useState<BatchItem[]>([]);
  const [done, setDone] = useState<Done[]>([]);
  const [current, setCurrent] = useState(-1);
  const [running, setRunning] = useState(false);
  const [finished, setFinished] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [stageRef, box] = useBox(560);
  const canvas = useRef<ConstellationHandle>(null);
  const started = useRef(0);

  // What is in the tray, once the company exists.
  useEffect(() => {
    if (phase !== "batch" || items.length) return;
    api
      .get<{ total: number; items: BatchItem[] }>("/api/demo/batch")
      .then((batch) => setItems(batch.items))
      .catch((cause) => setError(cause instanceof ApiError ? cause.message : String(cause)));
  }, [phase, items.length]);

  // While the server builds the company, light the clusters in order and keep time.
  useEffect(() => {
    if (!building) return;
    started.current = performance.now();
    const tick = window.setInterval(() => setElapsed((performance.now() - started.current) / 1000), 100);
    const step = window.setInterval(() => setLit((value) => (value < COMPANY.length - 1 ? value + 1 : value)), 420);
    return () => {
      window.clearInterval(tick);
      window.clearInterval(step);
    };
  }, [building]);

  const build = async () => {
    setError(null);
    setBuilding(true);
    setLit(0);
    try {
      const result = await api.post<{ seconds: number; counts: Record<string, number> }>("/api/demo/load", { size: "full" });
      setBuilt({ counts: result.counts, seconds: result.seconds });
      setLit(COMPANY.length);
      canvas.current?.flash("hub", "accent");
      window.setTimeout(() => setPhase("batch"), prefersReducedMotion() ? 0 : 1800);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setBuilding(false);
    }
  };

  const runBatch = async () => {
    if (!items.length) return;
    setError(null);
    setRunning(true);
    const results: Done[] = [];
    const reduce = prefersReducedMotion();
    for (let index = 0; index < items.length; index += 1) {
      const item = items[index];
      setCurrent(index);
      const begun = performance.now();
      try {
        const body = await api.post<BatchResult>(`/api/demo/run-batch?only=${encodeURIComponent(item.key)}`);
        const row = body.items[0];
        const entry: Done = { item, invoice: row.invoice, error: row.error, bucket: bucketOf(row.invoice) };
        // Let the pulse run round the triangle and land before the next one leaves.
        await new Promise<void>((resolve) => {
          const blocked = entry.bucket === "stopped";
          const path = blocked ? [`doc-${item.key}`, "inv", "mid", `b-${entry.bucket}`] : [`doc-${item.key}`, "inv", "ord", "del", "mid", `b-${entry.bucket}`];
          const tone = BUCKETS.find((b) => b.key === entry.bucket)?.tone ?? "accent";
          if (reduce || !canvas.current) return resolve();
          const wait = Math.max(0, 260 - (performance.now() - begun));
          window.setTimeout(() => {
            canvas.current?.pulse(path, { duration: blocked ? 700 : 950, tone, size: 3.2, onArrive: () => resolve() });
          }, wait);
          window.setTimeout(resolve, 2600);
        });
        results[index] = entry;
        setDone([...results]);
      } catch (cause) {
        setError(cause instanceof ApiError ? cause.message : String(cause));
        setRunning(false);
        setCurrent(-1);
        return;
      }
    }
    setCurrent(-1);
    setRunning(false);
    setFinished(true);
  };

  const companyView = useMemo(() => companyScene(lit, built?.counts ?? null, box.compact), [lit, built, box.compact]);
  const batchView = useMemo(() => batchScene(items, done, current, box.compact), [items, done, current, box.compact]);
  const scene = phase === "company" ? companyView : batchView;

  const processed = done.filter(Boolean).length;
  const fraction = items.length ? processed / items.length : 0;
  const percent = Math.round(fraction * 100);
  const latest = done.filter(Boolean).slice(-4).reverse();
  const counts = batchView.counts;

  const steps = [
    {
      key: "company",
      title: "Build the company",
      detail: built
        ? `${built.counts.vendors ?? 0} suppliers, ${built.counts.purchase_orders ?? 0} purchase orders, ${built.counts.goods_receipts ?? 0} deliveries, in ${built.seconds} s`
        : phase === "batch"
          ? "Two entities, 140 suppliers, 220 purchase orders and their deliveries"
          : "Two entities, the finance team, suppliers, orders and deliveries",
      state: phase === "batch" ? "done" : building ? "active" : "active",
    },
    {
      key: "batch",
      title: "Put the morning's post through",
      detail: finished
        ? `${processed} documents read, matched and decided`
        : running
          ? `Document ${Math.min(processed + 1, items.length)} of ${items.length}`
          : `${items.length || 19} documents, each one chosen because it breaks a prototype`,
      state: finished ? "done" : phase === "batch" ? "active" : "waiting",
    },
    { key: "desk", title: "Open the desk", detail: "What stopped, why, and what reached the ledger", state: finished ? "active" : "waiting" },
  ] as const;

  return (
    <Band top>
      <div className="lf-first">
        <div className="lf-first-copy">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              First run <span className="ds-eyebrow-sep">·</span> two steps <span className="ds-eyebrow-sep">·</span> about fifteen seconds
            </span>
          </Reveal>
          <Reveal index={1} y={36}>
            <h1 className="ds-display lf-hero-title lf-first-title">
              {phase === "company" ? (
                <>
                  Build the company.
                  <br />
                  <span className="ds-accent-text">Then open its post.</span>
                </>
              ) : (
                <>
                  Nineteen invoices arrived.
                  <br />
                  <span className="ds-accent-text">Watch each one matched.</span>
                </>
              )}
            </h1>
          </Reveal>
          <Reveal index={2}>
            <p className="ds-band-lede" style={{ fontSize: 17 }}>
              {phase === "company"
                ? "One press builds Hengtai Industrial Supply from a fixed seed: two legal entities, the finance team, 140 suppliers with the bank accounts on file, 220 purchase orders and everything delivered against them."
                : "Each document goes through the real pipeline, one at a time: read by the built-in engine, checked by code, matched against its purchase order and what arrived, then posted or stopped. The buckets on the right fill with what really happened."}
            </p>
          </Reveal>

          <Reveal index={3}>
            <div className="lf-first-steps">
              <NodeChain
                stagger={60}
                live={building || running}
                fill={phase === "batch" ? (finished ? 1 : 0.5) : 0}
                items={steps.map((step, index) => ({
                  key: step.key,
                  tone: step.state === "done" ? "accent" : step.state === "active" ? "warn" : undefined,
                  state: step.state,
                  marker: step.state === "done" ? "✓" : String(index + 1).padStart(2, "0"),
                  content: (
                    <span className="lf-first-step" data-state={step.state}>
                      <b>{step.title}</b>
                      <span>{step.detail}</span>
                    </span>
                  ),
                }))}
              />
            </div>
          </Reveal>

          {error && (
            <div style={{ marginTop: 18 }}>
              <ErrorNote error={error} />
            </div>
          )}

          {phase === "company" && (
            <Reveal index={4}>
              <div className="lf-first-action">
                {isAdministrator ? (
                  <Button tone="primary" size="large" busy={building} onClick={() => void build()} arrow>
                    {building ? `Building… ${elapsed.toFixed(1)} s` : "Build the company"}
                  </Button>
                ) : (
                  <Banner tone="warn" title="An administrator builds the company">
                    Sign in as the system administrator to build it.
                  </Banner>
                )}
                {building && (
                  <p className="ds-mono lf-first-note">
                    The server is generating it now · {elapsed.toFixed(1)} s · nothing is estimated
                  </p>
                )}
              </div>
            </Reveal>
          )}

          {phase === "batch" && (
            <div className="lf-first-progress" aria-live="polite">
              <div className="lf-first-progress-head">
                <span className="ds-display lf-first-percent">
                  <CountUp to={percent} duration={600} suffix="%" />
                </span>
                <StatusChip tone={error ? "fail" : finished ? "pass" : running ? "accent" : "neutral"} surface="dark" pulse={running} size="large">
                  {error ? "Stopped" : finished ? "All done" : running ? `Document ${Math.min(processed + 1, items.length)} of ${items.length}` : "Ready"}
                </StatusChip>
              </div>
              <div style={{ marginTop: 14 }}>
                <Meter value={fraction} size="large" label={`${processed} of ${items.length} documents processed`} />
              </div>
              <p className="lf-first-current">
                {finished
                  ? `${counts.posted} posted with nobody touching them · ${counts.approval} waiting for a signature · ${counts.held + counts.stopped} need a person`
                  : running && current >= 0
                    ? items[current]?.title
                    : `${items.length || 19} documents in the tray. Read by the built-in engine, decided by code.`}
              </p>
              <div className="lf-first-action">
                {finished ? (
                  <Button tone="primary" size="large" onClick={onFinished} arrow>
                    Open the desk
                  </Button>
                ) : (
                  <Button tone="primary" size="large" busy={running} disabled={!items.length} onClick={() => void runBatch()} arrow>
                    {running ? "Putting them through" : "Put the post through"}
                  </Button>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="lf-first-stage" ref={stageRef}>
          <div className="lf-first-canvas">
            <Constellation
              ref={canvas}
              nodes={scene.nodes}
              links={scene.links}
              ambient={box.compact ? 22 : 44}
              introStagger={10}
              traffic={building ? { paths: COMPANY.map((c) => ["hub", `c-${c.key}`]), every: 380, tone: "accent" } : undefined}
              label={
                phase === "company"
                  ? `Building Hengtai: ${lit} of ${COMPANY.length} kinds of record`
                  : `${processed} of ${items.length} documents processed`
              }
            />
          </div>
          {phase === "batch" && latest.length > 0 && (
            <ol className="lf-first-ticker" aria-label="The last documents processed">
              {latest.map((row) => {
                const state = matchState(row.invoice);
                return (
                  <li key={row.item.key} className="lf-first-tick">
                    <StatusChip tone={state.tone} surface="dark" size="small">
                      {state.label}
                    </StatusChip>
                    <span className="lf-first-tick-title">{row.item.title}</span>
                    <span className="lf-first-tick-meta ds-mono">
                      {row.invoice.invoice_number || row.invoice.reference} · {money(row.invoice.total_amount)} {row.invoice.currency}
                      {row.invoice.headline ? ` · ${row.invoice.headline}` : ""}
                    </span>
                    <span className="lf-first-tick-expect">Expected: {row.item.expect}</span>
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      </div>
    </Band>
  );
}
