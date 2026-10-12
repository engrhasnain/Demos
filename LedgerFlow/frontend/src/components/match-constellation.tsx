"use client";

/**
 * The three-way match constellation: LedgerFlow's signature.
 *
 * Built from one real invoice. The invoice, its purchase order and its
 * delivery are three clusters of nodes: a hub each, and one satellite per
 * line. A pulse carries every invoice line to its order line (the price
 * check) and on to what arrived (the quantity check). When all three agree a
 * pulse runs round the triangle and it closes; then the approvals route as a
 * chain of nodes, and a pulse travels to the ledger as the bill is written.
 * A corner that disagrees glows coral and the pulse stops there, with the
 * reason beside it.
 *
 * Under reduced motion the finished state is drawn once, without pulses.
 */

import { useEffect, useMemo, useRef, useState } from "react";

import {
  Constellation,
  type ConstellationHandle,
  type ConstellationLink,
  type ConstellationNode,
  type Tone,
} from "@/design/Constellation";
import { prefersReducedMotion } from "@/design/motion";
import { money, shorten } from "@/lib/format";
import type { ApprovalRow, InvoiceDetail, InvoiceLine } from "@/lib/types";

export type Verdict = {
  kind: "matched" | "held" | "stopped" | "credit";
  tone: Tone;
  word: string;
  reason: string;
};

type LineOutcome = { price: Tone; delivery: Tone; ordered: boolean };

function lineOutcome(line: InvoiceLine): LineOutcome {
  const held = line.held_amount && Number(line.held_amount) > 0;
  switch (line.match_result) {
    case "over_tolerance":
      return { price: "fail", delivery: "accent", ordered: true };
    case "not_received":
      return { price: "accent", delivery: "fail", ordered: true };
    case "partly_received":
      return { price: "accent", delivery: "warn", ordered: true };
    case "not_ordered":
      return { price: held ? "fail" : "light", delivery: held ? "fail" : "light", ordered: false };
    case "matched":
      return { price: "accent", delivery: "accent", ordered: true };
    default:
      return { price: "light", delivery: "light", ordered: Boolean(line.order_line_id) };
  }
}

export function verdictOf(detail: InvoiceDetail): Verdict {
  const open = detail.exceptions.filter((row) => !row.resolved_at);
  const block = open.find((row) => row.severity === "block");
  const hold = open.find((row) => row.severity === "hold");
  if (block) return { kind: "stopped", tone: "fail", word: "Stopped", reason: block.label };
  if (detail.kind === "credit_note")
    return { kind: "credit", tone: "light", word: "Credit note", reason: "Not matched: applied as a credit" };
  if (hold) return { kind: "held", tone: "warn", word: "Held", reason: hold.label };
  return { kind: "matched", tone: "accent", word: "Matched", reason: "All three agree" };
}

/** Which corner of the triangle a problem belongs to. */
function brokenCorner(detail: InvoiceDetail, verdict: Verdict): "invoice" | "order" | "delivery" | null {
  if (verdict.kind === "matched" || verdict.kind === "credit") return null;
  const open = detail.exceptions.filter((row) => !row.resolved_at);
  const first = open.find((row) => row.severity === (verdict.kind === "stopped" ? "block" : "hold")) ?? open[0];
  if (!first) return null;
  if (["over_tolerance", "no_purchase_order"].includes(first.kind)) return "order";
  if (["not_received", "partly_received"].includes(first.kind)) return "delivery";
  return "invoice";
}

function approvalTone(row: ApprovalRow): Tone {
  if (row.status === "approved") return "pass";
  if (row.status === "rejected") return "fail";
  return "warn";
}

function approvalWords(row: ApprovalRow): string {
  if (row.status === "approved") return `Signed${row.decided_by ? `: ${row.decided_by.name}` : ""}`;
  if (row.status === "rejected") return "Refused";
  return `Waiting: ${row.required_role_label}`;
}

export type Stage = 0 | 1 | 2 | 3 | 4 | 5 | 6;

/** The approvals that are part of the route (not withdrawn or replaced). */
export function liveApprovals(detail: InvoiceDetail): ApprovalRow[] {
  return detail.approvals.filter((row) => ["pending", "approved", "rejected"].includes(row.status)).slice(0, 3);
}

type Point = { x: number; y: number };

