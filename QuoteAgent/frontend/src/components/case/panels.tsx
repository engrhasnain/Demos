"use client";

import type { CSSProperties } from "react";

import { Button, Empty, Stamp } from "@/design/Surface";
import { CountUp } from "@/design/CountUp";
import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip, type ChipTone } from "@/design/StatusChip";
import { dateAndTime, duration, money, words } from "@/lib/format";
import type { Approval, CaseDetail, CaseEvent, QuoteVersion } from "@/lib/types";
import { Figure } from "@/components/trace";
import { Ledger, Td, Th, isLive, statusTone } from "@/components/ui";

/* ------------------------------------------------------------------ */
/* The approval gate: where the quote stands with its approvers        */
/* ------------------------------------------------------------------ */
export type GateState = "none" | "waiting" | "approved" | "reopened" | "rejected";

export function gateState(detail: CaseDetail): GateState {
  const approvals = detail.approvals;
  const pending = approvals.filter((approval) => approval.status === "pending");
  const superseded = approvals.some((approval) => approval.status === "superseded");
  if (detail.current_version?.needs_repricing && approvals.some((a) => a.status === "approved")) return "reopened";
  if (superseded && pending.length) return "reopened";
  if (approvals.some((approval) => approval.status === "rejected") && !pending.length) return "rejected";
  if (pending.length) return "waiting";
  if (approvals.some((approval) => approval.status === "approved")) return "approved";
  return "none";
}

const GATE_WORDS: Record<GateState, { title: string; tone: ChipTone; colour: string }> = {
  none: { title: "No approval needed", tone: "neutral", colour: "var(--ds-ink-muted)" },
  waiting: { title: "Waiting for approval", tone: "warn", colour: "var(--ds-warn)" },
  approved: { title: "Approved", tone: "pass", colour: "var(--ds-pass)" },
  reopened: { title: "Re-opened: the numbers moved", tone: "fail", colour: "var(--ds-fail)" },
  rejected: { title: "Rejected", tone: "fail", colour: "var(--ds-fail)" },
};

