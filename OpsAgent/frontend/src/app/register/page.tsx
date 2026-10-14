"use client";

/**
 * The access record: every query that ran, who ran it, how many rows came
 * back and which filter was on it, and the refusals, which are the half an
 * auditor wants.
 */

import { useMemo, useState } from "react";

import { counted, Figure } from "@/components/trace";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { Tabs } from "@/design/Tabs";
import { Band, Banner, Card, Empty } from "@/design/Surface";
import { useLoad, useSignedIn } from "@/lib/session";
import type { AccessEntry } from "@/lib/types";
import { capabilityWords, dayAndClock, filterWords, grouped, plain, reaches } from "@/lib/words";

export default function AccessRecord() {
  const user = useSignedIn();
  const allowedHere = reaches(user?.role, "manager");
  const { data, error } = useLoad<{ entries: AccessEntry[]; refused: number }>(
    user && allowedHere ? "/api/access-log?limit=300" : null,
    [user?.email],
  );
  const [only, setOnly] = useState<"all" | "refused">("all");

  const entries = useMemo(() => data?.entries ?? [], [data]);
  const shown = entries.filter((entry) => only === "all" || !entry.allowed);
  const refused = entries.filter((entry) => !entry.allowed);
  const rows = entries.reduce((total, entry) => total + (entry.allowed ? entry.rows_returned : 0), 0);
  const people = new Set(entries.map((entry) => entry.who)).size;

  if (!user) return null;

  const stat = (label: string, value: number, formula: string, list: AccessEntry[], tone?: "accent" | "fail") => (
    <div key={label}>
      <span className="ds-stat-value" data-tone={tone}>
        <Figure
          value={grouped(value)}
          count={value}
          content={counted(
            label,
            grouped(value),
            formula,
            list.slice(0, 8).map((entry) => ({
              label: `${entry.who} · ${capabilityWords(entry.capability)}`,
              value: entry.allowed ? `${grouped(entry.rows_returned)} rows` : "refused",
              source: dayAndClock(entry.occurred_at),
              sourceKind: "Access record",
            })),
          )}
        />
      </span>
      <span className="ds-mono-label ds-stat-label">{label}</span>
    </div>
  );

  return (
    <>
      <Band top>
        <div className="oa-page-band">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              Access record <span className="ds-eyebrow-sep">·</span> who read what
            </span>
          </Reveal>
          <Reveal index={1} y={32}>
            <h1 className="ds-display oa-page-title">
              Every read, on the record.
              <br />
              <span className="oa-light ds-accent-text">Including the refusals.</span>
            </h1>
          </Reveal>
          <Reveal index={2}>
            <p className="ds-band-lede">
              Each query that ran, who ran it, how many rows came back and which filter was on it. A refusal is recorded
              before anything runs, which is the half an auditor wants to read.
            </p>
          </Reveal>
          {allowedHere && data && (
            <Reveal index={3}>
              <div className="ds-stats">
                {stat("Reads recorded", entries.length, "count of entries in the access record shown here", entries, "accent")}
                {stat("Refused", refused.length, "count of reads the role check refused before anything ran", refused, "fail")}
                {stat("Rows returned", rows, "sum of rows returned by every read that was allowed", entries.filter((entry) => entry.allowed))}
                {stat("People", people, "count of different people in the record", entries)}
              </div>
            </Reveal>
          )}
        </div>
      </Band>

      <div className="ds-work">
        {!allowedHere ? (
          <Banner tone="warn" title="This record is for an operations manager or above">
            You are signed in as {user.role_label.toLowerCase()}. Switch who is asking from the menu at the top right to
            read it.
          </Banner>
        ) : (
          <>
            {error && <Banner tone="fail" title="The record did not load">{error}</Banner>}
            <Tabs
              label="Which reads to show"
              value={only}
              onChange={setOnly}
              tabs={[
                { key: "all", label: "Everything", badge: entries.length },
                { key: "refused", label: "Refused", badge: refused.length },
              ]}
            />
            <div style={{ marginTop: 18 }} id="tab-panel" role="tabpanel">
              {data && shown.length === 0 ? (
                <Empty title="Nothing recorded here yet." />
              ) : (
                <Card flush>
                  <div className="ds-table-wrap">
                    <table className="ds-table oa-record">
                      <thead>
                        <tr>
                          <th>When</th>
                          <th>Who</th>
                          <th>Reviewed query</th>
                          <th data-align="right">Rows</th>
                          <th>Filter, in words</th>
                        </tr>
                      </thead>
                      <tbody>
                        {shown.slice(0, 160).map((entry, index) => (
                          <Reveal
                            as="tr"
                            key={entry.id}
                            index={index}
                            className="ds-rowmark"
                            data-refused={entry.allowed ? undefined : ""}
                            style={{ "--row-tone": entry.allowed ? "var(--ds-accent)" : "var(--ds-fail)" } as React.CSSProperties}
                          >
                            <td className="ds-mono" style={{ fontSize: 12.5, whiteSpace: "nowrap" }}>
                              {dayAndClock(entry.occurred_at)}
                            </td>
                            <td style={{ whiteSpace: "nowrap" }}>{entry.who || "—"}</td>
                            <td style={{ minWidth: 220 }}>
                              {capabilityWords(entry.capability)}
                              {Object.keys(entry.parameters ?? {}).length > 0 && (
                                <span className="ds-mono oa-record-params">
                                  {Object.entries(entry.parameters)
                                    .map(([key, value]) => `${key === "text" ? "name" : key} ${String(value).replace(/^%|%$/g, "")}`)
                                    .join(" · ")}
                                </span>
                              )}
                              {!entry.allowed && (
                                <span className="oa-record-refusal">
                                  <StatusChip tone="fail" size="small">
                                    Refused
                                  </StatusChip>
                                  {plain(entry.refusal)}
                                </span>
                              )}
                            </td>
                            <td data-align="right">{entry.allowed ? grouped(entry.rows_returned) : "—"}</td>
                            <td style={{ fontSize: 12.5, color: "var(--ds-text-2)", minWidth: 200 }}>
                              {filterWords(entry.filter_applied, entry.allowed)}
                            </td>
                          </Reveal>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </Card>
              )}
            </div>
          </>
        )}
      </div>
    </>
  );
}
