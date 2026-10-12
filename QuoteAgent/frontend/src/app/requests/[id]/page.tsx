"use client";

import Link from "next/link";
import { use, useEffect, useState, type CSSProperties } from "react";

import { Band, Banner, Button, Card, Stamp, Stat } from "@/design/Surface";
import { Meter } from "@/design/Meter";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { StepRail } from "@/design/StepRail";
import { Tabs } from "@/design/Tabs";
import { useInView } from "@/design/motion";
import { api, documentUrl } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";
import { count, dateAndTime, dateOnly, money, percent } from "@/lib/format";
import type { CaseDetail, CaseEvent, SystemStatus } from "@/lib/types";
import { Figure } from "@/components/trace";
import { LinesTable } from "@/components/case/lines";
import {
  ApprovalGate,
  ApprovalsPanel,
  EmailsPanel,
  QuestionsPanel,
  TimelinePanel,
  VersionsPanel,
  gateState,
} from "@/components/case/panels";
import { LIFECYCLE, progressOf } from "@/components/case-progress";
import { ErrorNote, Loading, isLive, statusTone } from "@/components/ui";

const TABS = [
  { key: "lines", label: "Lines" },
  { key: "questions", label: "Questions" },
  { key: "approvals", label: "Approvals" },
  { key: "emails", label: "Emails" },
  { key: "timeline", label: "Timeline" },
  { key: "versions", label: "Versions" },
] as const;

type TabKey = (typeof TABS)[number]["key"];

