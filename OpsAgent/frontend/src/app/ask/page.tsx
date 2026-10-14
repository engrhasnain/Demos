"use client";

/**
 * Ask.
 *
 * A question goes in; the plan comes back step by step on a chain of nodes,
 * in time with pulses travelling through the operations brain to every system
 * it touches. A step the role check refuses stops at that system's ring, which
 * turns coral. Every number in the answer opens the reviewed query that
 * produced it, with its inputs, its filter and the minute it was read.
 */

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { CommandBar, SystemsRail } from "@/components/command";
import { OpsBrain, type BrainHandle, type BrainStep } from "@/components/ops-brain";
import { usePeople } from "@/components/shell";
import { counted, evidenceTrace, Figure } from "@/components/trace";
import { NodeChain, type ChainItem } from "@/design/NodeChain";
import { prefersReducedMotion } from "@/design/motion";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Band, Banner, Card, Empty } from "@/design/Surface";
import { api, ApiError, signInAs } from "@/lib/api";
import { brainDomains, brainSteps } from "@/lib/brain";
import { useLoad, useSignedIn } from "@/lib/session";
import type { Answer, DemoState, DocumentRow, Evidence, PlanStep, QuestionDetail, QuestionRow } from "@/lib/types";
import {
  capabilityWords,
  clock,
  DOMAIN_BY_ID,
  domainsOf,
  filterWords,
  grouped,
  initials,
  OUTCOME,
  outcomeOf,
  plain,
  refusalCause,
  roleWords,
} from "@/lib/words";

const STEP_MS = 560;

/** Split the answer so each sentence lines up with the query that wrote it. */
function sentences(text: string, count: number): string[] {
  const parts = text
    .split(/(?<=[.!?])\s+(?=[A-Z0-9])/)
    .map((part) => part.trim())
    .filter(Boolean);
  return parts.length === count ? parts : [text];
}

const NUMBER = /(\d{4}-\d{2}-\d{2}|(?<![\w-])\d[\d,]*(?:\.\d+)?(?![\w-]))/g;

