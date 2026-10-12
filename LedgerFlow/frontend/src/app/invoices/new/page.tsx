"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

import { Constellation, type ConstellationHandle } from "@/design/Constellation";
import { StatusChip } from "@/design/StatusChip";
import { API_URL, ApiError, readToken } from "@/lib/api";
import type { InvoiceDetail } from "@/lib/types";
import { Card, ErrorNote, PageBand } from "@/components/ui";

/** The drop zone's picture: a document node, the three corners, the ledger. */
const NODES = [
  { id: "doc", x: 0.12, y: 0.5, r: 4.2, tone: "light" as const, ring: true, lit: true, label: "Your file", side: "below" as const },
  { id: "inv", x: 0.38, y: 0.32, r: 3.4, tone: "accent" as const, lit: true, label: "Read" , side: "above" as const},
  { id: "ord", x: 0.56, y: 0.68, r: 3.4, tone: "accent" as const, lit: true, label: "Matched", side: "below" as const },
  { id: "chk", x: 0.7, y: 0.3, r: 3.4, tone: "accent" as const, lit: true, label: "Checked", side: "above" as const },
  { id: "led", x: 0.9, y: 0.5, r: 4.6, tone: "pass" as const, ring: true, lit: true, label: "Posted or stopped", side: "below" as const },
];
const LINKS = [
  { from: "doc", to: "inv", tone: "light" as const },
  { from: "inv", to: "ord", tone: "accent" as const },
  { from: "ord", to: "chk", tone: "accent" as const },
  { from: "inv", to: "chk", tone: "accent" as const },
  { from: "chk", to: "led", tone: "pass" as const },
];

export default function AddInvoice() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const canvas = useRef<ConstellationHandle>(null);
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [from, setFrom] = useState("");
  const [kind, setKind] = useState("bill");

  const send = async (file: File) => {
    setBusy(true);
    setError(null);
    canvas.current?.pulse(["doc", "inv", "ord", "chk", "led"], { duration: 1600, tone: "accent", size: 3.4 });
    const body = new FormData();
    body.append("file", file);
    body.append("received_from", from);
    body.append("kind", kind);
    try {
      const token = readToken();
      const response = await fetch(`${API_URL}/api/invoices/upload`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        body,
      });
      const text = await response.text();
      const payload = text ? JSON.parse(text) : null;
      if (!response.ok) {
        throw new ApiError(
          response.status,
          typeof payload?.detail === "string" ? payload.detail : `The server returned ${response.status}.`,
          payload,
        );
      }
      router.push(`/invoices/${(payload as InvoiceDetail).id}`);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setBusy(false);
    }
  };

  return (
    <div>
      <PageBand
        eyebrow={["Add an invoice", "read by the built-in engine", "checked by code"]}
        title="Drop it in."
        accent="It is read, matched and decided."
        lede="A PDF, a text file or a photograph of one. It goes through the same pipeline as the morning's post: read, checked, matched three ways, then posted or stopped with the reason."
      />
      <div className="ds-work" style={{ maxWidth: 920 }}>
        <Card eyebrow="One file at a time · up to 8 MB" title="The document">
          <div
            role="button"
            tabIndex={0}
            aria-label="Choose a file to upload, or drop one here"
            className="lf-drop"
            data-over={over ? "" : undefined}
            data-busy={busy ? "" : undefined}
            onDragOver={(event) => {
              event.preventDefault();
              setOver(true);
            }}
            onDragLeave={() => setOver(false)}
            onDrop={(event) => {
              event.preventDefault();
              setOver(false);
              const file = event.dataTransfer.files?.[0];
              if (file) void send(file);
            }}
            onClick={() => inputRef.current?.click()}
            onKeyDown={(event) => {
              if (event.key === "Enter" || event.key === " ") {
                event.preventDefault();
                inputRef.current?.click();
              }
            }}
          >
            <div className="lf-drop-canvas">
              <Constellation ref={canvas} nodes={NODES} links={LINKS} ambient={22} traffic={{ paths: [["doc", "inv", "ord", "chk", "led"]], every: busy ? 500 : 2400 }} />
            </div>
            <div className="lf-drop-words">
              <StatusChip tone={busy ? "accent" : over ? "pass" : "neutral"} surface="dark" pulse={busy}>
                {busy ? "Reading it" : over ? "Let go" : "Ready"}
              </StatusChip>
              <p className="lf-drop-title">{busy ? "Reading it…" : "Drop a file here, or press to choose one"}</p>
              <p className="lf-drop-sub">PDF · text · a photograph</p>
            </div>
            <input
              ref={inputRef}
              type="file"
              className="ds-sr-only"
              tabIndex={-1}
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) void send(file);
              }}
            />
          </div>

          <div className="lf-drop-fields">
            <label>
              <span className="ds-mono-label ds-field-label">From</span>
              <input className="ds-input" value={from} onChange={(event) => setFrom(event.target.value)} placeholder="accounts@supplier.example" />
            </label>
            <label>
              <span className="ds-mono-label ds-field-label">Kind</span>
              <select className="ds-input" value={kind} onChange={(event) => setKind(event.target.value)}>
                <option value="bill">Invoice</option>
                <option value="credit_note">Credit note</option>
              </select>
            </label>
          </div>

          {error && (
            <div style={{ marginTop: 16 }}>
              <ErrorNote error={error} />
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}

export const dynamic = "force-dynamic";
