"use client";

import { useMemo, useState } from "react";

import { Banner, Button, Card, Empty, Stamp, Stat } from "@/design/Surface";
import { Constellation, type ConstellationLink, type ConstellationNode } from "@/design/Constellation";
import { NodeChain, type ChainItem } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { api } from "@/lib/api";
import { useAction, useLoad } from "@/lib/hooks";
import { attributeWords, count, money, valueWords, words } from "@/lib/format";
import type { Product } from "@/lib/types";
import { Figure } from "@/components/trace";
import { ErrorNote, Ledger, Loading, PageBand, Td, Th, statusTone } from "@/components/ui";

type MatchProbe = {
  status: string;
  sku: string;
  method: string;
  confidence: string;
  reasons: string[];
  blocking_reason: string;
  questions: { kind: string; attribute: string; question: string; options: string[] }[];
  checks: {
    attribute: string;
    requested: string;
    catalogue: string;
    agrees: boolean;
    severity: string;
  }[];
  alternatives: { sku: string; description: string; score: string }[];
  how_it_was_read: {
    family: string;
    standard: string;
    attributes: Record<string, string>;
    missing: string[];
    conflicts: { attribute: string; values: string; explanation: string }[];
    notes: string[];
  };
  product?: Product;
};

type Summary = {
  families: { family: string; count: number }[];
  stocked: number;
  cross_references: number;
  explanation: string;
};

const EXAMPLES = [
  "DIN 912 M8x30 12.9 zinc",
  "SKF 6204-2RS1 C3",
  "NTN 6001LLU C3",
  "M10 bolt, class 8.8, zinc",
  "Socket head cap screw M8x40 A2-70 stainless, zinc plated",
  "Deep groove ball bearing 6205",
  "Hexagon nut ISO 4032 M12 class 8.8 zinc",
  "Shoulder bolt ISO 7379 12x50 M10 class 12.9 plain",
];

const FAMILY_WORDS: Record<string, string> = {
  fastener: "Fasteners",
  bearing: "Bearings",
  pneumatic: "Pneumatic parts",
};

function CatalogueMap({ summary }: { summary: Summary | null }) {
  const scene = useMemo(() => {
    const nodes: ConstellationNode[] = [];
    const links: ConstellationLink[] = [];
    if (!summary) return { nodes, links, paths: [] as string[][] };
    const max = Math.max(...summary.families.map((family) => family.count), 1);
    const places = [
      [0.3, 0.38],
      [0.72, 0.26],
      [0.68, 0.74],
    ];
    nodes.push({ id: "index", x: 0.5, y: 0.52, r: 5, tone: "accent", ring: true, lit: true, label: "Search index", side: "below", drift: 1 });
    summary.families.forEach((family, index) => {
      const [x, y] = places[index % places.length];
      const id = `f-${family.family}`;
      nodes.push({
        id,
        x,
        y,
        r: 3 + 4 * Math.sqrt(family.count / max),
        tone: "light",
        lit: true,
        label: `${FAMILY_WORDS[family.family] ?? family.family} ${count(family.count)}`,
        side: x < 0.5 ? "left" : "right",
      });
      links.push({ from: "index", to: id, tone: "accent", lit: true });
      const satellites = Math.min(14, 3 + Math.round(10 * Math.sqrt(family.count / max)));
      for (let dot = 0; dot < satellites; dot += 1) {
        const angle = (dot / satellites) * Math.PI * 2 + index;
        const distance = 0.07 + (dot % 3) * 0.025;
        const dotId = `${id}-${dot}`;
        nodes.push({ id: dotId, x: x + Math.cos(angle) * distance * 0.7, y: y + Math.sin(angle) * distance, r: 1.5, tone: "muted", drift: 5 });
        links.push({ from: id, to: dotId, tone: "light" });
      }
    });
    nodes.push({ id: "xref", x: 0.14, y: 0.8, r: 3.4, tone: "accent", label: `Cross-references ${count(summary.cross_references)}`, side: "right" });
    links.push({ from: "xref", to: "index", tone: "accent" });
    const paths = [
      ["xref", "index", ...summary.families.slice(0, 1).map((family) => `f-${family.family}`)],
      ...summary.families.map((family) => ["index", `f-${family.family}`]),
    ];
    return { nodes, links, paths };
  }, [summary]);

  return (
    <div style={{ position: "relative", height: 300 }}>
      <Constellation
        nodes={scene.nodes}
        links={scene.links}
        ambient={26}
        traffic={scene.paths.length ? { paths: scene.paths, every: 1100 } : undefined}
        label="The catalogue: fasteners, bearings and pneumatic parts around one search index"
      />
    </div>
  );
}

