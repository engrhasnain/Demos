"use client";

/**
 * The guided first run.
 *
 * Step one builds Hengtai: customers, suppliers, parts, orders and their
 * shipments, invoices, service desk cases, documents (including one planted
 * email with instructions in it) and the six people who ask, with their
 * grants. The server builds it in one request; while it works the stages
 * light in the order it builds them, and each system of the operations brain
 * switches on as its stage completes. The real counts arrive with the reply.
 *
 * Step two asks the same three questions as two people, for real, so the
 * first thing anybody sees is the product's point: the same question, a
 * different answer, depending on who asks.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { OpsBrain, type BrainHandle } from "@/components/ops-brain";
import { CountUp } from "@/design/CountUp";
import { Meter } from "@/design/Meter";
import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Banner, Band, Button } from "@/design/Surface";
import { api, ApiError, request, tokenFor } from "@/lib/api";
import { brainDomains, brainSteps } from "@/lib/brain";
import type { Answer, DemoPerson, QuestionDetail } from "@/lib/types";
import { grouped, OUTCOME, outcomeOf, plain, roleWords } from "@/lib/words";

type Stage = { key: string; label: string; counts: string[]; system: number };

/** In the order the server builds them; `system` is how many systems are lit once it is done. */
const STAGES: Stage[] = [
  { key: "customers", label: "Customers and their accounts", counts: ["customers"], system: 1 },
  { key: "suppliers", label: "Suppliers and their deliveries", counts: ["suppliers", "deliveries"], system: 1 },
  { key: "parts", label: "The parts catalogue", counts: ["parts"], system: 3 },
  { key: "orders", label: "Orders, order lines and shipments", counts: ["orders", "order_lines", "shipments"], system: 5 },
  { key: "stock", label: "Weekly demand and weeks of cover", counts: ["parts_moving", "parts_short"], system: 5 },
  { key: "invoices", label: "Invoices raised against delivered orders", counts: ["invoices"], system: 5 },
  { key: "tickets", label: "Service desk cases", counts: ["tickets"], system: 5 },
  { key: "documents", label: "Emails and documents, one with instructions in it", counts: ["documents"], system: 5 },
  { key: "people", label: "Six people who ask, and their grants", counts: ["people", "grants"], system: 5 },
];

/** Which systems are lit after each stage: orders, ledger, stock, conversations, shipments. */
const LIT_AFTER: number[][] = [[0], [0, 2], [0, 2], [0, 2, 4], [0, 2, 4], [0, 1, 2, 4], [0, 1, 2, 3, 4], [0, 1, 2, 3, 4], [0, 1, 2, 3, 4]];

const COUNT_WORDS: Record<string, string> = {
  customers: "customers",
  suppliers: "suppliers",
  deliveries: "deliveries",
  parts: "parts",
  orders: "orders",
  order_lines: "order lines",
  shipments: "shipments",
  parts_moving: "parts moving",
  parts_short: "parts short",
  invoices: "invoices",
  tickets: "cases",
  documents: "documents",
  people: "people",
  grants: "grants",
};

const FIRST_QUESTIONS = [
  "How are we doing this week?",
  "Which customers have late orders?",
  "What is owed altogether?",
];

type Asked = { person: string; role: string; question: string; answer: Answer | null; error?: string };

