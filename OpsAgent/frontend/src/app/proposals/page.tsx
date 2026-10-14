"use client";

/**
 * Proposals: suggested, never done.
 *
 * Approving one records that a named person decided it, and that is where
 * the code path ends. Nothing in this product places an order, sends a
 * message or writes to any operational table, and the page says so.
 */

import { useState } from "react";

import { counted, Figure } from "@/components/trace";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { StepRail } from "@/design/StepRail";
import { Band, Banner, Button, Card, Empty, LinkButton } from "@/design/Surface";
import { api, ApiError } from "@/lib/api";
import { useLoad, useSignedIn } from "@/lib/session";
import type { ProposalRow } from "@/lib/types";
import { dayAndClock, reaches } from "@/lib/words";

function detailWords(key: string): string {
  if (key === "parts") return "Parts";
  if (key === "orders") return "Orders";
  return key.replace(/_/g, " ");
}

export default function Proposals() {
  const user = useSignedIn();
  const { data, error, reload } = useLoad<{ proposals: ProposalRow[] }>(user ? "/api/proposals" : null, [user?.email]);
  const [busy, setBusy] = useState<number | null>(null);
  const [note, setNote] = useState<Record<number, string>>({});
  const [trouble, setTrouble] = useState("");
  const [justDecided, setJustDecided] = useState<number | null>(null);

  if (!user) return null;
  const all = data?.proposals ?? [];
  const waiting = all.filter((item) => item.status === "proposed");
  const decided = all.filter((item) => item.status !== "proposed");
  const approved = decided.filter((item) => item.status === "approved").length;

  const decide = async (item: ProposalRow, approve: boolean) => {
    setBusy(item.id);
    setTrouble("");
    try {
      await api.post(`/api/proposals/${item.id}/decide`, { approve, note: note[item.id] ?? "" });
      setJustDecided(item.id);
      reload();
    } catch (cause) {
      setTrouble(cause instanceof ApiError ? cause.message : String(cause));
    } finally {
      setBusy(null);
    }
  };

  const stat = (label: string, value: number, formula: string, list: ProposalRow[], tone?: "accent" | "pass" | "warn") => (
    <div key={label}>
      <span className="ds-stat-value" data-tone={tone}>
        <Figure
          value={String(value)}
          count={value}
          content={counted(
            label,
            String(value),
            formula,
            list.slice(0, 8).map((item) => ({
              label: item.reference,
              value: item.status === "proposed" ? "waiting" : item.status,
              source: item.summary,
              sourceKind: "Proposal",
            })),
          )}
        />
      </span>
      <span className="ds-mono-label ds-stat-label">{label}</span>
    </div>
  );

  return (
    <>
      <Band top>
        <div className="oa-page-band">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="warn" aria-hidden />
              Proposals <span className="ds-eyebrow-sep">·</span> decided by a person
            </span>
          </Reveal>
          <Reveal index={1} y={32}>
            <h1 className="ds-display oa-page-title">
              Suggested, never done.
              <br />
              <span className="oa-light ds-accent-text">A decision is recorded. Nothing acts on it.</span>
            </h1>
          </Reveal>
          <Reveal index={2}>
            <p className="ds-band-lede">
              Some answers come with something worth doing: order ahead before a supplier shuts, send a revised promise
              date. They wait here for the named role. There is no executor in this product, not a disabled one, not one
              behind a switch.
            </p>
          </Reveal>
          <Reveal index={3}>
            <div className="ds-stats">
              {stat("Waiting for a person", waiting.length, "count of proposals nobody has decided yet", waiting, "warn")}
              {stat("Approved", approved, "count of proposals a person approved", decided.filter((item) => item.status === "approved"), "pass")}
              {stat("Declined", decided.length - approved, "count of proposals a person declined", decided.filter((item) => item.status === "declined"))}
              {stat("Carried out by this product", 0, "count of actions this product has taken; there is no code path that acts", [])}
            </div>
          </Reveal>
        </div>
      </Band>

      <div className="ds-work">
        {(error || trouble) && (
          <div style={{ marginBottom: 20 }}>
            <Banner tone="fail" title="That did not go through">
              {trouble || error}
            </Banner>
          </div>
        )}

        <section className="oa-section" style={{ marginTop: 0 }}>
          <Reveal>
            <p className="ds-mono-label">Waiting</p>
          </Reveal>
          {data && waiting.length === 0 ? (
            <Empty title="Nothing waiting.">
              Ask what happens if a supplier shuts down, or which of a customer&rsquo;s orders are late, and a proposal
              lands here.
              <div style={{ marginTop: 12 }}>
                <LinkButton href="/ask" tone="primary" size="small" arrow>
                  Ask a question
                </LinkButton>
              </div>
            </Empty>
          ) : (
            <div className="oa-proposals">
              {waiting.map((item, index) => {
                const mine = reaches(user.role, item.needs_role);
                return (
                  <Reveal key={item.id} index={index}>
                    <Card
                      eyebrow={`${item.reference} · raised ${dayAndClock(item.raised_at)}`}
                      title={item.summary}
                      action={
                        <StatusChip tone="warn" pulse>
                          Needs {item.needs_role_label.toLowerCase()}
                        </StatusChip>
                      }
                    >
                      <StepRail
                        steps={[
                          { key: "asked", label: "Question answered", sub: item.question_id ? `question ${item.question_id}` : "" },
                          { key: "raised", label: "Proposal raised", sub: dayAndClock(item.raised_at) },
                          { key: "waiting", label: `Waiting for ${item.needs_role_label.toLowerCase()}`, sub: mine ? "you can decide" : "not yours to decide" },
                          { key: "decided", label: "Decision recorded", sub: "" },
                          { key: "done", label: "Nothing carried out", sub: "by design" },
                        ]}
                        current={2}
                        tone="warn"
                        label="Where this proposal is"
                      />
                      <dl className="oa-proposal-detail">
                        {Object.entries(item.detail ?? {}).map(([key, value]) => (
                          <div key={key}>
                            <dt className="ds-mono-label">{detailWords(key)}</dt>
                            <dd className="ds-mono">{Array.isArray(value) ? value.join(", ") : String(value)}</dd>
                          </div>
                        ))}
                      </dl>
                      <div className="oa-proposal-actions">
                        {mine ? (
                          <>
                            <input
                              className="ds-input"
                              value={note[item.id] ?? ""}
                              placeholder="A note for the record, if you like"
                              aria-label={`Note for ${item.reference}`}
                              onChange={(event) => setNote({ ...note, [item.id]: event.target.value })}
                            />
                            <Button tone="primary" busy={busy === item.id} onClick={() => void decide(item, true)}>
                              Approve
                            </Button>
                            <Button tone="secondary" disabled={busy === item.id} onClick={() => void decide(item, false)}>
                              Decline
                            </Button>
                          </>
                        ) : (
                          <p style={{ margin: 0, fontSize: 13.5, color: "var(--ds-text-2)" }}>
                            Not yours to decide: this needs the {item.needs_role_label.toLowerCase()} role, and you are{" "}
                            {user.role_label.toLowerCase()}.
                          </p>
                        )}
                      </div>
                    </Card>
                  </Reveal>
                );
              })}
            </div>
          )}
        </section>

        {decided.length > 0 && (
          <section className="oa-section">
            <Reveal>
              <p className="ds-mono-label">Decided</p>
            </Reveal>
            <Card flush>
              <div className="ds-table-wrap">
                <table className="ds-table">
                  <thead>
                    <tr>
                      <th>Reference</th>
                      <th>What was suggested</th>
                      <th>Decision</th>
                      <th>Who and when</th>
                    </tr>
                  </thead>
                  <tbody>
                    {decided.map((item, index) => (
                      <Reveal
                        as="tr"
                        key={item.id}
                        index={index}
                        className="ds-rowmark"
                        data-fresh={justDecided === item.id ? "" : undefined}
                        style={{ "--row-tone": item.status === "approved" ? "var(--ds-pass)" : "var(--ds-line-strong)" } as React.CSSProperties}
                      >
                        <td className="ds-mono" style={{ fontSize: 12.5, whiteSpace: "nowrap" }}>
                          {item.reference}
                        </td>
                        <td style={{ minWidth: 240 }}>
                          {item.summary}
                          {item.note && <div style={{ marginTop: 4, fontSize: 12.5, color: "var(--ds-text-2)" }}>&ldquo;{item.note}&rdquo;</div>}
                        </td>
                        <td>
                          <StatusChip tone={item.status === "approved" ? "pass" : "neutral"} size="small">
                            {item.status === "approved" ? "Approved · not carried out" : "Declined"}
                          </StatusChip>
                        </td>
                        <td className="ds-mono" style={{ fontSize: 12.5, whiteSpace: "nowrap" }}>
                          {item.decided_by} · {dayAndClock(item.decided_at)}
                        </td>
                      </Reveal>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </section>
        )}
      </div>
    </>
  );
}
