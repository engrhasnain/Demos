"use client";

/**
 * Two systems, no shared transaction: the posting journey.
 *
 * The top lane is LedgerFlow's own records; the bottom lane is the ledger,
 * a different system with its own database. Nothing can commit in both at
 * once, so posting is two writes: the ledger takes the bill, then LedgerFlow
 * records that it did. A glowing node carries the invoice along the top
 * lane, drops to the ledger, and climbs back to be confirmed.
 *
 * When the connection dies between those two writes, the climb back breaks
 * (coral) and the confirmation is left open. The retry carries the same key
 * down again; the ledger finds the bill it already has, rings, and nothing
 * new is written. The counter of bills in the ledger never moves past one.
 *
 * Scripts are chained on the canvas's own arrival callbacks, so the words
 * beside the diagram change exactly when the pulse lands. Under reduced
 * motion every arrival fires at once and the final state is drawn.
 */

import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import {
  Constellation,
  type ConstellationHandle,
  type ConstellationLink,
  type ConstellationNode,
  type Tone,
} from "@/design/Constellation";
import { CountUp } from "@/design/CountUp";
import { StatusChip } from "@/design/StatusChip";
import { useInView } from "@/design/motion";

export type JourneyFacts = {
  /** Top-lane steps already done before posting: 0 captured, 1 matched, 2 approved. */
  reached: number;
  approvalPending: boolean;
  blocked: boolean;
  blockedReason?: string;
  postingKey: string;
  billReference: string;
  ledgerName: string;
  attempts: number;
  bills: number;
};

export type JourneyState = "waiting" | "posted" | "dropped" | "recovered";
export type Script = "post" | "drop" | "retry" | "replay";

type Beat = {
  reached: number;
  bill: "none" | "written" | "found";
  link: "none" | "ok" | "dropped";
  confirmed: "none" | "open" | "done";
  attempts: number;
  bills: number;
  words: string;
  tone: "accent" | "pass" | "warn" | "fail" | "neutral";
};

function stillBeat(state: JourneyState, facts: JourneyFacts): Beat {
  if (state === "posted")
    return {
      reached: 3,
      bill: "written",
      link: "ok",
      confirmed: "done",
      attempts: facts.attempts,
      bills: facts.bills,
      words: `Posted once. The ledger has ${facts.billReference || "the bill"}, and LedgerFlow recorded it.`,
      tone: "pass",
    };
  if (state === "dropped")
    return {
      reached: 3,
      bill: "written",
      link: "dropped",
      confirmed: "open",
      attempts: facts.attempts,
      bills: facts.bills,
      words: "The ledger took the bill, then the connection dropped. LedgerFlow does not know yet. Posting again is safe.",
      tone: "fail",
    };
  if (state === "recovered")
    return {
      reached: 3,
      bill: "found",
      link: "ok",
      confirmed: "done",
      attempts: facts.attempts,
      bills: facts.bills,
      words: `Recovered. Attempt ${facts.attempts} found the bill an earlier attempt wrote, by its key. Still one bill.`,
      tone: "pass",
    };
  return {
    reached: facts.reached,
    bill: "none",
    link: "none",
    confirmed: "none",
    attempts: facts.attempts,
    bills: facts.bills,
    words: facts.blocked
      ? `Stopped before the ledger: ${facts.blockedReason || "something needs a person"}. Nothing can be written.`
      : facts.approvalPending
        ? "Waiting for a signature. Nothing goes to the ledger until it is signed."
        : "Ready. Posting writes the bill in the ledger, then records it here.",
    tone: facts.blocked ? "fail" : facts.approvalPending ? "warn" : "accent",
  };
}

const TOP = ["cap", "mat", "app", "key"] as const;