function layout(compact: boolean) {
  if (compact) {
    return {
      doc: { x: 0.05, y: 0.12 },
      invoice: { x: 0.2, y: 0.26 },
      order: { x: 0.74, y: 0.2 },
      delivery: { x: 0.46, y: 0.6 },
      ledger: { x: 0.84, y: 0.86 },
      approvalStart: { x: 0.6, y: 0.72 },
      approvalStep: { x: 0.08, y: 0.05 },
      spread: 0.085,
    };
  }
  return {
    doc: { x: 0.04, y: 0.13 },
    invoice: { x: 0.19, y: 0.3 },
    order: { x: 0.55, y: 0.15 },
    delivery: { x: 0.37, y: 0.7 },
    ledger: { x: 0.89, y: 0.5 },
    approvalStart: { x: 0.66, y: 0.64 },
    approvalStep: { x: 0.08, y: -0.05 },
    spread: 0.075,
  };
}

/** Satellites fan out on the side of a hub away from the triangle's centre. */
function satellites(hub: Point, centre: Point, count: number, distance: number, aspect: number): Point[] {
  const away = Math.atan2((hub.y - centre.y) / aspect, hub.x - centre.x);
  const spread = Math.min(Math.PI * 0.95, 0.42 * Math.max(1, count - 1) + 0.2);
  return Array.from({ length: count }, (_, index) => {
    const angle = count === 1 ? away : away - spread / 2 + (spread * index) / (count - 1);
    const reach = distance * (index % 2 ? 1.18 : 1);
    return {
      x: hub.x + Math.cos(angle) * reach,
      y: hub.y + Math.sin(angle) * reach * aspect,
    };
  });
}