export default function CasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const detail = useLoad<CaseDetail>(`/api/cases/${id}`);
  const timeline = useLoad<{ events: CaseEvent[]; elapsed: Record<string, string | number> }>(
    `/api/cases/${id}/timeline`,
  );
  const status = useLoad<SystemStatus>("/api/system/status");
  const [tab, setTab] = useState<TabKey>("lines");

  // "?tab=approvals" opens straight onto a tab: the walkthrough links here.
  useEffect(() => {
    const wanted = new URLSearchParams(window.location.search).get("tab");
    if (wanted && TABS.some((item) => item.key === wanted)) setTab(wanted as TabKey);
  }, []);
  const { busy, error, note, run } = useAction();

  const refresh = () => {
    detail.reload();
    timeline.reload();
  };

  const act = (key: string, path: string, body?: unknown, message?: string) =>
    void run(
      key,
      async () => {
        const result = await api.post(path, body ?? {});
        refresh();
        return result;
      },
      message,
    );

  if (detail.loading && !detail.data) {
    return (
      <Band top>
        <Loading what="Opening this request" />
      </Band>
    );
  }
  if (detail.error) {
    return (
      <Band top>
        <ErrorNote error={detail.error} />
      </Band>
    );
  }
  if (!detail.data) return null;

  const data = detail.data;
  const version = data.current_version;
  const counts = version?.line_counts ?? {};
  const openQuestions = data.questions.rounds
    .flatMap((round) => round.questions)
    .filter((question) => question.status === "open").length;
  const pendingApprovals = data.approvals.filter((a) => a.status === "pending").length;
  const draftEmail = data.messages.find((message) => message.awaiting_approval);
  const events = timeline.data?.events ?? [];
  const engines = Array.from(new Set(events.map((event) => event.engine).filter(Boolean)));
  const progress = progressOf(data.case.status, version?.needs_repricing);
  const gate = gateState(data);
  // The re-pricing banner already says this one; do not say it twice.
  const blocking = data.blocking_reasons.filter(
    (reason) => !version?.needs_repricing || reason.trim() !== version.repricing_reason.trim(),
  );

  const subs: Record<string, string> = {
    received: dateAndTime(data.case.created_at),
    read: version ? `${count(counts.total ?? version.lines?.length ?? 0)} lines` : "not yet",
    asked: openQuestions ? `${openQuestions} open` : data.questions.questions_asked ? "answered" : "none needed",
    priced: version && Number(version.totals.grand_total) > 0 ? money(version.totals.grand_total, version.currency) : "not yet",
    approval: pendingApprovals ? `${pendingApprovals} waiting` : gate === "approved" ? "approved" : gate === "none" ? "not needed" : "",
    sent: version?.sent_at ? dateAndTime(version.sent_at) : "",
    decided: data.case.status === "won" ? "won" : data.case.status === "lost" ? "lost" : "",
  };

  return (
    <div>
      {/* ---------------------------------------------------- the band */}
      <Band top>
        <Reveal y={20}>
          <Link href="/requests" className="qa-back">
            ← All requests
          </Link>
        </Reveal>
        <div className="qa-case-head">
          <div style={{ minWidth: 0 }}>
            <Reveal index={1} y={24}>
              <span className="ds-eyebrow">
                <span className="ds-live-dot" data-tone={progress.tone === "fail" ? "fail" : "accent"} aria-hidden />
                {data.case.reference}
                {version && (
                  <>
                    <span className="ds-eyebrow-sep">·</span> version {version.version_number}
                  </>
                )}
                <span className="ds-eyebrow-sep">·</span> {data.case.language?.startsWith("zh") ? "Chinese" : "English"}
              </span>
            </Reveal>
            <Reveal index={2} y={32}>
              <h1 className="ds-display ds-band-title" style={{ fontSize: "clamp(30px, 4vw, 52px)" }}>
                {data.case.customer?.name ?? data.case.contact_email}
              </h1>
            </Reveal>
            <Reveal index={3} y={24}>
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10, marginTop: 16 }}>
                <StatusChip tone={statusTone(data.case.status)} surface="dark" size="large" pulse={isLive(data.case.status)}>
                  {data.case.status_label}
                </StatusChip>
                <span className="ds-status-pill" style={{ height: 28 }}>
                  <span className="ds-live-dot" aria-hidden />
                  {engines.length
                    ? `Read by the ${engines.map((engine) => (engine === "built-in" ? "built-in engine" : `${engine} engine`)).join(" and ")}`
                    : status.data?.reasoning_engine.active_engine === "built-in"
                      ? "Built-in engine ready"
                      : "External model ready"}
                </span>
                <span className="ds-mono" style={{ fontSize: 12, color: "var(--ds-ink-muted)" }}>
                  {data.case.contact_email}
                </span>
              </div>
              {data.status.description && (
                <p className="ds-band-lede" style={{ fontSize: 15, marginTop: 14 }}>
                  {data.status.description}
                </p>
              )}
            </Reveal>
          </div>
          <Reveal index={3} y={28}>
            <Actions caseId={id} detail={data} busy={busy} act={act} draftEmailId={draftEmail?.id ?? null} />
          </Reveal>
        </div>

        <Reveal index={4} y={28}>
          <div className="qa-case-rail">
            <StepRail
              label="Where this request is"
              steps={LIFECYCLE.map((step) => ({ ...step, sub: subs[step.key] || undefined }))}
              current={progress.index}
              tone={progress.tone}
              complete={progress.complete}
            />
          </div>
        </Reveal>

        <div className="qa-case-stats">
          <Reveal index={5} y={28} style={{ minWidth: 0 }}>
            <div className="ds-stats" style={{ marginTop: 0 }}>
              <Stat
                label="Lines"
                value={
                  <Figure
                    value={count(counts.total ?? version?.lines?.length ?? 0)}
                    count={counts.total ?? version?.lines?.length ?? 0}
                    decimals={0}
                    heading="Lines on this quote"
                    explain={{
                      formula: "The lines on the current version, by where each one stands",
                      inputs: Object.entries(counts)
                        .filter(([key]) => key !== "total")
                        .map(([key, value]) => ({
                          label: key === "priced" ? "Priced" : key === "needs_clarification" ? "Question outstanding" : key === "awaiting_supplier" ? "Waiting for a supplier" : key === "non_catalogue" ? "Not a catalogue part" : key.replace(/_/g, " "),
                          value: String(value),
                          source: version ? `Quote version ${version.version_number}` : "Request",
                          sourceKind: "Quote lines",
                        })),
                    }}
                  />
                }
              />
              {version && (
                <Stat
                  label={`Quote total, ${version.currency}`}
                  tone="accent"
                  value={
                    <Figure
                      value={money(version.totals.grand_total)}
                      count={Number(version.totals.grand_total)}
                      heading={`Quote total, version ${version.version_number}`}
                      trace={version.totals_trace}
                      note={version.incoterm_explained}
                    />
                  }
                />
              )}
              {version && (
                <Stat
                  label="Margin"
                  value={
                    <Figure
                      value={percent(version.totals.margin_percent)}
                      count={Number(version.totals.margin_percent)}
                      decimals={1}
                      heading={`Margin on version ${version.version_number}`}
                      explain={{
                        formula: `(goods ${money(version.totals.goods)} − cost ${money(version.totals.total_cost)}) ÷ goods × 100, worked out by the pricing engine`,
                        result: percent(version.totals.margin_percent),
                        inputs: [
                          { label: "Goods", value: money(version.totals.goods, version.currency), source: "Sum of the line totals", sourceKind: "Pricing engine" },
                          { label: "Cost", value: money(version.totals.total_cost, version.currency), source: "Standard cost of each part", sourceKind: "Catalogue record" },
                        ],
                      }}
                      origin="From the pricing engine"
                    />
                  }
                />
              )}
              <Stat
                label="Open questions"
                tone={openQuestions ? "warn" : undefined}
                value={<Figure value={String(openQuestions)} count={openQuestions} decimals={0} heading="Open questions" explain={{
                  formula: "Questions sent to the customer that have not been answered yet",
                  inputs: data.questions.rounds.flatMap((round) => round.questions).filter((q) => q.status === "open").map((q) => ({
                    label: `Line ${q.line_number}`, value: q.question.slice(0, 60), source: `Round ${q.round_number}`, sourceKind: "Question",
                  })),
                }} />}
              />
              <Stat
                label="Agent working time"
                value={
                  <Figure
                    value={`${data.elapsed.agent_working_seconds ?? 0} s`}
                    count={Number(data.elapsed.agent_working_seconds ?? 0)}
                    decimals={2}
                    heading="Agent working time"
                    explain={{
                      formula: "The time the agent itself spent on this request, added up from the timeline. Waiting for people is not counted.",
                      inputs: [
                        { label: "Steps on the timeline", value: String(data.elapsed.steps ?? events.length), source: "Case timeline", sourceKind: "Record" },
                        { label: "Started", value: dateAndTime(String(data.elapsed.started_at ?? "")), source: "First event", sourceKind: "Record" },
                        { label: "Latest", value: dateAndTime(String(data.elapsed.latest_at ?? "")), source: "Latest event", sourceKind: "Record" },
                      ],
                    }}
                  />
                }
              />
            </div>
          </Reveal>
          <Reveal index={6} y={32} style={{ minWidth: 0 }}>
            <ApprovalGate detail={data} />
          </Reveal>
        </div>
      </Band>

      {/* ---------------------------------------------------- the work */}
      <div className="ds-work">
        <div style={{ display: "grid", gap: 12, marginBottom: 20 }}>
          {error && <ErrorNote error={error} />}
          {note && <Banner tone="pass">{note}</Banner>}
          {version?.needs_repricing && (
            <Banner
              tone="fail"
              title="The numbers moved. This quote has to be re-priced before it can go."
              action={
                <Button
                  size="small"
                  tone="primary"
                  busy={busy === "price"}
                  onClick={() => act("price", `/api/cases/${id}/price`)}
                >
                  Re-price now
                </Button>
              }
              className="qa-reopen-banner"
            >
              {version.repricing_reason.trim().replace(/([^.])$/, "$1.")} Any approval already given is re-opened
              on the new figures.
            </Banner>
          )}
          {blocking.length > 0 && (
            <Banner tone="warn" title="What is holding this quote">
              {blocking.join(" ")}
            </Banner>
          )}
        </div>

        <div className="qa-case-grid">
          <div style={{ minWidth: 0 }}>
            <Tabs
              label="Parts of this request"
              idPrefix="case"
              value={tab}
              onChange={setTab}
              tabs={TABS.map((item) => ({
                key: item.key,
                label: item.label,
                badge:
                  item.key === "questions"
                    ? openQuestions
                    : item.key === "approvals"
                      ? pendingApprovals
                      : item.key === "emails"
                        ? data.messages.length
                        : item.key === "versions"
                          ? data.versions.length
                          : item.key === "lines"
                            ? version?.lines?.length ?? 0
                            : 0,
              }))}
            />
            <div id="case-panel" role="tabpanel" aria-labelledby={`case-${tab}`} style={{ marginTop: 16 }} key={tab}>
              <Card flush={tab === "lines"}>
                {tab === "lines" &&
                  (version ? (
                    <LinesTable version={version} />
                  ) : (
                    <div style={{ padding: 20 }}>
                      <Banner tone="accent" title="Not read yet">
                        Press &ldquo;Run the agent&rdquo; to read the request and match every line.
                      </Banner>
                    </div>
                  ))}
                {tab === "questions" && <QuestionsPanel detail={data} />}
                {tab === "approvals" && (
                  <ApprovalsPanel
                    detail={data}
                    busy={busy}
                    onDecide={(approvalId, approved) =>
                      act(
                        `${approved ? "approve" : "reject"}-${approvalId}`,
                        `/api/cases/${id}/approvals/${approvalId}/decide`,
                        { approved, comment: "" },
                      )
                    }
                  />
                )}
                {tab === "emails" && (
                  <EmailsPanel
                    detail={data}
                    busy={busy}
                    onSend={(messageId) =>
                      act(`send-${messageId}`, `/api/cases/${id}/messages/send`, {
                        message_id: messageId,
                      })
                    }
                  />
                )}
                {tab === "timeline" && (
                  <TimelinePanel events={events} elapsed={timeline.data?.elapsed ?? {}} />
                )}
                {tab === "versions" && <VersionsPanel versions={data.versions} current={version} />}
              </Card>
            </div>
          </div>

          <Totals
            detail={data}
            caseId={id}
            floor={status.data?.policies.default_margin_floor_percent}
            validity={status.data?.policies.quote_validity_days}
          />
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
function Actions({
  caseId,
  detail,
  busy,
  act,
  draftEmailId,
}: {
  caseId: string;
  detail: CaseDetail;
  busy: string | null;
  act: (key: string, path: string, body?: unknown, message?: string) => void;
  draftEmailId: number | null;
}) {
  const hasVersion = Boolean(detail.current_version);
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: 10, justifyContent: "flex-end" }}>
      {!hasVersion && (
        <Button tone="primary" busy={busy === "run"} onClick={() => act("run", `/api/cases/${caseId}/run`)} arrow>
          Run the agent
        </Button>
      )}
      {draftEmailId && (
        <Button
          tone="primary"
          busy={busy === `send-${draftEmailId}`}
          onClick={() =>
            act(`send-${draftEmailId}`, `/api/cases/${caseId}/messages/send`, {
              message_id: draftEmailId,
            })
          }
        >
          Approve and send the questions
        </Button>
      )}
      {hasVersion && (
        <>
          <Button tone="ink" busy={busy === "price"} onClick={() => act("price", `/api/cases/${caseId}/price`)}>
            Re-price
          </Button>
          <Button
            tone={detail.blocking_reasons.length ? "ink" : "primary"}
            disabled={detail.blocking_reasons.length > 0}
            busy={busy === "send-quote"}
            title={
              detail.blocking_reasons.length
                ? detail.blocking_reasons.join(" ")
                : "Send the quote to the customer"
            }
            onClick={() => act("send-quote", `/api/cases/${caseId}/send-quote`)}
            arrow={!detail.blocking_reasons.length}
          >
            Send the quote
          </Button>
        </>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
function Composition({ parts }: { parts: { label: string; value: number; colour: string }[] }) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.3 });
  const total = parts.reduce((sum, part) => sum + part.value, 0) || 1;
  return (
    <div>
      <div ref={ref} className="qa-composition" data-shown={shown ? "" : undefined} aria-hidden>
        {parts.map((part, index) => (
          <span
            key={part.label}
            style={
              {
                width: `${(part.value / total) * 100}%`,
                background: part.colour,
                "--ds-d": `${index * 160}ms`,
              } as CSSProperties
            }
          />
        ))}
      </div>
    </div>
  );
}

