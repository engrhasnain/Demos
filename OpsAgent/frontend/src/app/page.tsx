"use client";

/**
 * Overview: the operations brain, live.
 *
 * On a fresh install it is the guided first run. After that it is the brain
 * with the questions people have actually asked travelling through it, the
 * counts behind the business (each one opens), and the six people who can
 * ask, so switching who is asking is one press away.
 */

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { FirstRun } from "@/components/first-run";
import { LiveQuestions, useLiveQuestions, type LiveEntry } from "@/components/live-questions";
import { CommandBar, SUGGESTED, SystemsRail } from "@/components/command";
import { OpsBrain, type BrainHandle, type BrainStep } from "@/components/ops-brain";
import { People } from "@/components/people";
import { usePeople } from "@/components/shell";
import { counted, Figure } from "@/components/trace";
import { LiveFeedCard, type FeedItem } from "@/design/LiveFeedCard";
import { Reveal } from "@/design/Reveal";
import { StepRail } from "@/design/StepRail";
import { Band, Card, LinkButton } from "@/design/Surface";
import { brainDomains } from "@/lib/brain";
import { useLoad, useSession } from "@/lib/session";
import type { DemoPerson, DemoState, Health } from "@/lib/types";
import { grouped, initials, roleWords } from "@/lib/words";

const PIPELINE = [
  { key: "question", label: "The question", sub: "in words, as typed" },
  { key: "planner", label: "The planner", sub: "picks from 19 reviewed queries" },
  { key: "role", label: "Role check", sub: "may this person run it at all" },
  { key: "filter", label: "Row filter", sub: "only the rows their grants allow" },
  { key: "database", label: "The database", sub: "computes every figure" },
  { key: "writer", label: "The writer", sub: "is handed only the rows" },
];

const PROPERTIES = [
  {
    title: "A fooled planner reaches nothing extra",
    body: "The worst a plan can name is one of the reviewed queries. An unknown name is refused; a known one runs under the asker's own role check and row filter, neither of which comes from the plan.",
  },
  {
    title: "Permissions cannot be forgotten",
    body: "The filter is attached by the permission layer, not by whoever wrote the query. A query that reads somebody's data and declares no scope will not load.",
  },
  {
    title: "No grant means nothing",
    body: "An account with no grants gets a filter that matches nothing, never an unfiltered query.",
  },
  {
    title: "Nothing is ever written",
    body: "Every query is checked for writes when the catalogue loads. Approving a proposal records a decision and stops there.",
  },
];

export default function Overview() {
  const { user, checked } = useSession();
  const { data: state, reload: reloadState } = useLoad<DemoState>("/api/demo/state");
  const { data: health } = useLoad<Health>("/api/health", [user?.email]);
  const [firstRun, setFirstRun] = useState<boolean | null>(null);
  const peopleData = usePeople();
  const [peopleKey, setPeopleKey] = useState(0);
  const { data: peopleFresh } = useLoad<{ people: DemoPerson[]; password: string }>(
    peopleKey ? "/api/demo/people" : null,
    [peopleKey],
  );
  const people = peopleFresh ?? peopleData;

  useEffect(() => {
    if (state && firstRun === null) setFirstRun(!state.loaded);
  }, [state, firstRun]);

  useEffect(() => {
    if (!checked || typeof window === "undefined") return;
    if (new URLSearchParams(window.location.search).get("choose")) {
      window.setTimeout(() => document.getElementById("who")?.scrollIntoView({ behavior: "smooth", block: "start" }), 500);
    }
  }, [checked, firstRun]);

  const finishFirstRun = useCallback(() => {
    reloadState();
    setPeopleKey((value) => value + 1);
    setFirstRun(false);
    window.setTimeout(() => document.getElementById("who")?.scrollIntoView({ behavior: "smooth", block: "start" }), 400);
  }, [reloadState]);

  if (!state || firstRun === null) {
    return (
      <Band top>
        <div className="oa-hero" aria-busy="true" />
      </Band>
    );
  }

  return (
    <>
      {firstRun ? (
        <FirstRun onFinished={finishFirstRun} />
      ) : (
        <Hero user={user} state={state} health={health} people={people?.people ?? []} />
      )}

      {state.loaded && !firstRun && (
        <div className="ds-work">
          <section id="who" className="oa-section">
            <Reveal>
              <p className="ds-mono-label">Who is asking</p>
              <h2 className="ds-title oa-section-title">Same question, different answer, depending on who asks.</h2>
              <p className="oa-section-lede">
                The role decides which questions exist for a person. Their grants decide which rows. Neither comes from
                anything typed into the box. Pick somebody and ask.
              </p>
            </Reveal>
            {people ? (
              <People people={people.people} password={people.password} user={user} totalCustomers={state.customers} />
            ) : null}
          </section>

          <section className="oa-section">
            <Reveal>
              <p className="ds-mono-label">How a question is answered</p>
              <h2 className="ds-title oa-section-title">The model chooses from a closed list and writes the sentence. Nothing else.</h2>
            </Reveal>
            <Reveal index={1}>
              <Card>
                <div className="oa-pipeline">
                  <StepRail steps={PIPELINE} current={PIPELINE.length - 1} label="How a question is answered" />
                </div>
              </Card>
            </Reveal>
            <div className="oa-properties">
              {PROPERTIES.map((item, index) => (
                <Reveal key={item.title} index={index + 2}>
                  <Card className="oa-property" title={item.title}>
                    <p>{item.body}</p>
                  </Card>
                </Reveal>
              ))}
            </div>
          </section>
        </div>
      )}
    </>
  );
}

