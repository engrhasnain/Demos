"use client";

import Link from "next/link";
import { use, useEffect, useMemo, useState } from "react";

import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { StepRail } from "@/design/StepRail";
import { Band, Banner, Button, Card } from "@/design/Surface";
import { ScreenDrive } from "@/components/screen-drive";
import { Figure } from "@/components/trace";
import { ErrorNote, Loading } from "@/components/ui";
import { placeOf } from "@/lib/feed";
import { useLoad } from "@/lib/hooks";
import { CARRIER_FIELDS, formValues, RENAMED_IN_V2, scenarioFromShipment } from "@/lib/scenario";
import type { Health, Run, ShipmentDetail, Step } from "@/lib/types";
import {
  ACTION_WORDS,
  CHECKPOINTS,
  COUNTRY_WORDS,
  OUTCOME_TAG,
  OUTCOME_WORDS,
  RUN_CHIP,
  SYSTEM_WORDS,
  clock,
  clockMs,
  milliseconds,
  plain,
  runKinds,
  shipmentChip,
  stageOf,
  stepsByRun,
} from "@/lib/words";

export default function OneShipment({ params }: { params: Promise<{ reference: string }> }) {
  const { reference } = use(params);
  const { data, error, loading } = useLoad<ShipmentDetail>(`/api/shipments/${encodeURIComponent(reference)}`);
  const { data: runData } = useLoad<{ items: Run[] }>("/api/runs");
  const { data: health } = useLoad<Health>("/api/health");
  const [play, setPlay] = useState(0);
  const [compact, setCompact] = useState(false);

  useEffect(() => {
    const query = window.matchMedia("(max-width: 640px)");
    const update = () => setCompact(query.matches);
    update();
    query.addEventListener?.("change", update);
    return () => query.removeEventListener?.("change", update);
  }, []);

  const runs = useMemo(() => runData?.items ?? [], [runData]);
  const kinds = useMemo(() => runKinds(runs), [runs]);
  const place = useMemo(() => (data ? placeOf(data, runs, kinds) : null), [data, runs, kinds]);
  const resumed = Boolean(place?.resumedAfter) && data?.state === "done";
  const scenario = useMemo(
    () => (data ? scenarioFromShipment(data, { resumedAfter: resumed ? place?.resumedAfter : null, run: place?.run?.id, carrier: health?.carrier }) : null),
    [data, resumed, place, health],
  );

  if (error) return <div className="ds-work"><ErrorNote error={error} /></div>;
  if (loading || !data) return <Band top><Loading what="Opening the trace" dark /></Band>;

  const chip = shipmentChip(data, resumed);
  let done = data.state === "done" ? 5 : data.state === "written_back" ? 4 : data.tracking_number ? 3 : data.consignment ? 2 : data.steps.some((s) => s.action === "assess_dangerous_goods" && s.outcome === "ok") ? 1 : 0;
  if (data.exception_kind && done < 2) done = stageOf(data.exception_kind) === "book" ? 1 : 0;
  const railTone = data.exception_kind ? "warn" : data.state === "done" ? "pass" : "accent";
  const groups = stepsByRun(data.steps, runs);

  return (
    <>
      <Band top>
        <Link href="/shipments" className="pb-back">
          ← Every shipment
        </Link>
        <div className="pb-band-grid" style={{ marginTop: 18, alignItems: "start" }}>
          <div style={{ minWidth: 0 }}>
            <Reveal y={24}>
              <span style={{ display: "inline-flex", flexWrap: "wrap", gap: 10, alignItems: "center" }}>
                <StatusChip tone={chip.tone} surface="dark" size="large" pulse={Boolean(data.exception_kind)}>
                  {chip.label}
                </StatusChip>
                {data.dangerous && (
                  <StatusChip tone="accent" surface="dark">
                    Dangerous goods
                  </StatusChip>
                )}
                <span className="pb-mono-time">{data.order_number}</span>
              </span>
            </Reveal>
            <Reveal index={1} y={32}>
              <h1 className="ds-display ds-band-title" style={{ fontSize: "clamp(32px, 4vw, 52px)" }}>
                {data.reference}
                <br />
                <span className="ds-accent-text pb-light">{data.customer}</span>
              </h1>
            </Reveal>
            <Reveal index={2}>
              <p className="ds-band-lede">
                {data.exception_kind
                  ? `${data.exception_label}. ${data.exception_detail}`
                  : resumed
                    ? `Picked up by run ${place?.run?.id}, the run after the one killed at ${place?.resumedAfter}. It asked the carrier first, booked it once and wrote the tracking number back.`
                    : data.state === "done"
                      ? `Booked with ${health?.carrier ?? "the carrier"} as ${data.consignment}, tracking ${data.tracking_number} written into ${data.order_number} and read back.`
                      : data.state_label}
              </p>
            </Reveal>
            <Reveal index={3}>
              <div style={{ marginTop: 26 }}>
                <StepRail
                  label="Checkpoints for this shipment"
                  tone={railTone}
                  current={Math.min(done, 4)}
                  complete={data.state === "done"}
                  steps={CHECKPOINTS.map((name, index) => ({
                    key: name,
                    label: name,
                    sub:
                      index === 1 && data.consignment
                        ? data.consignment
                        : index === 2 && data.tracking_number
                          ? data.tracking_number
                          : index === done && data.exception_kind
                            ? "held here"
                            : undefined,
                  }))}
                />
              </div>
            </Reveal>
          </div>
          <div className="pb-band-canvas" style={{ height: compact ? 380 : 470 }}>
            <ScreenDrive scenario={scenario} playKey={play} compact={compact} carrier={health?.carrier} portalVersion={health?.portal_version} />
            <div style={{ position: "absolute", right: 0, bottom: -6 }}>
              <Button tone="ink" size="small" onClick={() => setPlay((value) => value + 1)}>
                Replay this shipment
              </Button>
            </div>
          </div>
        </div>
      </Band>

      <div className="ds-work">
        <div className="pb-grid-main">
          <div className="pb-stack">
            <Card
              eyebrow="Trace"
              title="Every step, exactly as it happened"
              subtitle="Grouped by the run that took it. Open a step to see the screen as the bot filled it, and what came back."
            >
              {groups.map((group, groupIndex) => {
                const kind = group.run ? kinds.get(group.run.id) : undefined;
                return (
                  <div key={`${group.run?.id ?? "none"}-${groupIndex}`}>
                    <div className="pb-run-group">
                      {group.run ? <Link href={`/runs/${group.run.id}`}>Run {group.run.id}</Link> : <span style={{ fontWeight: 600 }}>Outside a run</span>}
                      {kind && (
                        <StatusChip tone={RUN_CHIP[kind].tone} size="small">
                          {RUN_CHIP[kind].label}
                        </StatusChip>
                      )}
                      <span className="ds-mono" style={{ fontSize: 11.5, color: "var(--ds-text-3)" }}>
                        {clock(group.steps[0]?.at)}
                      </span>
                    </div>
                    <NodeChain
                      live={groupIndex === groups.length - 1}
                      items={group.steps.map((step, index) => ({
                        key: String(step.id),
                        tone: OUTCOME_WORDS[step.outcome]?.tone === "neutral" ? "info" : OUTCOME_WORDS[step.outcome]?.tone,
                        state: "done",
                        marker: String(index + 1).padStart(2, "0"),
                        content: <StepView step={step} detail={data} />,
                      }))}
                    />
                  </div>
                );
              })}
            </Card>
          </div>

          <div className="pb-stack">
            <Reveal>
              <Card eyebrow="The consignment" title={data.to_name}>
                <dl style={{ margin: 0, display: "grid", gap: 10, fontSize: 13.5 }}>
                  <Row label="Deliver to">
                    {data.to_line1}, {data.city} {data.to_postcode}, {COUNTRY_WORDS[data.country] ?? data.country}
                  </Row>
                  <Row label="Packages">
                    <Figure
                      value={String(data.packages)}
                      origin="record"
                      heading="Packages"
                      explain={{ formula: "taken from the packing record", inputs: [{ label: "Packages", value: String(data.packages), source: `Packing record for ${data.order_number}`, sourceKind: "Shipment record" }] }}
                    />
                  </Row>
                  <Row label="Gross weight">
                    <Figure
                      value={`${data.weight_kg} kilograms`}
                      origin="record"
                      heading="Gross weight"
                      explain={{
                        formula: "total of the cartons, from the packing record",
                        inputs: [
                          { label: "Gross weight", value: `${data.weight_kg} kilograms`, source: `Packing record for ${data.order_number}`, sourceKind: "Shipment record" },
                          { label: "Packages", value: String(data.packages), source: "Same record", sourceKind: "Shipment record" },
                          { label: "Portal limit per package", value: "70 kilograms", source: "The carrier's own rule; it refuses heavier", sourceKind: "Carrier rule" },
                        ],
                      }}
                    />
                  </Row>
                  <Row label="Service">{data.service === "EXP" ? "Express" : "Standard"}</Row>
                  <Row label="Goods">{data.goods_description}</Row>
                  <Row label="Consignment">{data.consignment ? <span className="ds-mono">{data.consignment}</span> : "not booked"}</Row>
                  <Row label="Tracking number">{data.tracking_number ? <span className="ds-mono">{data.tracking_number}</span> : "none yet"}</Row>
                </dl>
              </Card>
            </Reveal>

            {data.dangerous_detail?.declarations?.length ? (
              <Reveal index={1}>
                <Card eyebrow="Dangerous goods" title="Declared from the table, by part number" tone="accent">
                  {data.dangerous_detail.declarations.map((declaration) => (
                    <dl key={declaration.un_number} style={{ margin: 0, display: "grid", gap: 10, fontSize: 13.5 }}>
                      <Row label="United Nations number"><span className="ds-mono" style={{ fontWeight: 700 }}>{declaration.un_number}</span></Row>
                      <Row label="Proper name">{declaration.proper_name}</Row>
                      <Row label="Class">
                        {declaration.dg_class}
                        {declaration.packing_group !== "—" && `, packing group ${declaration.packing_group}`}
                      </Row>
                    </dl>
                  ))}
                  <p className="pb-lede" style={{ fontSize: 13 }}>
                    A United Nations number is a legal declaration. It is looked up by part number and never inferred from a
                    description.
                  </p>
                </Card>
              </Reveal>
            ) : data.dangerous_detail?.unknown?.length ? (
              <Reveal index={1}>
                <Banner tone="warn" title="Reads as dangerous goods, and is not in the table">
                  {data.dangerous_detail.unknown.join(", ")}. The bot stops rather than guessing a United Nations number: the
                  wrong one can ground an aircraft and void the insurance.
                </Banner>
              </Reveal>
            ) : null}

            <Reveal index={2}>
              <Card eyebrow="Repeat safety" title="Why a retry cannot book it twice">
                <dl style={{ margin: 0, display: "grid", gap: 10, fontSize: 13.5 }}>
                  <Row label="Derived key">
                    <Figure
                      value={`${data.idempotency_key.slice(0, 12)}…`}
                      origin="script"
                      heading="The derived key"
                      explain={{
                        label: "Derived from the shipment, never generated",
                        formula: "first 32 characters of sha256(order | deliver to | postcode | packages | weight to 3 places)",
                        result: data.idempotency_key,
                        inputs: [
                          { label: "Order", value: data.order_number, source: "Shipment record", sourceKind: "Shipment record" },
                          { label: "Deliver to", value: data.to_name, source: "Shipment record", sourceKind: "Shipment record" },
                          { label: "Postcode", value: data.to_postcode, source: "Shipment record, after tidying", sourceKind: "Shipment record" },
                          { label: "Packages", value: String(data.packages), source: "Packing record", sourceKind: "Shipment record" },
                          { label: "Weight", value: data.weight_kg.toFixed(3), source: "Packing record", sourceKind: "Shipment record" },
                        ],
                        note: "The same shipment computes the same key on every machine on every run. A generated key is new on every attempt, which is exactly what books twice.",
                      }}
                    />
                  </Row>
                  <Row label="Runs that touched it">
                    <Figure
                      value={String(data.attempts)}
                      heading="Runs that touched it"
                      explain={{
                        formula: "one is added each time a run picks the row up",
                        inputs: groups.map((group) => ({
                          label: group.run ? `Run ${group.run.id}` : "Outside a run",
                          value: `${group.steps.length} steps`,
                          source: group.run ? RUN_CHIP[kinds.get(group.run.id) ?? "finished"].label : "",
                          sourceKind: "Trace",
                        })),
                      }}
                    />
                  </Row>
                  <Row label="Booked at">{clock(data.booked_at)}</Row>
                  <Row label="Written back at">{clock(data.written_back_at)}</Row>
                </dl>
                <p className="pb-lede" style={{ fontSize: 13 }}>
                  And before booking, it asks the carrier whether this reference is already there. Local state can be lost;
                  the carrier&rsquo;s cannot.
                </p>
              </Card>
            </Reveal>
          </div>
        </div>
      </div>
    </>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "minmax(120px, 0.7fr) minmax(0, 1.3fr)", gap: 12, paddingBottom: 10, borderBottom: "1px solid var(--ds-line)" }}>
      <dt className="ds-mono-label" style={{ paddingTop: 2 }}>{label}</dt>
      <dd style={{ margin: 0, minWidth: 0, overflowWrap: "anywhere" }}>{children}</dd>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* One step, with the screen as the bot saw it                         */