export function PostingJourney({
  facts,
  state,
  play,
  rehearsal = false,
  stacked = false,
  caption,
  footer,
}: {
  facts: JourneyFacts;
  /** Where the real record stands. */
  state: JourneyState;
  /** Change the nonce to run a script once. */
  play?: { script: Script; nonce: number } | null;
  /** Loop the whole story on its own (the desk and the ledger page). */
  rehearsal?: boolean;
  /** Diagram above, words below: for wide bands. */
  stacked?: boolean;
  caption?: ReactNode;
  footer?: ReactNode;
}) {
  const canvas = useRef<ConstellationHandle>(null);
  const [beat, setBeat] = useState<Beat>(() => stillBeat(state, facts));
  const [box, setBox] = useState({ compact: false });
  const wrap = useRef<HTMLDivElement>(null);
  const [viewRef, onScreen] = useInView<HTMLDivElement>({ once: false, threshold: 0.15, rootMargin: "0px" });
  const running = useRef(0);

  // Follow the real record when no script is playing.
  useEffect(() => {
    if (!running.current) setBeat(stillBeat(state, facts));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [state, facts.attempts, facts.bills, facts.reached, facts.approvalPending, facts.blocked, facts.billReference]);

  useEffect(() => {
    const element = wrap.current;
    if (!element) return;
    const measure = () => setBox({ compact: element.getBoundingClientRect().width < 560 });
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  const compact = box.compact;

  /* -------------------------------------------------------------- */
  /* Scripts                                                        */
  /* -------------------------------------------------------------- */
  const run = useCallback(
    (script: Script, done?: () => void) => {
      const pulse = canvas.current?.pulse;
      const flash = canvas.current?.flash;
      if (!pulse || !flash) return;
      const token = ++running.current;
      const alive = () => running.current === token;
      const finish = () => {
        if (!alive()) return;
        running.current = 0;
        done?.();
      };

      const writeBill = (attempt: number, then: () => void) => {
        setBeat((b) => ({ ...b, reached: 2, bill: "none", link: "none", confirmed: "none", attempts: attempt - 1, words: "Matched and approved. Preparing the posting under the invoice's key.", tone: "accent" }));
        pulse(["cap", "mat", "app", "key"], {
          duration: 1250,
          tone: "accent",
          size: 3.2,
          onArrive: () => {
            if (!alive()) return;
            setBeat((b) => ({ ...b, reached: 3, attempts: attempt, words: `Attempt ${attempt}: is there a bill under this key already? No. Writing it.`, tone: "accent" }));
            pulse(["key", "bill"], {
              duration: 800,
              tone: "accent",
              size: 3.2,
              onArrive: () => {
                if (!alive()) return;
                flash("bill", "pass");
                setBeat((b) => ({ ...b, bill: "written", bills: 1, words: "The ledger took the bill. One bill in the ledger.", tone: "pass" }));
                then();
              },
            });
          },
        });
      };

      const confirm = (words: string) =>
        pulse(["bill", "conf"], {
          duration: 800,
          tone: "pass",
          size: 3.2,
          onArrive: () => {
            if (!alive()) return;
            flash("conf", "pass");
            setBeat((b) => ({ ...b, link: "ok", confirmed: "done", words, tone: "pass" }));
            finish();
          },
        });

      const drop = (then?: () => void) =>
        pulse(["bill", "cut"], {
          duration: 520,
          tone: "fail",
          size: 3,
          onArrive: () => {
            if (!alive()) return;
            flash("cut", "fail");
            setBeat((b) => ({
              ...b,
              link: "dropped",
              confirmed: "open",
              words: "The connection dropped after the ledger took the bill. LedgerFlow never heard back.",
              tone: "fail",
            }));
            if (then) then();
            else finish();
          },
        });

      const retry = (attempt: number) => {
        setBeat((b) => ({ ...b, words: `Attempt ${attempt}: the same invoice makes the same key. Asking the ledger again.`, tone: "accent" }));
        pulse(["key", "bill"], {
          duration: 900,
          tone: "accent",
          size: 3.4,
          onArrive: () => {
            if (!alive()) return;
            flash("bill", "accent");
            setBeat((b) => ({ ...b, attempts: attempt, bill: "found", words: "Found by its key. Nothing new written: still one bill.", tone: "pass" }));
            window.setTimeout(() => {
              if (!alive()) return;
              confirm(`Recovered on attempt ${attempt}. One bill in the ledger, one posting here. Not paid twice.`);
            }, 650);
          },
        });
      };

      if (script === "post") {
        writeBill(Math.max(1, facts.attempts || 1), () => confirm("Confirmed here. One bill in the ledger, one posting in LedgerFlow."));
      } else if (script === "drop") {
        writeBill(Math.max(1, facts.attempts || 1), () => window.setTimeout(() => alive() && drop(), 380));
      } else if (script === "retry") {
        setBeat((b) => ({ ...b, reached: 3, bill: "written", link: "dropped", confirmed: "open", bills: Math.max(1, b.bills) }));
        retry(Math.max(2, facts.attempts || 2));
      } else {
        // replay: the whole story, drop then recover
        writeBill(1, () =>
          window.setTimeout(() => {
            if (!alive()) return;
            drop(() => window.setTimeout(() => alive() && retry(2), 1500));
          }, 380),
        );
      }
    },
    [facts.attempts],
  );

  // A requested script, once per nonce.
  const lastNonce = useRef<number | null>(null);
  useEffect(() => {
    if (!play || lastNonce.current === play.nonce) return;
    lastNonce.current = play.nonce;
    const handle = window.setTimeout(() => run(play.script), 60);
    return () => window.clearTimeout(handle);
  }, [play, run]);

  // The rehearsal loop: only while on screen.
  useEffect(() => {
    if (!rehearsal || !onScreen) return;
    let timer = 0;
    let stopped = false;
    const loop = () => {
      if (stopped) return;
      run("replay", () => {
        timer = window.setTimeout(() => {
          if (stopped) return;
          setBeat({ ...stillBeat("waiting", { ...facts, reached: 2, approvalPending: false, blocked: false }), bills: 0, attempts: 0 });
          timer = window.setTimeout(loop, 900);
        }, 4200);
      });
    };
    timer = window.setTimeout(loop, 500);
    return () => {
      stopped = true;
      window.clearTimeout(timer);
      running.current = 0;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rehearsal, onScreen, run]);

  /* -------------------------------------------------------------- */
  /* The diagram                                                    */
  /* -------------------------------------------------------------- */
  const { nodes, links } = useMemo(() => {
    const top = compact ? null : 0.3;
    const place = (name: string): { x: number; y: number } => {
      if (compact) {
        const column: Record<string, { x: number; y: number }> = {
          cap: { x: 0.1, y: 0.17 },
          mat: { x: 0.1, y: 0.31 },
          app: { x: 0.1, y: 0.45 },
          key: { x: 0.1, y: 0.59 },
          conf: { x: 0.1, y: 0.9 },
          bill: { x: 0.8, y: 0.68 },
          cut: { x: 0.45, y: 0.79 },
        };
        return column[name];
      }
      const row: Record<string, { x: number; y: number }> = {
        cap: { x: 0.06, y: top! },
        mat: { x: 0.24, y: top! },
        app: { x: 0.42, y: top! },
        key: { x: 0.58, y: top! },
        conf: { x: 0.86, y: top! },
        bill: { x: 0.7, y: 0.8 },
        cut: { x: 0.78, y: 0.55 },
      };
      return row[name];
    };
    const labels: Record<string, string> = {
      cap: "Captured",
      mat: "Matched three ways",
      app: facts.approvalPending ? "Waiting to be signed" : "Approved",
      key: "Posting key",
      conf: "Confirmed here",
      bill: "Bill in the ledger",
    };
    const side = compact ? "right" : "above";
    const topTone = (index: number): Tone => {
      if (facts.blocked && beat.reached <= index && index >= 1) return index === 1 ? "fail" : "muted";
      if (index === 2 && facts.approvalPending && beat.reached < 3 && !rehearsal) return "warn";
      return beat.reached >= index ? "accent" : "muted";
    };
    const n: ConstellationNode[] = TOP.map((name, index) => ({
      id: name,
      ...place(name),
      r: name === "key" ? 4 : 3.4,
      tone: topTone(index),
      lit: beat.reached >= index,
      ring: (index === 2 && facts.approvalPending && beat.reached < 3 && !rehearsal) || (name === "key" && beat.reached >= 3),
      label: labels[name],
      sub:
        name === "key"
          ? beat.reached >= 3 || facts.postingKey
            ? shortKey(facts.postingKey)
            : "made on first post"
          : undefined,
      side: name === "key" && !compact ? "below" : side,
      drift: 1.5,
    }));
    const billTone: Tone = beat.bill === "none" ? "muted" : beat.bill === "found" ? "accent" : "pass";
    n.push({
      id: "bill",
      ...place("bill"),
      r: 5,
      tone: billTone,
      ring: beat.bill !== "none",
      lit: beat.bill !== "none",
      label: labels.bill,
      sub: beat.bill === "none" ? "none yet" : beat.bill === "found" ? "found by its key" : facts.billReference || "written",
      side: compact ? "left" : "right",
      drift: 1.5,
    });
    n.push({
      id: "cut",
      ...place("cut"),
      r: beat.link === "dropped" ? 3.4 : 1.2,
      tone: beat.link === "dropped" ? "fail" : "muted",
      lit: beat.link === "dropped",
      visible: true,
      label: beat.link === "dropped" ? "Connection dropped" : undefined,
      side: compact ? "below" : "left",
      drift: 1,
    });
    const confTone: Tone = beat.confirmed === "done" ? "pass" : beat.confirmed === "open" ? "warn" : "muted";
    n.push({
      id: "conf",
      ...place("conf"),
      r: 5,
      tone: confTone,
      ring: beat.confirmed !== "none",
      lit: beat.confirmed === "done",
      label: labels.conf,
      sub: beat.confirmed === "done" ? "one posting" : beat.confirmed === "open" ? "not confirmed" : "not yet",
      side: compact ? "right" : "above",
      drift: 1.5,
    });

    const l: ConstellationLink[] = [];
    for (let index = 1; index < TOP.length; index += 1) {
      l.push({ from: TOP[index - 1], to: TOP[index], tone: beat.reached >= index ? "accent" : "light", lit: beat.reached >= index });
    }
    l.push({ from: "key", to: "bill", tone: beat.bill !== "none" ? "accent" : "light", lit: beat.bill !== "none" });
    l.push({ from: "bill", to: "cut", tone: beat.link === "dropped" ? "fail" : beat.link === "ok" ? "pass" : "light", lit: beat.link !== "none" });
    l.push({ from: "cut", to: "conf", tone: beat.link === "ok" ? "pass" : "light", lit: beat.link === "ok", visible: beat.link !== "dropped" });
    return { nodes: n, links: l };
  }, [beat, compact, facts.approvalPending, facts.blocked, facts.postingKey, facts.billReference, rehearsal]);

  return (
    <div className="lf-journey" ref={viewRef} data-stacked={stacked ? "" : undefined}>
      <div className="lf-journey-stage" ref={wrap} data-compact={compact ? "" : undefined}>
        <span className="lf-lane lf-lane-top ds-mono-label">LedgerFlow · our records</span>
        <span className="lf-lane-rule" aria-hidden>
          <span className="ds-mono-label">No shared transaction</span>
        </span>
        <span className="lf-lane lf-lane-bottom ds-mono-label">{facts.ledgerName || "The ledger"} · another system</span>
        <div className="lf-journey-canvas">
          <Constellation
            ref={canvas}
            nodes={nodes}
            links={links}
            ambient={compact ? 16 : 30}
            reach={compact ? 80 : 110}
            introStagger={40}
            label="Posting journey: LedgerFlow's records above, the ledger below"
          />
        </div>
      </div>

      <div className="lf-journey-side">
        <div className="lf-journey-words" aria-live="polite" data-tone={beat.tone}>
          <StatusChip tone={beat.tone === "neutral" ? "neutral" : beat.tone} surface="dark" pulse={Boolean(running.current) || beat.tone === "fail"}>
            {beat.tone === "fail" ? "Interrupted" : beat.confirmed === "done" ? (beat.bill === "found" ? "Recovered" : "Posted once") : beat.reached >= 3 ? "Posting" : facts.blocked ? "Stopped" : "Before posting"}
          </StatusChip>
          <p>{beat.words}</p>
        </div>
        <div className="lf-journey-counts">
          <div>
            <span className="lf-journey-count" data-tone={beat.attempts > 1 ? "warn" : undefined}>
              <CountUp to={beat.attempts} duration={500} />
            </span>
            <span className="ds-mono-label">Attempts</span>
          </div>
          <div>
            <span className="lf-journey-count" data-tone={beat.bills > 1 ? "fail" : beat.bills === 1 ? "pass" : undefined}>
              <CountUp to={beat.bills} duration={500} />
            </span>
            <span className="ds-mono-label">Bills in the ledger</span>
          </div>
        </div>
        {caption && <div className="lf-journey-caption">{caption}</div>}
        {footer}
      </div>
    </div>
  );
}

export function shortKey(key: string): string {
  if (!key) return "";
  return key.length > 18 ? `${key.slice(0, 11)}…${key.slice(-4)}` : key;
}
