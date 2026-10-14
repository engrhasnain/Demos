"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";

import { CountUp } from "@/design/CountUp";
import { Meter } from "@/design/Meter";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Band, Card, LinkButton, Stat } from "@/design/Surface";
import { DeskScene, type SceneCustomer, type SceneHandle } from "@/components/desk-scene";
import { FirstRun } from "@/components/first-run";
import { LiveConversation } from "@/components/live-conversation";
import { Figure } from "@/components/trace";
import { ChannelMark, ErrorNote, Loading, OutcomeChip, SectionHead } from "@/components/ui";
import { api } from "@/lib/api";
import {
  OUTCOME_WORDS,
  STATUS_WORDS,
  channelWord,
  clock,
  count,
  dayAndTime,
  engineWord,
  lastCustomerLine,
  outcomeOf,
  outcomeOfBrief,
  percent,
  shorten,
  toolWord,
} from "@/lib/format";
import { useLoad } from "@/lib/hooks";
import type { Conversation, ConversationBrief, Dashboard, DemoState, Page, Ticket, Visit } from "@/lib/types";

export default function OverviewPage() {
  const state = useLoad<DemoState>("/api/demo/state");
  if (state.loading && !state.data) {
    return (
      <Band top>
        <Loading what="Opening the desk" dark />
      </Band>
    );
  }
  if (state.error) {
    return (
      <Band top>
        <ErrorNote error={state.error} />
      </Band>
    );
  }
  if (!state.data) return null;
  return state.data.loaded ? <Overview /> : <FirstRun onFinished={state.reload} />;
}