/* ------------------------------------------------------------------ */
function StepView({ step, detail }: { step: Step; detail: ShipmentDetail }) {
  const [open, setOpen] = useState(false);
  const outcome = OUTCOME_WORDS[step.outcome] ?? { label: step.outcome, tone: "neutral" as const };
  const hasScreen = step.action === "book" || step.action === "write_tracking" || step.action === "verify_write" || step.action === "collect" || step.action === "validate_address";
  return (
    <div style={{ paddingBottom: 6 }}>
      <div className="pb-logline">
        <span className="pb-logline-time">{clockMs(step.at)}</span>
        <span className="pb-logline-tag" data-tone={outcome.tone}>
          [ {OUTCOME_TAG[step.outcome] ?? step.outcome.toUpperCase()} ]
        </span>
        <span className="pb-logline-system">{SYSTEM_WORDS[step.system] ?? step.system}</span>
      </div>
      <div className="pb-step-head">
        <span className="pb-step-title">{ACTION_WORDS[step.action] ?? plain(step.action)}</span>
        <StatusChip tone={outcome.tone} size="small">
          {outcome.label}
        </StatusChip>
        {step.attempt > 1 && (
          <StatusChip tone="warn" size="small">
            Attempt {step.attempt}
          </StatusChip>
        )}
        <span className="pb-step-time">
          took{" "}
          <Figure
            value={milliseconds(step.duration_ms)}
            origin="record"
            heading="How long the step took"
            explain={{ formula: "measured around the call to the screen", inputs: [{ label: "Duration", value: `${step.duration_ms} milliseconds`, source: `Step ${step.id} in the trace`, sourceKind: "Trace" }] }}
          />
        </span>
      </div>
      {step.note && <p className="pb-step-note">{step.note}</p>}
      {hasScreen && (
        <button type="button" className="ds-btn" data-tone="ghost" data-size="small" style={{ marginTop: 6, paddingLeft: 0 }} aria-expanded={open} onClick={() => setOpen((value) => !value)}>
          {open ? "Hide the screen" : "Show the screen"} <span aria-hidden>{open ? "▴" : "▾"}</span>
        </button>
      )}
      {open && <Capture step={step} detail={detail} />}
    </div>
  );
}

