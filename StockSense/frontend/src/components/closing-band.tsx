"use client";

/**
 * The ink band at the foot of every screen: where to go next in the
 * product. Behind it, a short row of parts that mostly sit dark and now and
 * then spark, joined by solid lines into one order: the product's motif,
 * quiet.
 */

import { Constellation, type ConstellationLink, type ConstellationNode } from "@/design/Constellation";
import { Band, LinkButton } from "@/design/Surface";
import { Reveal } from "@/design/Reveal";

const NODES: ConstellationNode[] = Array.from({ length: 12 }, (_, index) => {
  const hub = index === 5 || index === 11;
  return {
    id: `close-${index}`,
    x: 0.58 + (index % 6) * 0.07,
    y: index < 6 ? 0.3 + Math.sin(index * 1.3) * 0.08 : 0.68 + Math.cos(index * 1.1) * 0.08,
    r: hub ? 4 : 2.4,
    tone: hub ? "accent" : index % 4 === 1 ? "warn" : "light",
    ring: index === 11,
    lit: hub,
  };
});
const LINKS: ConstellationLink[] = [
  ...NODES.slice(0, 5).map((node) => ({ from: node.id, to: "close-5", tone: "light" as const })),
  ...NODES.slice(6, 11).map((node) => ({ from: node.id, to: "close-11", tone: "light" as const })),
  { from: "close-5", to: "close-11", tone: "accent", lit: true },
];
const PATHS = [
  ["close-0", "close-5", "close-11"],
  ["close-2", "close-5", "close-11"],
  ["close-7", "close-11"],
  ["close-9", "close-11"],
];

export function ClosingBand() {
  return (
    <Band
      canvas={
        <div className="ss-cta-canvas">
          <Constellation nodes={NODES} links={LINKS} ambient={36} traffic={{ paths: PATHS, every: 1500 }} />
        </div>
      }
      style={{ borderTop: "1px solid var(--ds-ink-line)" }}
    >
      <div className="ss-closing">
        <Reveal>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Measured, not claimed
          </p>
        </Reveal>
        <Reveal index={1}>
          <h2 className="ds-display ss-closing-title">
            Every number opens.
            <br />
            <span className="ds-accent-text">Every miss is shown.</span>
          </h2>
        </Reveal>
        <Reveal index={2}>
          <p className="ds-band-lede">
            A forecast that says zero every week beats this one on the usual error measure, and would empty the
            warehouse. So StockSense is graded on what it would have done: the last year replayed against the buyers&apos;
            own orders, stock-outs and money side by side.
          </p>
        </Reveal>
        <Reveal index={3}>
          <div className="ss-actions">
            <LinkButton href="/evidence" tone="primary" size="large" arrow>
              Replay the year
            </LinkButton>
            <LinkButton href="/plan" tone="ink" size="large">
              This week&apos;s orders
            </LinkButton>
          </div>
        </Reveal>
      </div>
    </Band>
  );
}
