"use client";

import { Constellation } from "@/design/Constellation";
import { StatusChip } from "@/design/StatusChip";
import { readUser } from "@/lib/api";
import { useLoad } from "@/lib/hooks";
import type { InvoiceBrief, Page } from "@/lib/types";
import { WalkthroughSteps } from "@/components/walkthrough";
import { ErrorNote, Loading, PageBand } from "@/components/ui";

const CHAIN = Array.from({ length: 9 }, (_, index) => ({
  id: `w-${index}`,
  x: 0.55 + (index % 3) * 0.13 + (Math.floor(index / 3) % 2 ? 0.06 : 0),
  y: 0.22 + Math.floor(index / 3) * 0.28,
  r: index === 8 ? 4.4 : 2.8,
  tone: (index === 8 ? "accent" : "light") as "accent" | "light",
  ring: index === 8,
  lit: index === 8,
}));
const CHAIN_LINKS = CHAIN.slice(1).map((node, index) => ({ from: CHAIN[index].id, to: node.id, tone: "accent" as const }));

export default function WalkthroughPage() {
  const list = useLoad<Page<InvoiceBrief>>("/api/invoices?limit=200");
  const user = readUser();
  const controller = user?.role === "controller" || user?.role === "administrator";

  return (
    <div>
      <PageBand
        eyebrow={["Walkthrough", "nine steps", "about eight minutes"]}
        title="Show it in nine steps."
        accent="Each one is a real invoice."
        lede="The order a controller would want to see it in: the post arriving, the cases that break a prototype, the dropped connection, and the measurements. Every button below opens the invoice that shows that step."
        canvas={<Constellation nodes={CHAIN} links={CHAIN_LINKS} ambient={36} traffic={{ paths: [CHAIN.map((n) => n.id)], every: 1600 }} />}
        aside={
          <div className="lf-walk-who">
            <p className="ds-mono-label" style={{ margin: 0 }}>
              Signed in as
            </p>
            <p style={{ margin: "8px 0 0", fontSize: 18, fontWeight: 650 }}>{user?.full_name ?? "—"}</p>
            <p style={{ margin: "2px 0 0", color: "var(--ds-ink-muted)" }}>{user?.role_label}</p>
            <div style={{ marginTop: 14 }}>
              <StatusChip tone={controller ? "pass" : "warn"} surface="dark">
                {controller ? "Can do every step" : "Some steps need a controller"}
              </StatusChip>
            </div>
            {!controller && (
              <p style={{ margin: "10px 0 0", fontSize: 13, color: "var(--ds-ink-muted)" }}>
                Sign in as Ravi Menon, the controller, to sign, post and record the call-back.
              </p>
            )}
          </div>
        }
      />
      <div className="ds-work">
        {list.error && <ErrorNote error={list.error} />}
        {list.loading && !list.data ? <Loading what="Finding the invoices" /> : <WalkthroughSteps invoices={list.data?.items ?? []} />}
      </div>
    </div>
  );
}

export const dynamic = "force-dynamic";
