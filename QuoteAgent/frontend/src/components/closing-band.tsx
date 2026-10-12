"use client";

/**
 * The closing band on the overview: where to go next in the product - the
 * ten step walkthrough, or the acceptance check with its misses.
 */

import { Constellation, type ConstellationLink, type ConstellationNode } from "@/design/Constellation";
import { Band, LinkButton } from "@/design/Surface";
import { Reveal } from "@/design/Reveal";

const NODES: ConstellationNode[] = Array.from({ length: 10 }, (_, index) => ({
  id: `close-${index}`,
  x: 0.6 + (index % 5) * 0.08,
  y: index < 5 ? 0.3 + Math.sin(index) * 0.08 : 0.68 + Math.cos(index) * 0.08,
  r: index === 4 || index === 9 ? 4 : 2.6,
  tone: index === 4 || index === 9 ? "accent" : "light",
  ring: index === 9,
  lit: index === 9,
}));
const LINKS: ConstellationLink[] = NODES.slice(1).map((node, index) => ({
  from: NODES[index].id,
  to: node.id,
  tone: "accent",
}));
const PATHS = [NODES.map((node) => node.id)];

export function ClosingBand() {
  return (
    <Band
      canvas={
        <div className="qa-cta-canvas">
          <Constellation nodes={NODES} links={LINKS} ambient={40} traffic={{ paths: PATHS, every: 1300 }} />
        </div>
      }
      style={{ borderTop: "1px solid var(--ds-ink-line)" }}
    >
      <div style={{ padding: "52px 0 48px", maxWidth: 660 }}>
        <Reveal>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Ten steps, one real request
          </p>
        </Reveal>
        <Reveal index={1}>
          <h2 className="ds-display" style={{ margin: "16px 0 0", fontSize: "clamp(30px, 4vw, 50px)" }}>
            Watch a forty line request
            <br />
            <span className="ds-accent-text" style={{ fontWeight: 300 }}>
              become an approved quote.
            </span>
          </h2>
        </Reveal>
        <Reveal index={2}>
          <p className="ds-band-lede">
            Questions to the customer, a supplier price request, a reply in Traditional Chinese, new trade terms, a new
            duty table, a discount below the margin floor and a revised bill of materials. Each step performs the real
            action, and every figure it produces opens.
          </p>
        </Reveal>
        <Reveal index={3}>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 12, marginTop: 26 }}>
            <LinkButton href="/demo" tone="primary" size="large" arrow>
              Open the walkthrough
            </LinkButton>
            <LinkButton href="/acceptance" tone="ink" size="large">
              Run the acceptance check
            </LinkButton>
          </div>
        </Reveal>
      </div>
    </Band>
  );
}
