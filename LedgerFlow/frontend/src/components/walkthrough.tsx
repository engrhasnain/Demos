"use client";

/**
 * The walkthrough, in nine steps, each one pointing at the real invoice
 * that shows it.
 *
 * The morning's post is put through in a fixed order, so the oldest
 * invoices line up with the batch the server describes. That is checked
 * against what each one must look like (the repeat has to be the one marked
 * "Already received"); if anything has moved, each step is found by what it
 * looks like instead.
 */

import Link from "next/link";
import { useMemo } from "react";

import { Card } from "@/design/Surface";
import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { useLoad } from "@/lib/hooks";
import { money } from "@/lib/format";
import type { BatchItem, InvoiceBrief } from "@/lib/types";
import { LinkButton, SectionHead, matchState } from "@/components/ui";

export type WalkStep = {
  number: number;
  key: string;
  title: string;
  doing: string;
  see: string;
  batchKey?: string;
  href?: string;
  linkWords?: string;
  invoice?: InvoiceBrief | null;
};

const STEPS: Omit<WalkStep, "number">[] = [
  {
    key: "post",
    title: "The morning's post",
    doing: "Nineteen documents arrive: ordinary invoices, a telephone photograph, a paper uniform invoice, an electronic one with its barcode, a four-page forwarder statement and the hard cases.",
    see: "The ordinary ones post with nobody touching them. Every other one stops, and says why in a few words.",
    href: "/invoices",
    linkWords: "Open the register",
  },
  {
    key: "partial",
    title: "Billed in full, part delivered",
    doing: "Open the invoice that bills for the whole order when the deliveries do not cover it.",
    see: "Only what arrived is payable; the rest is held, not refused. Press the held amount for the arithmetic and the goods receipt it came from.",
    batchKey: "partial_delivery",
  },
  {
    key: "repeat",
    title: "The same invoice, sent again as 0042",
    doing: "Open the photograph of an invoice already received, numbered 0042 instead of INV-0042.",
    see: "Blocked as a repeat, with the signals that caught it and a link to the original.",
    batchKey: "duplicate",
  },
  {
    key: "bank",
    title: "A new bank account",
    doing: "Open the invoice asking to be paid into an account never paid before.",
    see: "A hard stop. A call-back to the telephone number already on file. The supplier record is not changed until a controller records the call.",
    batchKey: "bank_change",
  },
  {
    key: "credit",
    title: "A credit note",
    doing: "Open the credit note for returned goods.",
    see: "Recognised as a credit, not matched three ways, and linked to the bill it credits.",
    batchKey: "credit_note",
  },
  {
    key: "buyer",
    title: "The wrong business number",
    doing: "Open the uniform invoice made out to somebody else's business number.",
    see: "Refused with the reason: it is not billed to us, so the tax cannot be claimed and it cannot be posted.",
    batchKey: "wrong_buyer",
  },
  {
    key: "freight",
    title: "Freight that is not on the order",
    doing: "Open the invoice with a delivery charge of 850 that no purchase order mentions.",
    see: "Accepted, because it is inside this supplier's allowance of 1,000. Press the line to see the rule.",
    batchKey: "freight_allowance",
  },
  {
    key: "retry",
    title: "Drop the connection half way",
    doing: "Sign the paper uniform invoice, then press Post, but drop the connection. Then post it again.",
    see: "The ledger took the bill before the connection died. The retry finds it by its key. Exactly one bill in the ledger.",
    batchKey: "uniform_paper",
  },
  {
    key: "numbers",
    title: "The numbers",
    doing: "Open the evidence and measure it now.",
    see: "Fields read right, repeats caught, bank changes blocked, invoices posted untouched and bills paid twice, measured, with every miss listed.",
    href: "/evidence",
    linkWords: "Open the evidence",
  },
];

function resolve(items: BatchItem[], invoices: InvoiceBrief[]): Record<string, InvoiceBrief | null> {
  const found: Record<string, InvoiceBrief | null> = {};
  const oldest = invoices.slice().sort((a, b) => a.id - b.id);
  const byOrder = new Map<string, InvoiceBrief>();
  items.forEach((item, index) => oldest[index] && byOrder.set(item.key, oldest[index]));
  const orderHolds = byOrder.get("duplicate")?.headline === "Already received" || !items.length;

  const guess: Record<string, (invoice: InvoiceBrief) => boolean> = {
    duplicate: (invoice) => invoice.headline === "Already received",
    bank_change: (invoice) => invoice.headline === "Bank details changed",
    credit_note: (invoice) => invoice.kind === "credit_note",
    wrong_buyer: (invoice) => invoice.headline === "Wrong buyer business number",
    partial_delivery: (invoice) => ["Only part of it has arrived", "Nothing has arrived yet"].includes(invoice.headline),
    uniform_paper: (invoice) => invoice.status === "awaiting_approval" && invoice.kind === "bill" && invoice.currency === "TWD",
    freight_allowance: () => false,
  };
  STEPS.forEach((step) => {
    if (!step.batchKey) return;
    const ordered = orderHolds ? byOrder.get(step.batchKey) : undefined;
    found[step.batchKey] = ordered ?? oldest.find(guess[step.batchKey] ?? (() => false)) ?? null;
  });
  return found;
}

