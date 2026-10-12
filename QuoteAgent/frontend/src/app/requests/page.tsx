"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useRef, useState, type CSSProperties } from "react";

import { Button, Card, Empty, Stamp } from "@/design/Surface";
import { CountUp } from "@/design/CountUp";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { useInView } from "@/design/motion";
import { api } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";
import { dateAndTime, money } from "@/lib/format";
import type { CaseSummary } from "@/lib/types";
import { Figure } from "@/components/trace";
import { MiniRail } from "@/components/case-progress";
import {
  ErrorNote,
  Ledger,
  Loading,
  PageBand,
  TONE_COLOUR,
  Td,
  Th,
  isLive,
  statusTone,
} from "@/components/ui";

type Sample = {
  key: string;
  title: string;
  description: string;
  attachments: string[];
};

type CaseList = {
  cases: CaseSummary[];
  counts_by_status: Record<string, number>;
  statuses: { code: string; label: string }[];
};

export default function RequestsPage() {
  return (
    <Suspense fallback={<Loading what="Loading" />}>
      <Requests />
    </Suspense>
  );
}

function totalExplain(item: CaseSummary) {
  return {
    formula: `The total of quote version ${item.current_version}, as the pricing engine worked it out and the server stored it. Open the request to see every line's build-up.`,
    result: money(item.grand_total, item.currency),
    inputs: [
      { label: "Lines on the quote", value: String(item.line_count), source: `Quote version ${item.current_version}`, sourceKind: "Quote" },
      { label: "Trade terms", value: `${item.incoterm} ${item.named_place}`, source: "The customer's request", sourceKind: "Request" },
      { label: "Currency", value: item.currency, source: "Locked on the quote date", sourceKind: "Exchange rate" },
    ],
  };
}

