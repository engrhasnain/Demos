"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Band, Button, Empty, Stamp } from "@/design/Surface";
import { Tabs } from "@/design/Tabs";
import { Figure } from "@/components/trace";
import { ErrorNote, Loading, ThesisStrip, Track } from "@/components/ui";
import { useLoad } from "@/lib/hooks";
import type { Dashboard, Page, ShipmentBrief } from "@/lib/types";
import { shipmentChip } from "@/lib/words";

type Filter = "all" | "done" | "needs_a_person" | "booked" | "pending";

const PAGE = 40;

export default function ShipmentsPage() {
  return (
    <Suspense fallback={<div className="ds-work"><Loading what="Opening the queue" /></div>}>
      <Queue />
    </Suspense>
  );
}

function Queue() {
  const params = useSearchParams();
  const router = useRouter();
  const exception = params.get("exception") ?? "";
  const initial = (params.get("state") as Filter | null) ?? "all";
  const [filter, setFilter] = useState<Filter>(["all", "done", "needs_a_person", "booked", "pending"].includes(initial) ? initial : "all");
  const [search, setSearch] = useState("");
  const [typed, setTyped] = useState("");
  const [offset, setOffset] = useState(0);

  useEffect(() => {
    const handle = window.setTimeout(() => {
      setSearch(typed.trim());
      setOffset(0);
    }, 280);
    return () => window.clearTimeout(handle);
  }, [typed]);

  const query = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (filter !== "all") query.set("state", filter);
  if (exception) query.set("exception_kind", exception);
  if (search) query.set("search", search);
  const { data, error, loading } = useLoad<Page<ShipmentBrief>>(`/api/shipments?${query.toString()}`);
  const { data: dashboard } = useLoad<Dashboard>("/api/dashboard");

  const by = (state: string) => dashboard?.by_state.find((row) => row.state === state)?.count ?? 0;
  const exceptionLabel = dashboard?.by_exception.find((row) => row.kind === exception)?.label;

  return (
    <>
      <Band top>
        <Reveal y={24}>
          <span className="ds-eyebrow">
            <span className="ds-live-dot" data-tone="accent" aria-hidden />
            Shipments <span className="ds-eyebrow-sep">·</span> today
          </span>
        </Reveal>
        <Reveal index={1} y={32}>
          <h1 className="ds-display ds-band-title">
            Every shipment,
            <br />
            <span className="ds-accent-text pb-light">and how far its row got.</span>
          </h1>
        </Reveal>
        <Reveal index={2}>
          <p className="ds-band-lede">
            Five checkpoints per row: checked, booked, tracking collected, written back, done. A row that needs a person
            stops at the checkpoint that refused it, with a name and the evidence. Open any row for its whole trace.
          </p>
        </Reveal>
        {dashboard && (
          <Reveal index={3}>
            <div className="ds-stats">
              {(
                [
                  ["Done", by("done"), "pass", "done"],
                  ["Needs a person", by("needs_a_person"), "warn", "needs_a_person"],
                  ["Not started", by("pending"), undefined, "pending"],
                ] as const
              ).map(([label, value, tone, state]) => (
                <div key={label}>
                  <span className="ds-stat-value" data-tone={tone}>
                    <Figure
                      value={String(value)}
                      count={value}
                      heading={label}
                      explain={{
                        formula: `count of rows whose state is "${label.toLowerCase()}"`,
                        inputs: [
                          { label, value: String(value), source: "Shipment rows, grouped by state", sourceKind: "Live rows" },
                          { label: "All rows today", value: String(dashboard.shipments), source: "Every shipment loaded", sourceKind: "Live rows" },
                        ],
                      }}
                    />
                  </span>
                  <button type="button" className="ds-mono-label ds-stat-label" style={{ background: "none", border: 0, padding: 0, cursor: "pointer" }} onClick={() => setFilter(state)}>
                    {label} →
                  </button>
                </div>
              ))}
            </div>
          </Reveal>
        )}
      </Band>

      <div className="ds-work" style={{ display: "grid", gap: 22 }}>
        <div className="pb-search">
          <Tabs<Filter>
            label="Filter the shipments"
            idPrefix="queue"
            value={filter}
            onChange={(next) => {
              setFilter(next);
              setOffset(0);
            }}
            tabs={[
              { key: "all", label: "All", badge: dashboard?.shipments },
              { key: "done", label: "Done", badge: by("done") },
              { key: "needs_a_person", label: "Needs a person", badge: by("needs_a_person") },
              { key: "booked", label: "Booked", badge: by("booked") },
              { key: "pending", label: "Not started", badge: by("pending") },
            ]}
          />
          <div style={{ display: "flex", flex: "1 1 260px", justifyContent: "flex-end", gap: 10, alignItems: "center" }}>
            <label htmlFor="queue-search" className="ds-sr-only">
              Search by shipment, order or customer
            </label>
            <input
              id="queue-search"
              className="ds-input"
              placeholder="Search shipment, order or customer"
              value={typed}
              onChange={(event) => setTyped(event.target.value)}
            />
          </div>
        </div>

        {exception && (
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 10 }}>
            <StatusChip tone="warn">Only: {exceptionLabel ?? exception.replace(/_/g, " ")}</StatusChip>
            <Button size="small" tone="ghost" onClick={() => router.replace("/shipments")}>
              Show every reason
            </Button>
          </div>
        )}

        {error && <ErrorNote error={error} />}

        <section className="ds-card" id="queue-panel" role="tabpanel" aria-labelledby={`queue-${filter}`}>
          {loading && !data ? (
            <div style={{ padding: "0 20px" }}>
              <Loading what="Reading the rows" />
            </div>
          ) : !data || data.items.length === 0 ? (
            <div style={{ padding: 20 }}>
              <Empty title="No shipment matches.">Try another filter or clear the search.</Empty>
            </div>
          ) : (
            <div className="ds-table-wrap">
              <table className="ds-table">
                <thead>
                  <tr>
                    <th>Shipment</th>
                    <th>Customer</th>
                    <th>Checkpoints</th>
                    <th>Tracking number</th>
                    <th>Where it is</th>
                    <th data-align="right">Runs that touched it</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((shipment, index) => {
                    const chip = shipmentChip(shipment);
                    return (
                      <Reveal
                        as="tr"
                        key={`${shipment.reference}-${filter}-${offset}`}
                        index={index}
                        y={24}
                        data-clickable=""
                        onClick={() => router.push(`/shipments/${encodeURIComponent(shipment.reference)}`)}
                      >
                        <td className="ds-rowmark" style={{ "--row-tone": `var(--ds-${chip.tone === "neutral" ? "line-strong" : chip.tone})` } as React.CSSProperties}>
                          <Link href={`/shipments/${encodeURIComponent(shipment.reference)}`} onClick={(event) => event.stopPropagation()}>
                            <Stamp>{shipment.reference}</Stamp>
                          </Link>
                          {shipment.dangerous && (
                            <span style={{ display: "block", marginTop: 6 }}>
                              <StatusChip tone="accent" size="small">
                                Dangerous goods
                              </StatusChip>
                            </span>
                          )}
                        </td>
                        <td style={{ maxWidth: 260 }}>
                          <span style={{ display: "block", fontWeight: 500 }}>{shipment.customer}</span>
                          <span className="ds-mono" style={{ fontSize: 11.5, color: "var(--ds-text-3)" }}>
                            {shipment.order_number} · {shipment.city}
                          </span>
                        </td>
                        <td>
                          <Track shipment={shipment} />
                        </td>
                        <td className="ds-mono" style={{ fontSize: 12.5 }}>
                          {shipment.tracking_number || <span style={{ color: "var(--ds-text-3)" }}>none yet</span>}
                        </td>
                        <td>
                          <StatusChip tone={chip.tone} size="small">
                            {chip.label}
                          </StatusChip>
                          {shipment.exception_label && (
                            <span style={{ display: "block", marginTop: 5, fontSize: 12.5, color: "var(--ds-warn-ink)" }}>{shipment.exception_label}</span>
                          )}
                        </td>
                        <td data-align="right" onClick={(event) => event.stopPropagation()}>
                          <Figure
                            value={String(shipment.attempts)}
                            heading={`Runs that touched ${shipment.reference}`}
                            align="end"
                            explain={{
                              formula: "one is added each time a run picks the row up",
                              inputs: [
                                { label: "Runs that picked it up", value: String(shipment.attempts), source: "The attempts counter on the row", sourceKind: "Live rows" },
                                { label: "Where it is now", value: shipment.state_label, source: "The row's own checkpoint", sourceKind: "Live rows" },
                              ],
                              note: "A finished row is never picked up again. A row that needs a person is looked at again by every run, and stops again at the same check until somebody fixes it.",
                            }}
                          />
                        </td>
                      </Reveal>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
          {data && data.total > PAGE && (
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 12, padding: "14px 20px", borderTop: "1px solid var(--ds-line)" }}>
              <span className="ds-mono" style={{ fontSize: 12, color: "var(--ds-text-3)" }}>
                {offset + 1} to {Math.min(offset + PAGE, data.total)} of {data.total}
              </span>
              <span style={{ display: "flex", gap: 8 }}>
                <Button size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                  Previous
                </Button>
                <Button size="small" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
                  Next
                </Button>
              </span>
            </div>
          )}
        </section>

        <ThesisStrip />
      </div>
    </>
  );
}
