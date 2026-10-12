"use client";

import { Fragment, useState, type CSSProperties } from "react";

import { Stamp } from "@/design/Surface";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { attributeWords, money, quantity, valueWords, words } from "@/lib/format";
import type { QuoteLine, QuoteVersion } from "@/lib/types";
import { Figure } from "@/components/trace";
import { Ledger, TONE_COLOUR, Td, Th, statusTone } from "@/components/ui";

/** True when the customer's wording adds nothing to what is already shown. */
function sameThing(written: string, ...shown: string[]): boolean {
  const strip = (value: string) => value.toUpperCase().replace(/[^A-Z0-9]/g, "");
  const left = strip(written);
  return shown.some((candidate) => strip(candidate) === left);
}

function unitNote(line: QuoteLine): string | undefined {
  return line.pricing.price_source_label
    ? `${line.pricing.price_source_label}${
        line.pricing.price_source_reference ? ` (${line.pricing.price_source_reference})` : ""
      }.`
    : undefined;
}

/** Why this part, and what was checked against it. */
function MatchDetail({ line }: { line: QuoteLine }) {
  const checks = line.match.attribute_check?.checks ?? [];
  const notes = line.match.attribute_check?.notes ?? [];
  const settled = Object.entries(line.settled_by_the_customer ?? {});

  return (
    <div className="qa-line-detail qa-detail-grid">
      <div>
        <p className="ds-mono-label" style={{ margin: 0 }}>
          What the customer wrote
        </p>
        <p className="ds-mono" style={{ margin: "6px 0 0", fontSize: 12.5, lineHeight: 1.6 }}>
          {line.original_request_text}
        </p>
        {line.source_reference && (
          <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--ds-text-3)" }}>From {line.source_reference}</p>
        )}

        {settled.length > 0 && (
          <>
            <p className="ds-mono-label" style={{ margin: "16px 0 0" }}>
              Settled by the customer&rsquo;s answer
            </p>
            <ul style={{ margin: "6px 0 0", padding: 0, listStyle: "none" }}>
              {settled.map(([attribute, value]) => (
                <li key={attribute} style={{ fontSize: 13 }}>
                  {attributeWords(attribute)}: <strong>{valueWords(String(value))}</strong>
                </li>
              ))}
            </ul>
          </>
        )}

        <p className="ds-mono-label" style={{ margin: "16px 0 0" }}>
          How it was matched
        </p>
        <p style={{ margin: "6px 0 0", fontWeight: 600, fontSize: 13.5 }}>
          {line.match.method_label}
          {line.match.confidence_percent && (
            <span className="ds-mono" style={{ marginLeft: 8, fontSize: 11.5, color: "var(--ds-accent-ink)" }}>
              {Number(line.match.confidence_percent).toFixed(0)}% sure
            </span>
          )}
        </p>
        <ul style={{ margin: "6px 0 0", padding: 0, listStyle: "none", display: "grid", gap: 6 }}>
          {line.match.reasons.map((reason, index) => (
            <li
              key={index}
              style={{ borderLeft: "3px solid var(--ds-accent)", paddingLeft: 10, fontSize: 13, lineHeight: 1.55, color: "var(--ds-text-2)" }}
            >
              {reason}
            </li>
          ))}
        </ul>
      </div>

      <div>
        {checks.length > 0 && (
          <>
            <p className="ds-mono-label" style={{ margin: 0 }}>
              Checked attribute by attribute
            </p>
            <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--ds-text-3)" }}>
              Proposed by {line.match.proposed_by}, checked by {line.match.verified_by}
            </p>
            <ul className="qa-checks">
              {checks.map((check, index) => (
                <li key={check.attribute} style={{ "--ds-d": `${index * 90}ms` } as CSSProperties}>
                  <span
                    className="qa-check-dot"
                    data-tone={check.agrees ? "pass" : check.severity === "must_agree" ? "fail" : "warn"}
                    aria-hidden
                  >
                    {check.agrees ? "✓" : "!"}
                  </span>
                  <span style={{ color: "var(--ds-text-3)" }}>{attributeWords(check.attribute)}</span>
                  <span style={{ marginLeft: "auto", textAlign: "right" }}>
                    asked for <strong>{valueWords(check.requested)}</strong>
                    {!check.agrees && (
                      <>
                        , part is <strong>{valueWords(check.catalogue)}</strong>
                      </>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        {notes.length > 0 && (
          <ul style={{ margin: "12px 0 0", padding: 0, listStyle: "none" }}>
            {notes.map((note, index) => (
              <li key={index} style={{ fontSize: 12.5, color: "var(--ds-text-2)" }}>
                {note}
              </li>
            ))}
          </ul>
        )}

        {line.match.alternatives.length > 0 && (
          <>
            <p className="ds-mono-label" style={{ margin: "16px 0 0" }}>
              Also considered
            </p>
            <ul style={{ margin: "6px 0 0", padding: 0, listStyle: "none", display: "grid", gap: 6 }}>
              {line.match.alternatives.slice(0, 3).map((alternative) => (
                <li key={alternative.sku} style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12.5 }}>
                  <Stamp tone="light">{alternative.sku}</Stamp>
                  <span style={{ minWidth: 0, flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", color: "var(--ds-text-2)" }}>
                    {alternative.description}
                  </span>
                  <span className="ds-num ds-mono" style={{ color: "var(--ds-text-3)" }}>
                    {(Number(alternative.score) * 100).toFixed(0)}%
                  </span>
                </li>
              ))}
            </ul>
          </>
        )}

        {line.supply.options.length > 0 && (
          <>
            <p className="ds-mono-label" style={{ margin: "16px 0 0" }}>
              How it would be supplied
            </p>
            <ul style={{ margin: "6px 0 0", padding: 0, listStyle: "none", display: "grid", gap: 6 }}>
              {line.supply.options.map((option) => (
                <li
                  key={option.code}
                  style={{
                    padding: "8px 12px",
                    borderRadius: 3,
                    fontSize: 12.5,
                    border: `1px solid ${option.code === line.supply.chosen ? "var(--ds-accent)" : "var(--ds-line)"}`,
                    background: option.code === line.supply.chosen ? "var(--ds-accent-soft)" : "var(--ds-surface)",
                  }}
                >
                  <p style={{ margin: 0, fontWeight: 600 }}>{option.label}</p>
                  <p style={{ margin: "2px 0 0", color: "var(--ds-text-2)" }}>{option.detail}</p>
                </li>
              ))}
            </ul>
          </>
        )}
      </div>
    </div>
  );
}

export function LinesTable({ version }: { version: QuoteVersion }) {
  const [open, setOpen] = useState<number | null>(null);
  const lines = version.lines ?? [];

  return (
    <>
      <div className="qa-only-wide">
        <Ledger
          head={
            <>
              <Th width="3.5rem" align="right">
                Line
              </Th>
              <Th>Line and matched part</Th>
              <Th align="right" width="7rem">
                Quantity
              </Th>
              <Th align="right" width="7.5rem">
                Unit price
              </Th>
              <Th align="right" width="9rem">
                Line total
              </Th>
            </>
          }
        >
          {lines.map((line, index) => {
            const expanded = open === line.line_number;
            const tone = statusTone(line.status);
            return (
              <Fragment key={line.line_number}>
                <Reveal
                  as="tr"
                  index={index}
                  y={24}
                  data-clickable=""
                  aria-expanded={expanded}
                  onClick={() => setOpen(expanded ? null : line.line_number)}
                >
                  <Td
                    align="right"
                    className="ds-rowmark"
                    style={{ "--row-tone": TONE_COLOUR[tone], paddingLeft: 18 } as CSSProperties}
                  >
                    <button
                      type="button"
                      className="qa-line-toggle"
                      aria-expanded={expanded}
                      aria-label={`${expanded ? "Hide" : "Show"} how line ${line.line_number} was matched`}
                      onClick={(event) => {
                        event.stopPropagation();
                        setOpen(expanded ? null : line.line_number);
                      }}
                    >
                      {String(line.line_number).padStart(2, "0")}
                    </button>
                  </Td>
                  <Td>
                    <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: 8 }}>
                      {line.product ? (
                        <>
                          <Stamp>{line.product.sku}</Stamp>
                          <span style={{ fontSize: 13.5 }}>{line.product.description}</span>
                        </>
                      ) : (
                        <span style={{ fontSize: 13.5 }}>{line.original_request_text}</span>
                      )}
                      {line.status !== "priced" && (
                        <StatusChip tone={tone} size="small" pulse={line.status === "awaiting_supplier"}>
                          {line.status_label}
                        </StatusChip>
                      )}
                      {line.pricing.below_margin_floor && (
                        <StatusChip tone="fail" size="small">
                          Below the margin floor
                        </StatusChip>
                      )}
                    </div>
                    {line.product &&
                      !sameThing(line.original_request_text, line.product.sku, line.product.description) && (
                        <p
                          className="ds-mono"
                          style={{ margin: "5px 0 0", fontSize: 11.5, color: "var(--ds-text-3)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", maxWidth: 520 }}
                        >
                          asked for: {line.original_request_text}
                        </p>
                      )}
                  </Td>
                  <Td align="right">
                    {quantity(line.pricing.quantity_billed)}
                    {line.pricing.unit_of_sale && (
                      <span style={{ display: "block", fontSize: 11, color: "var(--ds-text-3)" }}>
                        {line.pricing.unit_of_sale}
                      </span>
                    )}
                  </Td>
                  <Td align="right">
                    <span onClick={(event) => event.stopPropagation()}>
                      <Figure
                        value={money(line.pricing.unit_price)}
                        heading={`Line ${line.line_number} unit price`}
                        trace={line.calculation_trace}
                        note={unitNote(line)}
                      />
                    </span>
                  </Td>
                  <Td align="right">
                    <span onClick={(event) => event.stopPropagation()}>
                      <Figure
                        emphasis
                        value={money(line.pricing.line_total)}
                        heading={`Line ${line.line_number} total`}
                        trace={line.calculation_trace}
                      />
                      {Number(line.pricing.import_duty) > 0 && (
                        <span style={{ display: "block", marginTop: 4, whiteSpace: "nowrap", fontSize: 11.5, color: "var(--ds-text-3)" }}>
                          duty{" "}
                          <Figure
                            value={money(line.pricing.import_duty)}
                            heading={`Line ${line.line_number} import duty`}
                            trace={line.calculation_trace}
                            extra={<DutyBreakdown line={line} />}
                          />
                        </span>
                      )}
                    </span>
                  </Td>
                </Reveal>
                {expanded && (
                  <tr>
                    <td colSpan={5} style={{ background: "var(--ds-page)", padding: "18px 20px 22px 74px" }}>
                      <MatchDetail line={line} />
                    </td>
                  </tr>
                )}
              </Fragment>
            );
          })}
        </Ledger>
      </div>

      <ul className="qa-only-narrow" style={{ listStyle: "none", margin: 0, padding: 0 }}>
        {lines.map((line, index) => {
          const expanded = open === line.line_number;
          const tone = statusTone(line.status);
          return (
            <Reveal
              as="li"
              key={line.line_number}
              index={index}
              y={24}
              style={{ borderTop: index ? "1px solid var(--ds-line)" : undefined, padding: "14px 16px" }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
                <span className="ds-mono" style={{ fontSize: 11.5, fontWeight: 600, color: "var(--ds-text-3)" }}>
                  {String(line.line_number).padStart(2, "0")}
                </span>
                {line.product && <Stamp>{line.product.sku}</Stamp>}
                {line.status !== "priced" && (
                  <StatusChip tone={tone} size="small">
                    {line.status_label}
                  </StatusChip>
                )}
              </div>
              <p style={{ margin: "8px 0 0", fontSize: 13.5 }}>
                {line.product?.description ?? line.original_request_text}
              </p>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", gap: 10, marginTop: 8 }}>
                <span style={{ fontSize: 12.5, color: "var(--ds-text-2)" }}>
                  {quantity(line.pricing.quantity_billed)} ×{" "}
                  <Figure
                    value={money(line.pricing.unit_price)}
                    heading={`Line ${line.line_number} unit price`}
                    trace={line.calculation_trace}
                    note={unitNote(line)}
                  />
                </span>
                <span style={{ fontWeight: 600 }}>
                  <Figure
                    value={money(line.pricing.line_total)}
                    heading={`Line ${line.line_number} total`}
                    trace={line.calculation_trace}
                  />
                </span>
              </div>
              <button
                type="button"
                className="ds-btn"
                data-tone="ghost"
                data-size="small"
                style={{ marginTop: 8, paddingLeft: 0 }}
                aria-expanded={expanded}
                onClick={() => setOpen(expanded ? null : line.line_number)}
              >
                {expanded ? "Hide how it was matched" : "How it was matched"}
              </button>
              {expanded && <MatchDetail line={line} />}
            </Reveal>
          );
        })}
      </ul>
    </>
  );
}

function DutyBreakdown({ line }: { line: QuoteLine }) {
  if (!line.pricing.duty_breakdown.length) return null;
  return (
    <div>
      <p className="ds-mono-label" style={{ margin: 0 }}>
        Duty, component by component
      </p>
      <ul style={{ margin: "8px 0 0", padding: 0, listStyle: "none", display: "grid", gap: 8 }}>
        {line.pricing.duty_breakdown.map((component, index) => (
          <li
            key={index}
            style={{ padding: "10px 12px", borderRadius: 3, border: "1px solid var(--ds-line)", fontSize: 13 }}
          >
            <p style={{ margin: 0, display: "flex", justifyContent: "space-between", gap: 10 }}>
              <strong>{words(component.component)}</strong>
              <span className="ds-num ds-mono">{component.rate_percent}%</span>
            </p>
            {component.published_rate_percent &&
              component.published_rate_percent !== component.rate_percent && (
                <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--ds-warn-ink)" }}>
                  Published rate {component.published_rate_percent}%, reduced by the cap
                </p>
              )}
            {component.authority && (
              <p style={{ margin: "4px 0 0", fontSize: 12, color: "var(--ds-text-3)" }}>{component.authority}</p>
            )}
            {component.note && (
              <p style={{ margin: "4px 0 0", fontSize: 12, lineHeight: 1.5, color: "var(--ds-text-2)" }}>{component.note}</p>
            )}
          </li>
        ))}
      </ul>
      <p style={{ margin: "8px 0 0", fontSize: 12, color: "var(--ds-text-3)" }}>Confirm with a broker before shipment.</p>
    </div>
  );
}