export function useWalkthrough(invoices: InvoiceBrief[]): WalkStep[] {
  const batch = useLoad<{ total: number; items: BatchItem[] }>("/api/demo/batch");
  return useMemo(() => {
    const found = resolve(batch.data?.items ?? [], invoices);
    return STEPS.map((step, index) => {
      const invoice = step.batchKey ? found[step.batchKey] : null;
      let href = step.href;
      let linkWords = step.linkWords;
      if (invoice) {
        href = step.key === "bank" && invoice.vendor ? `/suppliers/${invoice.vendor.id}` : `/invoices/${invoice.id}${step.key === "retry" ? "#paid-once" : ""}`;
        linkWords = step.key === "bank" ? "Make the call-back" : `Open ${invoice.reference}`;
      }
      return { ...step, number: index + 1, invoice, href, linkWords };
    });
  }, [batch.data, invoices]);
}

/* ------------------------------------------------------------------ */
/* On the desk: the nine steps at a glance                             */
/* ------------------------------------------------------------------ */
export function WalkthroughPreview({ invoices }: { invoices: InvoiceBrief[] }) {
  const steps = useWalkthrough(invoices);
  return (
    <section style={{ marginTop: 64 }} aria-labelledby="walk-heading">
      <SectionHead
        label="Nine steps · about eight minutes"
        title="Show it to somebody"
        id="walk-heading"
        action={
          <LinkButton href="/walkthrough" tone="secondary" arrow>
            The walkthrough
          </LinkButton>
        }
      />
      <ol className="lf-walk-grid">
        {steps.map((step, index) => {
          const look = step.invoice ? matchState(step.invoice) : null;
          return (
            <Reveal as="li" key={step.key} index={index} className="lf-walk-card ds-lift">
              <Link href={step.href ?? "/walkthrough"} className="lf-walk-link">
                <span className="lf-walk-number ds-mono">{String(step.number).padStart(2, "0")}</span>
                <span className="lf-walk-title">{step.title}</span>
                <span className="lf-walk-see">{step.see}</span>
                <span className="lf-walk-foot">
                  {look ? (
                    <StatusChip tone={look.tone} size="small" pulse={look.live}>
                      {look.label}
                    </StatusChip>
                  ) : (
                    <StatusChip tone="accent" size="small">
                      Open
                    </StatusChip>
                  )}
                  <span className="ds-mono lf-walk-ref">{step.invoice?.reference ?? step.linkWords}</span>
                </span>
              </Link>
            </Reveal>
          );
        })}
      </ol>
    </section>
  );
}

/* ------------------------------------------------------------------ */
/* The walkthrough page: each step on a node chain                     */
/* ------------------------------------------------------------------ */
export function WalkthroughSteps({ invoices }: { invoices: InvoiceBrief[] }) {
  const steps = useWalkthrough(invoices);
  return (
    <Card flush eyebrow="Do this · see that" title="The walkthrough, in order">
      <div className="lf-walk-chain">
        <NodeChain
          stagger={80}
          items={steps.map((step) => {
            const look = step.invoice ? matchState(step.invoice) : null;
            return {
              key: step.key,
              tone: look ? (look.tone === "pass" ? "pass" : look.tone === "fail" ? "fail" : look.tone === "warn" ? "warn" : "accent") : "accent",
              marker: String(step.number).padStart(2, "0"),
              content: (
                <div className="lf-walk-step">
                  <div className="lf-walk-step-head">
                    <h3>{step.title}</h3>
                    {look && (
                      <StatusChip tone={look.tone} pulse={look.live}>
                        {look.label}
                      </StatusChip>
                    )}
                  </div>
                  <div className="lf-walk-cols">
                    <p>
                      <span className="ds-mono-label">Do</span>
                      {step.doing}
                    </p>
                    <p>
                      <span className="ds-mono-label">You should see</span>
                      {step.see}
                    </p>
                  </div>
                  <div className="lf-walk-step-foot">
                    {step.href && (
                      <LinkButton href={step.href} tone={step.number === 1 ? "primary" : "secondary"} size="small" arrow>
                        {step.linkWords ?? "Open"}
                      </LinkButton>
                    )}
                    {step.invoice && (
                      <span className="ds-mono lf-walk-ref">
                        {step.invoice.vendor_name} · {money(step.invoice.total_amount)} {step.invoice.currency}
                        {step.invoice.headline ? ` · ${step.invoice.headline}` : ""}
                      </span>
                    )}
                  </div>
                </div>
              ),
            };
          })}
        />
      </div>
    </Card>
  );
}
