"use client";

import Link from "next/link";
import { useState, type CSSProperties } from "react";

import { Button, Card, Empty } from "@/design/Surface";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Tabs } from "@/design/Tabs";
import { ErrorNote, Loading, PageBand } from "@/components/ui";
import { useLoad } from "@/lib/hooks";
import { BASE_CURRENCY, count, countryName, money, shortSupplier } from "@/lib/format";
import type { Page, PartBrief } from "@/lib/types";

const CLASSES = [
  { key: "", label: "Every class" },
  { key: "A", label: "Class A" },
  { key: "B", label: "Class B" },
  { key: "C", label: "Class C" },
] as const;

const PAGE = 40;

export default function Parts() {
  const [search, setSearch] = useState("");
  const [abc, setAbc] = useState<(typeof CLASSES)[number]["key"]>("");
  const [offset, setOffset] = useState(0);
  const query = [search && `search=${encodeURIComponent(search)}`, abc && `abc_class=${abc}`].filter(Boolean).join("&");
  const { data, error, loading } = useLoad<Page<PartBrief>>(`/api/parts?limit=${PAGE}&offset=${offset}${query ? `&${query}` : ""}`);
  const peak = Math.max(1, ...(data?.items ?? []).map((part) => Number(part.stock_value)));

  return (
    <>
      <PageBand
        eyebrow={["Parts", data ? `${count(data.total)} in the catalogue` : "the catalogue"]}
        title="Every part,"
        accent="and what it is worth on the shelf."
        lede="Class A parts matter most and are covered to 98 per cent, class B to 95, class C to 90. Open a part to see its two years of sales, its forecast range and how its order was reached."
        actions={
          <label className="ss-band-search">
            <span className="ds-sr-only">Search parts by number or description</span>
            <input
              className="ds-input"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
              placeholder="Search by part number or description"
            />
          </label>
        }
      />
      <div className="ds-work">
        <Reveal>
          <Tabs
            label="Class"
            value={abc}
            onChange={(key) => {
              setAbc(key);
              setOffset(0);
            }}
            tabs={CLASSES.map((item) => ({ key: item.key, label: item.label }))}
          />
        </Reveal>
        {error && <ErrorNote error={error} />}
        <Card flush style={{ marginTop: 18 }} eyebrow={data ? `${count(data.total)} parts` : "Parts"} title="The catalogue">
          {loading && !data ? (
            <div style={{ padding: 20 }}>
              <Loading what="Reading the catalogue" />
            </div>
          ) : !data || !data.items.length ? (
            <div style={{ padding: 20 }}>
              <Empty title="No parts match." />
            </div>
          ) : (
            <ol className="ss-rows" data-loading={loading ? "" : undefined}>
              {data.items.map((part, index) => (
                <li key={part.id} className="ss-row ss-part-row ds-reveal" data-shown="" style={{ "--ds-d": `${Math.min(index, 14) * 40}ms` } as CSSProperties}>
                  <Link href={`/parts/${part.id}`} className="ss-row-link">
                    <span className="ss-row-main">
                      <span className="ds-stamp">{part.code}</span>
                      <span className="ss-row-title">{part.description}</span>
                      <span className="ds-mono ss-row-sub">
                        {part.family} · {part.supplier ? `${shortSupplier(part.supplier.name)}, ${countryName(part.supplier.country)}` : "no supplier"}
                      </span>
                    </span>
                    <span className="ss-row-cell">
                      <span className="ds-mono-label">Cost</span>
                      <span className="ds-num">{money(part.unit_cost)}</span>
                    </span>
                    <span className="ss-row-cell">
                      <span className="ds-mono-label">On the shelf</span>
                      <span className="ds-num">{count(part.on_hand)}</span>
                    </span>
                    <span className="ss-row-cell">
                      <span className="ds-mono-label">On order</span>
                      <span className="ds-num">{part.on_order ? count(part.on_order) : "None"}</span>
                    </span>
                    <span className="ss-row-cell ss-row-worth">
                      <span className="ds-mono-label">Worth, {BASE_CURRENCY}</span>
                      <span className="ds-num" style={{ fontWeight: 600 }}>{money(part.stock_value)}</span>
                      <span className="ss-worth-bar" aria-hidden>
                        <span style={{ "--w": Number(part.stock_value) / peak, "--ds-d": `${Math.min(index, 14) * 40 + 250}ms` } as CSSProperties} />
                      </span>
                    </span>
                    <span className="ss-row-cell" style={{ alignItems: "flex-end" }}>
                      <StatusChip tone={part.abc_class === "A" ? "accent" : "neutral"}>Class {part.abc_class}</StatusChip>
                      {!part.is_active && <StatusChip size="small" tone="warn">Replaced</StatusChip>}
                    </span>
                  </Link>
                </li>
              ))}
            </ol>
          )}
        </Card>
        {data && data.total > data.limit && (
          <div className="ss-pager">
            <span className="ds-mono">
              {count(offset + 1)} to {count(Math.min(offset + data.limit, data.total))} of {count(data.total)}
            </span>
            <div style={{ display: "flex", gap: 8 }}>
              <Button size="small" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>
                Back
              </Button>
              <Button size="small" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)}>
                Next
              </Button>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
