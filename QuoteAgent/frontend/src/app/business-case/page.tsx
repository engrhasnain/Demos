"use client";

import { useMemo, useState, type CSSProperties } from "react";

import { Banner, Card, Stat } from "@/design/Surface";
import { NodeChain } from "@/design/NodeChain";
import { Reveal } from "@/design/Reveal";
import { useInView } from "@/design/motion";
import { Figure, type Explain } from "@/components/trace";
import { PageBand } from "@/components/ui";

/**
 * The business case.
 *
 * Every figure is computed from the inputs beside it and the arithmetic is
 * printed next to the answer, so a finance lead can check it rather than
 * believe it. The defaults are illustrative starting numbers for Hengtai;
 * change them to the client's own and the page answers for them.
 */

type Input = {
  key: string;
  label: string;
  unit: string;
  value: number;
  step: number;
  max: number;
};

const DEFAULTS: Input[] = [
  { key: "requests", label: "Requests for quotation a week", unit: "requests", value: 60, step: 5, max: 300 },
  { key: "hoursToday", label: "Hours each one takes today", unit: "hours", value: 3.5, step: 0.25, max: 12 },
  { key: "minutesWithAgent", label: "Minutes of review with the agent", unit: "minutes", value: 45, step: 5, max: 240 },
  { key: "hourlyCost", label: "Loaded cost of a sales engineer", unit: "TWD an hour", value: 1100, step: 50, max: 5000 },
  { key: "weeks", label: "Working weeks a year", unit: "weeks", value: 48, step: 1, max: 52 },
];

function format(value: number, places = 0): string {
  return value.toLocaleString("en-GB", {
    minimumFractionDigits: places,
    maximumFractionDigits: places,
  });
}