export default function CataloguePage() {
  const summary = useLoad<Summary>("/api/catalogue/summary");
  const [query, setQuery] = useState("");
  const results = useLoad<{ total_in_catalogue: number; returned: number; products: Product[] }>(
    `/api/catalogue/products?limit=20${query ? `&query=${encodeURIComponent(query)}` : ""}`,
  );

  const [probeText, setProbeText] = useState(EXAMPLES[0]);
  const [probe, setProbe] = useState<MatchProbe | null>(null);
  const [probed, setProbed] = useState(0);
  const { busy, error, run } = useAction();

  const tryLine = (text: string) => {
    setProbeText(text);
    void run("probe", async () => {
      const result = await api.post<MatchProbe>("/api/catalogue/match", { text });
      setProbe(result);
      setProbed((value) => value + 1);
      return result;
    });
  };

  const total = (summary.data?.families ?? []).reduce((sum, family) => sum + family.count, 0);

  return (
    <div>
      <PageBand
        eyebrow={["Catalogue", `${count(total)} parts`]}
        title="Catalogue"
        accent="Every line read, then checked."
        lede="A competitor or standard part number becomes a Hengtai part through the cross-reference table, attribute matching or text similarity, and every proposal is then checked attribute by attribute. Type a line and watch it being read."
        aside={<CatalogueMap summary={summary.data} />}
      >
        {summary.data && (
          <Reveal index={4}>
            <div className="ds-band-rule" />
            <div className="ds-stats">
              {summary.data.families.map((family) => (
                <Stat
                  key={family.family}
                  label={FAMILY_WORDS[family.family] ?? family.family}
                  value={
                    <Figure
                      value={count(family.count)}
                      count={family.count}
                      decimals={0}
                      heading={`${FAMILY_WORDS[family.family] ?? family.family} in the catalogue`}
                      explain={{
                        formula: `Catalogue records whose family is ${family.family}`,
                        inputs: [{ label: "Family", value: family.family, source: "Catalogue table", sourceKind: "Catalogue record" }],
                      }}
                    />
                  }
                />
              ))}
              <Stat
                label="In stock"
                tone="pass"
                value={
                  <Figure
                    value={count(summary.data.stocked)}
                    count={summary.data.stocked}
                    decimals={0}
                    heading="Parts held in stock"
                    explain={{
                      formula: "Catalogue records marked as stocked in Taichung or Ontario",
                      inputs: [{ label: "Out of", value: count(total), source: "Catalogue table", sourceKind: "Catalogue record" }],
                    }}
                  />
                }
              />
              <Stat
                label="Cross-references"
                tone="accent"
                value={
                  <Figure
                    value={count(summary.data.cross_references)}
                    count={summary.data.cross_references}
                    decimals={0}
                    heading="Cross-references"
                    explain={{
                      formula: summary.data.explanation,
                      inputs: [{ label: "Rows", value: count(summary.data.cross_references), source: "Cross-reference table", sourceKind: "Catalogue record" }],
                    }}
                  />
                }
              />
            </div>
          </Reveal>
        )}
      </PageBand>

      <div className="ds-work">
        <div className="qa-cat-grid">
          <Card tone="accent" eyebrow="Try a line" title="Read it the way the agent does">
            <form
              onSubmit={(event) => {
                event.preventDefault();
                tryLine(probeText);
              }}
            >
              <div style={{ display: "flex", gap: 10 }}>
                <label style={{ flex: 1, minWidth: 0 }}>
                  <span className="ds-sr-only">A line from a request</span>
                  <input
                    value={probeText}
                    onChange={(event) => setProbeText(event.target.value)}
                    placeholder="DIN 912 M8x30 12.9 zinc"
                    className="ds-input"
                    data-mono=""
                  />
                </label>
                <Button type="submit" tone="primary" busy={busy === "probe"}>
                  Read it
                </Button>
              </div>
            </form>

            <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 12 }}>
              {EXAMPLES.map((example) => (
                <button key={example} type="button" onClick={() => tryLine(example)} className="qa-example">
                  {example}
                </button>
              ))}
            </div>

            {error && (
              <div style={{ marginTop: 14 }}>
                <ErrorNote error={error} />
              </div>
            )}

            {probe && <ProbeResult key={probed} probe={probe} />}
            {!probe && (
              <p style={{ margin: "18px 0 0", fontSize: 13.5, color: "var(--ds-text-2)" }}>
                Press an example, or type any line from a bill of materials.
              </p>
            )}
          </Card>

          <Card eyebrow="Search" title="Find a part" flush>
            <div style={{ padding: "16px 20px" }}>
              <label>
                <span className="ds-sr-only">Search the catalogue</span>
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="M8x30, 6204, cylinder…"
                  className="ds-input"
                />
              </label>
            </div>
            {results.loading && <div style={{ padding: "0 20px" }}><Loading what="Searching" /></div>}
            {results.data && results.data.products.length === 0 && (
              <div style={{ padding: 20 }}>
                <Empty title="Nothing matched that" />
              </div>
            )}
            {results.data && results.data.products.length > 0 && (
              <Ledger
                head={
                  <>
                    <Th>Part</Th>
                    <Th align="right" width="7rem">
                      List price
                    </Th>
                    <Th width="6.5rem">Stock</Th>
                  </>
                }
              >
                {results.data.products.map((product, index) => (
                  <ResultRow key={product.id} product={product} index={index} />
                ))}
              </Ledger>
            )}
          </Card>
        </div>
      </div>
    </div>
  );
}