function Totals({
  detail,
  caseId,
  floor,
  validity = 14,
}: {
  detail: CaseDetail;
  caseId: string;
  floor?: number;
  validity?: number;
}) {
  const version = detail.current_version;
  if (!version) return <div />;

  const rows: [string, string, string][] = [
    ["Goods", version.totals.goods, "var(--ds-ink)"],
    ["Freight", version.totals.freight, "var(--ds-accent)"],
    ["Insurance", version.totals.insurance, "var(--ds-info)"],
    ["Import duty", version.totals.import_duty, "var(--ds-warn)"],
  ];
  const visible = rows.filter(([label, value]) => Number(value) !== 0 || label === "Goods");
  const margin = Number(version.totals.margin_percent);
  const floorValue = floor ?? 18;

  return (
    <div className="qa-totals">
      <Card tone="accent" eyebrow={`Quote total · version ${version.version_number}`}>
        <p className="ds-title ds-num" style={{ margin: 0, fontSize: 34, lineHeight: 1.05 }}>
          <Figure
            emphasis
            value={money(version.totals.grand_total)}
            count={Number(version.totals.grand_total)}
            heading={`Quote total, version ${version.version_number}`}
            trace={version.totals_trace}
            note={version.incoterm_explained}
          />
          <span className="ds-mono" style={{ marginLeft: 8, fontSize: 13, color: "var(--ds-text-3)" }}>
            {version.currency}
          </span>
        </p>
        <div style={{ marginTop: 16 }}>
          <Composition parts={visible.map(([label, value, colour]) => ({ label, value: Math.abs(Number(value)), colour }))} />
        </div>
        <dl style={{ margin: "14px 0 0", display: "grid", gap: 8 }}>
          {visible.map(([label, value, colour]) => (
            <div key={label} style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, fontSize: 13.5 }}>
              <dt style={{ display: "flex", alignItems: "center", gap: 8, color: "var(--ds-text-2)" }}>
                <span style={{ width: 9, height: 9, borderRadius: 2, background: colour }} aria-hidden />
                {label}
              </dt>
              <dd style={{ margin: 0 }}>
                <Figure
                  value={money(value)}
                  heading={`${label} on quote version ${version.version_number}`}
                  trace={version.totals_trace}
                />
              </dd>
            </div>
          ))}
        </dl>

        <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid var(--ds-line)" }}>
          <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", gap: 12, marginBottom: 22 }}>
            <span className="ds-mono-label">Margin</span>
            <span style={{ fontWeight: 600, color: margin < floorValue ? "var(--ds-fail-ink)" : "var(--ds-pass-ink)" }}>
              <Figure
                value={percent(version.totals.margin_percent)}
                heading={`Margin on version ${version.version_number}`}
                explain={{
                  formula: `(goods ${money(version.totals.goods)} − cost ${money(version.totals.total_cost)}) ÷ goods × 100`,
                  result: percent(version.totals.margin_percent),
                  inputs: [
                    { label: "Goods", value: money(version.totals.goods, version.currency), source: "Sum of the line totals", sourceKind: "Pricing engine" },
                    { label: "Cost", value: money(version.totals.total_cost, version.currency), source: "Standard cost of each part", sourceKind: "Catalogue record" },
                    { label: "Company margin floor", value: `${floorValue}%`, source: "Company setting for the default margin floor", sourceKind: "Company policy" },
                  ],
                }}
                origin="From the pricing engine"
              />
            </span>
          </div>
          <Meter
            value={Math.max(0, margin) / 60}
            mark={floorValue / 60}
            markLabel={`floor ${floorValue}%`}
            tone={margin < floorValue ? "fail" : "pass"}
            label={`Margin ${percent(version.totals.margin_percent)} against a floor of ${floorValue}%`}
          />
        </div>

        <dl style={{ margin: "20px 0 0", paddingTop: 14, borderTop: "1px solid var(--ds-line)", display: "grid", gap: 6, fontSize: 12.5, color: "var(--ds-text-2)" }}>
          <div>
            <dt className="ds-mono-label" style={{ display: "inline" }}>Terms </dt>
            <dd style={{ display: "inline", margin: 0 }}>
              {version.incoterm} {version.named_place} ({version.incoterm_name})
            </dd>
          </div>
          {version.valid_until && (
            <div>
              <dt className="ds-mono-label" style={{ display: "inline" }}>Valid until </dt>
              <dd style={{ display: "inline", margin: 0 }}>
                <Figure
                  value={dateOnly(version.valid_until)}
                  heading="Quote valid until"
                  explain={{
                    formula: "The quote date plus the company's validity period",
                    result: dateOnly(version.valid_until),
                    inputs: [{ label: "Validity period", value: `${validity} days`, source: "Company setting for how long a quote is valid", sourceKind: "Company policy" }],
                  }}
                />
              </dd>
            </div>
          )}
          {version.exchange_rate && (
            <div>
              <dt className="ds-mono-label" style={{ display: "inline" }}>Rate locked </dt>
              <dd style={{ display: "inline", margin: 0 }}>
                <Figure
                  value={version.exchange_rate.rate}
                  heading={`Exchange rate, ${version.exchange_rate.pair}`}
                  explain={{
                    formula: "The rate in force on the quote date, locked for the life of the quote",
                    result: version.exchange_rate.rate,
                    inputs: [
                      { label: "Pair", value: version.exchange_rate.pair, source: version.exchange_rate.source, sourceKind: "Exchange rate" },
                      { label: "As of", value: dateOnly(version.exchange_rate.as_of_date), source: version.exchange_rate.source, sourceKind: "Exchange rate" },
                    ],
                  }}
                />{" "}
                ({version.exchange_rate.pair}, {dateOnly(version.exchange_rate.as_of_date)})
              </dd>
            </div>
          )}
          {version.tariff_table && (
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 6 }}>
              <dt className="ds-mono-label">Duty table</dt>
              <dd style={{ margin: 0, display: "flex", flexWrap: "wrap", gap: 6, alignItems: "center" }}>
                <Stamp tone="light">{version.tariff_table.version}</Stamp>
                <StatusChip tone={version.tariff_table.signed_off ? "pass" : "warn"} size="small">
                  {version.tariff_table.signed_off ? "Signed off" : "Not signed off"}
                </StatusChip>
              </dd>
            </div>
          )}
        </dl>
      </Card>

      <Card eyebrow="Documents" style={{ marginTop: 16 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
          <a href={documentUrl(`/api/cases/${caseId}/quote-preview`)} target="_blank" rel="noreferrer" className="ds-btn" data-tone="secondary" data-size="small">
            The quote
          </a>
          <a href={documentUrl(`/api/cases/${caseId}/line-export`)} className="ds-btn" data-tone="secondary" data-size="small">
            The lines as a spreadsheet
          </a>
        </div>
      </Card>

      {detail.supplier_requests.length > 0 && (
        <Card eyebrow="Supplier requests" style={{ marginTop: 16 }}>
          <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 12 }}>
            {detail.supplier_requests.map((request) => (
              <li key={request.id} style={{ fontSize: 13 }}>
                <p style={{ margin: 0, display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                  <Stamp>{request.reference}</Stamp>
                  <StatusChip tone={request.status === "answered" ? "pass" : "warn"} pulse={request.status !== "answered"} size="small">
                    {request.status === "answered" ? "Answered" : "Waiting"}
                  </StatusChip>
                </p>
                <p style={{ margin: "6px 0 0", color: "var(--ds-text-2)" }}>
                  {request.supplier.name} · lines {request.line_numbers.join(", ")}
                </p>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

export const dynamic = "force-dynamic";
