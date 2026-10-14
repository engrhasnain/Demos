"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { NodeChain } from "@/design/NodeChain";
import { prefersReducedMotion } from "@/design/motion";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Band, Button, Card, Empty, LinkButton, Stat } from "@/design/Surface";
import { Tabs } from "@/design/Tabs";
import { Figure } from "@/components/trace";
import { TurnView } from "@/components/chat/turns";
import { ChannelMark, ErrorNote, Loading, OutcomeChip } from "@/components/ui";
import { api, readUser } from "@/lib/api";
import {
  STATUS_WORDS,
  clock,
  count,
  dayAndTime,
  outcomeOf,
  outcomeOfBrief,
  parseWhen,
  percent,
  plain,
  shorten,
  toolWord,
} from "@/lib/format";
import { useAction, useLoad } from "@/lib/hooks";
import type { AccessRow, Conversation, ConversationBrief, Dashboard, Page, ReturnRequest, Ticket, Visit } from "@/lib/types";

type TabKey = "queue" | "returns" | "conversations" | "visits" | "refused";

export default function DeskPage() {
  const user = readUser();
  const supervisor = ["supervisor", "administrator"].includes(user?.role ?? "");
  const [tab, setTab] = useState<TabKey>("queue");
  const [open, setOpen] = useState<string | null>(null);
  const board = useLoad<Dashboard>("/api/dashboard");
  const tickets = useLoad<{ total: number; items: Ticket[] }>("/api/tickets");
  const returns = useLoad<{ total: number; items: ReturnRequest[] }>("/api/returns?status=proposed");

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const wanted = params.get("tab");
    if (wanted && ["queue", "returns", "conversations", "visits", "refused"].includes(wanted)) setTab(wanted as TabKey);
    const conversation = params.get("conversation");
    if (conversation) {
      setTab("conversations");
      setOpen(conversation);
    }
  }, []);

  const data = board.data;
  const reloadAll = () => {
    board.reload();
    tickets.reload();
    returns.reload();
  };

  const tabs = [
    { key: "queue" as const, label: "With a person", badge: data?.open_tickets },
    { key: "returns" as const, label: "Returns to approve", badge: data?.returns_waiting },
    { key: "conversations" as const, label: "Conversations", badge: undefined },
    { key: "visits" as const, label: "Technician diary", badge: data?.visits_booked },
    ...(supervisor ? [{ key: "refused" as const, label: "Refused reaches", badge: data?.refused_attempts }] : []),
  ];

  return (
    <div>
      <Band top>
        <div className="fd-page-band">
          <div>
            <Reveal y={24}>
              <span className="ds-eyebrow">
                <span className="ds-live-dot" data-tone={data?.desk_open ? "pass" : "warn"} aria-hidden />
                Staff desk <span className="ds-eyebrow-sep">·</span>{" "}
                {data ? (data.desk_open ? "office open in Taipei" : "office closed in Taipei") : "Taipei"}
              </span>
            </Reveal>
            <Reveal index={1} y={32}>
              <h1 className="ds-display ds-band-title">
                The desk.
                <br />
                <span className="fd-light">Everything the assistant could not finish.</span>
              </h1>
            </Reveal>
            <Reveal index={2} y={28}>
              <p className="ds-band-lede">
                Handovers arrive with the conversation already written down and a reply time worked out from Taipei
                office hours. Returns wait here: the desk proposes every one, a person approves it.
              </p>
            </Reveal>
          </div>
          <Reveal index={3} y={28}>
            <div className="ds-stats fd-desk-stats">
              <Stat
                label="Handled alone"
                tone="accent"
                value={
                  <Figure
                    value={percent(data?.handled_share ?? 0)}
                    count={data?.handled_share ?? 0}
                    decimals={1}
                    heading="Conversations the desk finished without a person"
                    explain={{
                      formula: "handled ÷ (handled + handed to a person) × 100",
                      inputs: [
                        { label: "Handled", value: count(data?.resolved ?? 0), sourceKind: "Conversation state" },
                        { label: "Handed to a person", value: count(data?.escalated ?? 0), sourceKind: "Conversation state" },
                      ],
                    }}
                  />
                }
              />
              <Stat
                label="With a person"
                tone="warn"
                value={
                  <Figure
                    value={count(data?.open_tickets ?? 0)}
                    count={data?.open_tickets ?? 0}
                    heading="Open handovers"
                    explain={{
                      formula: "Handovers not yet closed",
                      inputs: (tickets.data?.items ?? []).slice(0, 14).map((ticket) => ({
                        label: `${ticket.reference} · ${ticket.reason_label}`,
                        value: ticket.customer ?? "Not verified",
                        source: `Reply ${ticket.reply_wording}`,
                        sourceKind: "Handover",
                      })),
                    }}
                  />
                }
              />
              <Stat
                label="Returns waiting"
                tone="warn"
                value={
                  <Figure
                    value={count(data?.returns_waiting ?? 0)}
                    count={data?.returns_waiting ?? 0}
                    heading="Returns waiting for a person"
                    explain={{
                      formula: "Returns the desk proposed that nobody has approved or refused yet",
                      inputs: (returns.data?.items ?? []).map((item) => ({
                        label: `${item.reference} · ${item.customer ?? ""}`,
                        value: item.triage_label,
                        source: `Order ${item.order ?? "—"}`,
                        sourceKind: "Return",
                      })),
                    }}
                  />
                }
              />
              <Stat
                label="Reaches refused"
                tone={data?.refused_attempts ? "fail" : undefined}
                value={
                  <Figure
                    value={count(data?.refused_attempts ?? 0)}
                    count={data?.refused_attempts ?? 0}
                    heading="Reaches for records outside the verified customer"
                    origin="Counted from the access log"
                    explain={{
                      formula: "Every lookup outside the verified customer's own scope, refused by the code and logged",
                      inputs: [{ label: "Refused", value: count(data?.refused_attempts ?? 0), sourceKind: "Access log" }],
                    }}
                  />
                }
              />
            </div>
          </Reveal>
        </div>
      </Band>

      <div className="ds-work">
        {board.error && <ErrorNote error={board.error} />}
        <Tabs tabs={tabs} value={tab} onChange={setTab} label="Desk sections" idPrefix="desk" />
        <div id="desk-panel" role="tabpanel" aria-labelledby={`desk-${tab}`} className="fd-tab-panel" key={tab}>
          {tab === "queue" && <Queue data={tickets.data} loading={tickets.loading} onOpen={setOpen} />}
          {tab === "returns" && <Returns data={returns.data} loading={returns.loading} onDecided={reloadAll} />}
          {tab === "conversations" && <Conversations onOpen={setOpen} />}
          {tab === "visits" && <Visits />}
          {tab === "refused" && supervisor && <Refused />}
        </div>
      </div>

      {open && <ConversationDrawer reference={open} onClose={() => setOpen(null)} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
function Queue({
  data,
  loading,
  onOpen,
}: {
  data: { total: number; items: Ticket[] } | null;
  loading: boolean;
  onOpen: (reference: string) => void;
}) {
  if (!data && loading) return <Loading what="Reading the queue" />;
  if (!data?.items.length) return <Empty title="Nobody is waiting for a person." />;
  return (
    <div className="fd-cards">
      {data.items.map((ticket, index) => (
        <Reveal key={ticket.reference} index={index} className="fd-ticket-card ds-lift">
          <div className="fd-ticket-top">
            <span className="ds-stamp">{ticket.reference}</span>
            <StatusChip tone={ticket.reason === "systems_disagree" || ticket.reason === "locked_out" ? "fail" : "warn"} pulse>
              {ticket.reason_label}
            </StatusChip>
          </div>
          <p className="fd-ticket-who">{ticket.customer ?? "A visitor, not verified"}</p>
          <p className="fd-ticket-summary">{shorten(plain(ticket.summary), 220)}</p>
          <div className="fd-ticket-foot">
            <span className="ds-mono">
              Reply{" "}
              <Figure
                value={ticket.reply_wording}
                heading="When the customer was told to expect a reply"
                origin="Worked out from office hours"
                explain={{
                  formula:
                    "Inside Taipei office hours (09:00 to 18:00, Monday to Friday) a reply within 45 minutes; outside them, 90 minutes after the next opening, said in the customer's own time",
                  result: dayAndTime(ticket.reply_by),
                  inputs: [
                    { label: "Raised", value: dayAndTime(ticket.at), sourceKind: "Handover" },
                    { label: "Reply by", value: dayAndTime(ticket.reply_by), sourceKind: "Handover" },
                  ],
                }}
              />
            </span>
            <Button size="small" tone="secondary" onClick={() => onOpen(ticket.conversation)} arrow>
              Read the conversation
            </Button>
          </div>
        </Reveal>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
function Returns({
  data,
  loading,
  onDecided,
}: {
  data: { total: number; items: ReturnRequest[] } | null;
  loading: boolean;
  onDecided: () => void;
}) {
  const { busy, error, run } = useAction();
  const [decided, setDecided] = useState<Record<string, { approved: boolean; by: string }>>({});
  const user = readUser();

  if (!data && loading) return <Loading what="Reading the returns" />;
  if (!data?.items.length && !Object.keys(decided).length) return <Empty title="No return is waiting for approval." />;

  const decide = (reference: string, approved: boolean) =>
    run(reference, () =>
      api.post<ReturnRequest>(`/api/returns/${reference}`, {
        approved,
        note: approved ? "Agreed." : "Not covered.",
      }),
    ).then((result) => {
      if (!result) return;
      setDecided((previous) => ({ ...previous, [reference]: { approved, by: result.decided_by?.name ?? user?.full_name ?? "" } }));
      window.setTimeout(onDecided, prefersReducedMotion() ? 0 : 1400);
    });

  return (
    <>
      {error && (
        <div style={{ marginBottom: 16 }}>
          <ErrorNote error={error} />
        </div>
      )}
      <div className="fd-cards">
        {(data?.items ?? []).map((request, index) => {
          const decision = decided[request.reference];
          const confidence = Math.round(request.triage_confidence * 100);
          return (
            <Reveal key={request.reference} index={index} className="fd-return-card" data-decided={decision ? (decision.approved ? "approved" : "refused") : undefined}>
              <div className="fd-ticket-top">
                <span className="ds-stamp">{request.reference}</span>
                <StatusChip tone={request.within_warranty ? "pass" : "warn"}>
                  {request.within_warranty ? "Inside the terms" : "Outside the terms"}
                </StatusChip>
              </div>
              <p className="fd-ticket-who">{request.customer}</p>
              <p className="fd-ticket-summary">“{request.reported}”</p>
              <dl className="fd-facts">
                <div>
                  <dt className="ds-mono-label">Order</dt>
                  <dd>{request.order ?? "—"}</dd>
                </div>
                <div>
                  <dt className="ds-mono-label">Part</dt>
                  <dd className="ds-mono">{request.part_code}</dd>
                </div>
                <div>
                  <dt className="ds-mono-label">Looks like</dt>
                  <dd>
                    {request.triage_label}{" "}
                    <Figure
                      value={`${confidence}%`}
                      heading="How sure the triage was"
                      origin="Counted by the triage rules"
                      explain={{
                        formula: "Signals in the customer's own description, each with a weight; below 62% it says it is not sure",
                        inputs: (request.triage_detail?.reasons ?? []).map((reason) => ({
                          label: reason,
                          value: "signal",
                          sourceKind: "Description",
                        })),
                      }}
                    />
                  </dd>
                </div>
                <div>
                  <dt className="ds-mono-label">Usually paid by</dt>
                  <dd>{request.who_usually_pays}</dd>
                </div>
              </dl>
              {request.warranty_detail?.note && <p className="fd-small-note">{request.warranty_detail.note}</p>}
              {request.photo_name && (
                <p className="ds-mono" style={{ margin: "8px 0 0", fontSize: 11.5, color: "var(--ds-text-3)" }}>
                  Photograph attached · {request.photo_name}
                </p>
              )}
              {decision ? (
                <div className="fd-decision" data-approved={decision.approved ? "" : undefined}>
                  <span className="fd-decision-stamp">{decision.approved ? "Approved" : "Refused"}</span>
                  <span>by {decision.by}. The customer is told by a person, not by the desk.</span>
                </div>
              ) : (
                <div className="fd-return-actions">
                  <Button tone="primary" size="small" busy={busy === request.reference} onClick={() => void decide(request.reference, true)}>
                    Approve
                  </Button>
                  <Button tone="danger" size="small" busy={busy === request.reference} onClick={() => void decide(request.reference, false)}>
                    Refuse
                  </Button>
                  <span className="ds-mono" style={{ fontSize: 11, color: "var(--ds-text-3)" }}>
                    Your name goes on the decision
                  </span>
                </div>
              )}
            </Reveal>
          );
        })}
      </div>
    </>
  );
}

/* ------------------------------------------------------------------ */
function Conversations({ onOpen }: { onOpen: (reference: string) => void }) {
  const [channel, setChannel] = useState<"" | "web" | "line">("");
  const { data, loading } = useLoad<Page<ConversationBrief>>(
    `/api/conversations?limit=60${channel ? `&channel=${channel}` : ""}`,
  );
  return (
    <div>
      <div className="fd-filter" role="radiogroup" aria-label="Channel">
        {(
          [
            ["", "Both channels"],
            ["web", "Website"],
            ["line", "LINE"],
          ] as const
        ).map(([key, label]) => (
          <button key={key} type="button" role="radio" aria-checked={channel === key} data-on={channel === key ? "" : undefined} onClick={() => setChannel(key)}>
            {label}
          </button>
        ))}
        {data && <span className="ds-mono" style={{ fontSize: 12, color: "var(--ds-text-3)" }}>{count(data.total)} in all</span>}
      </div>
      {!data && loading && <Loading what="Reading the conversations" />}
      {data && !data.items.length && <Empty title="No conversations yet." />}
      {data && data.items.length > 0 && (
        <Card flush>
          <ul className="fd-rows">
            {data.items.map((brief, index) => {
              const outcome = outcomeOfBrief(brief);
              return (
                <Reveal as="li" key={brief.reference} index={index} from="left" y={24}>
                  <button type="button" className="fd-row" data-outcome={outcome} onClick={() => onOpen(brief.reference)}>
                    <ChannelMark channel={brief.channel} withWord={false} />
                    <span className="ds-stamp">{brief.reference}</span>
                    <span className="fd-row-main">
                      <span className="fd-row-title">{brief.customer ?? "A visitor, not verified"}</span>
                      <span className="fd-row-sub">{brief.last_said ? `“${shorten(brief.last_said, 110)}”` : "Nothing said yet"}</span>
                    </span>
                    <span className="ds-mono fd-row-meta">
                      {brief.intent_label || "—"} · {brief.turns} turns · {clock(brief.at)}
                    </span>
                    <OutcomeChip outcome={outcome} />
                  </button>
                </Reveal>
              );
            })}
          </ul>
        </Card>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
function Visits() {
  const { data, loading } = useLoad<{ total: number; items: Visit[] }>("/api/visits");
  const byTechnician = useMemo(() => {
    const groups = new Map<string, Visit[]>();
    (data?.items ?? []).forEach((visit) => {
      const key = visit.technician ?? "Unassigned";
      groups.set(key, [...(groups.get(key) ?? []), visit]);
    });
    return [...groups.entries()];
  }, [data]);
  if (!data && loading) return <Loading what="Reading the diary" />;
  if (!data?.items.length) return <Empty title="No technician visit is booked yet." />;
  return (
    <div className="fd-diary">
      {byTechnician.map(([technician, visits], index) => (
        <Reveal key={technician} index={index} className="fd-diary-card">
          <Card eyebrow={`${visits.length} visit${visits.length === 1 ? "" : "s"}`} title={technician}>
            <NodeChain
              live={false}
              items={visits.map((visit) => ({
                key: visit.reference,
                tone: visit.status === "booked" ? "pass" : undefined,
                state: "done",
                marker: (parseWhen(visit.starts_at)?.toLocaleDateString("en-GB", { day: "2-digit", timeZone: "Asia/Taipei" }) ?? "").slice(0, 2),
                content: (
                  <div style={{ paddingBottom: 4 }}>
                    <p style={{ margin: 0, fontWeight: 600 }}>
                      {parseWhen(visit.starts_at)?.toLocaleString("en-GB", {
                        weekday: "short",
                        day: "2-digit",
                        month: "short",
                        hour: "2-digit",
                        minute: "2-digit",
                        timeZone: "Asia/Taipei",
                      })}{" "}
                      <span className="ds-mono" style={{ fontSize: 11, color: "var(--ds-text-3)" }}>
                        Taipei · {visit.minutes} minutes
                      </span>
                    </p>
                    <p style={{ margin: "2px 0 0", fontSize: 13, color: "var(--ds-text-2)" }}>
                      {visit.customer} · {visit.city} · <span className="ds-mono">{visit.reference}</span>
                    </p>
                  </div>
                ),
              }))}
            />
          </Card>
        </Reveal>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
function Refused() {
  const { data, error, loading } = useLoad<{ total: number; items: AccessRow[] }>("/api/access-log?refused_only=true&limit=100");
  if (error) return <ErrorNote error={error} />;
  if (!data && loading) return <Loading what="Reading the access log" />;
  if (!data?.items.length) return <Empty title="Nothing has been refused." />;
  return (
    <Card flush eyebrow="Access log" title="Every reach for a record outside the verified customer, refused">
      <ul className="fd-rows">
        {data.items.map((row, index) => (
          <Reveal as="li" key={row.id} index={index} from="left" y={24}>
            <div className="fd-row fd-refused-row">
              <span className="fd-refused-mark" aria-hidden />
              <span className="ds-mono" style={{ fontSize: 12, color: "var(--ds-text-3)" }}>
                {clock(row.at)}
              </span>
              <span className="fd-row-main">
                <span className="fd-row-title">{toolWord(row.tool)}</span>
                <span className="fd-row-sub ds-mono">
                  {Object.entries(row.arguments)
                    .map(([key, value]) => `${key.replace(/_/g, " ")}: ${String(value)}`)
                    .join(" · ") || "no arguments"}
                </span>
              </span>
              <span className="fd-row-meta" style={{ color: "var(--ds-fail-ink)" }}>
                {plain(row.refusal)}
              </span>
              <StatusChip tone="fail">Refused</StatusChip>
            </div>
          </Reveal>
        ))}
      </ul>
    </Card>
  );
}

/* ------------------------------------------------------------------ */
/* The conversation, opened from the queue or the list                  */
/* ------------------------------------------------------------------ */
function ConversationDrawer({ reference, onClose }: { reference: string; onClose: () => void }) {
  const [closing, setClosing] = useState(false);
  const { data, error } = useLoad<Conversation>(`/api/conversations/${encodeURIComponent(reference)}`);
  const close = useCallback(() => setClosing(true), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") close();
    };
    window.addEventListener("keydown", onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = previous;
    };
  }, [close]);

  useEffect(() => {
    if (!closing) return;
    const handle = window.setTimeout(onClose, prefersReducedMotion() ? 0 : 320);
    return () => window.clearTimeout(handle);
  }, [closing, onClose]);

  const outcome = data ? outcomeOf(data) : null;

  return (
    <div className="ds-sheet-root" data-closing={closing ? "" : undefined}>
      <div className="ds-sheet-scrim" onClick={close} aria-hidden />
      <aside className="ds-sheet fd-drawer" role="dialog" aria-modal="true" aria-label={`Conversation ${reference}`}>
        <header className="ds-sheet-head">
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 }}>
            <span className="ds-mono-label">Conversation · {data ? STATUS_WORDS[data.status] ?? data.status : "…"}</span>
            <button type="button" className="ds-close" onClick={close} autoFocus>
              Close <span aria-hidden>×</span>
            </button>
          </div>
          <p className="ds-sheet-heading">{data?.customer?.name ?? "A visitor, not verified"}</p>
          <div className="fd-drawer-chips">
            <span className="ds-stamp">{reference}</span>
            {data && <ChannelMark channel={data.channel} />}
            {outcome && <OutcomeChip outcome={outcome} surface="dark" />}
            {data?.verified ? (
              <StatusChip tone="pass" surface="dark">
                Verified as {data.contact?.name ?? "the customer"}
              </StatusChip>
            ) : (
              <StatusChip tone="neutral" surface="dark">
                Never verified
              </StatusChip>
            )}
          </div>
        </header>
        <div className="ds-sheet-body fd-drawer-body">
          {error && <ErrorNote error={error} />}
          {!data && !error && <Loading what="Reading the conversation" />}
          {data?.ticket && (
            <div className="fd-ticket" style={{ marginBottom: 18 }}>
              <span className="fd-handover-node" aria-hidden>
                <i />
              </span>
              <div>
                <p className="ds-mono-label" style={{ margin: 0 }}>
                  With a person · {data.ticket.reason_label}
                </p>
                <p style={{ margin: "4px 0 0", fontWeight: 600 }}>
                  <span className="ds-stamp">{data.ticket.reference}</span> Reply {data.ticket.reply_wording}
                </p>
              </div>
            </div>
          )}
          <div className="fd-thread fd-thread-static">
            {data?.turns.map((turn, index) => (
              <TurnView key={turn.id} turn={turn} index={index} ticket={data.ticket} variant={data.channel === "line" ? "line" : "web"} />
            ))}
            {data && data.turns.length === 0 && <Empty title="Nothing was said in this conversation." />}
          </div>
        </div>
        <footer className="ds-sheet-foot">
          <StatusChip tone="accent">Read from the conversation record</StatusChip>
          <span style={{ fontSize: 12, color: "var(--ds-text-3)" }}>Every reply names the engine that phrased it and the tool it used.</span>
          {data && (
            <LinkButton href={data.channel === "line" ? "/line" : "/chat"} tone="ghost" size="small" arrow>
              Open a new one like it
            </LinkButton>
          )}
        </footer>
      </aside>
    </div>
  );
}

export const dynamic = "force-dynamic";