export default function BusinessCasePage() {
  const [inputs, setInputs] = useState<Input[]>(DEFAULTS);
  const get = (key: string) => inputs.find((input) => input.key === key)?.value ?? 0;

  const sums = useMemo(() => {
    const requests = get("requests");
    const hoursToday = get("hoursToday");
    const minutesWithAgent = get("minutesWithAgent");
    const hourlyCost = get("hourlyCost");
    const weeks = get("weeks");
    const hoursNow = requests * hoursToday;
    const hoursAfter = (requests * minutesWithAgent) / 60;
    const released = hoursNow - hoursAfter;
    const peopleEquivalent = released / 40;
    const yearlyHours = released * weeks;
    const yearlyCost = yearlyHours * hourlyCost;
    return {
      requests,
      hoursToday,
      minutesWithAgent,
      hourlyCost,
      weeks,
      hoursNow,
      hoursAfter,
      released,
      peopleEquivalent,
      yearlyHours,
      yearlyCost,
      percentReleased: hoursNow > 0 ? (released / hoursNow) * 100 : 0,
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inputs]);

  const update = (key: string, value: number) =>
    setInputs((current) => current.map((input) => (input.key === key ? { ...input, value } : input)));

  const yours = (label: string, value: string) => ({ label, value, source: "Your numbers on this page", sourceKind: "Input" });

  const explainReleased: Explain = {
    formula: `${format(sums.requests)} requests × ${sums.hoursToday} hours − ${format(sums.requests)} requests × ${sums.minutesWithAgent} minutes ÷ 60`,
    result: `${format(sums.released)} hours a week`,
    inputs: [
      yours("Requests a week", format(sums.requests)),
      yours("Hours each today", String(sums.hoursToday)),
      yours("Minutes of review with the agent", String(sums.minutesWithAgent)),
    ],
  };
  const explainPeople: Explain = {
    formula: `${format(sums.released)} hours released ÷ 40 hours a week`,
    result: `${format(sums.peopleEquivalent, 1)} sales engineers`,
    inputs: [yours("Hours released a week", format(sums.released)), { label: "A working week", value: "40 hours", source: "Fixed in this sum", sourceKind: "Assumption" }],
  };
  const explainCost: Explain = {
    formula: `${format(sums.released)} hours × ${format(sums.weeks)} weeks × ${format(sums.hourlyCost)} an hour`,
    result: `${format(sums.yearlyCost)} TWD a year`,
    inputs: [
      yours("Hours released a week", format(sums.released)),
      yours("Working weeks a year", format(sums.weeks)),
      yours("Loaded cost an hour", `${format(sums.hourlyCost)} TWD`),
    ],
  };

  return (
    <div>
      <PageBand
        eyebrow={["Business case", "illustrative: change the inputs"]}
        title="What it is worth,"
        accent="worked out in front of you."
        lede="These are starting figures for a team like Hengtai's. Put in your own and every number below is worked out again, with the arithmetic printed beside it. This product measures its pricing, not this saving."
        aside={
          <div className="qa-verdict">
            <div className="ds-stats" style={{ marginTop: 0 }}>
              <Stat
                label="Hours released a week"
                tone="accent"
                value={<Figure value={format(sums.released)} count={sums.released} decimals={0} heading="Hours released a week" explain={explainReleased} origin="Worked out on this page" />}
              />
              <Stat
                label="Sales engineers"
                value={
                  <Figure
                    value={format(sums.peopleEquivalent, 1)}
                    count={sums.peopleEquivalent}
                    decimals={1}
                    heading="People that is equivalent to"
                    explain={explainPeople}
                    origin="Worked out on this page"
                  />
                }
              />
            </div>
            <div className="ds-band-rule" style={{ margin: "22px 0 18px" }} />
            <Stat
              label="A year, at your cost, in TWD"
              tone="pass"
              value={
                <Figure value={format(sums.yearlyCost)} count={sums.yearlyCost} decimals={0} heading="Cost of the time released over a year" explain={explainCost} origin="Worked out on this page" />
              }
            />
          </div>
        }
      />

      <div className="ds-work">
        <div className="qa-bc-grid">
          <Card eyebrow="Your numbers" title="Change any of them" flush className="qa-inputs">
            <div>
              {inputs.map((input, index) => (
                <Reveal key={input.key} index={index} y={20} style={{ padding: "16px 20px", borderTop: index ? "1px solid var(--ds-line)" : undefined }}>
                  <label style={{ display: "block" }}>
                    <span className="ds-mono-label ds-field-label">{input.label}</span>
                    <span style={{ display: "flex", alignItems: "center", gap: 10 }}>
                      <input
                        type="number"
                        value={input.value}
                        step={input.step}
                        min={0}
                        onChange={(event) => update(input.key, Number(event.target.value) || 0)}
                        className="ds-input ds-num"
                        data-mono=""
                        style={{ width: 110, textAlign: "right" }}
                      />
                      <span style={{ fontSize: 12.5, color: "var(--ds-text-3)" }}>{input.unit}</span>
                    </span>
                  </label>
                  <input
                    type="range"
                    aria-label={`${input.label}, slider`}
                    min={0}
                    max={input.max}
                    step={input.step}
                    value={Math.min(input.value, input.max)}
                    onChange={(event) => update(input.key, Number(event.target.value))}
                    className="qa-range"
                  />
                </Reveal>
              ))}
            </div>
            <div style={{ padding: "12px 20px", borderTop: "1px solid var(--ds-line)" }}>
              <button type="button" onClick={() => setInputs(DEFAULTS)} className="ds-btn" data-tone="ghost" data-size="small">
                Back to the starting figures
              </button>
            </div>
          </Card>

          <div style={{ display: "grid", gap: 20, minWidth: 0 }}>
            <Card eyebrow="Hours spent quoting, every week" title="Today against with the agent">
              <HoursChart
                today={sums.hoursNow}
                after={sums.hoursAfter}
                released={sums.released}
                percent={sums.percentReleased}
                formulas={[
                  `${format(sums.requests)} requests × ${sums.hoursToday} hours`,
                  `${format(sums.requests)} requests × ${sums.minutesWithAgent} minutes ÷ 60`,
                ]}
              />
            </Card>

            <Card eyebrow="How that is worked out" title="Five sums, in order">
              <NodeChain
                stagger={110}
                items={[
                  {
                    label: "Hours spent quoting today",
                    formula: `${format(sums.requests)} requests × ${sums.hoursToday} hours`,
                    result: `${format(sums.hoursNow)} hours a week`,
                  },
                  {
                    label: "Hours spent reviewing with the agent",
                    formula: `${format(sums.requests)} requests × ${sums.minutesWithAgent} minutes ÷ 60`,
                    result: `${format(sums.hoursAfter)} hours a week`,
                  },
                  {
                    label: "Hours released",
                    formula: `${format(sums.hoursNow)} − ${format(sums.hoursAfter)}`,
                    result: `${format(sums.released)} hours a week, ${format(sums.percentReleased)}% of the time spent today`,
                  },
                  {
                    label: "People that is equivalent to",
                    formula: `${format(sums.released)} hours ÷ 40 hours a week`,
                    result: `${format(sums.peopleEquivalent, 1)} sales engineers`,
                  },
                  {
                    label: "Cost of that time over a year",
                    formula: `${format(sums.released)} hours × ${format(sums.weeks)} weeks × ${format(sums.hourlyCost)} an hour`,
                    result: `${format(sums.yearlyCost)} TWD a year`,
                  },
                ].map((step, index, all) => ({
                  key: step.label,
                  tone: index === all.length - 1 ? "accent" : undefined,
                  marker: String(index + 1).padStart(2, "0"),
                  content: (
                    <div style={{ paddingBottom: 4 }}>
                      <p className="ds-trace-step-title" style={{ margin: 0, paddingTop: 3 }}>
                        {step.label}
                      </p>
                      <p className="ds-trace-formula">{step.formula}</p>
                      <p className="ds-trace-result" style={{ margin: "8px 0 0" }}>
                        <span style={{ color: "var(--ds-text-3)" }}>= </span>
                        <b>{step.result}</b>
                      </p>
                    </div>
                  ),
                }))}
              />
            </Card>

            <Card eyebrow="Not counted" title="Left out on purpose">
              <ul style={{ listStyle: "none", margin: 0, padding: 0, display: "grid", gap: 10 }}>
                {[
                  "Deals won because the quote arrived first",
                  "Margin no longer lost to pricing mistakes",
                  "What it costs to run: nothing on the built-in engine",
                ].map((item, index) => (
                  <Reveal as="li" key={item} index={index} y={16} from="left" style={{ display: "flex", gap: 10, alignItems: "center", fontSize: 14 }}>
                    <span style={{ width: 8, height: 8, borderRadius: 2, background: "var(--ds-accent)", flexShrink: 0 }} aria-hidden />
                    {item}
                  </Reveal>
                ))}
              </ul>
            </Card>

            <Banner tone="accent" title="Illustrative figures">
              The saving depends on how a particular team works, and no amount of software testing establishes it. What
              this product measures is on the acceptance criteria screen.
            </Banner>
          </div>
        </div>
      </div>
    </div>
  );
}

/** Two solid bars that grow when they come into view, and again when the inputs move. */
function HoursChart({
  today,
  after,
  released,
  percent,
  formulas,
}: {
  today: number;
  after: number;
  released: number;
  percent: number;
  formulas: [string, string];
}) {
  const [ref, shown] = useInView<HTMLDivElement>({ threshold: 0.3 });
  const max = Math.max(today, after, 1);
  const bars = [
    { label: "Today", value: today, colour: "var(--ds-ink)", formula: formulas[0] },
    { label: "With the agent", value: after, colour: "var(--ds-accent)", formula: formulas[1] },
  ];
  return (
    <div ref={ref} className="qa-hours" data-shown={shown ? "" : undefined}>
      <div className="qa-hours-bars">
        {bars.map((bar, index) => (
          <div key={bar.label} className="qa-hours-col">
            <span className="ds-title ds-num" style={{ fontSize: 22 }}>
              <Figure
                value={format(bar.value)}
                heading={`Hours a week, ${bar.label.toLowerCase()}`}
                explain={{
                  formula: bar.formula,
                  result: `${format(bar.value)} hours a week`,
                  inputs: [{ label: "Your numbers", value: bar.formula, source: "Inputs on this page", sourceKind: "Input" }],
                }}
                origin="Worked out on this page"
              />
              <span className="ds-mono" style={{ fontSize: 11, color: "var(--ds-text-3)", marginLeft: 4 }}>
                hours
              </span>
            </span>
            <div className="qa-hours-track">
              <span
                style={
                  {
                    "--h": Math.max(0.02, bar.value / max),
                    background: bar.colour,
                    "--ds-d": `${index * 180}ms`,
                  } as CSSProperties
                }
              />
            </div>
            <span className="ds-mono-label">{bar.label}</span>
          </div>
        ))}
      </div>
      <div className="qa-hours-note">
        <span className="ds-display" style={{ fontSize: 44, color: "var(--ds-accent-ink)" }}>
          <Figure
            value={`${format(percent)}%`}
            count={percent}
            decimals={0}
            heading="Share of quoting time released"
            explain={{
              formula: `${format(released)} hours released ÷ ${format(today)} hours today × 100`,
              result: `${format(percent)}%`,
              inputs: [
                { label: "Hours today", value: format(today), source: "Your numbers on this page", sourceKind: "Input" },
                { label: "Hours with the agent", value: format(after), source: "Your numbers on this page", sourceKind: "Input" },
              ],
            }}
            origin="Worked out on this page"
          />
        </span>
        <p style={{ margin: "6px 0 0", fontSize: 14, color: "var(--ds-text-2)" }}>
          of the time spent quoting comes back: {format(released)} hours every week.
        </p>
      </div>
    </div>
  );
}

export const dynamic = "force-dynamic";
