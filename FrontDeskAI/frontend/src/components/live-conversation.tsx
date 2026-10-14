"use client";

/**
 * Conversations live: the hero of the home screen.
 *
 * Real conversations from the server, replayed turn by turn the way they
 * happened - the customer's message slides in, the desk types, the reply
 * arrives with the engine and the tool it used. Then the next conversation.
 * Each one is also sent through the constellation below (`onIndex`).
 *
 * Pauses when off screen, under the pointer or with keyboard focus inside.
 * Under reduced motion every conversation is shown whole and nothing
 * advances on its own; the dashes still switch between them.
 */

import Link from "next/link";
import { useEffect, useMemo, useState, type CSSProperties } from "react";

import { useInView, useReducedMotion } from "@/design/motion";
import { ChannelMark, OutcomeChip } from "@/components/ui";
import { Typing } from "@/components/chat/turns";
import { clock, engineWord, outcomeOf, toolWord } from "@/lib/format";
import type { Conversation, Turn } from "@/lib/types";

const MAX_TURNS = 6;

function visible(conversation: Conversation): Turn[] {
  return conversation.turns.filter((turn) => turn.text).slice(-MAX_TURNS);
}

export function LiveConversation({
  conversations,
  onIndex,
}: {
  conversations: Conversation[];
  onIndex?: (index: number) => void;
}) {
  const reduce = useReducedMotion();
  const [index, setIndex] = useState(0);
  const [shown, setShown] = useState(0);
  const [typing, setTyping] = useState(false);
  const [held, setHeld] = useState(false);
  const [ref, onScreen] = useInView<HTMLDivElement>({ once: false, threshold: 0.1, rootMargin: "0px" });
  const count = conversations.length;
  const safe = count ? index % count : 0;
  const current = conversations[safe];
  const turns = useMemo(() => (current ? visible(current) : []), [current]);
  const paused = held || !onScreen || reduce;

  useEffect(() => {
    if (count) onIndex?.(safe);
  }, [safe, count, onIndex]);

  useEffect(() => {
    setShown(reduce ? turns.length : 0);
    setTyping(false);
  }, [safe, reduce, turns.length]);

  useEffect(() => {
    if (paused || !current) return;
    if (shown < turns.length) {
      const next = turns[shown];
      if (next.speaker !== "customer" && !typing) {
        const handle = window.setTimeout(() => setTyping(true), 380);
        return () => window.clearTimeout(handle);
      }
      const handle = window.setTimeout(
        () => {
          setTyping(false);
          setShown((value) => value + 1);
        },
        next.speaker === "customer" ? (shown === 0 ? 500 : 900) : 1100,
      );
      return () => window.clearTimeout(handle);
    }
    const handle = window.setTimeout(() => setIndex((value) => value + 1), 3400);
    return () => window.clearTimeout(handle);
  }, [paused, current, shown, turns, typing]);

  if (!current) return null;
  const outcome = outcomeOf(current);
  const lastDesk = [...current.turns].reverse().find((turn) => turn.speaker === "desk");
  const progress = turns.length ? Math.min(1, shown / turns.length) : 1;

  return (
    <div
      ref={ref}
      className="fd-live"
      onPointerEnter={() => setHeld(true)}
      onPointerLeave={() => setHeld(false)}
      onFocus={() => setHeld(true)}
      onBlur={() => setHeld(false)}
    >
      <div className="fd-live-head">
        <span className="ds-mono-label">Conversations live</span>
        <span className="fd-live-source">
          <span className="ds-live-dot" aria-hidden />
          from the server · {String(safe + 1).padStart(2, "0")}/{String(count).padStart(2, "0")}
        </span>
      </div>
      <div className="fd-live-meta">
        <OutcomeChip outcome={outcome} />
        <ChannelMark channel={current.channel} />
        <span className="fd-live-stamp">
          {clock(lastDesk?.at ?? current.turns[0]?.at)} · {current.reference}
        </span>
      </div>
      <p className="fd-live-title">{current.customer?.name ?? "A visitor, not verified yet"}</p>
      <p className="fd-live-intent">
        {current.intent_label || "Just started"} · {engineWord(lastDesk?.engine)} · {toolWord(lastDesk?.tool ?? "")}
      </p>

      <div className="fd-live-thread" aria-live="polite">
        {turns.slice(0, shown).map((turn) => (
          <div
            key={turn.id}
            className="fd-msg"
            data-side={turn.speaker === "customer" ? "customer" : "desk"}
            data-animate={reduce ? undefined : ""}
            data-variant={current.channel === "line" ? "line" : "web"}
          >
            {turn.speaker !== "customer" && (
              <span className="fd-desk-avatar" aria-hidden>
                <i />
              </span>
            )}
            <div style={{ minWidth: 0, flex: turn.speaker === "customer" ? undefined : 1 }}>
              <div className="fd-bubble" data-side={turn.speaker === "customer" ? "customer" : "desk"} data-refused={turn.refusal ? "" : undefined}>
                {turn.text}
              </div>
              <span className="fd-msg-meta" data-side={turn.speaker}>
                {clock(turn.at)}
                {turn.speaker !== "customer" && ` · ${engineWord(turn.engine)}${turn.tool ? ` · ${toolWord(turn.tool)}` : ""}`}
              </span>
            </div>
          </div>
        ))}
        {typing && <Typing variant={current.channel === "line" ? "line" : "web"} />}
      </div>

      <div className="fd-live-foot">
        <div className="fd-live-dashes" role="tablist" aria-label="Choose a conversation">
          {conversations.map((conversation, position) => (
            <button
              key={conversation.reference}
              type="button"
              role="tab"
              aria-selected={position === safe}
              aria-label={`Show conversation ${position + 1} of ${count}`}
              className="fd-live-dash"
              data-state={position === safe ? "active" : position < safe ? "done" : "waiting"}
              style={{ "--fd-progress": position === safe ? progress : 0 } as CSSProperties}
              onClick={() => setIndex(position)}
            >
              <i />
            </button>
          ))}
        </div>
        <Link href={`/desk?conversation=${encodeURIComponent(current.reference)}`} className="fd-live-link">
          Open on the desk →
        </Link>
      </div>
    </div>
  );
}