function Capture({ step, detail }: { step: Step; detail: ShipmentDetail }) {
  if (step.action === "book") {
    const sent = step.sent ?? {};
    const values = formValues(detail);
    const shown = Object.keys(sent).length > 0;
    return (
      <div className="pb-screen" role="group" aria-label="The carrier's booking form as the bot filled it">
        <div className="pb-screen-bar">
          <span className="pb-screen-dots" aria-hidden>
            <i />
            <i />
            <i />
          </span>
          <span>Carrier portal · book a consignment</span>
          <span>{clock(step.at)}</span>
        </div>
        <div className="pb-screen-grid">
          {CARRIER_FIELDS.map((field, index) => {
            const renamed = RENAMED_IN_V2[field.portal];
            const key = field.portal in sent ? field.portal : renamed && renamed in sent ? renamed : field.portal;
            const value = shown ? sent[key] : values[field.key];
            return (
              <div key={field.key} className="pb-screen-field" style={{ "--ds-d": `${index * 45}ms` } as React.CSSProperties}>
                <span className="pb-screen-name">
                  {field.word}
                  <code>{key}</code>
                </span>
                <span className="pb-screen-value">{value === undefined || value === "" ? "—" : String(value)}</span>
              </div>
            );
          })}
          {["dg_un", "dg_class", "dg_pg"].filter((key) => key in sent).map((key, index) => (
            <div key={key} className="pb-screen-field" style={{ "--ds-d": `${(CARRIER_FIELDS.length + index) * 45}ms` } as React.CSSProperties}>
              <span className="pb-screen-name">
                {key === "dg_un" ? "United Nations number" : key === "dg_class" ? "Class" : "Packing group"}
                <code>{key}</code>
              </span>
              <span className="pb-screen-value">{String(sent[key])}</span>
            </div>
          ))}
        </div>
        <div className="pb-screen-foot">
          <span>Portal answered:</span>
          <span className="ds-mono" style={{ fontWeight: 600 }}>
            {Object.entries(step.received ?? {}).map(([key, value]) => `${plain(key)} ${String(value)}`).join(" · ") || "nothing"}
          </span>
        </div>
      </div>
    );
  }
  if (step.action === "write_tracking" || step.action === "verify_write") {
    const sent = step.sent ?? {};
    const received = step.received ?? {};
    const bad = step.action === "verify_write";
    const rows: [string, string, boolean][] = [
      ["Order", String(sent.order ?? detail.order_number), false],
      ["Tracking number", String(sent.tracking_number ?? detail.tracking_number), false],
      ["Field width", "18 characters, truncates silently", false],
      ["Stored", String(received.tracking_number ?? sent.tracking_number ?? ""), bad],
      ["Revision", String(received.revision ?? "—"), false],
      ["Status", bad ? "MISMATCH ON READ BACK" : "DESPATCHED · READ BACK MATCHES", bad],
    ];
    return (
      <div className="pb-terminal" role="group" aria-label="The order screen in the business system">
        <div style={{ color: "var(--ds-ink-faint)", marginBottom: 6 }}>HENGTAI ORDER SCREEN · {clock(step.at)}</div>
        {rows.map(([label, value, wrong], index) => (
          <div key={label} className="pb-terminal-row" data-bad={wrong ? "" : undefined} style={{ "--ds-d": `${index * 90}ms` } as React.CSSProperties}>
            <span>{label}</span>
            <b>{value}</b>
          </div>
        ))}
        <span className="pb-cursor" aria-hidden />
      </div>
    );
  }
  return (
    <div className="pb-terminal" role="group" aria-label="What came back">
      {Object.entries(step.received ?? {}).map(([key, value], index) => (
        <div key={key} className="pb-terminal-row" style={{ "--ds-d": `${index * 80}ms` } as React.CSSProperties}>
          <span>{plain(key)}</span>
          <b>{String(value)}</b>
        </div>
      ))}
    </div>
  );
}