function ResultRow({ product, index }: { product: Product; index: number }) {
  return (
    <Reveal as="tr" index={index} y={20}>
      <Td style={{ paddingLeft: 20 }}>
        <Stamp>{product.sku}</Stamp>
        <p style={{ margin: "6px 0 0", fontSize: 13, lineHeight: 1.45 }}>{product.description}</p>
        <p className="ds-mono" style={{ margin: "3px 0 0", fontSize: 11, color: "var(--ds-text-3)" }}>
          {product.commodity_code} · {product.pack_size} a box
        </p>
      </Td>
      <Td align="right">
        <Figure
          value={money(product.list_price)}
          heading={`${product.sku} list price`}
          explain={{
            formula:
              "The list price on the catalogue record. A customer's contract price or volume break, where there is one, is applied by the pricing engine on the quote.",
            result: money(product.list_price),
            inputs: [
              { label: "Part", value: product.sku, source: "Catalogue record", sourceKind: "Catalogue record" },
              { label: "Pack size", value: `${product.pack_size} a box`, source: "Catalogue record", sourceKind: "Catalogue record" },
              { label: "Standard cost", value: money(product.standard_cost), source: "Catalogue record", sourceKind: "Catalogue record" },
            ],
          }}
        />
      </Td>
      <Td>
        <StatusChip tone={product.is_stocked ? "pass" : "warn"} size="small">
          {product.is_stocked ? "Stocked" : "To order"}
        </StatusChip>
      </Td>
    </Reveal>
  );
}