export function MatchConstellation({
  detail,
  stage,
  compact,
  aspect = 1.4,
  className = "",
  ambient,
  labels = true,
}: {
  detail: InvoiceDetail | null;
  /** 0 nothing · 1 invoice · 2 order · 3 delivery · 4 verdict · 5 approvals · 6 ledger */
  stage: Stage;
  compact: boolean;
  /** Width over height of the canvas box, so the clusters stay round. */
  aspect?: number;
  className?: string;
  ambient?: number;
  labels?: boolean;
}) {
  const canvas = useRef<ConstellationHandle>(null);
  const key = detail ? `i${detail.id}` : "none";

  const facts = useMemo(() => {
    if (!detail) return null;
    const lines = detail.lines.slice().sort((a, b) => a.line_number - b.line_number);
    const shown = lines.slice(0, compact ? 3 : 5);
    const verdict = verdictOf(detail);
    const corner = brokenCorner(detail, verdict);
    const approvals = liveApprovals(detail);
    const bill = detail.postings.find((row) => row.status === "posted");
    const dropped = detail.postings.find((row) => row.status === "failed");
    const posted = detail.status === "posted";
    const arrived = lines.filter((line) => !["not_received"].includes(line.match_result) && line.order_line_id).length;
    const ordered = lines.filter((line) => line.order_line_id).length;
    return { lines, shown, verdict, corner, approvals, bill, dropped, posted, arrived, ordered };
  }, [detail, compact]);

  const { nodes, links, paths } = useMemo(() => {
    const out = {
      nodes: [] as ConstellationNode[],
      links: [] as ConstellationLink[],
      paths: { approval: [] as string[], toLedger: [] as string[] },
    };
    if (!detail || !facts) return out;
    const L = layout(compact);
    const id = (name: string) => `${key}-${name}`;
    const centre = {
      x: (L.invoice.x + L.order.x + L.delivery.x) / 3,
      y: (L.invoice.y + L.order.y + L.delivery.y) / 3,
    };
    const { verdict, corner, shown, approvals } = facts;
    const credit = verdict.kind === "credit";
    const hasOrder = Boolean(detail.purchase_order) && !credit;
    const cornerTone = (name: "invoice" | "order" | "delivery"): Tone =>
      corner === name && stage >= (name === "invoice" ? 1 : name === "order" ? 2 : 3) ? verdict.tone : "light";

    // ------------------------------------------------ the arrival point
    out.nodes.push({ id: id("doc"), x: L.doc.x, y: L.doc.y, r: 1.8, tone: "muted", visible: stage >= 1, drift: 2 });
    out.links.push({ from: id("doc"), to: id("inv"), tone: "light", lit: stage === 1 });

    // ------------------------------------------------ the three hubs
    const invoiceTone: Tone = corner === "invoice" && stage >= 2 ? verdict.tone : stage >= 1 ? "light" : "muted";
    out.nodes.push({
      id: id("inv"),
      x: L.invoice.x,
      y: L.invoice.y,
      r: 4.4,
      tone: invoiceTone,
      ring: corner === "invoice" && stage >= 2,
      lit: stage >= 1,
      label: labels ? (credit ? "Credit note" : "Invoice") : undefined,
      sub: labels ? `${money(detail.total_amount)} ${detail.currency}` : undefined,
      side: "above",
      visible: stage >= 1,
      drift: 2,
    });
    out.nodes.push({
      id: id("ord"),
      x: L.order.x,
      y: L.order.y,
      r: 4.4,
      tone: !hasOrder ? (stage >= 2 ? (credit ? "muted" : "fail") : "muted") : cornerTone("order") === "light" ? "light" : cornerTone("order"),
      ring: corner === "order" && stage >= 2,
      lit: stage >= 2 && hasOrder,
      label: labels ? "Purchase order" : undefined,
      sub: labels
        ? hasOrder
          ? detail.purchase_order!.number
          : credit
            ? "Not needed"
            : "None found"
        : undefined,
      side: compact ? "below" : "above",
      visible: stage >= 2,
      drift: 2,
    });
    const deliveryWords = !hasOrder
      ? "Nothing to match"
      : facts.arrived === facts.ordered
        ? "Everything arrived"
        : facts.arrived === 0
          ? "Nothing arrived yet"
          : `${facts.arrived} of ${facts.ordered} lines arrived`;
    out.nodes.push({
      id: id("del"),
      x: L.delivery.x,
      y: L.delivery.y,
      r: 4.4,
      tone: !hasOrder ? "muted" : cornerTone("delivery"),
      ring: corner === "delivery" && stage >= 3,
      lit: stage >= 3 && hasOrder,
      label: labels ? "Delivery" : undefined,
      sub: labels ? deliveryWords : undefined,
      side: "below",
      visible: stage >= 3,
      drift: 2,
    });

    // ------------------------------------------------ one satellite per line
    const aspectRatio = aspect;
    const invPoints = satellites(L.invoice, centre, shown.length, L.spread, aspectRatio);
    const ordPoints = satellites(L.order, centre, shown.length, L.spread, aspectRatio);
    const delPoints = satellites(L.delivery, centre, shown.length, L.spread, aspectRatio);
    shown.forEach((line, index) => {
      const outcome = lineOutcome(line);
      const il = id(`il${line.line_number}`);
      const ol = id(`ol${line.line_number}`);
      const dl = id(`dl${line.line_number}`);
      out.nodes.push({ id: il, ...invPoints[index], r: 2.2, tone: "light", visible: stage >= 1, drift: 4 });
      out.links.push({ from: id("inv"), to: il, tone: "light", lit: stage === 1 });
      if (!hasOrder) return;
      const ordered = outcome.ordered;
      out.nodes.push({
        id: ol,
        ...ordPoints[index],
        r: 2.2,
        tone: stage >= 2 ? (ordered ? (outcome.price === "light" ? "light" : outcome.price) : "muted") : "light",
        lit: stage >= 2 && outcome.price === "fail",
        visible: stage >= 2,
        drift: 4,
      });
      out.links.push({ from: id("ord"), to: ol, tone: "light" });
      out.links.push({
        from: il,
        to: ol,
        tone: ordered ? outcome.price : "muted",
        lit: stage >= 2 && ordered,
        visible: stage >= 2,
      });
      out.nodes.push({
        id: dl,
        ...delPoints[index],
        r: 2.2,
        tone: stage >= 3 ? (outcome.delivery === "light" ? "light" : outcome.delivery) : "light",
        lit: stage >= 3 && (outcome.delivery === "fail" || outcome.delivery === "warn"),
        visible: stage >= 3,
        drift: 4,
      });
      out.links.push({ from: id("del"), to: dl, tone: "light" });
      out.links.push({
        from: ol,
        to: dl,
        tone: outcome.delivery,
        lit: stage >= 3 && ordered,
        visible: stage >= 3,
      });
    });
    if (facts.lines.length > shown.length && labels) {
      out.nodes.push({
        id: id("more"),
        x: Math.max(0.03, L.invoice.x - 0.1),
        y: Math.min(0.95, L.invoice.y + (compact ? 0.18 : 0.2)),
        r: 1.4,
        tone: "muted",
        label: `+${facts.lines.length - shown.length} more lines`,
        side: "right",
        visible: stage >= 1,
      });
    }

    // ------------------------------------------------ the triangle
    const closed = stage >= 4 && verdict.kind === "matched";
    const edgeTone = (a: string, b: string): Tone => {
      if (stage < 4) return "light";
      if (verdict.kind === "matched") return "accent";
      if (credit) return "muted";
      if (corner && (a === corner || b === corner)) return verdict.tone;
      return "accent";
    };
    const edges: [string, string, "invoice" | "order" | "delivery", "invoice" | "order" | "delivery"][] = [
      ["inv", "ord", "invoice", "order"],
      ["ord", "del", "order", "delivery"],
      ["del", "inv", "delivery", "invoice"],
    ];
    edges.forEach(([a, b, ca, cb]) =>
      out.links.push({
        from: id(a),
        to: id(b),
        tone: edgeTone(ca, cb),
        lit: stage >= 4 && !credit,
        visible: stage >= 2 && (hasOrder || credit ? true : a !== "ord" && b !== "ord"),
      }),
    );

    // ------------------------------------------------ the verdict, in the middle
    out.nodes.push({
      id: id("mid"),
      x: centre.x,
      y: centre.y,
      r: closed ? 4 : 3.2,
      tone: stage >= 4 ? verdict.tone : "muted",
      ring: stage >= 4,
      lit: stage >= 4,
      label: labels && stage >= 4 ? verdict.word : undefined,
      sub: labels && stage >= 4 ? shorten(verdict.reason, compact ? 22 : 30) : undefined,
      side: compact ? "right" : "right",
      visible: stage >= 4,
      drift: 1,
    });
    ["inv", "ord", "del"].forEach((hub) =>
      out.links.push({ from: id(hub), to: id("mid"), tone: stage >= 4 ? verdict.tone : "light", lit: closed, visible: stage >= 4 }),
    );

    // ------------------------------------------------ approvals, as a chain
    let previous = id("mid");
    const route: string[] = [id("mid")];
    approvals.forEach((row, index) => {
      const node = id(`ap${row.id}`);
      const tone = approvalTone(row);
      out.nodes.push({
        id: node,
        x: L.approvalStart.x + L.approvalStep.x * index,
        y: L.approvalStart.y + L.approvalStep.y * index,
        r: 3.2,
        tone: stage >= 5 ? tone : "muted",
        ring: stage >= 5 && row.status === "pending",
        lit: stage >= 5,
        label: labels && stage >= 5 && !compact ? (row.step > 1 ? "Second signature" : "Signature") : undefined,
        sub: labels && stage >= 5 && !compact ? shorten(approvalWords(row), 26) : undefined,
        side: "below",
        visible: stage >= 4,
        drift: 2,
      });
      out.links.push({ from: previous, to: node, tone: stage >= 5 ? tone : "light", lit: stage >= 5, visible: stage >= 4 });
      previous = node;
      route.push(node);
    });

    // ------------------------------------------------ the ledger
    const ledgerTone: Tone = facts.posted ? "pass" : facts.dropped ? "warn" : "muted";
    out.nodes.push({
      id: id("ledger"),
      x: L.ledger.x,
      y: L.ledger.y,
      r: 5.4,
      tone: stage >= 6 ? ledgerTone : "muted",
      ring: true,
      lit: stage >= 6 && facts.posted,
      label: labels ? "The ledger" : undefined,
      sub: labels
        ? stage >= 6
          ? facts.posted
            ? facts.bill?.external_reference || "Bill written"
            : facts.dropped
              ? "Bill written, not confirmed"
              : verdict.kind === "stopped"
                ? "Nothing posted"
                : "Not posted yet"
          : "…"
        : undefined,
      side: "below",
      visible: stage >= 1,
      drift: 1.5,
    });
    out.links.push({
      from: previous,
      to: id("ledger"),
      tone: stage >= 6 ? (facts.posted ? "pass" : verdict.kind === "stopped" ? "fail" : "light") : "light",
      lit: stage >= 6 && facts.posted,
      visible: stage >= 4 && verdict.kind !== "stopped",
    });
    route.push(id("ledger"));

    out.paths.approval = route.slice(0, -1);
    out.paths.toLedger = route;
    return out;
  }, [detail, facts, stage, compact, aspect, key, labels]);

  // Fire the pulses that carry each stage into the next.
  const fired = useRef("");
  useEffect(() => {
    if (!detail || !facts || prefersReducedMotion()) return;
    const mark = `${key}-${stage}`;
    if (fired.current === mark) return;
    fired.current = mark;
    const id = (name: string) => `${key}-${name}`;
    const { shown, verdict, corner, approvals } = facts;
    const hasOrder = Boolean(detail.purchase_order) && verdict.kind !== "credit";
    const pulse = canvas.current?.pulse;
    if (!pulse) return;

    if (stage === 1) {
      pulse([id("doc"), id("inv")], { duration: 700, tone: "light", size: 3 });
      shown.forEach((line, index) =>
        pulse([id("inv"), id(`il${line.line_number}`)], { delay: 520 + index * 70, duration: 420, tone: "light", size: 2 }),
      );
    }
    if (stage === 2 && hasOrder) {
      shown.forEach((line, index) => {
        const outcome = lineOutcome(line);
        if (!outcome.ordered) return;
        pulse([id(`il${line.line_number}`), id(`ol${line.line_number}`)], {
          delay: index * 110,
          duration: 720,
          tone: outcome.price === "light" ? "accent" : outcome.price,
        });
      });
    }
    if (stage === 3 && hasOrder) {
      shown.forEach((line, index) => {
        const outcome = lineOutcome(line);
        if (!outcome.ordered) return;
        pulse([id(`ol${line.line_number}`), id(`dl${line.line_number}`)], {
          delay: index * 110,
          duration: 720,
          tone: outcome.delivery === "light" ? "accent" : outcome.delivery,
        });
      });
    }
    if (stage === 4) {
      if (verdict.kind === "matched") {
        pulse([id("inv"), id("ord"), id("del"), id("inv")], { duration: 1100, tone: "accent", size: 3.2 });
        canvas.current?.flash(id("mid"), "accent");
      } else if (verdict.kind !== "credit") {
        const to = corner === "order" ? "ord" : corner === "delivery" ? "del" : "inv";
        const path = to === "inv" ? [id("doc"), id("inv")] : to === "ord" ? [id("inv"), id("ord")] : [id("inv"), id("ord"), id("del")];
        pulse(path, { duration: 800, tone: verdict.tone, size: 3.2, onArrive: () => canvas.current?.flash(id(to), verdict.tone) });
        canvas.current?.flash(id("mid"), verdict.tone);
      }
    }
    if (stage === 5 && approvals.length && verdict.kind !== "stopped") {
      const chain = [id("mid"), ...approvals.map((row) => id(`ap${row.id}`))];
      const last = approvals[approvals.length - 1];
      pulse(chain, { duration: 520 * approvals.length + 300, tone: approvalTone(last), size: 2.8 });
    }
    if (stage === 6 && facts.posted) {
      pulse(paths.toLedger, { duration: 900, tone: "pass", size: 3.4, onArrive: () => canvas.current?.flash(id("ledger"), "pass") });
    }
  }, [stage, key, detail, facts, paths.toLedger]);

  const traffic = useMemo(() => {
    if (!detail || !facts || stage < 6) return undefined;
    const id = (name: string) => `${key}-${name}`;
    if (facts.posted) {
      return {
        paths: [
          [id("doc"), id("inv"), id("ord"), id("del"), id("mid"), ...paths.toLedger.slice(1)],
          paths.toLedger,
        ],
        every: 1500,
        tone: "accent" as Tone,
      };
    }
    if (facts.verdict.kind === "stopped") {
      return { paths: [[id("doc"), id("inv")]], every: 2200, tone: "fail" as Tone };
    }
    if (facts.verdict.kind === "held") {
      const to = facts.corner === "order" ? [id("inv"), id("ord")] : [id("inv"), id("ord"), id("del")];
      return { paths: [to], every: 2000, tone: "warn" as Tone };
    }
    return { paths: [[id("inv"), id("ord"), id("del"), id("inv")], paths.approval], every: 1700, tone: "accent" as Tone };
  }, [detail, facts, stage, key, paths]);

  return (
    <Constellation
      ref={canvas}
      className={className}
      nodes={nodes}
      links={links}
      traffic={traffic}
      ambient={ambient ?? (compact ? 26 : 52)}
      reach={compact ? 88 : 118}
      introStagger={14}
    />
  );
}

