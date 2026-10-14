"use client";

import type { CSSProperties, ReactNode } from "react";

import { Constellation, type ConstellationLink, type ConstellationNode } from "@/design/Constellation";
import { useInView } from "@/design/motion";
import { Reveal } from "@/design/Reveal";
import { Band, Banner, LinkButton, Spinner } from "@/design/Surface";
import type { ShipmentBrief } from "@/lib/types";
import { CHECKPOINTS, stageOf } from "@/lib/words";

export function ErrorNote({ error }: { error: string }) {
  return (
    <Banner tone="fail" title="That did not work">
      {error}
    </Banner>
  );
}

export function Loading({ what, dark = false }: { what: string; dark?: boolean }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 10,
        padding: "28px 0",
        fontSize: 14,
        color: dark ? "var(--ds-ink-muted)" : "var(--ds-text-2)",
      }}
    >
      <Spinner /> {what}…
    </div>
  );
}

/** Five checkpoints for one row, as small nodes on a solid line. */
export function Track({ shipment }: { shipment: ShipmentBrief }) {
  const held = Boolean(shipment.exception_kind);
  let done =
    shipment.state === "done" ? 5 : shipment.state === "written_back" ? 4 : shipment.tracking_number ? 3 : shipment.consignment ? 2 : 0;
  if (held && done < 2) {
    const stage = stageOf(shipment.exception_kind);
    done = stage === "address" || stage === "dangerous" ? 0 : 1;
  }
  const words = held ? `${CHECKPOINTS.slice(0, done).join(", ") || "Nothing"} done, held at ${CHECKPOINTS[done]}` : `${done} of 5 checkpoints`;
  return (
    <span className="pb-track" role="img" aria-label={words}>
      {CHECKPOINTS.map((name, index) => {
        const state = index < done ? "done" : held && index === done ? "held" : "waiting";
        return <span key={name} className="pb-pip" data-state={state} title={name} />;
      })}
    </span>
  );
}

/** The thesis, said on every screen that matters: a changed screen stops it. */
export function ThesisStrip({ action }: { action?: ReactNode }) {
  return (
    <div className="pb-thesis">
      <span className="pb-thesis-mark" aria-hidden>
        ‖
      </span>
      <div>
        <p className="pb-thesis-title">A changed screen will stop it — by design.</p>
        <p className="pb-thesis-text">
          Driving a screen is a last resort, for systems with no other way in. The script records the shape of the form
          it was written against and checks it before every run. A mismatch stops the run before anything is sent, and a
          person reads the difference. Nothing rewrites the script.
        </p>
      </div>
      {action ?? (
        <LinkButton href="/evidence" tone="ink" size="small" arrow>
          See it measured
        </LinkButton>
      )}
    </div>
  );
}

/** A segmented bar that fills on view. */
export function Segments({ parts, label }: { parts: { value: number; colour: string; title: string }[]; label: string }) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.3 });
  const total = parts.reduce((sum, part) => sum + part.value, 0) || 1;
  let delay = 0;
  return (
    <div ref={ref} className="pb-segments" data-shown={shown ? "" : undefined} role="img" aria-label={label}>
      {parts
        .filter((part) => part.value > 0)
        .map((part) => {
          const style = {
            width: `${(part.value / total) * 100}%`,
            background: part.colour,
            "--ds-d": `${delay}ms`,
          } as CSSProperties;
          delay += 160;
          return <span key={part.title} style={style} title={`${part.title}: ${part.value}`} />;
        })}
    </div>
  );
}

const CLOSE_NODES: ConstellationNode[] = Array.from({ length: 12 }, (_, index) => {
  const left = index < 6;
  const i = index % 6;
  return {
    id: `close-${index}`,
    x: left ? 0.12 + (i % 3) * 0.1 : 0.62 + (i % 3) * 0.1,
    y: 0.3 + Math.floor(i / 3) * 0.24 + (left ? 0 : 0.06),
    r: i === 5 ? 3.6 : 2.6,
    tone: i === 5 ? "accent" : "light",
    ring: index === 11,
    lit: index === 11,
  };
});
const CLOSE_LINKS: ConstellationLink[] = [
  ...CLOSE_NODES.slice(1, 6).map((node, index) => ({ from: CLOSE_NODES[index].id, to: node.id, tone: "light" as const })),
  ...CLOSE_NODES.slice(7).map((node, index) => ({ from: CLOSE_NODES[index + 6].id, to: node.id, tone: "light" as const })),
  { from: "close-5", to: "close-6", tone: "accent", lit: true },
];
const CLOSE_PATHS = [CLOSE_NODES.map((node) => node.id)];

/** The closing band: where to go next inside the product. */
export function ClosingBand() {
  return (
    <Band
      canvas={
        <div className="pb-close-canvas">
          <Constellation nodes={CLOSE_NODES} links={CLOSE_LINKS} ambient={36} traffic={{ paths: CLOSE_PATHS, every: 1500 }} />
        </div>
      }
      style={{ borderTop: "1px solid var(--ds-ink-line)" }}
    >
      <div style={{ padding: "52px 0 48px", maxWidth: 640 }}>
        <Reveal>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            What it does not claim
          </p>
        </Reveal>
        <Reveal index={1}>
          <h2 className="ds-display" style={{ margin: "16px 0 0", fontSize: "clamp(30px, 4vw, 48px)" }}>
            Not unbreakable.
            <br />
            <span className="ds-accent-text pb-light">It knows when it has broken.</span>
          </h2>
        </Reveal>
        <Reveal index={2}>
          <p className="ds-band-lede">
            A bot that stops at nine in the morning costs one clerk one morning. A bot that carries on against a changed
            page, puts the postcode in the weight field and books a hundred and eighty shipments wrong costs a week. So
            PortalBot stops, names the fields that moved, and waits for a person.
          </p>
        </Reveal>
        <Reveal index={3}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 26 }}>
            <LinkButton href="/evidence" tone="primary" size="large" arrow>
              Open the evidence
            </LinkButton>
            <LinkButton href="/runs" tone="ink" size="large">
              Every run, with its checkpoints
            </LinkButton>
          </div>
        </Reveal>
      </div>
    </Band>
  );
}