export default function AskPage() {
  const user = useSignedIn();
  const people = usePeople();
  const { data: state } = useLoad<DemoState>("/api/demo/state");
  const { data: documentsData } = useLoad<{ documents: DocumentRow[] }>(user ? "/api/documents?limit=40" : null, [user?.email]);
  const { data: history, reload: reloadHistory } = useLoad<{ questions: QuestionRow[] }>(
    user ? "/api/questions?limit=12" : null,
    [user?.email],
  );

  const [question, setQuestion] = useState("");
  const [attached, setAttached] = useState("");
  const [asking, setAsking] = useState(false);
  const [answer, setAnswer] = useState<Answer | null>(null);
  const [plan, setPlan] = useState<PlanStep[] | null>(null);
  const [shown, setShown] = useState(0);
  const [trouble, setTrouble] = useState("");
  const [switching, setSwitching] = useState("");
  const [run, setRun] = useState(0);
  const [lastSteps, setLastSteps] = useState<BrainStep[]>([]);
  const brain = useRef<BrainHandle>(null);
  const results = useRef<HTMLDivElement>(null);

  const domains = useMemo(
    () => brainDomains(user?.role, user?.reach, { customers: state?.customers ?? 200, suppliers: state?.suppliers ?? 40 }),
    [user?.role, user?.reach, state?.customers, state?.suppliers],
  );

  const ask = useCallback(
    async (text: string, opts: { document?: string } = {}) => {
      const asked = text.trim();
      if (!asked || asking) return;
      const documentReference = opts.document ?? attached;
      setAsking(true);
      setTrouble("");
      setShown(0);
      try {
        const out = await api.post<Answer>("/api/ask", { question: asked, document_reference: documentReference });
        let steps: PlanStep[] = [];
        if (out.question_id) {
          const detail = await api.get<QuestionDetail>(`/api/questions/${out.question_id}`).catch(() => null);
          steps = detail?.plan ?? [];
        }
        setAnswer(out);
        setPlan(steps);
        setRun((value) => value + 1);
        const travel = brainSteps(out, steps);
        setLastSteps(travel);
        brain.current?.play(travel, { document: Boolean(documentReference), gap: STEP_MS });
        reloadHistory();
        window.setTimeout(() => results.current?.scrollIntoView({ behavior: prefersReducedMotion() ? "auto" : "smooth", block: "start" }), 250);
      } catch (error) {
        setTrouble(error instanceof ApiError ? error.message : String(error));
      } finally {
        setAsking(false);
      }
    },
    [asking, attached, reloadHistory],
  );

  /** Switch who is asking, and ask the same question again as them. */
  const askAs = async (email: string) => {
    if (!people) return;
    setSwitching(email);
    try {
      await signInAs(email, people.password);
      if (answer) {
        setAsking(false);
        window.setTimeout(() => void askRef.current(answer.question), 60);
      }
    } catch (error) {
      setTrouble(error instanceof ApiError ? error.message : String(error));
    } finally {
      setSwitching("");
    }
  };
  const askRef = useRef(ask);
  askRef.current = ask;

  const handed = useRef(false);
  useEffect(() => {
    if (!user || handed.current) return;
    const q = new URLSearchParams(window.location.search).get("q");
    if (!q) return;
    handed.current = true;
    setQuestion(q);
    window.history.replaceState(null, "", "/ask");
    window.setTimeout(() => void askRef.current(q), 700);
  }, [user]);

  const chain = useMemo(() => (answer && user ? planChain(answer, plan ?? [], user.role, user.name) : []), [answer, plan, user]);

  // Reveal the plan one step at a time, in time with the brain.
  useEffect(() => {
    if (!chain.length) return;
    if (prefersReducedMotion()) {
      setShown(chain.length);
      return;
    }
    setShown(1);
    let count = 1;
    const timer = window.setInterval(() => {
      count += 1;
      setShown(count);
      if (count >= chain.length) window.clearInterval(timer);
    }, STEP_MS);
    return () => window.clearInterval(timer);
  }, [run, chain.length]);

  if (!user) return null;

  const done = answer !== null && shown >= chain.length;
  const documents = documentsData?.documents ?? [];
  const outcome = answer ? outcomeOf(answer.refused, answer.injection_seen) : null;
  const litNames = answer ? answer.evidence.map((step) => step.capability) : [];

  return (
    <>
      <Band top>
        <div className="oa-cc oa-cc-ask">
          <div className="oa-cc-head">
            <Reveal y={24}>
              <span className="ds-eyebrow">
                <span className="ds-live-dot" data-tone="accent" aria-hidden />
                Ask <span className="ds-eyebrow-sep">·</span> as {user.name}, {user.role_label.toLowerCase()}
              </span>
            </Reveal>
            <Reveal index={1} y={32}>
              <h1 className="ds-display oa-cc-title oa-cc-title-small">
                Ask across every system. <span className="oa-light ds-accent-text">Only what {user.name.split(" ")[0]} may see.</span>
              </h1>
            </Reveal>
            <Reveal index={2} y={28}>
              <CommandBar
                value={question}
                onChange={setQuestion}
                onSubmit={(text) => void ask(text)}
                busy={asking}
                role={user.role}
                reach={user.reach}
                who={
                  <>
                    <span className="oa-avatar" data-size="small">
                      {initials(user.name)}
                    </span>
                    <span>{user.role_label}</span>
                  </>
                }
                extra={
                  <div className="oa-ask-doc">
                    <label htmlFor="document" className="ds-mono-label">
                      Read alongside a document
                    </label>
                    <select id="document" value={attached} onChange={(event) => setAttached(event.target.value)} className="oa-ask-select">
                      <option value="">No document</option>
                      {documents.map((document) => (
                        <option key={document.reference} value={document.reference}>
                          {document.reference} — {document.subject}
                        </option>
                      ))}
                    </select>
                    {attached && <span className="oa-ask-doc-note">Read as text from outside, never as instructions</span>}
                  </div>
                }
              />
            </Reveal>
          </div>

          <div className="oa-cc-grid">
            <Reveal className="oa-cc-left" index={3} from="left">
              <div className="oa-rail-panel">
                <p className="oa-rail-title">
                  <span className="ds-mono-label">{answer ? "Ask the same question as" : "Who is asking"}</span>
                  <span className="oa-rail-count">06</span>
                </p>
                <div className="oa-asker-list" role="group" aria-label="Who is asking">
                  {(people?.people ?? []).map((person) => (
                    <button
                      key={person.email}
                      type="button"
                      className="oa-asker-button"
                      data-current={person.email === user.email ? "" : undefined}
                      aria-pressed={person.email === user.email}
                      disabled={switching !== "" || asking}
                      title={`${person.name}, ${roleWords(person.role)}: ${person.reach.summary}`}
                      onClick={() => (person.email === user.email ? undefined : void askAs(person.email))}
                    >
                      <span className="oa-avatar" data-size="small">
                        {switching === person.email ? <span className="ds-spinner" aria-hidden /> : initials(person.name)}
                      </span>
                      <span className="oa-asker-text">
                        <b>{person.name}</b>
                        <span>
                          {roleWords(person.role)} · {person.reach.everything ? "every account" : person.reach.summary.replace(/\.$/, "")}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>
              </div>
            </Reveal>

            <div className="oa-cc-map">
              <span className="oa-corner" data-at="tl" aria-hidden />
              <span className="oa-corner" data-at="tr" aria-hidden />
              <span className="oa-corner" data-at="bl" aria-hidden />
              <span className="oa-corner" data-at="br" aria-hidden />
              <span className="oa-map-label" data-at="top">
                Operations map · {user.role_label.toLowerCase()} view
              </span>
              <span className="oa-map-label" data-at="bottom">
                {answer
                  ? `${answer.queries} ${answer.queries === 1 ? "query" : "queries"} · ${grouped(answer.rows_read)} rows · ${answer.seconds.toFixed(2)} s`
                  : "Ask, and the plan travels across the map"}
              </span>
              <div className="oa-cc-canvas">
                <OpsBrain
                  ref={brain}
                  domains={domains}
                  lit={litNames}
                  document={Boolean(attached)}
                  label={`The five systems as ${user.name} sees them`}
                />
              </div>
            </div>

            <Reveal className="oa-cc-right" index={4}>
              <SystemsRail domains={domains} last={lastSteps} title="What the last question touched" />
            </Reveal>
          </div>
        </div>
      </Band>

      <div className="ds-work" ref={results} style={{ scrollMarginTop: 110 }}>
        {trouble && (
          <div style={{ marginBottom: 20 }}>
            <Banner tone="fail" title="That did not go through">
              {trouble}
            </Banner>
          </div>
        )}

        {!answer && !asking && (
          <Empty title="Ask something, or press one of the questions above.">
            The plan will run here step by step, and every number in the answer will open the query behind it.
          </Empty>
        )}

        {answer && (
          <article className="oa-briefing" key={run} data-outcome={done && outcome ? outcome : "working"}>
            <header className="oa-briefing-head">
              <span className="oa-briefing-ref">Briefing {String(answer.question_id ?? 0).padStart(4, "0")}</span>
              <span className="oa-briefing-meta">
                {clock(new Date().toISOString())} · {answer.engine === "external" ? "external model" : "built-in engine"} · as {user.name},{" "}
                {user.role_label.toLowerCase()}
              </span>
              {done && outcome ? (
                <StatusChip tone={OUTCOME[outcome].tone} surface="dark" size="large" pulse={outcome !== "answered"}>
                  {OUTCOME[outcome].label}
                </StatusChip>
              ) : (
                <StatusChip tone="accent" surface="dark" pulse size="large">
                  Working · step {Math.min(shown, chain.length)} of {chain.length}
                </StatusChip>
              )}
            </header>
            <h2 className="oa-briefing-question">{answer.question}</h2>
            <div className="oa-briefing-body">
              <section className="oa-briefing-answer" aria-live="polite">
                <p className="ds-mono-label" style={{ margin: "0 0 12px" }}>
                  The answer
                </p>
                {!done ? (
                  <div className="oa-working">
                    <span />
                    <span />
                    <span />
                    <p>Running the plan. Nothing is written until every step has come back.</p>
                  </div>
                ) : (
                  <AnswerBody answer={answer} />
                )}
              </section>
              <section className="oa-briefing-plan">
                <p className="ds-mono-label" style={{ margin: 0 }}>
                  The plan, step by step
                </p>
                <p className="oa-briefing-reading">{answer.reading || "No reviewed query matched"}</p>
                <NodeChain
                  items={chain.slice(0, Math.max(1, shown))}
                  live={!done}
                  stagger={0}
                  fill={done ? 1 : Math.min(1, shown / Math.max(1, chain.length))}
                />
              </section>
            </div>
          </article>
        )}

        <section className="oa-section" style={{ marginTop: answer ? 48 : 36 }}>
          <Reveal>
            <p className="ds-mono-label">Asked earlier as {user.name}</p>
          </Reveal>
          {!history ? null : history.questions.length === 0 ? (
            <Empty title="Nothing asked yet as this person." />
          ) : (
            <Card flush>
              <div className="ds-table-wrap">
                <table className="ds-table oa-history">
                  <thead>
                    <tr>
                      <th>When</th>
                      <th>Question</th>
                      <th>What became of it</th>
                      <th data-align="right">Queries</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {history.questions.map((row, index) => {
                      const result = outcomeOf(row.refused, row.injection_seen);
                      return (
                        <Reveal as="tr" key={row.id} index={index} className="ds-rowmark" style={{ "--row-tone": `var(--ds-${OUTCOME[result].tone})` } as React.CSSProperties}>
                          <td className="ds-mono" style={{ whiteSpace: "nowrap", fontSize: 12.5 }}>
                            {clock(row.asked_at)}
                          </td>
                          <td style={{ minWidth: 220 }}>{row.text}</td>
                          <td>
                            <StatusChip tone={OUTCOME[result].tone} size="small">
                              {OUTCOME[result].label}
                            </StatusChip>
                            {row.injection_seen && (
                              <StatusChip tone="fail" size="small" className="oa-chip-gap">
                                Instructions ignored
                              </StatusChip>
                            )}
                          </td>
                          <td data-align="right">{row.queries}</td>
                          <td data-align="right">
                            <button
                              type="button"
                              className="ds-btn"
                              data-tone="ghost"
                              data-size="small"
                              disabled={asking}
                              onClick={() => {
                                setQuestion(row.text);
                                void ask(row.text);
                              }}
                            >
                              Ask again
                            </button>
                          </td>
                        </Reveal>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </Card>
          )}
        </section>
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
/* The plan as a chain                                                 */
/* ------------------------------------------------------------------ */
function planChain(answer: Answer, plan: PlanStep[], role: string, name: string): ChainItem[] {
  const items: ChainItem[] = [];
  items.push({
    key: "read",
    tone: plan.length ? "accent" : "warn",
    state: "done",
    marker: "Q",
    content: (
      <div className="oa-step">
        <p className="oa-step-title">The question was read</p>
        <p className="oa-step-text">
          {plan.length
            ? `Read as: ${answer.reading}`
            : "No reviewed query matches this question, so nothing ran. The planner refuses rather than improvises."}
        </p>
        {answer.injection_seen && (
          <p className="oa-step-flag">
            The attached document contained instructions. It was read as text from outside; the plan did not grow.
          </p>
        )}
      </div>
    ),
  });

  plan.forEach((step, index) => {
    const evidence: Evidence | undefined = answer.evidence[index];
    const blocked = !evidence && index === answer.evidence.length && Boolean(answer.refused) && /role|whole-company/i.test(answer.refused);
    const skipped = !evidence && !blocked;
    const domains = domainsOf(step.capability).map((id) => DOMAIN_BY_ID[id].label).join(" + ");
    items.push({
      key: `step-${index}`,
      tone: blocked ? "fail" : skipped ? "info" : "accent",
      state: blocked ? "active" : skipped ? "waiting" : "done",
      marker: String(index + 1).padStart(2, "0"),
      content: (
        <div className="oa-step" data-state={blocked ? "blocked" : skipped ? "skipped" : "ran"}>
          <p className="oa-step-title">
            {capabilityWords(step.capability)}
            <span className="oa-step-domain">{domains}</span>
          </p>
          <ul className="oa-checks">
            <li data-ok={blocked ? "no" : skipped ? "skip" : "yes"}>
              <b>Role check</b>
              {blocked
                ? `${plain(answer.refused)} ${name} is ${roleWords(role).toLowerCase()}. Nothing ran.`
                : skipped
                  ? "Not reached"
                  : `passed for ${roleWords(role).toLowerCase()}`}
            </li>
            {!blocked && !skipped && evidence && (
              <>
                <li data-ok="yes">
                  <b>Row filter</b>
                  {filterWords(evidence.filter_applied)}
                </li>
                <li data-ok={evidence.row_count > 0 ? "yes" : "empty"}>
                  <b>Database</b>
                  {grouped(evidence.row_count)} {evidence.row_count === 1 ? "row" : "rows"} in {evidence.duration_ms} ms, read at {clock(evidence.read_at)}
                </li>
              </>
            )}
            {skipped && (
              <li data-ok="skip">
                <b>Not run</b>
                {answer.refused ? refusalCause(answer.refused) : "The step before it ended the plan"}
              </li>
            )}
          </ul>
          {step.from_step !== null && (
            <p className="oa-step-note">Takes the {step.takes.replace("_id", "")} found by step {step.from_step + 1}, never a value typed into the question.</p>
          )}
        </div>
      ),
    });
  });

  const outcome = outcomeOf(answer.refused, answer.injection_seen);
  items.push({
    key: "write",
    tone: outcome === "answered" ? "pass" : outcome === "not-permitted" ? "fail" : "warn",
    state: "done",
    marker: outcome === "answered" ? "✓" : "×",
    content: (
      <div className="oa-step">
        <p className="oa-step-title">{outcome === "answered" ? "The answer was written" : "The answer is a refusal"}</p>
        <p className="oa-step-text">
          {outcome === "answered"
            ? `The ${answer.engine === "external" ? "external model" : "built-in writer"} was handed only the rows and wrote the sentence. Every figure in it came from the database.`
            : `${refusalCause(answer.refused)}. Took ${answer.seconds.toFixed(2)} s.`}
        </p>
      </div>
    ),
  });
  return items;
}

/* ------------------------------------------------------------------ */
/* The answer, with every number opening its trace                      */
/* ------------------------------------------------------------------ */
function AnswerBody({ answer }: { answer: Answer }) {
  const sources = answer.evidence;
  const spoken = sources.filter((step) => !step.capability.startsWith("find_"));
  const lines = answer.ok ? sentences(answer.text, spoken.length) : [];
  const aligned = lines.length === spoken.length;

  const withFigures = (text: string, evidence: Evidence | undefined, sentence: string) => {
    if (!evidence) return text;
    const index = sources.indexOf(evidence) + 1;
    const parts = text.split(NUMBER);
    return parts.map((part, position) =>
      position % 2 === 1 ? (
        <Figure
          key={position}
          value={part}
          content={() => evidenceTrace({ figure: part, evidence, index, sentence, reading: answer.reading, engine: answer.engine })}
        />
      ) : (
        <span key={position}>{part}</span>
      ),
    );
  };

  return (
    <div className="oa-answer">
      <div className="oa-answer-chips">
        <StatusChip tone="neutral">{answer.engine === "external" ? "External model wrote the words" : "Built-in engine"}</StatusChip>
        {answer.injection_seen && <StatusChip tone="fail">Instructions in the document ignored</StatusChip>}
      </div>

      {answer.ok ? (
        <p className="oa-answer-text">
          {aligned
            ? lines.map((line, index) => (
                <span key={index} className="oa-answer-line" style={{ "--ds-d": `${index * 120}ms` } as React.CSSProperties}>
                  {withFigures(line, spoken[index], line)}{" "}
                </span>
              ))
            : withFigures(answer.text, spoken[0] ?? sources[0], answer.text)}
        </p>
      ) : (
        <div>
          <p className="oa-answer-text oa-answer-refused">{plain(answer.refused)}</p>
          <p className="oa-answer-cause">{refusalCause(answer.refused)}.</p>
          {/Nothing on this account matches/.test(answer.refused) && (
            <p className="oa-answer-cause">
              The refusal does not confirm the name exists: it says the same whether the account is somebody else&rsquo;s or
              nobody&rsquo;s.
            </p>
          )}
        </div>
      )}

      {answer.injection_seen && (
        <Banner tone="fail" title="The attached document contained instructions">
          They were read as text from outside and nothing was done about them: the plan is the one the question alone
          produces, no address was repeated back, and no proposal was approved.
        </Banner>
      )}

      <dl className="oa-answer-stats">
        <div>
          <dt className="ds-mono-label">Queries run</dt>
          <dd>
            <Figure
              value={String(answer.queries)}
              content={counted(
                "Queries run for this question",
                String(answer.queries),
                "count of reviewed queries that ran, in plan order",
                sources.map((step, index) => ({
                  label: `Step ${index + 1}`,
                  value: capabilityWords(step.capability),
                  source: filterWords(step.filter_applied),
                  sourceKind: "Ran",
                })),
                "Counted by the server",
                "Each query is logged in the access record with who ran it.",
              )}
            />
          </dd>
        </div>
        <div>
          <dt className="ds-mono-label">Rows read</dt>
          <dd>
            <Figure
              value={grouped(answer.rows_read)}
              content={counted(
                "Rows read for this question",
                grouped(answer.rows_read),
                `sum of rows returned by each query = ${sources.map((step) => step.row_count).join(" + ") || "0"}`,
                sources.map((step) => ({
                  label: capabilityWords(step.capability),
                  value: `${grouped(step.row_count)} rows`,
                  source: `Read at ${clock(step.read_at)}`,
                  sourceKind: "Query",
                })),
              )}
            />
          </dd>
        </div>
        <div>
          <dt className="ds-mono-label">Took</dt>
          <dd>
            <Figure
              value={`${answer.seconds.toFixed(2)} s`}
              content={counted(
                "Time from question to answer",
                `${answer.seconds.toFixed(2)} s`,
                "measured by the server, from reading the question to writing the answer",
                sources.map((step) => ({
                  label: capabilityWords(step.capability),
                  value: `${step.duration_ms} ms`,
                  source: "Time inside the database",
                  sourceKind: "Query",
                })),
                "Measured by the server",
                "Nothing here is a language model counting.",
              )}
            />
          </dd>
        </div>
      </dl>

      {sources.length > 0 && (
        <div className="oa-sources">
          <p className="ds-mono-label">Where it came from</p>
          <ol>
            {sources.map((step, index) => (
              <li key={index} className="oa-source" style={{ "--ds-d": `${index * 90}ms` } as React.CSSProperties}>
                <span className="oa-source-index">{index + 1}</span>
                <div style={{ minWidth: 0 }}>
                  <p className="oa-source-title">{capabilityWords(step.capability)}</p>
                  <p className="oa-source-meta">
                    {filterWords(step.filter_applied)} · read at {clock(step.read_at)} · {step.duration_ms} ms
                  </p>
                </div>
                <Figure
                  value={`${grouped(step.row_count)} ${step.row_count === 1 ? "row" : "rows"}`}
                  content={evidenceTrace({ figure: String(step.row_count), evidence: step, index: index + 1, reading: answer.reading, engine: answer.engine })}
                  className="oa-source-figure"
                />
              </li>
            ))}
          </ol>
        </div>
      )}

      {answer.proposals.length > 0 && (
        <div className="oa-raised">
          <p className="ds-mono-label">Raised for a person to decide</p>
          {answer.proposals.map((proposal) => (
            <Link key={proposal.id} href="/proposals" className="oa-raised-item">
              <StatusChip tone="warn" pulse size="small">
                Needs {proposal.needs_role_label.toLowerCase()}
              </StatusChip>
              <span>{proposal.summary}</span>
              <span className="ds-mono">{proposal.reference} →</span>
            </Link>
          ))}
          <p className="oa-raised-note">Suggested, never done. Approving one records a decision; nothing in this product acts on it.</p>
        </div>
      )}
    </div>
  );
}