/* ------------------------------------------------------------------ */
function Overview() {
  const board = useLoad<Dashboard>("/api/dashboard");
  const list = useLoad<Page<ConversationBrief>>("/api/conversations?limit=60");
  const tickets = useLoad<{ total: number; items: Ticket[] }>("/api/tickets");
  const visits = useLoad<{ total: number; items: Visit[] }>("/api/visits");
  const web = useLoad<Page<ConversationBrief>>("/api/conversations?channel=web&limit=1");
  const line = useLoad<Page<ConversationBrief>>("/api/conversations?channel=line&limit=1");
  const briefs = useMemo(() => list.data?.items ?? [], [list.data]);

  return (
    <div>
      <Hero
        board={board.data}
        briefs={briefs}
        tickets={tickets.data?.items ?? []}
        visits={visits.data?.items ?? []}
      />
      <div className="ds-work">
        {board.error && <ErrorNote error={board.error} />}
        <Intents board={board.data} />
        <Endings board={board.data} webTotal={web.data?.total ?? 0} lineTotal={line.data?.total ?? 0} />
        <Latest briefs={briefs} total={list.data?.total ?? 0} />
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Hero                                                                 */
/* ------------------------------------------------------------------ */
function Hero({
  board,
  briefs,
  tickets,
  visits,
}: {
  board: Dashboard | null;
  briefs: ConversationBrief[];
  tickets: Ticket[];
  visits: Visit[];
}) {
  const [details, setDetails] = useState<Record<string, Conversation>>({});
  const [compact, setCompact] = useState(false);
  const stageBox = useRef<HTMLDivElement>(null);
  const scene = useRef<SceneHandle>(null);

  const recent = useMemo(() => briefs.filter((brief) => brief.turns > 0).slice(0, 8), [briefs]);

  useEffect(() => {
    let cancelled = false;
    recent.forEach((brief) => {
      api
        .get<Conversation>(`/api/conversations/${brief.reference}`)
        .then((detail) => {
          if (!cancelled) setDetails((previous) => ({ ...previous, [brief.reference]: detail }));
        })
        .catch(() => undefined);
    });
    return () => {
      cancelled = true;
    };
  }, [recent]);

  useEffect(() => {
    const element = stageBox.current;
    if (!element) return;
    const measure = () => setCompact(element.getBoundingClientRect().width < 600);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const ready = recent.filter((brief) => details[brief.reference]);
  const customers: SceneCustomer[] = useMemo(
    () =>
      briefs.slice(0, 24).map((brief) => ({
        id: brief.reference,
        channel: brief.channel,
        owner: brief.verified ? brief.customer : null,
        outcome: outcomeOfBrief(brief),
      })),
    [briefs],
  );
  const owners = useMemo(() => {
    const names: string[] = [];
    for (const brief of briefs) {
      if (brief.verified && brief.customer && !names.includes(brief.customer)) names.push(brief.customer);
    }
    return names;
  }, [briefs]);

  const onIndex = useCallback(
    (index: number) => {
      const brief = ready[index];
      if (!brief) return;
      const detail = details[brief.reference];
      scene.current?.play(brief.reference, {
        outcome: detail ? outcomeOf(detail) : outcomeOfBrief(brief),
        owner: brief.verified ? brief.customer : null,
        delay: 250,
      });
    },
    [ready, details],
  );

  const finished = (board?.resolved ?? 0) + (board?.escalated ?? 0);

  return (
    <Band top>
      <div className="fd-hero">
        <div className="fd-hero-copy">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              Customer service desk <span className="ds-eyebrow-sep">·</span> website and LINE{" "}
              <span className="ds-eyebrow-sep">·</span> around the clock
            </span>
          </Reveal>
          <Reveal index={1} y={36}>
            <h1 className="ds-display fd-hero-title">
              Every customer answered.
              <br />
              <span className="fd-light">Only from their own records.</span>
              <br />
              <span className="ds-accent-text">A person one tap away.</span>
            </h1>
          </Reveal>
          <Reveal index={2} y={30}>
            <p className="ds-band-lede" style={{ fontSize: 17 }}>
              FrontDesk answers Hengtai&apos;s customers from live records, on the website and on LINE. It asks who you
              are before it shows anything, never shows one customer another&apos;s data, books technicians from a real
              diary, and hands over to a person the moment it should.{" "}
              <strong style={{ color: "var(--ds-ink-text)" }}>Every number here opens.</strong>
            </p>
          </Reveal>
          <Reveal index={3} y={28}>
            <div className="fd-hero-actions">
              <LinkButton href="/chat" tone="primary" size="large" arrow>
                Open the customer chat
              </LinkButton>
              <LinkButton href="/desk" tone="ink" size="large">
                Open the desk
              </LinkButton>
            </div>
          </Reveal>

          <Reveal index={4} y={28}>
            <div className="ds-band-rule" style={{ marginTop: 34 }} />
            <div className="ds-stats fd-hero-stats">
              <Stat
                label="Conversations"
                value={
                  <Figure
                    value={count(board?.conversations ?? 0)}
                    count={board?.conversations ?? 0}
                    heading="Conversations held"
                    explain={{
                      formula: "Every conversation on both channels, counted by where it stands now",
                      inputs: (board?.by_status ?? []).map((row) => ({
                        label: STATUS_WORDS[row.status] ?? row.status,
                        value: count(row.count),
                        source: "Live conversation records",
                        sourceKind: "Conversation state",
                      })),
                    }}
                  />
                }
              />
              <Stat
                label="Handled alone"
                tone="accent"
                value={
                  <Figure
                    value={percent(board?.handled_share ?? 0)}
                    count={board?.handled_share ?? 0}
                    decimals={1}
                    heading="Conversations the desk finished without a person"
                    note="Containment, not deflection: a conversation counts only if the desk answered it, the customer never asked for a person and nothing was handed over."
                    explain={{
                      formula: "handled ÷ (handled + handed to a person) × 100",
                      result: percent(board?.handled_share ?? 0),
                      inputs: [
                        { label: "Handled by the desk", value: count(board?.resolved ?? 0), sourceKind: "Conversation state" },
                        { label: "Handed to a person", value: count(board?.escalated ?? 0), sourceKind: "Conversation state" },
                        { label: "Finished either way", value: count(finished), sourceKind: "Sum" },
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
                    value={count(board?.open_tickets ?? 0)}
                    count={board?.open_tickets ?? 0}
                    heading="Conversations waiting for a person"
                    explain={{
                      formula: "Open handovers, soonest reply first",
                      inputs: tickets.slice(0, 14).map((ticket) => ({
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
                label="Visits booked"
                value={
                  <Figure
                    value={count(board?.visits_booked ?? 0)}
                    count={board?.visits_booked ?? 0}
                    heading="Technician visits booked"
                    explain={{
                      formula: "Visits in the technician diary with the state booked; one technician, one time, enforced by the database",
                      inputs: visits.slice(0, 14).map((visit) => ({
                        label: `${visit.reference} · ${visit.technician ?? ""}`,
                        value: dayAndTime(visit.starts_at),
                        source: `${visit.customer ?? ""}, ${visit.city}`,
                        sourceKind: "Visit",
                      })),
                    }}
                  />
                }
              />
              <Stat
                label="Reaches refused"
                tone={board?.refused_attempts ? "fail" : undefined}
                value={
                  <Figure
                    value={count(board?.refused_attempts ?? 0)}
                    count={board?.refused_attempts ?? 0}
                    heading="Reaches for somebody else's records, refused"
                    origin="Counted from the access log"
                    explain={{
                      formula: "Every lookup outside the verified customer's own scope is refused by the code, not by a prompt, and written to the access log",
                      inputs: [
                        { label: "Refused and logged", value: count(board?.refused_attempts ?? 0), source: "Access log", sourceKind: "Log" },
                        { label: "Customers on file", value: count(board?.customers ?? 0), sourceKind: "Records" },
                      ],
                    }}
                  />
                }
              />
            </div>
            <p className="ds-mono fd-hero-note">
              Counted from live records when this page loaded · {engineWord(board?.engine)}
              {board ? (board.desk_open ? " · office open in Taipei" : " · office closed in Taipei, replies timed for tomorrow") : ""}
            </p>
          </Reveal>
        </div>

        <div className="fd-hero-stage">
          <Reveal index={2} y={40} from="scale">
            {ready.length > 0 ? (
              <LiveConversation conversations={ready.map((brief) => details[brief.reference])} onIndex={onIndex} />
            ) : (
              <div className="fd-live" style={{ padding: 22 }}>
                <span className="ds-mono-label">Conversations live</span>
                <p style={{ margin: "14px 0 0", color: "var(--ds-text-2)" }}>
                  {briefs.length ? "Reading the latest conversations…" : "No conversations yet. Open the customer chat and say hello."}
                </p>
              </div>
            )}
          </Reveal>
        </div>
      </div>

      <Reveal y={36}>
        <div className="fd-signature" ref={stageBox}>
          <div className="fd-signature-head">
            <div>
              <span className="ds-mono-label">Two doors, one identity ring</span>
              <p className="fd-signature-title">Nothing reaches a record until the customer has proved who they are.</p>
            </div>
            <div className="fd-legend" aria-hidden>
              <span><i data-tone="web" />Website</span>
              <span><i data-tone="line" />LINE</span>
              <span><i data-tone="accent" />Identity ring</span>
              <span><i data-tone="warn" />A person</span>
            </div>
          </div>
          <div className="fd-signature-canvas">
            <DeskScene
              ref={scene}
              customers={customers}
              owners={owners}
              technicians={board?.technicians ?? 6}
              compact={compact}
              label="Customers arriving on the website and on LINE, passing the identity ring; only the verified customer's records light up"
            />
          </div>
        </div>
      </Reveal>
    </Band>
  );
}

/* ------------------------------------------------------------------ */
/* What customers came for                                              */
/* ------------------------------------------------------------------ */
const CAN_FINISH: Record<string, boolean> = {
  order_status: true,
  quote_status: true,
  opening_hours: true,
  book_visit: true,
  greeting: true,
  return_request: false,
  human: false,
  unknown: false,
};

function Intents({ board }: { board: Dashboard | null }) {
  const rows = board?.by_intent ?? [];
  const total = Math.max(1, rows.reduce((sum, row) => sum + row.count, 0));
  return (
    <section aria-labelledby="intents-heading">
      <Reveal>
        <SectionHead
          id="intents-heading"
          eyebrow="Why they wrote"
          title="What customers came for"
          action={
            <LinkButton href="/desk" tone="secondary" arrow>
              Open the desk
            </LinkButton>
          }
        />
      </Reveal>
      <div className="fd-intents">
        {rows.map((row, index) => {
          const finishable = CAN_FINISH[row.intent] ?? false;
          return (
            <Reveal key={row.intent} index={index} className="fd-intent ds-lift">
              <div className="fd-intent-top">
                <StatusChip tone={finishable ? "pass" : "warn"} size="small">
                  {finishable ? "Desk can finish" : "Needs a person"}
                </StatusChip>
                <span className="ds-mono" style={{ fontSize: 11.5, color: "var(--ds-text-3)" }}>
                  {Math.round((row.count / total) * 100)}% of contacts
                </span>
              </div>
              <div className="fd-intent-count">
                <Figure
                  value={count(row.count)}
                  count={row.count}
                  heading={`Conversations about "${row.label}"`}
                  explain={{
                    formula: `Conversations whose last understood intent is "${row.label}", read by the intent rules`,
                    inputs: [
                      { label: row.label, value: count(row.count), sourceKind: "Intent" },
                      { label: "All conversations with an intent", value: count(total), sourceKind: "Sum" },
                    ],
                  }}
                />
              </div>
              <p className="fd-intent-label">{row.label}</p>
              <Meter
                value={row.count / total}
                tone={finishable ? "accent" : "warn"}
                size="small"
                delay={index * 80}
                label={`${row.count} of ${total} conversations`}
              />
            </Reveal>
          );
        })}
        {rows.length === 0 && (
          <Card>
            <p style={{ margin: 0 }}>No conversations yet.</p>
          </Card>
        )}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* Where they ended                                                     */
/* ------------------------------------------------------------------ */
function Endings({ board, webTotal, lineTotal }: { board: Dashboard | null; webTotal: number; lineTotal: number }) {
  const total = Math.max(1, board?.conversations ?? 1);
  const parts = [
    { key: "resolved", label: "Handled by the desk", tone: "var(--ds-pass)", value: board?.resolved ?? 0 },
    { key: "escalated", label: "Handed to a person", tone: "var(--ds-warn)", value: board?.escalated ?? 0 },
    {
      key: "open",
      label: "Still open",
      tone: "var(--ds-line-strong)",
      value: Math.max(0, (board?.conversations ?? 0) - (board?.resolved ?? 0) - (board?.escalated ?? 0)),
    },
  ];
  const channels = Math.max(1, webTotal + lineTotal);
  return (
    <section style={{ marginTop: 56 }} aria-labelledby="endings-heading">
      <Reveal>
        <SectionHead id="endings-heading" eyebrow="Measured strictly" title="Where every conversation ended" />
      </Reveal>
      <div className="fd-endings">
        <Reveal className="fd-ending-card">
          <Card eyebrow="By outcome" title="A contained conversation is not a solved one">
            <CompositionBar parts={parts} total={total} />
            <ul className="fd-ending-legend">
              {parts.map((part) => (
                <li key={part.key}>
                  <i style={{ background: part.tone }} aria-hidden />
                  <span>{part.label}</span>
                  <Figure
                    value={count(part.value)}
                    count={part.value}
                    heading={part.label}
                    explain={{
                      formula:
                        part.key === "open"
                          ? "All conversations − handled − handed to a person"
                          : `Conversations whose state is "${STATUS_WORDS[part.key]}"`,
                      inputs: (board?.by_status ?? []).map((row) => ({
                        label: STATUS_WORDS[row.status] ?? row.status,
                        value: count(row.count),
                        sourceKind: "Conversation state",
                      })),
                    }}
                  />
                </li>
              ))}
            </ul>
            <p className="fd-small-note">
              Returns always go to a person, offering slots is not finishing, and anything not understood is handed
              over. All three count against the desk on purpose.
            </p>
          </Card>
        </Reveal>
        <Reveal index={1} className="fd-ending-card">
          <Card eyebrow="By channel" title="One engine behind both doors">
            <div className="fd-channel-split">
              {[
                { channel: "web", value: webTotal },
                { channel: "line", value: lineTotal },
              ].map((row, index) => (
                <div key={row.channel} className="fd-channel-row">
                  <ChannelMark channel={row.channel} />
                  <Meter
                    value={row.value / channels}
                    tone={row.channel === "line" ? "pass" : "ink"}
                    delay={index * 120}
                    label={`${row.value} conversations`}
                  />
                  <Figure
                    value={count(row.value)}
                    count={row.value}
                    heading={`Conversations on ${channelWord(row.channel)}`}
                    explain={{
                      formula: "Conversations whose channel is this one; both are answered by the same engine and the same rules",
                      inputs: [
                        { label: "Website", value: count(webTotal), sourceKind: "Channel" },
                        { label: "LINE", value: count(lineTotal), sourceKind: "Channel" },
                      ],
                    }}
                  />
                </div>
              ))}
            </div>
            <p className="fd-small-note">
              {board?.line_configured
                ? "LINE is connected: every webhook is checked against the channel secret."
                : "LINE is not connected on this server, so LINE replies are recorded rather than pushed. The signature check and single-use reply tokens are real and tested."}
            </p>
          </Card>
        </Reveal>
      </div>
    </section>
  );
}

function CompositionBar({ parts, total }: { parts: { key: string; tone: string; value: number }[]; total: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [shown, setShown] = useState(false);
  useEffect(() => {
    const element = ref.current;
    if (!element || typeof IntersectionObserver === "undefined") {
      setShown(true);
      return;
    }
    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) {
        setShown(true);
        observer.disconnect();
      }
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return (
    <div className="fd-composition" ref={ref} data-shown={shown ? "" : undefined} aria-hidden>
      {parts.map((part, index) => (
        <span
          key={part.key}
          style={{ flexGrow: part.value / total, background: part.tone, "--fd-d": `${index * 160}ms` } as CSSProperties}
        />
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Latest conversations                                                 */
/* ------------------------------------------------------------------ */
function Latest({ briefs, total }: { briefs: ConversationBrief[]; total: number }) {
  const rows = briefs.filter((brief) => brief.turns > 0).slice(0, 8);
  return (
    <section style={{ marginTop: 56 }} aria-labelledby="latest-heading">
      <Reveal>
        <SectionHead
          id="latest-heading"
          eyebrow="Latest activity"
          title="Conversations, newest first"
          action={
            <LinkButton href="/desk?tab=conversations" tone="secondary" arrow>
              All {count(total)}
            </LinkButton>
          }
        />
      </Reveal>
      <Card flush style={{ marginTop: 22 }}>
        <ul className="fd-rows">
          {rows.map((brief, index) => {
            const outcome = outcomeOfBrief(brief);
            return (
              <Reveal as="li" key={brief.reference} index={index} from="left" y={28}>
                <Link href={`/desk?conversation=${encodeURIComponent(brief.reference)}`} className="fd-row" data-outcome={outcome}>
                  <ChannelMark channel={brief.channel} withWord={false} />
                  <span className="ds-stamp">{brief.reference}</span>
                  <span className="fd-row-main">
                    <span className="fd-row-title">{brief.customer ?? "A visitor, not verified"}</span>
                    <span className="fd-row-sub">“{shorten(brief.last_said, 110)}”</span>
                  </span>
                  <span className="ds-mono fd-row-meta">
                    {brief.intent_label || "—"} · {brief.turns} turns · {clock(brief.at)}
                  </span>
                  <OutcomeChip outcome={outcome} />
                </Link>
              </Reveal>
            );
          })}
          {rows.length === 0 && <li style={{ padding: 20 }}>No conversations yet.</li>}
        </ul>
      </Card>
    </section>
  );
}

export const dynamic = "force-dynamic";
