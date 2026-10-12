"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Constellation } from "@/design/Constellation";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { useLoad } from "@/lib/hooks";
import { count, dateAndTime } from "@/lib/format";
import type { CallBack, Page, VendorBrief } from "@/lib/types";
import { Figure } from "@/components/trace";
import { Card, Empty, ErrorNote, Ledger, Loading, PageBand, SectionHead, Td, Th } from "@/components/ui";

/** Suppliers as a ring of nodes around the company, one of them coral. */
const RING = Array.from({ length: 14 }, (_, index) => {
  const angle = (index / 14) * Math.PI * 2;
  return {
    id: `s-${index}`,
    x: 0.78 + Math.cos(angle) * 0.13,
    y: 0.5 + Math.sin(angle) * 0.36,
    r: index === 3 ? 3.4 : 2.2,
    tone: (index === 3 ? "fail" : "light") as "fail" | "light",
    ring: index === 3,
    lit: index === 3,
  };
});
const HUB = { id: "hub", x: 0.78, y: 0.5, r: 4.6, tone: "accent" as const, ring: true, lit: true };
const RING_LINKS = RING.map((node) => ({ from: "hub", to: node.id, tone: (node.tone === "fail" ? "fail" : "light") as "fail" | "light", lit: node.tone === "fail" }));

export default function Suppliers() {
  const router = useRouter();
  const [search, setSearch] = useState("");
  const calls = useLoad<{ total: number; items: CallBack[] }>("/api/vendors/call-backs");
  const { data, error, loading } = useLoad<Page<VendorBrief>>(`/api/vendors?limit=60${search ? `&search=${encodeURIComponent(search)}` : ""}`);
  const open = calls.data?.items ?? [];

  return (
    <div>
      <PageBand
        eyebrow={["Suppliers", `${count(data?.total ?? 0)} on file`, "bank accounts verified by telephone"]}
        title="Who we pay,"
        accent="and where the money goes."
        lede="A supplier's bank account changes only after a controller rings the number already on file. An invoice can ask for a new account; it can never change one."
        canvas={<Constellation nodes={[HUB, ...RING]} links={RING_LINKS} ambient={30} traffic={{ paths: RING.map((node) => ["hub", node.id]), every: 700 }} />}
        aside={
          <div className="lf-band-tiles">
            <div className="lf-band-tile" data-static="">
              <span className="ds-stat-value" data-tone={open.length ? "fail" : "pass"}>
                <Figure
                  value={count(calls.data?.total ?? 0)}
                  count={calls.data?.total ?? 0}
                  decimals={0}
                  heading="Call-backs to make"
                  explain={{
                    formula: "Open call-back tasks: an invoice asked for a bank account that is not on file",
                    inputs: open.map((task) => ({
                      label: task.vendor_name,
                      value: task.requested_change.account_on_invoice ?? "",
                      source: `Raised ${dateAndTime(task.created_at)}`,
                      sourceKind: "Call-back task",
                    })),
                  }}
                />
              </span>
              <span className="ds-mono-label ds-stat-label">Call-backs to make</span>
            </div>
          </div>
        }
      />

      <div className="ds-work">
        {open.length > 0 && (
          <section style={{ marginBottom: 48 }} aria-labelledby="calls-heading">
            <SectionHead label="Hard stop · nothing paid until the call" title="Calls to make" id="calls-heading" />
            <ul className="lf-calls">
              {open.map((task, index) => (
                <Reveal as="li" key={task.id} index={index} className="lf-call ds-lift">
                  <Link href={`/suppliers/${task.vendor_id}`} className="lf-call-link">
                    <span className="lf-call-head">
                      <StatusChip tone="fail" pulse>
                        Bank account change
                      </StatusChip>
                      <span className="ds-mono lf-cell-sub">{task.requested_change.invoice_reference}</span>
                    </span>
                    <span className="lf-call-title">{task.vendor_name}</span>
                    <span className="lf-call-accounts">
                      <span>
                        <span className="ds-mono-label">On the invoice</span>
                        <b className="ds-mono" style={{ color: "var(--ds-fail-ink)" }}>
                          {task.requested_change.account_on_invoice}
                        </b>
                      </span>
                      <span>
                        <span className="ds-mono-label">Ring</span>
                        <b className="ds-mono">{task.telephone_on_file}</b>
                      </span>
                    </span>
                    <span className="lf-call-go">Make the call-back →</span>
                  </Link>
                </Reveal>
              ))}
            </ul>
          </section>
        )}

        <div className="lf-filter-bar">
          <SectionHead label="The supplier record" title="Every supplier" />
          <label className="lf-search">
            <span className="ds-sr-only">Search suppliers</span>
            <input className="ds-input" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search by name or code" />
          </label>
        </div>

        {error && <ErrorNote error={error} />}

        <Card flush eyebrow={data ? `${count(data.total)} found · first 60` : "Loading"} title="Suppliers on file" style={{ marginTop: 20 }}>
          {loading && !data ? (
            <Loading what="Loading" />
          ) : !data || data.items.length === 0 ? (
            <div style={{ padding: 20 }}>
              <Empty title="Nobody by that name." />
            </div>
          ) : (
            <Ledger
              head={
                <>
                  <Th>Name</Th>
                  <Th>Code</Th>
                  <Th>Country</Th>
                  <Th>Pays in</Th>
                  <Th>Bank account</Th>
                </>
              }
            >
              {data.items.map((vendor, index) => (
                <Reveal as="tr" key={vendor.id} index={index} y={18} data-clickable="" onClick={() => router.push(`/suppliers/${vendor.id}`)}>
                  <Td className="ds-rowmark" style={{ "--row-tone": vendor.bank_change_pending ? "var(--ds-fail)" : "var(--ds-line-strong)" } as React.CSSProperties}>
                    <Link href={`/suppliers/${vendor.id}`} className="lf-cell-link" onClick={(event) => event.stopPropagation()}>
                      {vendor.name}
                    </Link>
                  </Td>
                  <Td>
                    <span className="ds-mono" style={{ fontSize: 12.5 }}>
                      {vendor.code}
                    </span>
                  </Td>
                  <Td style={{ color: "var(--ds-text-2)" }}>{vendor.country}</Td>
                  <Td>{vendor.currency}</Td>
                  <Td>
                    {vendor.bank_change_pending ? (
                      <StatusChip tone="fail" pulse size="small">
                        Change asked for, blocked
                      </StatusChip>
                    ) : (
                      <StatusChip tone="neutral" size="small">
                        On file
                      </StatusChip>
                    )}
                  </Td>
                </Reveal>
              ))}
            </Ledger>
          )}
        </Card>
      </div>
    </div>
  );
}

export const dynamic = "force-dynamic";