export function FirstRun({ onFinished }: { onFinished: () => void }) {
  const [phase, setPhase] = useState<"idle" | "building" | "asking" | "done" | "failed">("idle");
  const [stage, setStage] = useState(0);
  const [counts, setCounts] = useState<Record<string, number> | null>(null);
  const [trouble, setTrouble] = useState("");
  const [asked, setAsked] = useState<Asked[]>([]);
  const [elapsed, setElapsed] = useState(0);
  const brain = useRef<BrainHandle>(null);
  const started = useRef(0);

  // While the server builds, the stages light on a clock that never quite
  // reaches the end; the reply finishes them.
  useEffect(() => {
    if (phase !== "building") return;
    const timer = window.setInterval(() => {
      const seconds = (performance.now() - started.current) / 1000;
      setElapsed(seconds);
      setStage((current) => Math.min(STAGES.length - 1, Math.max(current, Math.floor(seconds / 0.85))));
    }, 120);
    return () => window.clearInterval(timer);
  }, [phase]);

  const litSystems = phase === "idle" ? 0 : phase === "building" ? (LIT_AFTER[Math.max(0, stage - 1)]?.length ?? 0) : 5;

  const askAsTwoPeople = useCallback(async () => {
    setPhase("asking");
    try {
      const who = await api.get<{ people: DemoPerson[]; password: string }>("/api/demo/people");
      const pick = [
        who.people.find((person) => person.role === "director"),
        who.people.find((person) => person.role === "salesperson"),
      ].filter(Boolean) as DemoPerson[];
      for (const person of pick) {
        const token = await tokenFor(person.email, who.password);
        for (const question of FIRST_QUESTIONS) {
          let answer: Answer | null = null;
          let error = "";
          try {
            answer = await api.post<Answer>("/api/ask", { question }, token);
            let plan = null;
            if (!answer.ok && answer.question_id) {
              const detail = await request<QuestionDetail>(`/api/questions/${answer.question_id}`, { token }).catch(
                () => null,
              );
              plan = detail?.plan ?? null;
            }
            brain.current?.play(brainSteps(answer, plan), { gap: 380 });
          } catch (cause) {
            error = cause instanceof ApiError ? cause.message : String(cause);
          }
          setAsked((list) => [...list, { person: person.name, role: person.role, question, answer, error }]);
          await new Promise((resolve) => window.setTimeout(resolve, 650));
        }
      }
      setPhase("done");
    } catch (cause) {
      setTrouble(cause instanceof ApiError ? cause.message : String(cause));
      setPhase("done");
    }
  }, []);

  const build = async () => {
    setTrouble("");
    setPhase("building");
    setStage(0);
    started.current = performance.now();
    try {
      const out = await api.post<{ loaded: boolean; counts: Record<string, number> }>("/api/demo/load", {
        customers: 200,
        orders: 1200,
      });
      setCounts(out.counts);
      // finish the remaining stages quickly, one after another
      for (let index = 0; index <= STAGES.length; index += 1) {
        setStage((current) => Math.max(current, index));
        await new Promise((resolve) => window.setTimeout(resolve, 110));
      }
      await askAsTwoPeople();
    } catch (cause) {
      setTrouble(cause instanceof ApiError ? cause.message : String(cause));
      setPhase("failed");
    }
  };

  const fraction =
    phase === "idle" || phase === "failed"
      ? 0
      : phase === "building"
        ? Math.min(0.92, stage / STAGES.length + 0.04)
        : phase === "asking"
          ? 0.92 + Math.min(0.08, asked.length / 6 * 0.08)
          : 1;
  const percent = Math.round(fraction * 100);

  const domains = useMemo(() => brainDomains(null, null, { customers: 200, suppliers: 40 }), []);

  return (
    <Band top>
      <div className="oa-hero" data-first="">
        <div className="oa-hero-copy">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              First run <span className="ds-eyebrow-sep">·</span> about ten seconds
            </span>
          </Reveal>
          <Reveal index={1} y={36}>
            <h1 className="ds-display oa-hero-title">
              Build the business.
              <br />
              <span className="oa-light ds-accent-text">Then ask it anything.</span>
            </h1>
          </Reveal>
          <Reveal index={2}>
            <p className="ds-band-lede" style={{ fontSize: 17 }}>
              One press builds Hengtai Industrial Supply: 200 customers, 40 suppliers, about a thousand parts, 1,200
              orders with their shipments and invoices, the service desk, a few emails, and six people who ask, each
              allowed to see something different. Then the same three questions are asked as two of them.
            </p>
          </Reveal>

          {phase === "idle" || phase === "failed" ? (
            <Reveal index={3}>
              <div className="oa-get">
                {(
                  [
                    [200, "customers"],
                    [40, "suppliers"],
                    [1200, "orders"],
                    [19, "reviewed queries"],
                    [6, "people who ask"],
                  ] as const
                ).map(([value, label], index) => (
                  <div key={label}>
                    <span className="ds-stat-value" style={{ fontSize: 26 }}>
                      <CountUp to={value} delay={index * 80} />
                    </span>
                    <span className="ds-mono-label ds-stat-label">{label}</span>
                  </div>
                ))}
              </div>
              {trouble && (
                <div style={{ marginTop: 16 }}>
                  <Banner tone="fail" title="The build did not finish">
                    {trouble}
                  </Banner>
                </div>
              )}
              <div style={{ marginTop: 22, display: "flex", flexWrap: "wrap", gap: 12 }}>
                <Button tone="primary" size="large" onClick={() => void build()} arrow>
                  Build the business
                </Button>
              </div>
            </Reveal>
          ) : (
            <div className="oa-progress" aria-live="polite">
              <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 16 }}>
                <span className="ds-display oa-progress-number">
                  <CountUp to={percent} duration={600} suffix="%" />
                </span>
                <StatusChip
                  tone={phase === "done" ? "pass" : "accent"}
                  surface="dark"
                  pulse={phase !== "done"}
                  size="large"
                >
                  {phase === "building"
                    ? `Stage ${Math.min(stage + 1, STAGES.length)} of ${STAGES.length}`
                    : phase === "asking"
                      ? `First questions · ${asked.length} of 6`
                      : "Ready"}
                </StatusChip>
              </div>
              <div style={{ marginTop: 14 }}>
                <Meter value={fraction} size="large" label={`${percent} per cent done`} />
              </div>
              <p style={{ margin: "12px 0 0", fontSize: 15, fontWeight: 600 }}>
                {phase === "building"
                  ? `Building: ${STAGES[Math.min(stage, STAGES.length - 1)].label.toLowerCase()}`
                  : phase === "asking"
                    ? "Asking the same three questions as two people"
                    : "Hengtai is built and the first questions are answered."}
              </p>
              {phase === "building" && (
                <p className="ds-mono" style={{ margin: "4px 0 0", fontSize: 12, color: "var(--ds-ink-muted)" }}>
                  {elapsed.toFixed(1)} s · the server builds it in one go and replies with the counts
                </p>
              )}
            </div>
          )}

          {phase !== "idle" && phase !== "failed" && (
            <div className="oa-first-stages">
              <NodeChain
                stagger={40}
                live={phase !== "done"}
                fill={Math.min(1, stage / STAGES.length)}
                items={STAGES.map((item, index) => {
                  const done = index < stage || (counts !== null && stage >= STAGES.length);
                  const active = index === stage && phase === "building";
                  const shown = item.counts
                    .filter((key) => counts && counts[key] !== undefined)
                    .map((key) => `${grouped(counts![key])} ${COUNT_WORDS[key] ?? key}`)
                    .join(" · ");
                  return {
                    key: item.key,
                    tone: done ? "accent" : active ? "warn" : undefined,
                    state: done ? "done" : active ? "active" : "waiting",
                    marker: done ? "✓" : String(index + 1).padStart(2, "0"),
                    content: (
                      <span className="oa-stage" data-state={done ? "done" : active ? "active" : "waiting"}>
                        <span>{item.label}</span>
                        {done && shown && <span className="ds-mono oa-stage-count">{shown}</span>}
                      </span>
                    ),
                  };
                })}
              />
            </div>
          )}

          {asked.length > 0 && (
            <div className="oa-first-asked">
              <p className="ds-mono-label" style={{ margin: "0 0 10px" }}>
                The same question, two people
              </p>
              <ul>
                {asked.map((item, index) => {
                  const outcome = item.answer ? outcomeOf(item.answer.refused) : "needs-review";
                  return (
                    <li key={index} className="oa-first-ask" style={{ "--ds-d": "0ms" } as React.CSSProperties}>
                      <StatusChip tone={OUTCOME[outcome].tone} surface="dark" size="small">
                        {OUTCOME[outcome].label}
                      </StatusChip>
                      <span className="oa-first-ask-who">
                        {item.person} · {roleWords(item.role)}
                      </span>
                      <span className="oa-first-ask-q">{item.question}</span>
                      <span className="oa-first-ask-a">
                        {item.error || (item.answer ? (item.answer.ok ? item.answer.text : plain(item.answer.refused)) : "")}
                      </span>
                    </li>
                  );
                })}
              </ul>
              {phase === "done" && (
                <div style={{ marginTop: 18 }}>
                  <Button tone="primary" size="large" onClick={onFinished} arrow>
                    Choose who is asking
                  </Button>
                </div>
              )}
            </div>
          )}
        </div>

        <div className="oa-hero-stage oa-cc-map">
          <span className="oa-corner" data-at="tl" aria-hidden />
          <span className="oa-corner" data-at="tr" aria-hidden />
          <span className="oa-corner" data-at="bl" aria-hidden />
          <span className="oa-corner" data-at="br" aria-hidden />
          <span className="oa-map-label" data-at="top">
            Operations map · {litSystems} of 5 systems built
          </span>
          <div className="oa-cc-canvas">
            <OpsBrain
              ref={brain}
              domains={domains}
              built={litSystems}
              idle={phase === "done"}
              label={`The five systems OpsAgent reads: ${litSystems} of 5 built`}
            />
          </div>
        </div>
      </div>
    </Band>
  );
}
