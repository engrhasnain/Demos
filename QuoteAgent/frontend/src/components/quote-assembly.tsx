"use client";

/**
 * The quote-assembly constellation: QuoteAgent's signature.
 *
 * Built from a real request: each request line is a node on the left; a
 * pulse carries it to the catalogue part it was matched to; from the part a
 * second pulse reaches the priced line, where the amount appears; the priced
 * lines converge on the approval gate, which lights in the colour of where
 * the quote actually stands. Lines that became questions, supplier requests
 * or non-catalogue parts stop where the agent stopped them, in their own
 * colour. Then the next request in flight is assembled.
 *
 * Under reduced motion the finished assembly is drawn once, without pulses.
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
import { money } from "@/lib/format";
import type { CaseDetail, QuoteLine } from "@/lib/types";

const MAX_LINES = 7;

type Gate = { tone: Tone; label: string };

export function gateFor(detail: CaseDetail): Gate {
  const status = detail.case.status;
  if (detail.current_version?.needs_repricing) return { tone: "fail", label: "Re-opened: numbers moved" };
  if (status === "awaiting_approval") return { tone: "warn", label: "Waiting for approval" };
  if (status === "priced") return { tone: "accent", label: "Ready to send" };
  if (status === "sent") return { tone: "pass", label: "Quote sent" };
  if (status === "won") return { tone: "pass", label: "Won" };
  if (status === "lost" || status === "cancelled") return { tone: "fail", label: detail.case.status_label };
  if (status === "awaiting_customer") return { tone: "warn", label: "Questions out" };
  if (status === "awaiting_supplier") return { tone: "warn", label: "Supplier asked" };
  return { tone: "light", label: detail.case.status_label };
}

function outcome(line: QuoteLine): { tone: Tone; part: string; priced: boolean } {
  if (line.status === "needs_clarification") return { tone: "warn", part: "Question", priced: false };
  if (line.status === "awaiting_supplier") return { tone: "warn", part: "Supplier asked", priced: false };
  if (line.status === "non_catalogue") return { tone: "fail", part: "Not in catalogue", priced: false };
  if (line.status === "withdrawn") return { tone: "muted", part: "Withdrawn", priced: false };
  const priced = Boolean(line.pricing?.line_total) && Number(line.pricing.line_total) > 0;
  return { tone: priced ? "accent" : "light", part: line.product?.sku ?? "Matched", priced };
}

function shorten(text: string, length: number): string {
  const clean = text.replace(/\s+/g, " ").trim();
  return clean.length > length ? `${clean.slice(0, length - 1)}…` : clean;
}

export function QuoteAssembly({
  detail,
  compact,
  stage,
  className = "",
}: {
  detail: CaseDetail | null;
  compact: boolean;
  /** 0 nothing, 1 request lines, 2 parts, 3 prices, 4 gate. */
  stage: number;
  className?: string;
}) {
  const canvas = useRef<ConstellationHandle>(null);
  const lines = useMemo(
    () => (detail?.current_version?.lines ?? []).slice().sort((a, b) => a.line_number - b.line_number),
    [detail],
  );
  const shown = lines.slice(0, compact ? 5 : MAX_LINES);
  const more = lines.length - shown.length;
  const gate = detail ? gateFor(detail) : { tone: "light" as Tone, label: "" };
  const caseKey = detail ? `${detail.case.id}` : "none";

  const { nodes, links } = useMemo(() => {
    const result: { nodes: ConstellationNode[]; links: ConstellationLink[] } = { nodes: [], links: [] };
    if (!detail) return result;
    const top = compact ? 0.14 : 0.12;
    const bottom = compact ? 0.86 : 0.6;
    const span = shown.length > 1 ? (bottom - top) / (shown.length - 1) : 0;
    const columns = compact
      ? { request: 0.08, part: 0.36, price: 0.62, gate: 0.88 }
      : { request: 0.2, part: 0.43, price: 0.655, gate: 0.895 };
    const gateY = shown.length ? top + ((shown.length - 1) * span) / 2 : 0.4;

    shown.forEach((line, index) => {
      const y = top + index * span;
      const result_ = outcome(line);
      const request = `r-${caseKey}-${line.line_number}`;
      const part = `p-${caseKey}-${line.line_number}`;
      const price = `v-${caseKey}-${line.line_number}`;
      result.nodes.push({
        id: request,
        x: columns.request,
        y,
        r: 2.6,
        tone: "light",
        label: compact ? undefined : shorten(line.original_request_text || line.request_text, 17),
        side: "left",
        visible: stage >= 1,
        lit: stage === 1,
      });
      result.nodes.push({
        id: part,
        x: columns.part,
        y: y + (index % 2 ? 0.012 : -0.012),
        r: 3,
        tone: result_.tone === "accent" ? "light" : result_.tone,
        label: compact ? undefined : shorten(result_.part, 22),
        side: "right",
        visible: stage >= 2,
        lit: stage === 2 || result_.tone === "warn" || result_.tone === "fail",
      });
      result.links.push({ from: request, to: part, tone: "light", lit: stage === 2 });
      if (result_.priced) {
        result.nodes.push({
          id: price,
          x: columns.price,
          y,
          r: 3,
          tone: "accent",
          label: shorten(money(line.pricing.line_total), 12),
          side: "right",
          visible: stage >= 3,
          lit: stage >= 3,
        });
        result.links.push({ from: part, to: price, tone: "accent", lit: stage === 3 });
        result.links.push({ from: price, to: `g-${caseKey}`, tone: gate.tone, lit: stage >= 4 });
      }
    });

    if (more > 0) {
      result.nodes.push({
        id: `m-${caseKey}`,
        x: columns.request,
        y: Math.min(0.95, top + shown.length * span + (compact ? 0.02 : 0.06)),
        r: 1.6,
        tone: "muted",
        label: `+${more} more lines`,
        side: compact ? "right" : "left",
        visible: stage >= 1,
      });
    }
    result.nodes.push({
      id: `g-${caseKey}`,
      x: columns.gate,
      y: gateY,
      r: 5,
      tone: stage >= 4 ? gate.tone : "muted",
      ring: true,
      lit: stage >= 4,
      label: compact ? undefined : "Approval",
      sub: stage >= 4 ? gate.label : "…",
      side: "below",
      visible: stage >= 1,
      drift: 1.5,
    });
    return result;
  }, [detail, shown, more, stage, compact, caseKey, gate.tone, gate.label]);

  // Fire the pulses that carry each stage into the next.
  const fired = useRef<string>("");
  useEffect(() => {
    if (!detail || prefersReducedMotion()) return;
    const key = `${caseKey}-${stage}`;
    if (fired.current === key) return;
    fired.current = key;
    shown.forEach((line, index) => {
      const r = outcome(line);
      const request = `r-${caseKey}-${line.line_number}`;
      const part = `p-${caseKey}-${line.line_number}`;
      const price = `v-${caseKey}-${line.line_number}`;
      if (stage === 2) {
        canvas.current?.pulse([request, part], {
          delay: index * 110,
          duration: 720,
          tone: r.tone === "accent" ? "light" : r.tone,
        });
      }
      if (stage === 3 && r.priced) {
        canvas.current?.pulse([part, price], { delay: index * 110, duration: 720, tone: "accent" });
      }
      if (stage === 4 && r.priced) {
        canvas.current?.pulse([price, `g-${caseKey}`], {
          delay: index * 80,
          duration: 820,
          tone: gate.tone,
          size: 2.4,
        });
      }
    });
  }, [stage, caseKey, detail, shown, gate.tone]);

  const traffic = useMemo(() => {
    if (!detail || stage < 4) return undefined;
    const paths = shown
      .filter((line) => outcome(line).priced)
      .map((line) => [
        `r-${caseKey}-${line.line_number}`,
        `p-${caseKey}-${line.line_number}`,
        `v-${caseKey}-${line.line_number}`,
        `g-${caseKey}`,
      ]);
    return paths.length ? { paths, every: 900, tone: "accent" as Tone } : undefined;
  }, [detail, stage, shown, caseKey]);

  return (
    <Constellation
      ref={canvas}
      className={className}
      nodes={nodes}
      links={links}
      traffic={traffic}
      ambient={compact ? 30 : 58}
      reach={compact ? 90 : 120}
      introStagger={18}
    />
  );
}

/** Drives the stage of the assembly: 1 lines, 2 parts, 3 prices, 4 gate. */
export function useAssemblyStage(key: string | null): number {
  const [stage, setStage] = useState(0);
  useEffect(() => {
    if (!key) return;
    if (prefersReducedMotion()) {
      setStage(4);
      return;
    }
    setStage(1);
    const timers = [
      window.setTimeout(() => setStage(2), 650),
      window.setTimeout(() => setStage(3), 1750),
      window.setTimeout(() => setStage(4), 2850),
    ];
    return () => timers.forEach((timer) => window.clearTimeout(timer));
  }, [key]);
  return stage;
}
