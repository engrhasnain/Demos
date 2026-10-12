"use client";

import Link from "next/link";
import { use, useMemo, useState } from "react";

import { Band, Banner, Button, Card, Empty, Stamp } from "@/design/Surface";
import { Constellation, type ConstellationLink, type ConstellationNode } from "@/design/Constellation";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { api, readUser } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";
import { count, dateAndTime, dateOnly, money } from "@/lib/format";
import type { CallBack, InvoiceBrief, VendorDetail } from "@/lib/types";
import { Figure } from "@/components/trace";
import { ErrorNote, Field, Ledger, Loading, MatchGlyph, PageBand, Td, Th, matchState } from "@/components/ui";

export default function OneSupplier({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { data, error, loading, reload } = useLoad<VendorDetail>(`/api/vendors/${id}`);

  if (error)
    return (
      <Band top>
        <div style={{ padding: "24px 0" }}>
          <ErrorNote error={error} />
        </div>
      </Band>
    );
  if (loading && !data)
    return (
      <Band top>
        <Loading what="Opening the supplier" />
      </Band>
    );
  if (!data) return null;

  const open = data.call_backs.filter((task) => task.status === "open");
  const done = data.call_backs.filter((task) => task.status !== "open");
  const invoices = data.invoices ?? [];

  return (
    <div>
      <PageBand
        back={
          <Link href="/suppliers" className="lf-back">
            ← Every supplier
          </Link>
        }
        eyebrow={["Supplier", data.code, `${data.country} · pays in ${data.currency}`]}
        title={data.name}
        lede={
          data.bank_change_pending
            ? "An invoice from this supplier asked to be paid into an account we have never paid. Every open invoice from them is blocked until a controller rings the number already on file."
            : `Bills ${data.entity_code === "US" ? "Hengtai Industrial Supply USA" : "Hengtai Industrial Supply, Taiwan"}. Paid on ${data.payment_terms_days} days.`
        }
        aside={
          <div className="lf-band-tiles">
            <div className="lf-band-tile" data-static="">
              <span className="ds-stat-value" data-tone={data.bank_change_pending ? "fail" : "pass"}>
                {data.bank_change_pending ? "Blocked" : "Clear"}
              </span>
              <span className="ds-mono-label ds-stat-label">Payments</span>
            </div>
            <div className="lf-band-tile" data-static="">
              <span className="ds-stat-value">
                <Figure
                  value={count(invoices.length)}
                  count={invoices.length}
                  decimals={0}
                  heading={`Invoices from ${data.name}`}
                  explain={{
                    formula: "Invoices received from this supplier",
                    inputs: invoices.map((invoice) => ({
                      label: invoice.invoice_number || invoice.reference,
                      value: `${money(invoice.total_amount)} ${invoice.currency}`,
                      source: invoice.status_label,
                      sourceKind: "Invoice",
                    })),
                  }}
                />
              </span>
              <span className="ds-mono-label ds-stat-label">Invoices</span>
            </div>
          </div>
        }
      />

      <div className="ds-work">
        {open.map((task) => (
          <div key={task.id} style={{ marginBottom: 32 }}>
            <CallBackCard task={task} onDone={reload} />
          </div>
        ))}

        <div className="lf-invoice-grid">
          <div className="lf-invoice-main">
            <Card flush eyebrow="Only a recorded call changes these" title="Bank accounts on file">
              <Ledger
                head={
                  <>
                    <Th>Bank</Th>
                    <Th>Account</Th>
                    <Th>Checked</Th>
                    <Th align="right">Now</Th>
                  </>
                }
              >
                {data.bank_accounts.map((account, index) => (
                  <Reveal as="tr" key={account.id} index={index} y={18}>
                    <Td className="ds-rowmark" style={{ "--row-tone": account.is_current ? "var(--ds-pass)" : "var(--ds-line-strong)" } as React.CSSProperties}>
                      {account.bank}
                    </Td>
                    <Td>
                      <span className="ds-mono">{account.shown_as}</span>
                    </Td>
                    <Td style={{ color: "var(--ds-text-2)", fontSize: 12.5 }}>
                      {account.verified_by ? `${account.verified_by}, ` : ""}
                      {dateOnly(account.verified_at)}
                    </Td>
                    <Td align="right">
                      {account.is_current ? (
                        <StatusChip tone="pass" size="small">
                          In use
                        </StatusChip>
                      ) : (
                        <StatusChip tone="neutral" size="small">
                          Not current
                        </StatusChip>
                      )}
                    </Td>
                  </Reveal>
                ))}
              </Ledger>
            </Card>

            <Card flush eyebrow={`${invoices.length} received`} title="Their invoices">
              {!invoices.length ? (
                <div style={{ padding: 20 }}>
                  <Empty title="None yet." />
                </div>
              ) : (
                <Ledger
                  head={
                    <>
                      <Th width="3rem">Match</Th>
                      <Th>Number</Th>
                      <Th>Date</Th>
                      <Th align="right">Invoiced</Th>
                      <Th align="right">Payable</Th>
                      <Th>Where it is</Th>
                    </>
                  }
                >
                  {invoices.map((invoice: InvoiceBrief, index) => {
                    const look = matchState(invoice);
                    return (
                      <Reveal as="tr" key={invoice.id} index={index} y={18}>
                        <Td>
                          <MatchGlyph state={look} posted={invoice.status === "posted"} />
                        </Td>
                        <Td>
                          <Link href={`/invoices/${invoice.id}`} className="lf-cell-link ds-mono">
                            {invoice.invoice_number || invoice.reference}
                          </Link>
                        </Td>
                        <Td style={{ color: "var(--ds-text-2)" }}>{dateOnly(invoice.invoice_date)}</Td>
                        <Td align="right">{money(invoice.total_amount)}</Td>
                        <Td align="right" style={{ fontWeight: 650 }}>
                          {money(invoice.approved_amount)}
                        </Td>
                        <Td>
                          <StatusChip tone={look.tone} pulse={look.live} size="small">
                            {look.label}
                          </StatusChip>
                        </Td>
                      </Reveal>
                    );
                  })}
                </Ledger>
              )}
            </Card>

            {done.length > 0 && (
              <Card eyebrow="Call-backs" title="Calls already made">
                <ul className="lf-done-calls">
                  {done.map((task) => (
                    <li key={task.id}>
                      <StatusChip tone={task.outcome === "confirmed" ? "pass" : "fail"} size="small">
                        {task.outcome || task.status}
                      </StatusChip>
                      <span>
                        {task.completed_by?.name ?? "—"} · {dateAndTime(task.completed_at)}
                      </span>
                      <span className="lf-cell-sub">{task.note}</span>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
          </div>

          <aside className="lf-invoice-side">
            <Card eyebrow="The supplier record" title="On file">
              <dl>
                <Field label="Bills">{data.entity_code}</Field>
                <Field label="Business number">
                  <span className="ds-mono">{data.tax_identifier || "—"}</span>
                </Field>
                <Field label="Email">{data.email}</Field>
                <Field label="Telephone">
                  <span className="ds-mono">{data.telephone}</span>
                </Field>
                <Field label="Paid on">{data.payment_terms_days} days</Field>
              </dl>
            </Card>
            <Card eyebrow="How far it may drift" title="Tolerances">
              <dl>
                <Field label="Above the order">
                  <Figure
                    value={`${data.tolerance_percent}% or ${money(data.tolerance_absolute)}`}
                    heading="Price tolerance"
                    explain={{
                      formula: "A unit price may sit above the order by this share or this amount, whichever is larger; beyond it the line is held",
                      inputs: [
                        { label: "Share", value: `${data.tolerance_percent}%`, source: data.name, sourceKind: "Supplier record" },
                        { label: "Amount", value: money(data.tolerance_absolute), source: data.name, sourceKind: "Supplier record" },
                      ],
                    }}
                  />
                </Field>
                <Field label="Not on the order">
                  <Figure
                    value={`up to ${money(data.unordered_allowance)}`}
                    heading="Charges not on the order"
                    explain={{
                      formula: "Freight and handling that no purchase order mentions are accepted up to this amount; beyond it, held",
                      inputs: [{ label: "Allowance", value: money(data.unordered_allowance), source: data.name, sourceKind: "Supplier record" }],
                    }}
                  />
                </Field>
              </dl>
            </Card>
          </aside>
        </div>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* The call-back: ring the number on file, never the one on the invoice */
/* ------------------------------------------------------------------ */
function callScene(task: CallBack, outcome: "open" | "confirmed" | "refused") {
  const confirmed = outcome === "confirmed";
  const refused = outcome === "refused";
  const nodes: ConstellationNode[] = [
    { id: "us", x: 0.5, y: 0.5, r: 5, tone: "accent", ring: true, lit: true, label: "Hengtai", side: "below", drift: 1 },
    {
      id: "file",
      x: 0.16,
      y: 0.3,
      r: 4,
      tone: confirmed ? "muted" : "pass",
      lit: !confirmed,
      label: "Account on file",
      sub: task.requested_change.accounts_on_file?.[0]?.number ?? "",
      side: "below",
      drift: 2,
    },
    {
      id: "new",
      x: 0.84,
      y: 0.3,
      r: 4,
      tone: confirmed ? "pass" : "fail",
      ring: !confirmed,
      lit: true,
      label: confirmed ? "Confirmed by telephone" : refused ? "Refused" : "Asked for by the invoice",
      sub: task.requested_change.account_on_invoice ?? "",
      side: "below",
      drift: 2,
    },
    { id: "phone", x: 0.5, y: 0.12, r: 3.4, tone: confirmed ? "pass" : "warn", ring: outcome === "open", lit: true, label: "Ring the number on file", sub: task.telephone_on_file, side: "right", drift: 1.5 },
  ];
  const links: ConstellationLink[] = [
    { from: "us", to: "file", tone: confirmed ? "light" : "pass", lit: !confirmed },
    { from: "us", to: "new", tone: confirmed ? "pass" : "fail", lit: confirmed },
    { from: "us", to: "phone", tone: confirmed ? "pass" : "warn", lit: true },
    { from: "phone", to: "file", tone: "light", lit: false },
  ];
  return { nodes, links };
}

function CallBackCard({ task, onDone }: { task: CallBack; onDone: () => void }) {
  const user = readUser();
  const mayDecide = ["controller", "finance_director", "administrator"].includes(user?.role ?? "");
  const { busy, error, run } = useAction();
  const [note, setNote] = useState("");
  const [result, setResult] = useState<{ outcome: "confirmed" | "refused"; freed: number } | null>(null);
  const scene = useMemo(() => callScene(task, result?.outcome ?? "open"), [task, result]);

  const decide = (confirmed: boolean) =>
    void run(confirmed ? "yes" : "no", () =>
      api.post<{ invoices_freed: unknown[] }>(`/api/vendors/call-backs/${task.id}`, { confirmed, note }),
    ).then((response) => {
      if (response) {
        setResult({ outcome: confirmed ? "confirmed" : "refused", freed: response.invoices_freed.length });
        window.setTimeout(onDone, 2600);
      }
    });

  return (
    <Reveal>
      <div className="lf-callback">
        <div className="lf-callback-stage">
          <Constellation nodes={scene.nodes} links={scene.links} ambient={22} traffic={{ paths: [["us", "phone"], ["phone", "us"]], every: 1300, tone: result ? "pass" : "warn" }} label="The call-back: the account on file, the account the invoice asked for, and the telephone number to ring" />
        </div>
        <div className="lf-callback-body">
          <StatusChip tone={result ? (result.outcome === "confirmed" ? "pass" : "fail") : "fail"} surface="dark" pulse={!result}>
            {result ? (result.outcome === "confirmed" ? "Confirmed by telephone" : "Not confirmed") : "Hard stop · call-back raised"}
          </StatusChip>
          <h2 className="ds-title lf-callback-title">A new bank account was asked for</h2>
          <p className="lf-callback-text">
            Invoice {task.requested_change.invoice_reference} asked to be paid into {task.requested_change.account_on_invoice}. Nothing was
            changed. Ring the number already on file, not one printed on the invoice.
          </p>
          <div className="lf-callback-ring">
            <span className="ds-mono-label">Ring this, not the invoice</span>
            <b className="ds-mono">{task.telephone_on_file}</b>
          </div>
          {mayDecide && !result ? (
            <>
              <label className="ds-sr-only" htmlFor={`call-note-${task.id}`}>
                Who you spoke to
              </label>
              <input
                id={`call-note-${task.id}`}
                className="ds-input lf-callback-input"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="Who you spoke to, on what number"
              />
              <div className="lf-actions" style={{ marginTop: 12 }}>
                <Button tone="primary" busy={busy === "yes"} disabled={Boolean(busy)} onClick={() => decide(true)}>
                  They confirmed it
                </Button>
                <Button tone="ink" busy={busy === "no"} disabled={Boolean(busy)} onClick={() => decide(false)}>
                  They did not
                </Button>
              </div>
              <p className="lf-callback-hint">A note is required: who you spoke to, and on which number.</p>
            </>
          ) : !result ? (
            <p className="lf-callback-hint">A controller records the call.</p>
          ) : null}
          {result && (
            <div style={{ marginTop: 14 }}>
              <Banner tone={result.outcome === "confirmed" ? "pass" : "warn"} title="Recorded">
                {result.outcome === "confirmed"
                  ? `The account is changed. ${result.freed} ${result.freed === 1 ? "invoice" : "invoices"} released.`
                  : "The account was not changed. The invoice stays blocked."}
              </Banner>
            </div>
          )}
          {error && (
            <div style={{ marginTop: 12 }}>
              <ErrorNote error={error} />
            </div>
          )}
        </div>
      </div>
    </Reveal>
  );
}

export const dynamic = "force-dynamic";