function ProbeResult({ probe }: { probe: MatchProbe }) {
  const read = probe.how_it_was_read;
  const agreed = probe.checks.filter((check) => check.agrees).length;
  const items: ChainItem[] = [
    {
      key: "read",
      tone: "accent",
      marker: "01",
      content: (
        <div style={{ paddingTop: 2 }}>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            How it was read
          </p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
            <Stamp>{read.family}</Stamp>
            {read.standard && <Stamp>{read.standard}</Stamp>}
            {Object.entries(read.attributes)
              .filter(([key]) => !["seal_suffix_seen", "pitch_kind"].includes(key))
              .map(([key, value]) => (
                <Stamp key={key} tone="light">
                  {attributeWords(key)}: {valueWords(String(value))}
                </Stamp>
              ))}
          </div>
        </div>
      ),
    },
  ];

  if (read.missing.length || read.conflicts.length) {
    items.push({
      key: "gaps",
      tone: read.conflicts.length ? "fail" : "warn",
      marker: "02",
      content: (
        <div style={{ display: "grid", gap: 8, paddingTop: 2 }}>
          {read.missing.length > 0 && (
            <Banner tone="warn" title="The line does not say">
              {read.missing.map(attributeWords).join(", ")}
            </Banner>
          )}
          {read.conflicts.map((conflict, index) => (
            <Banner key={index} tone="fail" title="The line contradicts itself">
              {conflict.values}. {conflict.explanation}
            </Banner>
          ))}
        </div>
      ),
    });
  }

  if (probe.checks.length) {
    items.push({
      key: "checks",
      tone: agreed === probe.checks.length ? "pass" : "warn",
      marker: String(items.length + 1).padStart(2, "0"),
      content: (
        <div style={{ paddingTop: 2 }}>
          <p className="ds-mono-label" style={{ margin: 0 }}>
            Checked attribute by attribute · {agreed} of {probe.checks.length} agree
          </p>
          <ul className="qa-checks">
            {probe.checks.map((check, index) => (
              <li key={check.attribute} style={{ "--ds-d": `${300 + index * 90}ms` } as React.CSSProperties}>
                <span className="qa-check-dot" data-tone={check.agrees ? "pass" : "fail"} aria-hidden>
                  {check.agrees ? "✓" : "!"}
                </span>
                <span style={{ color: "var(--ds-text-3)" }}>{attributeWords(check.attribute)}</span>
                <span style={{ marginLeft: "auto", textAlign: "right" }}>
                  {valueWords(check.requested)}
                  {!check.agrees && ` against ${valueWords(check.catalogue)}`}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ),
    });
  }

  items.push({
    key: "result",
    tone: statusTone(probe.status) === "pass" ? "pass" : statusTone(probe.status) === "fail" ? "fail" : "warn",
    marker: String(items.length + 1).padStart(2, "0"),
    content: (
      <div style={{ paddingTop: 2 }}>
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
          <StatusChip tone={statusTone(probe.status)} size="large">
            {words(probe.status)}
          </StatusChip>
          {probe.sku && <Stamp>{probe.sku}</Stamp>}
          {probe.method !== "none" && (
            <span style={{ fontSize: 12.5, color: "var(--ds-text-2)" }}>
              by {words(probe.method).toLowerCase()} ·{" "}
              <Figure
                value={`${(Number(probe.confidence) * 100).toFixed(0)}% sure`}
                heading="How sure the matcher is"
                explain={{
                  formula: "Set by the route that found the part, then lowered by any attribute that does not agree",
                  inputs: [
                    { label: "Route", value: words(probe.method), source: "Matching service", sourceKind: "Matcher" },
                    { label: "Attributes that agree", value: `${agreed} of ${probe.checks.length}`, source: "Attribute check", sourceKind: "Matcher" },
                  ],
                }}
              />
            </span>
          )}
        </div>
        {probe.reasons.length > 0 && (
          <ul style={{ listStyle: "none", margin: "10px 0 0", padding: 0, display: "grid", gap: 6 }}>
            {probe.reasons.map((reason, index) => (
              <li key={index} style={{ borderLeft: "3px solid var(--ds-accent)", paddingLeft: 10, fontSize: 13, lineHeight: 1.55, color: "var(--ds-text-2)" }}>
                {reason}
              </li>
            ))}
          </ul>
        )}
        {probe.questions.length > 0 && (
          <>
            <p className="ds-mono-label" style={{ margin: "12px 0 0" }}>
              What it would ask the customer
            </p>
            <ul style={{ listStyle: "none", margin: "8px 0 0", padding: 0, display: "grid", gap: 8 }}>
              {probe.questions.map((question, index) => (
                <li key={index} style={{ padding: "10px 12px", borderRadius: 3, border: "1px solid var(--ds-line)", fontSize: 13 }}>
                  {question.question}
                  {question.options.length > 0 && (
                    <span style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 8 }}>
                      {question.options.slice(0, 6).map((option) => (
                        <Stamp key={option} tone="light">
                          {option}
                        </Stamp>
                      ))}
                    </span>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    ),
  });

  return (
    <div style={{ marginTop: 22 }}>
      <NodeChain items={items} stagger={160} />
    </div>
  );
}

export const dynamic = "force-dynamic";