function Hero({
  user,
  state,
  health,
  people,
}: {
  user: ReturnType<typeof useSession>["user"];
  state: DemoState;
  health: Health | null;
  people: DemoPerson[];
}) {
  const router = useRouter();
  const brain = useRef<BrainHandle>(null);
  const [question, setQuestion] = useState("");
  const [last, setLast] = useState<BrainStep[]>([]);
  const domains = useMemo(
    () => brainDomains(user?.role ?? null, user?.reach ?? null, { customers: state.customers, suppliers: state.suppliers }),
    [user?.role, user?.reach, state.customers, state.suppliers],
  );
  const entries = useLiveQuestions(user, people, health?.engine ?? "built-in");
  const onShow = useCallback((entry: LiveEntry) => {
    setLast(entry.steps);
    if (entry.steps.length) brain.current?.play(entry.steps, { gap: 420 });
  }, []);

  const peopleFeed: FeedItem[] = people.map((person) => ({
    key: person.email,
    chip: { label: roleWords(person.role), tone: person.reach.everything ? "accent" : "neutral" },
    stamp: person.reach.everything ? "every account" : person.reach.summary.replace(/\.$/, ""),
    title: person.name,
    body: person.reach.everything
      ? "Sees every account and every supplier. Whole-company figures are open."
      : "Sees only the accounts granted to them. Questions outside that reach come back refused or empty.",
    href: "/?choose=1",
  }));

  const asked = health?.questions_asked ?? 0;
  const stats = [
    {
      label: "Questions answered",
      value: asked,
      trace: counted(
        "Questions answered so far",
        grouped(asked),
        "count of every question in the question log, answered or refused",
        [{ label: "Question log", value: grouped(asked), source: "Every question is logged with who asked it", sourceKind: "Database" }],
      ),
    },
    {
      label: "Reviewed queries",
      value: health?.capabilities ?? 19,
      trace: counted(
        "Reviewed queries",
        String(health?.capabilities ?? 19),
        "count of queries in the catalogue; nothing else can run",
        [{ label: "Catalogue", value: String(health?.capabilities ?? 19), source: "Written and reviewed by a person, checked when the server starts", sourceKind: "Catalogue" }],
      ),
    },
    {
      label: "Customers",
      value: state.customers,
      trace: counted("Customers", grouped(state.customers), "count of customer accounts", [
        { label: "Customers", value: grouped(state.customers), source: "Hengtai's customer records", sourceKind: "Database" },
      ]),
    },
    {
      label: "Orders",
      value: state.orders,
      trace: counted("Orders", grouped(state.orders), "count of orders, open and closed", [
        { label: "Orders", value: grouped(state.orders), source: "Hengtai's orders", sourceKind: "Database" },
      ]),
    },
  ];

  const go = (text: string) => {
    if (!user) {
      document.getElementById("who")?.scrollIntoView({ behavior: "smooth", block: "start" });
      return;
    }
    router.push(`/ask?q=${encodeURIComponent(text)}`);
  };

  return (
    <Band top>
      <div className="oa-cc">
        <div className="oa-cc-head">
          <Reveal y={24}>
            <span className="ds-eyebrow">
              <span className="ds-live-dot" data-tone="accent" aria-hidden />
              Command centre <span className="ds-eyebrow-sep">·</span> five systems, one question
            </span>
          </Reveal>
          <Reveal index={1} y={36}>
            <h1 className="ds-display oa-cc-title">
              Ask the business. <span className="oa-light ds-accent-text">See where every number came from.</span>
            </h1>
          </Reveal>
          <Reveal index={2} y={28}>
            <CommandBar
              value={question}
              onChange={setQuestion}
              onSubmit={go}
              role={user?.role}
              reach={user?.reach}
              suggestions={SUGGESTED.slice(0, 4)}
              who={
                user ? (
                  <>
                    <span className="oa-avatar" data-size="small">
                      {initials(user.name)}
                    </span>
                    <span>{user.role_label}</span>
                  </>
                ) : (
                  <span>Choose who is asking</span>
                )
              }
            />
          </Reveal>
        </div>

        <div className="oa-cc-grid">
          <Reveal className="oa-cc-left" index={3} from="left">
            <SystemsRail domains={domains} last={last} title={user ? `Systems · as ${user.name.split(" ")[0]}` : "Systems"} />
            <div className="oa-rail-panel oa-cc-stats">
              <p className="oa-rail-title">
                <span className="ds-mono-label">The business, counted</span>
              </p>
              <div className="oa-cc-stat-grid">
                {stats.map((stat, index) => (
                  <div key={stat.label}>
                    <span className="ds-stat-value" data-tone={index === 0 ? "accent" : undefined}>
                      <Figure value={grouped(stat.value)} count={stat.value} content={stat.trace} />
                    </span>
                    <span className="ds-mono-label ds-stat-label">{stat.label}</span>
                  </div>
                ))}
              </div>
            </div>
          </Reveal>

          <div className="oa-cc-map">
            <span className="oa-corner" data-at="tl" aria-hidden />
            <span className="oa-corner" data-at="tr" aria-hidden />
            <span className="oa-corner" data-at="bl" aria-hidden />
            <span className="oa-corner" data-at="br" aria-hidden />
            <span className="oa-map-label" data-at="top">
              Operations map · {user ? `${user.role_label.toLowerCase()} view` : "every system"}
            </span>
            <span className="oa-map-label" data-at="bottom">
              Open ring: reachable · closed ring: refused before anything runs
            </span>
            <div className="oa-cc-canvas">
              <OpsBrain
                ref={brain}
                domains={domains}
                label={
                  user
                    ? `The five systems as ${user.name} sees them: ${domains.filter((d) => d.closed).length} closed to this role`
                    : "The five systems OpsAgent reads across"
                }
              />
            </div>
          </div>

          <Reveal className="oa-cc-right" index={4}>
            {user && entries && entries.length > 0 ? (
              <LiveQuestions entries={entries} onShow={onShow} source={`as seen by ${user.name.split(" ")[0]}`} />
            ) : user && entries && entries.length === 0 ? (
              <div className="ds-feed oa-feed-empty">
                <div className="ds-feed-head">
                  <span className="ds-mono-label ds-feed-title">Questions answered live</span>
                  <span className="ds-feed-source">
                    <span className="ds-live-dot" aria-hidden />
                    waiting
                  </span>
                </div>
                <div style={{ padding: "16px 18px 18px" }}>
                  <p style={{ margin: 0, fontWeight: 600, fontSize: 16 }}>Nothing asked yet as {user.name}.</p>
                  <p style={{ margin: "6px 0 12px", fontSize: 13.5, color: "var(--ds-ink-muted)" }}>
                    Ask the first question and it travels across the map.
                  </p>
                  <Link href="/ask" className="ds-btn" data-tone="primary" data-size="small">
                    Ask a question
                  </Link>
                </div>
              </div>
            ) : !user && peopleFeed.length ? (
              <LiveFeedCard title="People who can ask" source="six roles, six reaches" items={peopleFeed} interval={4200} />
            ) : null}
            <div className="oa-cc-actions">
              {user ? (
                <>
                  <LinkButton href="/ask" tone="primary" arrow>
                    Open the ask view
                  </LinkButton>
                  <LinkButton href="/catalogue" tone="ink">
                    Reviewed queries
                  </LinkButton>
                </>
              ) : (
                <LinkButton href="/?choose=1" tone="primary" arrow>
                  Choose who is asking
                </LinkButton>
              )}
            </div>
          </Reveal>
        </div>
      </div>
    </Band>
  );
}
