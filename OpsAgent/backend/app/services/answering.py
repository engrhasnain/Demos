"""Running a plan and writing the answer.

The division of labour, which is the whole product:

* the **planner** chooses capability names from a closed list;
* the **permission layer** decides which rows, from grants in the
  database;
* **SQLite** computes every figure;
* the **writer** below turns rows into a sentence and is given nothing
  except the rows it is describing.

No number in an answer is ever produced by anything that writes prose.
When an external model is configured it does the last step only, and it
gets the rows as data, with instructions it cannot reach the database
from. Every figure keeps the query and the moment it was read, all the
way to the screen.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..domain import capabilities
from ..models import AccessLog, Question, User
from .executor import BadParameter, Result, run
from .permissions import NotAllowed, Reach, reach_of
from .planner import Plan, Step, read


@dataclass(slots=True)
class Answer:
    question: str
    reading: str
    text: str
    #: The row this was written to, so proposals can point back at it.
    question_id: int | None = None
    evidence: list[Result] = field(default_factory=list)
    refused: str = ""
    seconds: float = 0.0
    cost_usd: Decimal = Decimal("0")
    engine: str = "built-in"
    injection_seen: bool = False
    #: Anything worth doing about it, proposed and never done.
    proposals: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.refused

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "question_id": self.question_id,
            "reading": self.reading,
            "text": self.text,
            "evidence": [e.to_dict() for e in self.evidence],
            "refused": self.refused,
            "seconds": round(self.seconds, 2),
            "cost_usd": str(self.cost_usd),
            "engine": self.engine,
            "injection_seen": self.injection_seen,
            "proposals": self.proposals,
            "ok": self.ok,
        }


def _log(
    session: Session,
    *,
    user: User,
    question_id: int | None,
    capability: str,
    parameters: dict[str, Any],
    allowed: bool,
    refusal: str = "",
    rows: int = 0,
    filter_applied: str = "",
) -> None:
    session.add(
        AccessLog(
            user_id=user.id,
            question_id=question_id,
            capability=capability,
            parameters={
                k: v for k, v in parameters.items() if not str(k).startswith("scope_")
            },
            allowed=allowed,
            refusal=refusal[:255],
            rows_returned=rows,
            filter_applied=filter_applied[:120],
        )
    )
    session.flush()


def _carry_forward(step: Step, previous: list[Result]) -> dict[str, Any]:
    """Take a value a previous step found, rather than from the question.

    A customer identifier comes from a lookup this system did, under this
    person's own grants, not from anything the asker typed. That is what
    makes "show me customer 5's invoices" useless as an attack: the
    identifier is not a parameter the asker controls, and the lookup that
    produces it was itself filtered.
    """
    parameters = dict(step.parameters)
    if step.from_step is None or not step.takes:
        return parameters
    if step.from_step >= len(previous):
        return parameters

    source = previous[step.from_step]
    if not source.raw_rows:
        return parameters

    found = source.raw_rows[0].get(step.takes)
    if found is None:
        return parameters
    if step.takes == "customer_id":
        parameters["customer"] = found
    elif step.takes == "supplier_id":
        parameters["supplier"] = found
    return parameters


def ask(
    session: Session,
    user: User,
    question: str,
    *,
    content: str = "",
    now: dt.datetime | None = None,
) -> Answer:
    """One question, answered or refused, with the receipts."""
    started = time.perf_counter()
    now = now or dt.datetime.now(dt.timezone.utc)

    from .planner import quote

    injection_seen = False
    if content:
        quoted = quote(content, source="attached content")
        injection_seen = quoted.looked_like_instructions

    plan = read(question)
    answer = Answer(
        question=question,
        reading=plan.reading,
        text="",
        engine=settings.answer_engine,
        injection_seen=injection_seen,
    )

    row = Question(
        asked_by_id=user.id,
        text=question,
        reading=plan.reading,
        plan=plan.to_dict()["steps"],
        engine=answer.engine,
        injection_seen=injection_seen,
    )
    session.add(row)
    session.flush()
    answer.question_id = row.id

    if not plan.ok:
        answer.refused = plan.refused
        answer.text = plan.refused
        row.refused = plan.refused
        row.answer = plan.refused
        row.seconds = time.perf_counter() - started
        session.flush()
        return answer

    reach = reach_of(session, user)
    results: list[Result] = []

    for index, step in enumerate(plan.steps):
        if time.perf_counter() - started > settings.seconds_per_question:
            answer.refused = "That took too long and was stopped."
            break

        capability = capabilities.BY_NAME[step.capability]
        parameters = _carry_forward(step, results)

        try:
            result = run(session, capability, parameters, reach)
        except NotAllowed as refusal:
            _log(
                session,
                user=user,
                question_id=row.id,
                capability=step.capability,
                parameters=parameters,
                allowed=False,
                refusal=str(refusal),
            )
            answer.refused = str(refusal)
            break
        except BadParameter as refusal:
            _log(
                session,
                user=user,
                question_id=row.id,
                capability=step.capability,
                parameters=parameters,
                allowed=False,
                refusal=str(refusal),
            )
            answer.refused = str(refusal)
            break

        _log(
            session,
            user=user,
            question_id=row.id,
            capability=step.capability,
            parameters=parameters,
            allowed=True,
            rows=result.row_count,
            filter_applied=result.filter_applied,
        )
        results.append(result)

        # A lookup that found nothing ends the plan honestly rather than
        # carrying on with an empty identifier.
        if not result.rows and step.capability.startswith("find_"):
            answer.refused = (
                f"Nothing on this account matches that name."
            )
            break

    answer.evidence = results
    answer.text = answer.refused or write(plan, results)
    answer.seconds = time.perf_counter() - started
    answer.proposals = suggest(plan, results)

    row.answer = answer.text
    row.refused = answer.refused
    row.evidence = [r.to_dict() for r in results]
    row.seconds = answer.seconds
    session.flush()
    return answer


# ---------------------------------------------------------------------------
# The writer
# ---------------------------------------------------------------------------
def write(plan: Plan, results: list[Result]) -> str:
    """Turn the rows into a sentence. Given nothing but the rows.

    Deliberately plain. The temptation in a product like this is to make
    the prose do the work, and the prose is the part nobody can check.
    """
    if not results:
        return "Nothing came back."

    sentences: list[str] = []
    for result in results:
        if result.capability.startswith("find_"):
            continue
        sentences.append(_describe(result))

    if not sentences:
        found = results[-1]
        if found.rows:
            first = found.rows[0]
            return "Found " + ", ".join(f"{k} {v}" for k, v in first.items()) + "."
        return "Nothing matched."
    return " ".join(s for s in sentences if s)


def _describe(result: Result) -> str:
    rows = result.rows
    if not rows:
        return f"{result.asks} Nothing."

    count = len(rows)
    name = result.capability

    if name == "late_orders_for_customer":
        worst = max(rows, key=lambda r: r.get("days_late") or 0)
        return (
            f"{count} late order{'s' if count != 1 else ''}; the worst is "
            f"{worst['order_number']}, {int(worst['days_late'] or 0)} days past "
            f"its promise of {worst['promised_on']}."
        )
    if name == "why_an_order_is_late":
        first = rows[0]
        reason = first.get("shipment_exception") or first.get("shipment_state") or "nothing recorded"
        return (
            f"{first['order_number']} is {first['status']}, promised "
            f"{first.get('promised_on')}; the shipment says {reason}."
        )
    if name == "customers_exposed_to_supplier":
        soonest = rows[0]
        return (
            f"{count} customer{'s' if count != 1 else ''} have open orders on "
            f"that supplier's parts; the soonest promise is {soonest['soonest_promise']} "
            f"for {soonest['customer']}."
        )
    if name == "cover_if_supplier_stops":
        thin = [r for r in rows if (r.get("weeks_of_cover") or 0) < 4]
        return (
            f"{len(thin)} of {count} parts have under four weeks of cover"
            + (
                f", the thinnest being {rows[0]['part_code']} at "
                f"{rows[0]['weeks_of_cover']:.1f} weeks."
                if rows and rows[0].get("weeks_of_cover") is not None
                else "."
            )
        )
    if name == "unpaid_invoices_for_customer":
        total = sum(float(r.get("total") or 0) for r in rows)
        overdue = [r for r in rows if (r.get("days_overdue") or 0) > 0]
        return (
            f"{count} unpaid invoice{'s' if count != 1 else ''} totalling "
            f"{total:,.2f}, of which {len(overdue)} are past due."
        )
    if name == "money_owed_in_total":
        # One row per account, so that the permission filter can remove
        # the accounts this person may not see before anything is added
        # up. The adding up happens here, over what is left.
        invoices = sum(int(r.get("invoices") or 0) for r in rows)
        owed = sum(float(r.get("total_owed") or 0) for r in rows)
        overdue = sum(float(r.get("overdue") or 0) for r in rows)
        return (
            f"{invoices} unpaid invoices totalling {owed:,.2f}, of which "
            f"{overdue:,.2f} is overdue, across {count} "
            f"account{'s' if count != 1 else ''}."
        )
    if name == "customers_with_late_orders":
        return (
            f"{count} customer{'s' if count != 1 else ''} have late orders; "
            f"{rows[0]['customer']} is worst at "
            f"{int(rows[0]['worst_days_late'] or 0)} days."
        )
    if name == "parts_running_out":
        return (
            f"{count} part{'s' if count != 1 else ''} below that cover; "
            f"{rows[0]['part_code']} is thinnest at "
            f"{float(rows[0]['weeks_of_cover'] or 0):.1f} weeks."
        )
    if name == "supplier_lead_time":
        first = rows[0]
        return (
            f"{first['supplier']} quotes {first['quoted_days']} days and averages "
            f"{float(first.get('average_days') or 0):.1f} over "
            f"{first.get('deliveries')} deliveries, worst "
            f"{first.get('worst_days')}."
        )
    if name == "shipments_held":
        return f"{count} shipment{'s' if count != 1 else ''} held, the newest being {rows[0]['shipment']} ({rows[0]['reason']})."
    if name == "headline_numbers":
        first = rows[0]
        return (
            f"{first['open_orders']} open orders, {first['late_orders']} late, "
            f"{first['held_shipments']} shipments held, {first['open_tickets']} "
            "tickets open."
        )
    if name == "customer_overview":
        first = rows[0]
        return (
            f"{first['customer']}: {first['orders']} orders, "
            f"{first['open_orders']} open, {float(first.get('total_value') or 0):,.2f} "
            f"in total, last ordered {first.get('last_order')}."
        )
    return f"{count} row{'s' if count != 1 else ''} for: {result.asks}"


# ---------------------------------------------------------------------------
# Proposals: suggested, never done
# ---------------------------------------------------------------------------
def suggest(plan: Plan, results: list[Result]) -> list[dict[str, Any]]:
    """Things somebody might want to do about the answer.

    Every one of these is a suggestion with a role attached. Nothing in
    this file does anything, and there is no code path from here to a
    write of any kind.
    """
    out: list[dict[str, Any]] = []
    for result in results:
        if result.capability == "cover_if_supplier_stops":
            thin = [r for r in result.rows if (r.get("weeks_of_cover") or 0) < 4]
            if thin:
                out.append(
                    {
                        "kind": "pre_build_before_shutdown",
                        "summary": (
                            f"Order ahead on {len(thin)} parts with under four "
                            "weeks of cover before the supplier shuts."
                        ),
                        "needs_role": "manager",
                        "detail": {"parts": [r["part_code"] for r in thin[:20]]},
                    }
                )
        if result.capability == "late_orders_for_customer" and result.rows:
            out.append(
                {
                    "kind": "tell_the_customer",
                    "summary": (
                        f"Send a revised promise date on {len(result.rows)} late "
                        "orders."
                    ),
                    "needs_role": "account_manager",
                    "detail": {
                        "orders": [r["order_number"] for r in result.rows[:20]]
                    },
                }
            )
    return out