/** Drives the stages: 1 invoice, 2 order, 3 delivery, 4 verdict, 5 approvals, 6 ledger. */
export function useMatchStage(key: string | null, pace = 1): Stage {
  const [stage, setStage] = useState<Stage>(0);
  useEffect(() => {
    if (!key) return;
    if (prefersReducedMotion()) {
      setStage(6);
      return;
    }
    setStage(1);
    const at = [0, 0, 850, 1750, 2650, 3500, 4250].map((ms) => ms * pace);
    const timers = ([2, 3, 4, 5, 6] as Stage[]).map((next) => window.setTimeout(() => setStage(next), at[next]));
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [key, pace]);
  return stage;
}

/** Width over height of an element, kept current, and whether it is narrow. */
export function useBox(threshold = 560) {
  const ref = useRef<HTMLDivElement>(null);
  const [box, setBox] = useState({ compact: false, aspect: 1.4 });
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const measure = () => {
      const rect = element.getBoundingClientRect();
      if (!rect.width || !rect.height) return;
      setBox((previous) => {
        const next = { compact: rect.width < threshold, aspect: rect.width / rect.height };
        return previous.compact === next.compact && Math.abs(previous.aspect - next.aspect) < 0.05 ? previous : next;
      });
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, [threshold]);
  return [ref, box] as const;
}
