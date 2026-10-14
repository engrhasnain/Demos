"use client";

/**
 * Who is asking. Six people, six different reaches: the same question gets
 * a different answer depending on who asks, and that is the product.
 */

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Meter } from "@/design/Meter";
import { Reveal } from "@/design/Reveal";
import { StatusChip } from "@/design/StatusChip";
import { ApiError, signInAs, type SignedInUser } from "@/lib/api";
import type { DemoPerson } from "@/lib/types";
import { initials, reaches, roleWords } from "@/lib/words";

function closedTo(role: string): string {
  if (reaches(role, "director")) return "Nothing is closed to this role.";
  if (reaches(role, "manager")) return "Whole-company figures need every account; this person has some.";
  return "Money owed and the weekly headline numbers are closed to this role.";
}

export function People({
  people,
  password,
  user,
  totalCustomers,
  then = "/ask",
}: {
  people: DemoPerson[];
  password: string;
  user: SignedInUser | null;
  totalCustomers: number;
  then?: string;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState("");
  const [trouble, setTrouble] = useState("");

  const choose = async (person: DemoPerson) => {
    setBusy(person.email);
    setTrouble("");
    try {
      await signInAs(person.email, password);
      router.push(then);
    } catch (error) {
      setTrouble(error instanceof ApiError ? error.message : String(error));
      setBusy("");
    }
  };

  return (
    <div>
      <ul className="oa-people">
        {people.map((person, index) => {
          const share = person.reach.everything ? 1 : Math.min(1, (person.reach.customers ?? 0) / Math.max(1, totalCustomers));
          const current = user?.email === person.email;
          return (
            <Reveal as="li" key={person.email} index={index} className="oa-person" data-current={current ? "" : undefined}>
              <div className="oa-person-head">
                <span className="oa-avatar" data-size="large">
                  {initials(person.name)}
                </span>
                <span style={{ minWidth: 0 }}>
                  <span className="oa-person-name">{person.name}</span>
                  <span className="ds-mono-label">{roleWords(person.role)}</span>
                </span>
                {current && (
                  <StatusChip tone="accent" pulse size="small">
                    Asking now
                  </StatusChip>
                )}
              </div>
              <div className="oa-person-reach">
                <div className="oa-person-reach-line">
                  <span>Sees</span>
                  <b>{person.reach.everything ? "every account" : person.reach.summary.replace(/\.$/, "")}</b>
                </div>
                <Meter
                  value={share}
                  size="small"
                  delay={index * 90}
                  tone={share >= 1 ? "accent" : share > 0.2 ? "info" : "warn"}
                  label={`${Math.round(share * 100)} per cent of accounts in reach`}
                />
                <p>{closedTo(person.role)}</p>
              </div>
              <button
                type="button"
                className="ds-btn"
                data-tone={current ? "secondary" : "primary"}
                data-full=""
                disabled={busy !== ""}
                onClick={() => void choose(person)}
              >
                {busy === person.email && <span className="ds-spinner" aria-hidden />}
                {current ? "Keep asking as" : "Ask as"} {person.name.split(" ")[0]}
                <span className="ds-btn-arrow" aria-hidden>
                  →
                </span>
              </button>
            </Reveal>
          );
        })}
      </ul>
      {trouble && <p style={{ marginTop: 12, color: "var(--ds-fail-ink)", fontSize: 13.5 }}>{trouble}</p>}
      <p className="ds-mono" style={{ marginTop: 14, fontSize: 12, color: "var(--ds-text-3)" }}>
        Every account uses the same password, {password}. The role and grants come from the database at sign-in, never
        from anything typed into a question.
      </p>
    </div>
  );
}
