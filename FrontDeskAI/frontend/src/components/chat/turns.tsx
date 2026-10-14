"use client";

/**
 * One turn of a conversation, as the customer and the staff both see it.
 *
 * The words are what the desk said. Under them, a card built from the same
 * tool result the server stored with the turn: the order as our system and
 * the carrier each see it, the slots the scheduler found, the booking, the
 * return proposal, the handover. Nothing on a card is composed by the engine.
 */

import type { CSSProperties, ReactNode } from "react";

import { StatusChip } from "@/design/StatusChip";
import { Figure } from "@/components/trace";
import { clock, dayAndTime, engineWord, money, parseWhen, toolWord } from "@/lib/format";
import type { Slot, Turn } from "@/lib/types";

type Result = Record<string, unknown>;

function asText(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

function taipei(iso: string, withDay = true): string {
  const date = parseWhen(iso);
  if (!date) return iso;
  return date.toLocaleString("en-GB", {
    timeZone: "Asia/Taipei",
    ...(withDay ? { weekday: "long", day: "2-digit", month: "long" } : {}),
    hour: "2-digit",
    minute: "2-digit",
  });
}

function date(iso: unknown): string {
  const text = asText(iso);
  if (!text) return "—";
  const value = new Date(text.length === 10 ? `${text}T00:00:00Z` : text);
  return Number.isNaN(value.getTime())
    ? text
    : value.toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

/* ------------------------------------------------------------------ */
/* The meta line under every desk reply                                */
/* ------------------------------------------------------------------ */
function DeskMeta({ turn }: { turn: Turn }) {
  return (
    <div className="fd-msg-meta">
      <span>{clock(turn.at)}</span>
      <span aria-hidden>·</span>
      <span>{engineWord(turn.engine)}</span>
      {turn.tool && (
        <>
          <span aria-hidden>·</span>
          <span>{toolWord(turn.tool)}</span>
        </>
      )}
      {turn.intent_label && turn.intent && (
        <>
          <span aria-hidden>·</span>
          <span>
            {turn.intent_label}{" "}
            <Figure
              value={`${Math.round((turn.confidence ?? 0) * 100)}%`}
              heading={`How sure the desk was that this was "${turn.intent_label}"`}
              origin="Counted by the intent rules"
              explain={{
                formula:
                  "The words of the message are matched against a fixed list of phrases for each intent; the strongest match wins and its score becomes the confidence. A model, if one is configured, may only choose from the same list.",
                result: `${Math.round((turn.confidence ?? 0) * 100)}%`,
                inputs: [
                  { label: "Intent chosen", value: turn.intent_label, sourceKind: "Intent list" },
                  { label: "Engine", value: engineWord(turn.engine), sourceKind: "This reply" },
                ],
              }}
            />
          </span>
        </>
      )}
      {turn.duration_ms > 0 && (
        <>
          <span aria-hidden>·</span>
          <span>
            <Figure
              value={`${turn.duration_ms} milliseconds`}
              heading="How long the reply took on the server"
              origin="Measured by the server"
              explain={{
                formula: "Time from the message arriving to the reply being written, measured on the server for this one turn",
                result: `${turn.duration_ms} milliseconds`,
                inputs: [{ label: "Turn", value: `#${turn.id}`, source: "The conversation record", sourceKind: "Turn" }],
              }}
            />
          </span>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Cards                                                               */
/* ------------------------------------------------------------------ */
function OrderCard({ result }: { result: Result }) {
  const lines = (result.lines as Result[] | undefined) ?? [];
  const events = (result.carrier_events as Result[] | undefined) ?? [];
  const gap = result.disagreement as Result | null | undefined;
  const latest = events[events.length - 1];
  const currency = asText(result.currency);
  return (
    <div className="fd-card-rich fd-spring" data-tone={gap ? "warn" : "pass"}>
      <div className="fd-card-rich-head">
        <span className="ds-stamp">{asText(result.number)}</span>
        <StatusChip tone={gap ? "warn" : "pass"} size="small">
          {gap ? "The two systems disagree" : "Both systems agree"}
        </StatusChip>
      </div>
      <div className="fd-two-systems">
        <div>
          <p className="ds-mono-label">Our system says</p>
          <p className="fd-system-says">{asText(result.status) || "—"}</p>
          <p className="fd-system-sub">
            Placed {date(result.placed_on)} · despatched {date(result.despatched_on)}
          </p>
        </div>
        <div className="fd-two-systems-link" aria-hidden>
          <span />
        </div>
        <div>
          <p className="ds-mono-label">{asText(result.carrier) || "The carrier"} says</p>
          <p className="fd-system-says">{asText(result.latest) || "nothing yet"}</p>
          <p className="fd-system-sub">
            {latest ? `${asText(latest.place) || "—"} · ${dayAndTime(asText(latest.occurred_at))}` : "No scan on record"}
          </p>
        </div>
      </div>
      {gap && (
        <p className="fd-gap">
          <b>{asText(gap.summary)}</b> Our system says {asText(gap.system_says)}; the carrier says {asText(gap.carrier_says)}.
          A person is chasing it rather than the desk guessing.
        </p>
      )}
      {lines.length > 0 && (
        <ul className="fd-order-lines">
          {lines.slice(0, 4).map((line) => (
            <li key={asText(line.line_number)}>
              <span className="ds-mono">{asText(line.part_code)}</span>
              <span className="fd-order-line-desc">{asText(line.description)}</span>
              <span className="ds-num">× {Number(line.quantity).toLocaleString("en-GB")}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="fd-card-rich-foot">
        <span className="ds-mono-label">Order value</span>
        <Figure
          value={money(asText(result.total), currency)}
          heading={`Value of order ${asText(result.number)}`}
          origin="Read from the order record"
          explain={{
            formula: "The order total as the business system holds it; the desk reads it under this customer's verified scope and does not add anything up itself",
            result: money(asText(result.total), currency),
            inputs: lines.map((line) => ({
              label: `${asText(line.part_code)} · lot ${asText(line.lot_number)}`,
              value: `${Number(line.quantity).toLocaleString("en-GB")} pieces`,
              source: asText(line.description),
              sourceKind: "Order line",
            })),
          }}
        />
      </div>
    </div>
  );
}

function HeldBack() {
  return (
    <div className="fd-held fd-spring">
      <span className="fd-held-ring" aria-hidden />
      <div>
        <p className="ds-mono-label" style={{ margin: 0 }}>
          Nothing shown
        </p>
        <p style={{ margin: "3px 0 0", fontSize: 13 }}>
          The same words come back for an order that is somebody else&apos;s and for one that does not exist, so nothing
          can be learned by guessing.
        </p>
      </div>
    </div>
  );
}

function SlotCards({
  result,
  onBook,
  busy,
  live,
}: {
  result: Result;
  onBook?: (key: string) => void;
  busy?: boolean;
  live: boolean;
}) {
  const slots = ((result.slots as Slot[] | undefined) ?? (result.alternatives as Slot[] | undefined) ?? []).slice(0, 3);
  const ruledOut = (result.ruled_out as Record<string, number> | undefined) ?? {};
  const considered = Number(result.considered ?? 0);
  if (!slots.length) return null;
  return (
    <div className="fd-slots">
      {slots.map((slot, index) => (
        <button
          key={slot.key}
          type="button"
          className="fd-slot fd-spring"
          style={{ "--fd-d": `${index * 90}ms` } as CSSProperties}
          disabled={!live || busy || !onBook}
          onClick={() => onBook?.(slot.key)}
        >
          <span className="ds-mono-label">{slot.shown_as.split(",")[0]}</span>
          <span className="fd-slot-time">{slot.shown_as.split(",")[1]?.trim() ?? slot.shown_as}</span>
          <span className="fd-slot-who">{slot.technician}</span>
          <span className="fd-slot-sub">
            {slot.minutes} minute visit · {slot.travel_minutes} minutes travel
          </span>
          {live && onBook && <span className="fd-slot-take">Take this slot →</span>}
        </button>
      ))}
      {considered > 0 && (
        <p className="fd-slots-note">
          Checked against skills, van stock, travel time either side and working hours:{" "}
          <Figure
            value={`${considered} technicians considered`}
            heading="Technicians the scheduler considered"
            origin="Counted by the scheduler"
            explain={{
              formula: "Every technician is checked against the rules; a slot is offered only when all of them pass. The engine is never asked for a time.",
              result: `${considered} considered, ${slots.length} slots offered`,
              inputs: [
                ...Object.entries(ruledOut).map(([reason, number]) => ({
                  label: reason.replace(/_/g, " "),
                  value: `${number} ruled out`,
                  sourceKind: "Scheduling rule",
                })),
                ...slots.map((slot) => ({
                  label: slot.technician,
                  value: slot.shown_as,
                  source: `${slot.city}, ${slot.travel_minutes} minutes travel`,
                  sourceKind: "Offered",
                })),
              ],
            }}
          />
        </p>
      )}
    </div>
  );
}

function BookingCard({ result }: { result: Result }) {
  return (
    <div className="fd-booked fd-spring-big">
      <span className="fd-booked-check" aria-hidden>
        <svg viewBox="0 0 24 24" width="22" height="22">
          <path d="M5 12.5l4.2 4.2L19 7" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="square" />
        </svg>
      </span>
      <div style={{ minWidth: 0 }}>
        <p className="ds-mono-label" style={{ margin: 0 }}>
          Technician booked
        </p>
        <p className="fd-booked-when">{taipei(asText(result.starts_at))}</p>
        <p className="fd-booked-who">
          {asText(result.technician)} · Taipei time · <span className="ds-stamp">{asText(result.reference)}</span>
        </p>
      </div>
    </div>
  );
}

function HandoverCard({ turn, reference, wording }: { turn: Turn; reference?: string; wording?: string }) {
  const result = (turn.tool_result ?? {}) as Result;
  const ref = reference || asText(result.reference);
  const by = wording || asText(result.reply_by);
  return (
    <div className="fd-handover fd-spring">
      <span className="fd-handover-node" aria-hidden>
        <i />
      </span>
      <div style={{ minWidth: 0 }}>
        <p className="ds-mono-label" style={{ margin: 0 }}>
          Handed to a person
        </p>
        <p style={{ margin: "4px 0 0", fontWeight: 600, fontSize: 14 }}>
          {ref ? <span className="ds-stamp">{ref}</span> : null} {by ? `Reply ${by}` : "A person will reply"}
        </p>
        <p className="fd-system-sub">The conversation so far goes with it, so nobody asks the customer to repeat themselves.</p>
      </div>
    </div>
  );
}

function ReturnCard({ result }: { result: Result }) {
  const triage = (result.triage as Result | undefined) ?? {};
  const cover = (result.cover as Result | undefined) ?? {};
  const confidence = Math.round(Number(triage.confidence ?? 0) * 100);
  return (
    <div className="fd-card-rich fd-spring" data-tone="warn">
      <div className="fd-card-rich-head">
        <span className="ds-stamp">{asText(result.reference)}</span>
        <StatusChip tone="warn" size="small" pulse>
          Waiting for a person to approve
        </StatusChip>
      </div>
      <dl className="fd-facts">
        <div>
          <dt className="ds-mono-label">Against order</dt>
          <dd>{asText(result.order)}</dd>
        </div>
        <div>
          <dt className="ds-mono-label">Part</dt>
          <dd className="ds-mono">{asText(result.part_code)}</dd>
        </div>
        <div>
          <dt className="ds-mono-label">Looks like</dt>
          <dd>
            {triage.confident_enough ? asText(triage.label) : "Not sure yet"}{" "}
            <Figure
              value={`${confidence}%`}
              heading="How sure the triage was"
              origin="Counted by the triage rules"
              explain={{
                formula: "Signals in the customer's own description, each with a weight; below 62% the desk says it is not sure and a person decides",
                result: `${confidence}%`,
                inputs: ((triage.reasons as string[] | undefined) ?? []).map((reason) => ({
                  label: reason,
                  value: "signal",
                  sourceKind: "Description",
                })),
              }}
            />
          </dd>
        </div>
        <div>
          <dt className="ds-mono-label">Cover</dt>
          <dd>{cover.covered ? "Inside the terms" : "Outside the terms"}</dd>
        </div>
      </dl>
      {asText(cover.note) && <p className="fd-system-sub" style={{ marginTop: 10 }}>{asText(cover.note)}</p>}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* The turn                                                            */
/* ------------------------------------------------------------------ */
export function TurnView({
  turn,
  index = 0,
  latestSlots = false,
  onBook,
  busy,
  ticket,
  animate = true,
  variant = "web",
}: {
  turn: Turn;
  index?: number;
  /** This is the newest slot offer: its slots can still be taken. */
  latestSlots?: boolean;
  onBook?: (key: string) => void;
  busy?: boolean;
  ticket?: { reference: string; reply_wording: string } | null;
  animate?: boolean;
  variant?: "web" | "line";
}) {
  const result = (turn.tool_result ?? {}) as Result;
  const mine = turn.speaker === "customer";
  const style = { "--fd-d": `${Math.min(index, 6) * 40}ms` } as CSSProperties;

  if (mine) {
    return (
      <div className="fd-msg" data-side="customer" data-animate={animate ? "" : undefined} data-variant={variant} style={style}>
        <div className="fd-bubble" data-side="customer">
          {turn.text}
          {turn.attachment && <span className="fd-attachment">Photograph · {turn.attachment}</span>}
        </div>
        <span className="fd-msg-meta" data-side="customer">
          {clock(turn.at)} · You
        </span>
      </div>
    );
  }

  let card: ReactNode = null;
  if (turn.tool === "order_status" && result.number) card = <OrderCard result={result} />;
  else if (turn.tool === "order_status" && turn.refusal) card = <HeldBack />;
  else if (turn.tool === "find_slots") card = <SlotCards result={result} onBook={onBook} busy={busy} live={latestSlots} />;
  else if (turn.tool === "book_visit" && result.reference) card = <BookingCard result={result} />;
  else if (turn.tool === "book_visit" && result.taken)
    card = <SlotCards result={result} onBook={onBook} busy={busy} live={latestSlots} />;
  else if (turn.tool === "propose_return") card = <ReturnCard result={result} />;
  else if (turn.tool === "raise_ticket") card = <HandoverCard turn={turn} reference={ticket?.reference} wording={ticket?.reply_wording} />;

  return (
    <div className="fd-msg" data-side="desk" data-animate={animate ? "" : undefined} data-variant={variant} style={style}>
      <span className="fd-desk-avatar" aria-hidden>
        <i />
      </span>
      <div style={{ minWidth: 0, flex: 1 }}>
        <div className="fd-bubble" data-side="desk" data-refused={turn.refusal ? "" : undefined}>
          {turn.text}
        </div>
        {card}
        <DeskMeta turn={turn} />
      </div>
    </div>
  );
}

export function Typing({ variant = "web" }: { variant?: "web" | "line" }) {
  return (
    <div className="fd-msg" data-side="desk" data-animate="" data-variant={variant}>
      <span className="fd-desk-avatar" aria-hidden>
        <i />
      </span>
      <div className="fd-bubble fd-typing" data-side="desk" role="status" aria-label="The desk is replying">
        <span />
        <span />
        <span />
      </div>
    </div>
  );
}