function Requests() {
  const router = useRouter();
  const search = useSearchParams();
  const status = search.get("status") ?? "";
  const [showNew, setShowNew] = useState(search.get("new") === "1");

  const list = useLoad<CaseList>(
    `/api/cases?limit=100${status ? `&status=${status}` : ""}`,
    [status],
  );
  const everything = useLoad<CaseList>("/api/cases?limit=1");

  const setStatus = (next: string) => {
    router.replace(next ? `/requests?status=${next}` : "/requests", { scroll: false });
  };

  const counts = everything.data?.counts_by_status ?? list.data?.counts_by_status ?? {};
  const statuses = everything.data?.statuses ?? list.data?.statuses ?? [];
  const total = Object.values(counts).reduce((sum, value) => sum + value, 0);
  const segments = statuses.filter((option) => counts[option.code]);
  const activeLabel = statuses.find((option) => option.code === status)?.label;

  return (
    <div>
      <PageBand
        eyebrow={["Requests for quotation", `${total} in the inbox`]}
        title="Requests"
        accent="Every one, by where it stands."
        lede="Each request is read, matched line by line, priced by the pricing engine and held for a named approver. Press a state to see only those."
        actions={
          <Button tone="primary" size="large" onClick={() => setShowNew((open) => !open)} arrow={!showNew}>
            {showNew ? "Close the new request" : "New request"}
          </Button>
        }
      >
        <Reveal index={4} y={28}>
          <StatusBar
            segments={segments.map((option) => ({ code: option.code, label: option.label, count: counts[option.code] }))}
            total={total}
            active={status}
            onPick={setStatus}
          />
        </Reveal>
      </PageBand>

      <div className="ds-work">
        {showNew && (
          <div style={{ marginBottom: 24 }}>
            <NewRequest onCreated={(id) => router.push(`/requests/${id}`)} />
          </div>
        )}

        <Card
          flush
          eyebrow={status ? "Showing one state" : "Showing every state"}
          title={activeLabel ?? "All requests"}
          action={
            status ? (
              <Button tone="ghost" size="small" onClick={() => setStatus("")}>
                Show every state
              </Button>
            ) : undefined
          }
        >
          {list.loading && <div style={{ padding: "0 20px" }}><Loading what="Loading the requests" /></div>}
          {list.error && (
            <div style={{ padding: 20 }}>
              <ErrorNote error={list.error} />
            </div>
          )}
          {list.data && list.data.cases.length === 0 && (
            <div style={{ padding: 20 }}>
              <Empty title="Nothing here." />
            </div>
          )}
          {list.data && list.data.cases.length > 0 && (
            <>
              <div className="qa-only-wide">
                <Ledger
                  head={
                    <>
                      <Th width="11rem">Reference</Th>
                      <Th>Customer</Th>
                      <Th align="right" width="5rem">
                        Lines
                      </Th>
                      <Th width="9rem">Progress</Th>
                      <Th width="9rem">Terms</Th>
                      <Th align="right" width="10rem">
                        Value
                      </Th>
                      <Th width="13rem">State</Th>
                    </>
                  }
                >
                  {list.data.cases.map((item, index) => (
                    <Reveal
                      as="tr"
                      key={item.id}
                      index={index}
                      y={24}
                      data-clickable=""
                      onClick={() => router.push(`/requests/${item.id}`)}
                    >
                      <Td
                        className="ds-rowmark"
                        style={{ "--row-tone": TONE_COLOUR[statusTone(item.status)], paddingLeft: 20 } as CSSProperties}
                      >
                        <Link
                          href={`/requests/${item.id}`}
                          className="ds-stamp"
                          onClick={(event) => event.stopPropagation()}
                        >
                          {item.reference}
                        </Link>
                        <p className="ds-mono" style={{ margin: "6px 0 0", fontSize: 11, color: "var(--ds-text-3)" }}>
                          {dateAndTime(item.created_at)}
                        </p>
                      </Td>
                      <Td>
                        <p style={{ margin: 0, fontWeight: 600 }}>{item.customer?.name ?? "Not recognised"}</p>
                        <p
                          className="ds-mono"
                          style={{ margin: "3px 0 0", fontSize: 11.5, color: "var(--ds-text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 280 }}
                        >
                          {item.contact_email}
                        </p>
                      </Td>
                      <Td align="right">{item.line_count}</Td>
                      <Td>
                        <MiniRail status={item.status} />
                      </Td>
                      <Td style={{ fontSize: 13 }}>
                        {item.incoterm} {item.named_place}
                      </Td>
                      <Td align="right" style={{ fontWeight: 600 }}>
                        <span onClick={(event) => event.stopPropagation()}>
                          {Number(item.grand_total) > 0 ? (
                            <Figure
                              value={money(item.grand_total, item.currency)}
                              heading={`${item.reference} quote total`}
                              explain={totalExplain(item)}
                            />
                          ) : (
                            <span style={{ color: "var(--ds-text-3)", fontWeight: 500 }}>Not priced yet</span>
                          )}
                        </span>
                      </Td>
                      <Td>
                        <StatusChip tone={statusTone(item.status)} pulse={isLive(item.status)}>
                          {item.status_label}
                        </StatusChip>
                      </Td>
                    </Reveal>
                  ))}
                </Ledger>
              </div>

              <ul className="qa-only-narrow" style={{ listStyle: "none", margin: 0, padding: 0 }}>
                {list.data.cases.map((item, index) => (
                  <Reveal as="li" key={item.id} index={index} y={24} style={{ borderTop: index ? "1px solid var(--ds-line)" : undefined }}>
                    <div style={{ padding: "14px 16px" }}>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                        <Link href={`/requests/${item.id}`} className="ds-stamp">
                          {item.reference}
                        </Link>
                        <StatusChip tone={statusTone(item.status)} pulse={isLive(item.status)} size="small">
                          {item.status_label}
                        </StatusChip>
                      </div>
                      <Link
                        href={`/requests/${item.id}`}
                        style={{ display: "block", marginTop: 10, fontWeight: 600, color: "inherit", textDecoration: "none" }}
                      >
                        {item.customer?.name ?? item.contact_email}
                      </Link>
                      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10, marginTop: 8 }}>
                        <span className="ds-mono" style={{ fontSize: 11.5, color: "var(--ds-text-3)" }}>
                          {item.line_count} lines · {item.incoterm}
                        </span>
                        <span style={{ fontWeight: 600 }}>
                          {Number(item.grand_total) > 0 ? (
                            <Figure
                              value={money(item.grand_total, item.currency)}
                              heading={`${item.reference} quote total`}
                              explain={totalExplain(item)}
                            />
                          ) : (
                            <span style={{ color: "var(--ds-text-3)", fontWeight: 500 }}>Not priced yet</span>
                          )}
                        </span>
                      </div>
                      <div style={{ marginTop: 10 }}>
                        <MiniRail status={item.status} />
                      </div>
                    </div>
                  </Reveal>
                ))}
              </ul>
            </>
          )}
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* The state bar: one solid segment per state, sized by its count      */
/* ------------------------------------------------------------------ */
function StatusBar({
  segments,
  total,
  active,
  onPick,
}: {
  segments: { code: string; label: string; count: number }[];
  total: number;
  active: string;
  onPick: (code: string) => void;
}) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.2 });
  if (!total) return null;
  return (
    <div ref={ref} style={{ marginTop: 34 }}>
      <div className="qa-statusbar" data-shown={shown ? "" : undefined} role="group" aria-label="Requests by state">
        {segments.map((segment, index) => {
          const tone = statusTone(segment.code);
          return (
            <button
              key={segment.code}
              type="button"
              className="qa-statusbar-seg"
              aria-pressed={active === segment.code}
              aria-label={`${segment.label}: ${segment.count}`}
              title={`${segment.label}: ${segment.count}`}
              data-dim={active && active !== segment.code ? "" : undefined}
              style={
                {
                  flexGrow: segment.count,
                  background: TONE_COLOUR[tone],
                  "--ds-d": `${index * 80}ms`,
                } as CSSProperties
              }
              onClick={() => onPick(active === segment.code ? "" : segment.code)}
            />
          );
        })}
      </div>
      <div className="qa-statuslegend">
        <button
          type="button"
          className="qa-legend"
          aria-pressed={!active}
          onClick={() => onPick("")}
        >
          <span className="ds-stat-value" style={{ fontSize: 26 }}>
            <CountUp to={total} />
          </span>
          <span className="ds-mono-label" style={{ display: "block", marginTop: 6 }}>
            All
          </span>
        </button>
        {segments.map((segment, index) => {
          const tone = statusTone(segment.code);
          return (
            <button
              key={segment.code}
              type="button"
              className="qa-legend"
              aria-pressed={active === segment.code}
              onClick={() => onPick(active === segment.code ? "" : segment.code)}
            >
              <span className="ds-stat-value" style={{ fontSize: 26 }}>
                <CountUp to={segment.count} delay={index * 60} />
              </span>
              <span className="ds-mono-label" style={{ display: "flex", alignItems: "center", gap: 7, marginTop: 6 }}>
                <span style={{ width: 8, height: 8, borderRadius: 2, background: TONE_COLOUR[tone], flexShrink: 0 }} aria-hidden />
                {segment.label}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Bring your own bill of materials                                    */
/* ------------------------------------------------------------------ */
function NewRequest({ onCreated }: { onCreated: (caseId: number) => void }) {
  const samples = useLoad<Sample[]>("/api/cases/samples");
  const { busy, error, run } = useAction();
  const [file, setFile] = useState<File | null>(null);
  const [over, setOver] = useState(false);
  const [sender, setSender] = useState("r.mendez@pacificmotion.example");
  const [note, setNote] = useState("");
  const input = useRef<HTMLInputElement>(null);

  const readAsBase64 = (chosen: File) =>
    new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => {
        const result = String(reader.result);
        resolve(result.slice(result.indexOf(",") + 1));
      };
      reader.onerror = () => reject(new Error("The file could not be read."));
      reader.readAsDataURL(chosen);
    });

  const submit = useCallback(
    () =>
      void run("upload", async () => {
        if (!file && !note.trim()) {
          throw new Error("Attach a file, or type the lines.");
        }
        const attachments = file
          ? [
              {
                filename: file.name,
                content_type:
                  file.type ||
                  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                content_base64: await readAsBase64(file),
              },
            ]
          : [];

        const created = await api.post<{ case: CaseSummary }>("/api/cases", {
          sender,
          subject: file ? `Request for quotation - ${file.name}` : "Request for quotation",
          body: note.trim() || "Hi,\n\nPlease quote the attached.\n\nThanks",
          external_message_id: `<upload-${Date.now()}@quoteagent.local>`,
          attachments,
        });
        await api.post(`/api/cases/${created.case.id}/run`);
        onCreated(created.case.id);
        return created;
      }),
    [file, note, run, sender, onCreated],
  );

  const openSample = (key: string) =>
    void run(key, async () => {
      const created = await api.post<{ case: CaseSummary }>("/api/cases/from-sample", {
        sample_key: key,
      });
      await api.post(`/api/cases/${created.case.id}/run`);
      onCreated(created.case.id);
      return created;
    });

  return (
    <Card tone="accent" eyebrow="Bring your own" title="New request">
      <div className="qa-new">
        <div>
          <div
            role="button"
            tabIndex={0}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                input.current?.click();
              }
            }}
            onDragOver={(event) => {
              event.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(event) => {
              event.preventDefault();
              setOver(false);
              const dropped = event.dataTransfer.files?.[0];
              if (dropped) setFile(dropped);
            }}
            onClick={() => input.current?.click()}
            className="qa-drop"
            data-over={over ? "" : undefined}
          >
            <input
              ref={input}
              type="file"
              accept=".xlsx,.xlsm,.csv,.tsv,.pdf,.txt"
              style={{ display: "none" }}
              onChange={(event) => setFile(event.target.files?.[0] ?? null)}
            />
            <span className="qa-drop-icon" aria-hidden>
              ↑
            </span>
            {file ? (
              <>
                <p style={{ margin: "10px 0 0", fontWeight: 600 }}>{file.name}</p>
                <p style={{ margin: "4px 0 0", fontSize: 12.5, color: "var(--ds-text-2)" }}>
                  {(file.size / 1024).toFixed(0)} KB · press to choose another
                </p>
              </>
            ) : (
              <>
                <p style={{ margin: "10px 0 0", fontWeight: 600 }}>Drop a spreadsheet, a PDF or a text file</p>
                <p style={{ margin: "4px 0 0", fontSize: 12.5, color: "var(--ds-text-2)" }}>or press to choose one</p>
              </>
            )}
          </div>

          <label style={{ display: "block", marginTop: 16 }}>
            <span className="ds-mono-label ds-field-label">Or type the lines</span>
            <textarea
              value={note}
              onChange={(event) => setNote(event.target.value)}
              rows={4}
              placeholder={"1. DIN 912 M8x30 12.9 zinc - 2000 pcs\n2. 6204-2RS C3 - 40 pcs"}
              className="ds-input"
              data-mono=""
            />
          </label>

          <label style={{ display: "block", marginTop: 12 }}>
            <span className="ds-mono-label ds-field-label">From</span>
            <input value={sender} onChange={(event) => setSender(event.target.value)} className="ds-input" data-mono="" />
          </label>

          {error && (
            <div style={{ marginTop: 14 }}>
              <ErrorNote error={error} />
            </div>
          )}

          <div style={{ marginTop: 16 }}>
            <Button tone="primary" busy={busy === "upload"} onClick={submit} arrow>
              Read it and quote it
            </Button>
          </div>
        </div>

        <div>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Or start from a sample
          </p>
          <ul style={{ listStyle: "none", margin: "12px 0 0", padding: 0, display: "grid", gap: 10 }}>
            {(samples.data ?? []).map((sample, index) => (
              <Reveal as="li" key={sample.key} index={index} y={20}>
                <button
                  type="button"
                  disabled={Boolean(busy)}
                  onClick={() => openSample(sample.key)}
                  className="qa-sample ds-lift"
                >
                  <span style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 10 }}>
                    <span style={{ fontWeight: 600, fontSize: 14 }}>{sample.title}</span>
                    {busy === sample.key ? <span className="ds-spinner" aria-hidden /> : <span aria-hidden>→</span>}
                  </span>
                  {sample.attachments.length > 0 && (
                    <span style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                      {sample.attachments.map((name) => (
                        <Stamp key={name} tone="light">
                          {name}
                        </Stamp>
                      ))}
                    </span>
                  )}
                </button>
              </Reveal>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

export const dynamic = "force-dynamic";
