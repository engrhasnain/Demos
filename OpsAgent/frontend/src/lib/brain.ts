/**
 * Turning a person's role and grants into the operations brain.
 *
 * Which systems are open, which are closed, and how much of each one this
 * person can see, from the same facts the server uses: the role's rank, the
 * whole-company rule and the number of accounts and suppliers granted.
 */

import type { BrainDomain, BrainStep } from "@/components/ops-brain";
import type { Reach } from "@/lib/api";
import type { Answer, PlanStep } from "@/lib/types";
import { CAPABILITIES, DOMAINS, domainsOf, outcomeOf, reaches, type DomainId } from "@/lib/words";

export type Totals = { customers: number; suppliers: number };

export function capabilityAllowed(name: string, role: string | null | undefined, reach?: Reach | null): boolean {
  const known = CAPABILITIES[name];
  if (!known) return false;
  if (!role) return true;
  if (!reaches(role, known.needs)) return false;
  if (name === "headline_numbers" && reach && !reach.everything) return false;
  return true;
}

export function brainDomains(
  role: string | null | undefined,
  reach: Reach | null | undefined,
  totals: Totals,
): BrainDomain[] {
  return DOMAINS.map((domain) => {
    const names = Object.keys(CAPABILITIES).filter((name) => CAPABILITIES[name].domains[0] === domain.id);
    const capabilities = names.map((name) => ({ name, allowed: capabilityAllowed(name, role, reach) }));
    const closed = Boolean(role) && capabilities.every((item) => !item.allowed);
    const bySupplier = domain.id === "stock";
    let share = 1;
    let sub = `${names.length} reviewed ${names.length === 1 ? "query" : "queries"}`;
    if (role && reach && !reach.everything) {
      const have = bySupplier ? reach.suppliers ?? 0 : reach.customers ?? 0;
      const total = Math.max(1, bySupplier ? totals.suppliers : totals.customers);
      share = have > 0 ? Math.max(0.17, Math.min(1, have / total)) : 0;
      sub = have > 0 ? `${have} of ${total} ${bySupplier ? "suppliers" : "accounts"}` : `no ${bySupplier ? "suppliers" : "accounts"} granted`;
    } else if (role && reach?.everything) {
      sub = "every record";
    }
    if (closed) sub = "closed to this role";
    return { id: domain.id, label: domain.label, short: domain.short, sub, closed, reach: closed ? 0 : share, capabilities };
  });
}

/**
 * The steps to animate for an answer: every query that ran, and the step the
 * role check stopped, if there was one.
 */
export function brainSteps(answer: Answer, plan: PlanStep[] | null): BrainStep[] {
  const ran: BrainStep[] = answer.evidence.map((step) => ({
    capability: step.capability,
    domain: domainsOf(step.capability)[0],
  }));
  if (answer.ok || !plan) return ran;
  const outcome = outcomeOf(answer.refused);
  const next = plan[answer.evidence.length];
  if (outcome === "not-permitted" && next && /role|whole-company/i.test(answer.refused)) {
    ran.push({ capability: next.capability, domain: domainsOf(next.capability)[0], blocked: true });
  }
  return ran;
}

export function stepsFromPlan(plan: PlanStep[], ranCount: number, refused: string): BrainStep[] {
  return plan.slice(0, ranCount + (refused && /role|whole-company/i.test(refused) ? 1 : 0)).map((step, index) => ({
    capability: step.capability,
    domain: domainsOf(step.capability)[0] as DomainId,
    blocked: index >= ranCount,
  }));
}