export function ApprovalGate({ detail }: { detail: CaseDetail }) {
  const state = gateState(detail);
  const words_ = GATE_WORDS[state];
  const pending = detail.approvals.filter((approval) => approval.status === "pending");
  const superseded = detail.approvals.filter((approval) => approval.status === "superseded");
  const detailText =
    state === "reopened"
      ? superseded.length
        ? `${superseded.length} approval${superseded.length > 1 ? "s were" : " was"} given on figures that have since changed, so ${pending.length || "it"} ${pending.length === 1 ? "is" : "are"} asked for again.`
        : "The quote has to be re-priced; the approval already given no longer covers these figures."
      : state === "waiting"
        ? pending.map((approval) => `${approval.required_role_label}: ${approval.title}`).join(" · ")
        : state === "approved"
          ? detail.approvals
              .filter((approval) => approval.status === "approved")
              .map((approval) => `${approval.title}, by ${approval.decided_by || "an approver"}`)
              .join(" · ")
          : state === "rejected"
            ? "An approver said no. Re-price or change the terms."
            : "Every line is above the margin floor and the quote is under the director's threshold.";

  return (
    <div className="qa-gate" data-state={state} role="status" aria-label={`Approval: ${words_.title}`}>
      <div className="qa-gate-ring qa-gate-shake" aria-hidden>
        <svg viewBox="0 0 54 54" width="54" height="54">
          <circle cx="27" cy="27" r="25" fill="none" stroke="var(--ds-ink-line)" strokeWidth="2" />
          <g className="qa-gate-spin">
            <path
              className="qa-gate-arc qa-gate-arc-a"
              d="M27 4 A23 23 0 0 1 50 27"
              fill="none"
              stroke={words_.colour}
              strokeWidth="3.5"
              strokeLinecap="round"
            />
            <path
              className="qa-gate-arc qa-gate-arc-b"
              d="M27 50 A23 23 0 0 1 4 27"
              fill="none"
              stroke={words_.colour}
              strokeWidth="3.5"
              strokeLinecap="round"
            />
          </g>
          {state === "approved" && (
            <path d="M18 27.5 L24.5 34 L36.5 21" fill="none" stroke="var(--ds-pass)" strokeWidth="3.5" strokeLinecap="round" strokeLinejoin="round" />
          )}
          {(state === "reopened" || state === "rejected") && (
            <path d="M27 17 V30 M27 36 V37" fill="none" stroke="var(--ds-fail)" strokeWidth="3.5" strokeLinecap="round" />
          )}
          {state === "waiting" && <circle cx="27" cy="27" r="6" fill="var(--ds-warn)" />}
          {state === "none" && <circle cx="27" cy="27" r="4" fill="var(--ds-ink-muted)" />}
        </svg>
      </div>
      <div style={{ minWidth: 0 }}>
        <span className="ds-mono-label">Approval gate</span>
        <p style={{ margin: "6px 0 0", fontWeight: 600, fontSize: 16 }}>
          <StatusChip tone={words_.tone} surface="dark" pulse={state === "waiting" || state === "reopened"}>
            {words_.title}
          </StatusChip>
        </p>
        <p style={{ margin: "8px 0 0", fontSize: 12.5, lineHeight: 1.5, color: "var(--ds-ink-muted)" }}>{detailText}</p>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Questions                                                           */
/* ------------------------------------------------------------------ */
export function QuestionsPanel({ detail }: { detail: CaseDetail }) {
  const rounds = detail.questions.rounds;
  if (!rounds.length) {
    return <Empty title="No questions were needed">Every line said enough to be priced.</Empty>;
  }

  return (
    <div style={{ display: "grid", gap: 24 }}>
      {detail.questions.statement && (
        <p style={{ margin: 0, fontSize: 13.5, color: "var(--ds-text-2)" }}>{detail.questions.statement}</p>
      )}
      {rounds.map((round) => (
        <div key={round.round_number}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 12 }}>
            <p className="ds-mono-label" style={{ margin: 0 }}>
              Round {round.round_number} · one email
            </p>
            <span className="ds-mono" style={{ fontSize: 12, color: "var(--ds-text-3)" }}>
              {round.answered} of {round.asked} answered
            </span>
          </div>
          <div className="qa-round-meter" style={{ marginTop: 8 }}>
            <span style={{ transform: `scaleX(${round.asked ? round.answered / round.asked : 0})` }} />
          </div>
          <ul style={{ listStyle: "none", margin: "14px 0 0", padding: 0, display: "grid", gap: 10 }}>
            {round.questions.map((question, index) => (
              <Reveal
                as="li"
                key={question.id}
                index={index}
                y={24}
                className="qa-question"
                data-answered={question.status === "answered" ? "" : undefined}
              >
                <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                  <Stamp>line {String(question.line_number).padStart(2, "0")}</Stamp>
                  <StatusChip
                    tone={question.status === "answered" ? "pass" : "warn"}
                    pulse={question.status !== "answered"}
                    size="small"
                  >
                    {question.status === "answered" ? "Answered" : "Open"}
                  </StatusChip>
                  <span style={{ fontSize: 12, color: "var(--ds-text-3)" }}>{words(question.kind)}</span>
                </div>
                <p style={{ margin: "10px 0 0", fontSize: 14, lineHeight: 1.55 }}>{question.question}</p>
                {question.question_chinese && (
                  <p style={{ margin: "4px 0 0", fontSize: 14, lineHeight: 1.55, color: "var(--ds-text-2)" }}>
                    {question.question_chinese}
                  </p>
                )}
                {question.options.length > 0 && (
                  <p style={{ margin: "10px 0 0", display: "flex", flexWrap: "wrap", gap: 6 }}>
                    {question.options.map((option) => (
                      <Stamp key={option} tone="light">
                        {option}
                      </Stamp>
                    ))}
                  </p>
                )}
                {question.answer && (
                  <p style={{ margin: "12px 0 0", padding: "8px 12px", borderLeft: "3px solid var(--ds-pass)", background: "var(--ds-pass-soft)", borderRadius: 0, fontSize: 13 }}>
                    <span style={{ color: "var(--ds-pass-ink)", fontWeight: 600 }}>Customer answered: </span>
                    {question.answer}
                    {typeof question.answer_understood_as?.value === "string" &&
                      question.answer_understood_as.value && (
                        <span style={{ marginLeft: 6, color: "var(--ds-text-2)" }}>
                          (understood as {String(question.answer_understood_as.value)})
                        </span>
                      )}
                  </p>
                )}
              </Reveal>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Approvals                                                           */
/* ------------------------------------------------------------------ */
type ApprovalLine = {
  line_number: number;
  part: string;
  margin_percent?: string;
  unit_price?: string;
  unit_cost?: string;
  shortfall_percent?: string;
  price_build_up?: { subject: string; steps: [] };
};

function approvalTone(approval: Approval): ChipTone {
  if (approval.status === "approved") return "pass";
  if (approval.status === "rejected" || approval.status === "superseded") return "fail";
  if (approval.status === "pending") return "warn";
  return "neutral";
}

const APPROVAL_WORDS: Record<string, string> = {
  pending: "Waiting",
  approved: "Approved",
  rejected: "Rejected",
  withdrawn: "No longer needed",
  superseded: "Re-opened: numbers moved",
};

export function ApprovalsPanel({
  detail,
  onDecide,
  busy,
}: {
  detail: CaseDetail;
  onDecide: (id: number, approved: boolean) => void;
  busy: string | null;
}) {
  if (!detail.approvals.length) {
    return <Empty title="Nothing needs approving">Every line is above the margin floor and the total is under the director&rsquo;s threshold.</Empty>;
  }
  const ordered = detail.approvals
    .slice()
    .sort((a, b) => (a.status === "pending" ? -1 : b.status === "pending" ? 1 : 0));

  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 14 }}>
      {ordered.map((approval, index) => {
        const pending = approval.status === "pending";
        const superseded = approval.status === "superseded";
        const lines = (approval.detail?.lines as ApprovalLine[] | undefined) ?? [];

        return (
          <Reveal
            as="li"
            key={approval.id}
            index={index}
            y={28}
            className="qa-approval"
            data-status={approval.status}
          >
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: 14 }}>
              <div style={{ minWidth: 0 }}>
                <p style={{ margin: 0, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, fontWeight: 600, fontSize: 15 }}>
                  {approval.title}
                  <StatusChip tone={approvalTone(approval)} pulse={pending || superseded}>
                    {APPROVAL_WORDS[approval.status] ?? approval.status}
                  </StatusChip>
                </p>
                <p style={{ margin: "6px 0 0", fontSize: 12.5, color: "var(--ds-text-3)" }}>
                  Needs the {approval.required_role_label.toLowerCase()}
                  {approval.decided_by && ` · decided by ${approval.decided_by}`}
                  {approval.decided_at && ` · ${dateAndTime(approval.decided_at)}`}
                </p>
                {approval.reason && (
                  <p style={{ margin: "6px 0 0", fontSize: 13, color: "var(--ds-text-2)" }}>{approval.reason}</p>
                )}
                {superseded && (
                  <p className="qa-reopened-note">
                    {approval.comment || "The quote was re-priced after this decision."} The approval has been asked
                    for again on the new figures.
                  </p>
                )}
              </div>
              {pending && (
                <div style={{ display: "flex", gap: 8 }}>
                  <Button
                    size="small"
                    tone="primary"
                    busy={busy === `approve-${approval.id}`}
                    onClick={() => onDecide(approval.id, true)}
                  >
                    Approve
                  </Button>
                  <Button
                    size="small"
                    tone="danger"
                    busy={busy === `reject-${approval.id}`}
                    onClick={() => onDecide(approval.id, false)}
                  >
                    Reject
                  </Button>
                </div>
              )}
            </div>

            {lines.length > 0 && (
              <div style={{ marginTop: 14, border: "1px solid var(--ds-line)", borderRadius: 3, overflow: "hidden" }}>
                <Ledger
                  head={
                    <>
                      <Th width="4rem">Line</Th>
                      <Th>Part</Th>
                      <Th align="right">Unit price</Th>
                      <Th align="right">Unit cost</Th>
                      <Th align="right">Margin</Th>
                    </>
                  }
                >
                  {lines.slice(0, 8).map((row) => (
                    <tr key={row.line_number}>
                      <Td className="ds-mono" style={{ fontSize: 12 }}>
                        {String(row.line_number).padStart(2, "0")}
                      </Td>
                      <Td>
                        <Stamp>{row.part}</Stamp>
                      </Td>
                      <Td align="right">
                        <Figure
                          value={money(row.unit_price)}
                          heading={`Line ${row.line_number} price build-up`}
                          trace={row.price_build_up as never}
                        />
                      </Td>
                      <Td align="right">
                        <Figure
                          value={money(row.unit_cost)}
                          heading={`Line ${row.line_number} unit cost`}
                          explain={{
                            formula: "The standard cost of the part, from the catalogue record the price was built on",
                            inputs: [{ label: "Part", value: row.part, source: "Catalogue record", sourceKind: "Catalogue" }],
                          }}
                        />
                      </Td>
                      <Td align="right" style={{ color: "var(--ds-fail-ink)", fontWeight: 600 }}>
                        <Figure
                          value={`${row.margin_percent}%`}
                          heading={`Line ${row.line_number} margin`}
                          trace={row.price_build_up as never}
                          explain={{
                            formula: `(unit price ${money(row.unit_price)} − unit cost ${money(row.unit_cost)}) ÷ unit price × 100`,
                            inputs: [
                              { label: "Unit price", value: money(row.unit_price), source: "Pricing engine", sourceKind: "Quote line" },
                              { label: "Unit cost", value: money(row.unit_cost), source: "Catalogue record", sourceKind: "Catalogue" },
                              ...(row.shortfall_percent
                                ? [{ label: "Short of the floor by", value: `${row.shortfall_percent}%`, source: "Customer margin floor", sourceKind: "Company policy" }]
                                : []),
                            ],
                          }}
                        />
                      </Td>
                    </tr>
                  ))}
                </Ledger>
                {lines.length > 8 && (
                  <p style={{ margin: 0, padding: "8px 14px", fontSize: 12, color: "var(--ds-text-3)" }}>
                    and {lines.length - 8} more
                  </p>
                )}
              </div>
            )}
          </Reveal>
        );
      })}
    </ul>
  );
}

/* ------------------------------------------------------------------ */
/* Emails                                                              */
/* ------------------------------------------------------------------ */
export function EmailsPanel({
  detail,
  onSend,
  busy,
}: {
  detail: CaseDetail;
  onSend: (id: number) => void;
  busy: string | null;
}) {
  if (!detail.messages.length) return <Empty title="No emails yet" />;
  return (
    <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 14 }}>
      {detail.messages.map((message, index) => (
        <Reveal
          as="li"
          key={message.id}
          index={index}
          y={24}
          className="qa-email"
          data-waiting={message.awaiting_approval ? "" : undefined}
          data-direction={message.direction}
        >
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-start", justifyContent: "space-between", gap: 12 }}>
            <div style={{ minWidth: 0 }}>
              <p style={{ margin: 0, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8, fontWeight: 600 }}>
                {message.subject || "(no subject)"}
                <StatusChip tone={message.direction === "inbound" ? "neutral" : "accent"} size="small">
                  {message.direction === "inbound" ? "Received" : "Outgoing"}
                </StatusChip>
                {message.awaiting_approval && (
                  <StatusChip tone="warn" size="small" pulse>
                    Waiting for approval
                  </StatusChip>
                )}
              </p>
              <p className="ds-mono" style={{ margin: "6px 0 0", fontSize: 11.5, color: "var(--ds-text-3)", overflowWrap: "anywhere" }}>
                {message.direction === "inbound" ? `From ${message.sender}` : `To ${message.recipients.join(", ")}`} ·{" "}
                {dateAndTime(message.sent_at ?? message.occurred_at)}
              </p>
            </div>
            {message.awaiting_approval && (
              <Button size="small" tone="primary" busy={busy === `send-${message.id}`} onClick={() => onSend(message.id)}>
                Approve and send
              </Button>
            )}
          </div>

          {message.attachments.length > 0 && (
            <ul style={{ listStyle: "none", margin: "10px 0 0", padding: 0, display: "flex", flexWrap: "wrap", gap: 6 }}>
              {message.attachments.map((attachment) => (
                <li key={attachment.id}>
                  <Stamp title={attachment.note} tone="light">
                    {attachment.filename} · {attachment.row_count} rows · read with {attachment.read_with}
                  </Stamp>
                </li>
              ))}
            </ul>
          )}

          <pre className="qa-email-body">{message.body}</pre>
        </Reveal>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ */
/* Timeline: a node chain, a pulse running down it                     */
/* ------------------------------------------------------------------ */
const ACTOR_TONE: Record<string, ChipTone> = {
  agent: "accent",
  person: "pass",
  customer: "warn",
  supplier: "warn",
  system: "info",
};

export function TimelinePanel({
  events,
  elapsed,
}: {
  events: CaseEvent[];
  elapsed: Record<string, string | number>;
}) {
  const totalCost = events.reduce((sum, event) => sum + Number(event.cost_usd || 0), 0);
  const engines = Array.from(new Set(events.map((event) => event.engine).filter(Boolean)));
  const working = Number(elapsed.agent_working_seconds ?? 0);
  const minutes = Number(elapsed.elapsed_minutes ?? 0);

  const tiles: { label: string; value: number; decimals: number; final: string; explain: string }[] = [
    { label: "Steps", value: events.length, decimals: 0, final: String(events.length), explain: "Every event written to this request's record, in order" },
    {
      label: "Agent working time",
      value: working,
      decimals: 2,
      final: `${working} s`,
      explain: "The time the agent itself spent on the steps it ran, added up by the server; waiting for people is not included",
    },
    {
      label: "Elapsed",
      value: minutes,
      decimals: 1,
      final: `${minutes} min`,
      explain: "From the request arriving to the latest event on this record",
    },
    {
      label: "Reasoning cost",
      value: totalCost,
      decimals: 4,
      final: `$${totalCost.toFixed(4)}`,
      explain: "The cost of every external model call on this request; the built-in engine costs nothing",
    },
  ];

  return (
    <div>
      <div className="qa-tiles">
        {tiles.map((tile, index) => (
          <Reveal key={tile.label} index={index} className="qa-tile">
            <p className="ds-mono-label" style={{ margin: 0 }}>
              {tile.label}
            </p>
            <p className="ds-title ds-num" style={{ margin: "8px 0 0", fontSize: 24 }}>
              <Figure
                value={tile.final}
                count={tile.value}
                decimals={tile.decimals}
                heading={tile.label}
                explain={{
                  formula: tile.explain,
                  inputs: events
                    .filter((event) => tile.label !== "Reasoning cost" || Number(event.cost_usd) > 0)
                    .slice(0, 10)
                    .map((event) => ({
                      label: event.summary.slice(0, 70),
                      value:
                        tile.label === "Agent working time"
                          ? duration(event.duration_ms)
                          : tile.label === "Reasoning cost"
                            ? `$${Number(event.cost_usd).toFixed(4)}`
                            : dateAndTime(event.occurred_at),
                      source: words(event.actor_type),
                      sourceKind: "Timeline event",
                    })),
                }}
              />
            </p>
          </Reveal>
        ))}
      </div>
      <p style={{ margin: "14px 0 22px", fontSize: 12.5, color: "var(--ds-text-3)" }}>
        Engines used on this request:{" "}
        {engines.length ? engines.map((engine) => (engine === "built-in" ? "the built-in engine" : `${engine}`)).join(", ") : "none yet"}.
        Every price came from the pricing engine.
      </p>

      <NodeChain
        items={events.map((event) => ({
          key: String(event.id),
          tone: ACTOR_TONE[event.actor_type] ?? "info",
          marker: event.actor_type === "agent" ? "A" : event.actor_type === "person" ? "P" : event.actor_type === "customer" ? "C" : event.actor_type === "supplier" ? "S" : "·",
          content: (
            <div style={{ paddingTop: 3 }}>
              <p className="ds-mono" style={{ margin: 0, display: "flex", flexWrap: "wrap", gap: "2px 10px", fontSize: 11.5, color: "var(--ds-text-3)" }}>
                <span>{dateAndTime(event.occurred_at)}</span>
                <span>{words(event.actor_type)}</span>
                {event.actor_name && <span>{event.actor_name}</span>}
                {event.duration_ms > 0 && <span>{duration(event.duration_ms)}</span>}
                {event.engine && (
                  <span style={{ color: "var(--ds-accent-ink)", fontWeight: 600 }}>
                    {event.engine === "built-in" ? "built-in engine" : `${event.engine} engine`}
                  </span>
                )}
                {Number(event.cost_usd) > 0 && <span>${Number(event.cost_usd).toFixed(4)}</span>}
              </p>
              <p style={{ margin: "4px 0 0", fontSize: 14, lineHeight: 1.55 }}>{event.summary}</p>
            </div>
          ),
        }))}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Versions                                                            */
/* ------------------------------------------------------------------ */
const CHANGE_WORDS: Record<string, string> = {
  added: "Added",
  removed: "Removed",
  quantity_changed: "Quantity changed",
  changed: "Changed",
  unchanged: "Unchanged",
};

export function VersionsPanel({
  versions,
  current,
}: {
  versions: QuoteVersion[];
  current: QuoteVersion | null;
}) {
  const changes = current?.change_log ?? [];
  return (
    <div style={{ display: "grid", gap: 22 }}>
      <div style={{ border: "1px solid var(--ds-line)", borderRadius: 3, overflow: "hidden" }}>
        <Ledger
          head={
            <>
              <Th width="6rem">Version</Th>
              <Th width="12rem">State</Th>
              <Th>Terms</Th>
              <Th align="right">Total</Th>
              <Th width="10rem">Sent</Th>
            </>
          }
        >
          {versions.map((version, index) => (
            <Reveal as="tr" key={version.id} index={index} y={20}>
              <Td className="ds-mono" style={{ fontSize: 12.5, fontWeight: 600 }}>
                Version {version.version_number}
              </Td>
              <Td>
                <StatusChip tone={statusTone(version.status)} pulse={isLive(version.status)} size="small">
                  {words(version.status)}
                </StatusChip>
              </Td>
              <Td>
                {version.incoterm} {version.named_place}
              </Td>
              <Td align="right" style={{ fontWeight: 600 }}>
                <Figure
                  value={money(version.totals.grand_total, version.currency)}
                  heading={`Total of version ${version.version_number}`}
                  trace={version.totals_trace}
                />
              </Td>
              <Td>{version.sent_at ? dateAndTime(version.sent_at) : "Not sent"}</Td>
            </Reveal>
          ))}
        </Ledger>
      </div>

      {changes.length > 0 && (
        <div>
          <p className="ds-mono-label" style={{ margin: "0 0 10px" }}>
            What changed in version {current?.version_number}
          </p>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 8 }}>
            {changes
              .filter((change) => change.kind !== "unchanged")
              .map((change, index) => (
                <Reveal
                  as="li"
                  key={index}
                  index={index}
                  y={20}
                  from="left"
                  style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, padding: "10px 14px", borderRadius: 3, border: "1px solid var(--ds-line)", fontSize: 13 } as CSSProperties}
                >
                  <Stamp>line {String(change.line_number).padStart(2, "0")}</Stamp>
                  <StatusChip
                    tone={change.kind === "added" ? "pass" : change.kind === "removed" ? "fail" : "warn"}
                    size="small"
                  >
                    {CHANGE_WORDS[change.kind] ?? words(change.kind)}
                  </StatusChip>
                  <span style={{ minWidth: 0, flex: 1 }}>{change.description}</span>
                  <span style={{ fontSize: 12, color: "var(--ds-text-3)" }}>{change.note}</span>
                </Reveal>
              ))}
          </ul>
          <p style={{ margin: "10px 0 0", fontSize: 12.5, color: "var(--ds-text-3)" }}>
            <CountUp to={changes.filter((change) => change.kind === "unchanged").length} /> lines carried over
            unchanged, with their prices intact.
          </p>
        </div>
      )}
    </div>
  );
}
