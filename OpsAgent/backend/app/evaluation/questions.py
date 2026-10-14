"""The labelled set: questions whose right answer is known independently.

The temptation in evaluating something like this is to ask it a question
and have a person read the reply and nod. That measures the reader.

Every case below instead works out the right answer a second time, with
ORM queries written here, against the same database but not through the
capability catalogue. Then it checks the figures the product produced
against the figures this file produced. If somebody edits a capability's
SQL and gets it subtly wrong, the two disagree and the case fails — which
is the only kind of regression test worth having over a system whose
whole job is to be trusted with numbers.

Three of the cases expect a refusal. A product that answers everything
is a product that invents things, and "I do not have a way to answer
that" is a correct answer that has to be measured like any other.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import (
    Customer,
    Invoice,
    Order,
    OrderLine,
    Part,
    Shipment,
    Supplier,
    Ticket,
)


@dataclass(slots=True)
class Case:
    question: str
    #: What this case is really checking, for the report.
    about: str
    #: Given the answer, is it right? Compares against figures worked out
    #: in this file, not against a string somebody typed.
    check: Callable[[Any], bool] = lambda answer: True
    expect_refusal: bool = False
    #: The capabilities it ought to have gone through, in order.
    expect_steps: tuple[str, ...] = ()


def _today(session: Session) -> dt.date:
    """What SQLite means by ``date('now')``, which is UTC."""
    return dt.datetime.now(dt.timezone.utc).date()


def _steps(answer: Any) -> list[str]:
    return [step.capability for step in answer.evidence]


def _rows(answer: Any, capability: str) -> list[dict[str, Any]]:
    for step in answer.evidence:
        if step.capability == capability:
            return step.rows
    return []


def _close(left: float, right: float, tolerance: float = 0.51) -> bool:
    return abs(float(left) - float(right)) <= tolerance


def suite(session: Session) -> list[Case]:
    """Build the set against whatever is actually in the database."""
    today = _today(session)
    cases: list[Case] = []

    # ------------------------------------------------------------------
    # The headline. Four numbers, each recomputed here.
    # ------------------------------------------------------------------
    closed = ("delivered", "cancelled")
    open_orders = session.scalar(
        select(func.count(Order.id)).where(Order.status.notin_(closed))
    )
    late_orders = session.scalar(
        select(func.count(Order.id)).where(
            Order.promised_on < today, Order.status.notin_(closed)
        )
    )
    held = session.scalar(
        select(func.count(Shipment.id)).where(Shipment.exception_kind != "")
    )
    open_tickets = session.scalar(
        select(func.count(Ticket.id)).where(Ticket.status == "open")
    )

    def headline_right(answer: Any) -> bool:
        rows = _rows(answer, "headline_numbers")
        if len(rows) != 1:
            return False
        row = rows[0]
        return (
            row["open_orders"] == open_orders
            and row["late_orders"] == late_orders
            and row["held_shipments"] == held
            and row["open_tickets"] == open_tickets
        )

    cases.append(
        Case(
            question="How are we doing this week?",
            about="the four headline counts, each recomputed",
            check=headline_right,
            expect_steps=("headline_numbers",),
        )
    )

    # ------------------------------------------------------------------
    # One customer's late orders, through a two-step plan.
    # ------------------------------------------------------------------
    worst = session.execute(
        select(Order.customer_id, func.count(Order.id).label("n"))
        .where(Order.promised_on < today, Order.status.notin_(closed))
        .group_by(Order.customer_id)
        .order_by(func.count(Order.id).desc())
        .limit(1)
    ).first()

    if worst:
        customer = session.get(Customer, worst.customer_id)
        expected_late = worst.n

        def late_right(answer: Any, expected: int = expected_late) -> bool:
            return len(_rows(answer, "late_orders_for_customer")) == expected

        cases.append(
            Case(
                question=f'Which of "{customer.name}" orders are late?',
                about="a name resolved to an account, then that account's late orders",
                check=late_right,
                expect_steps=("find_customer", "late_orders_for_customer"),
            )
        )

        def overview_right(answer: Any, cid: int = customer.id) -> bool:
            rows = _rows(answer, "customer_overview")
            if len(rows) != 1:
                return False
            total = session.scalar(
                select(func.count(Order.id)).where(Order.customer_id == cid)
            )
            return rows[0]["orders"] == total

        cases.append(
            Case(
                question=f'How is "{customer.name}" doing?',
                about="one account's overall position",
                check=overview_right,
                expect_steps=("find_customer", "customer_overview"),
            )
        )

    # ------------------------------------------------------------------
    # One order, and what is holding it.
    # ------------------------------------------------------------------
    late_order = session.scalar(
        select(Order)
        .where(Order.promised_on < today, Order.status.notin_(closed))
        .order_by(Order.promised_on)
        .limit(1)
    )
    if late_order:

        def order_right(answer: Any, number: str = late_order.number) -> bool:
            rows = _rows(answer, "why_an_order_is_late")
            return len(rows) == 1 and rows[0]["order_number"] == number

        cases.append(
            Case(
                question=f"Why is {late_order.number} late?",
                about="one order, with whatever the shipment says about it",
                check=order_right,
                expect_steps=("why_an_order_is_late",),
            )
        )

    # ------------------------------------------------------------------
    # Money. The figure a finance director would check by hand.
    # ------------------------------------------------------------------
    unpaid = session.scalars(select(Invoice).where(Invoice.paid_on.is_(None))).all()
    owed = sum(float(i.total) for i in unpaid)
    overdue = sum(float(i.total) for i in unpaid if i.due_on < today)

    def owed_right(answer: Any) -> bool:
        rows = _rows(answer, "money_owed_in_total")
        if not rows:
            return False
        count = sum(int(r["invoices"]) for r in rows)
        total = sum(float(r["total_owed"]) for r in rows)
        late_money = sum(float(r["overdue"]) for r in rows)
        return (
            count == len(unpaid)
            and _close(total, owed, 1.0)
            and _close(late_money, overdue, 1.0)
        )

    cases.append(
        Case(
            question="What is owed altogether?",
            about="the receivables total, added up from rows the asker may see",
            check=owed_right,
            expect_steps=("money_owed_in_total",),
        )
    )

    owing = session.execute(
        select(Invoice.customer_id, func.count(Invoice.id).label("n"))
        .where(Invoice.paid_on.is_(None))
        .group_by(Invoice.customer_id)
        .order_by(func.count(Invoice.id).desc())
        .limit(1)
    ).first()
    if owing:
        debtor = session.get(Customer, owing.customer_id)

        def debt_right(answer: Any, expected: int = owing.n) -> bool:
            return len(_rows(answer, "unpaid_invoices_for_customer")) == expected

        cases.append(
            Case(
                question=f'What does "{debtor.name}" owe?',
                about="one account's unpaid invoices",
                check=debt_right,
                expect_steps=("find_customer", "unpaid_invoices_for_customer"),
            )
        )

    # ------------------------------------------------------------------
    # Stock.
    # ------------------------------------------------------------------
    def running_out_right(answer: Any, weeks: int = 4) -> bool:
        rows = _rows(answer, "parts_running_out")
        expected = [
            p
            for p in session.scalars(select(Part).where(Part.weekly_demand > 0))
            if p.on_hand / p.weekly_demand < weeks
        ]
        return len(rows) == len(expected)

    cases.append(
        Case(
            question="Which parts are running out within 4 weeks?",
            about="cover, against a threshold taken from the question",
            check=running_out_right,
            expect_steps=("parts_running_out",),
        )
    )

    def two_weeks_right(answer: Any) -> bool:
        rows = _rows(answer, "parts_running_out")
        expected = [
            p
            for p in session.scalars(select(Part).where(Part.weekly_demand > 0))
            if p.on_hand / p.weekly_demand < 2
        ]
        return len(rows) == len(expected)

    cases.append(
        Case(
            question="Which parts have less than 2 weeks of cover?",
            about="the same question with a different number in it",
            check=two_weeks_right,
            expect_steps=("parts_running_out",),
        )
    )

    part = session.scalar(select(Part).order_by(Part.code).limit(1))
    if part:

        def stock_right(answer: Any, code: str = part.code, on_hand: int = part.on_hand) -> bool:
            rows = _rows(answer, "stock_for_part")
            return (
                len(rows) == 1
                and rows[0]["part_code"] == code
                and rows[0]["on_hand"] == on_hand
            )

        cases.append(
            Case(
                question=f"How much {part.code} is there?",
                about="one part's position, by its code",
                check=stock_right,
                expect_steps=("stock_for_part",),
            )
        )

        def waiting_right(answer: Any, code: str = part.code) -> bool:
            rows = _rows(answer, "orders_waiting_on_a_part")
            expected = session.scalar(
                select(func.count(OrderLine.id))
                .join(Order, Order.id == OrderLine.order_id)
                .where(OrderLine.part_code == code, Order.status.notin_(closed))
            )
            return len(rows) == expected

        cases.append(
            Case(
                question=f"Which orders are waiting on {part.code}?",
                about="open orders that need one part",
                check=waiting_right,
                expect_steps=("orders_waiting_on_a_part",),
            )
        )

    # ------------------------------------------------------------------
    # Suppliers, including the three-step one.
    # ------------------------------------------------------------------
    supplier = session.scalar(
        select(Supplier).where(Supplier.shutdown_from.is_not(None)).limit(1)
    )
    if supplier:

        def shutdown_right(answer: Any) -> bool:
            names = _steps(answer)
            return names == [
                "find_supplier",
                "customers_exposed_to_supplier",
                "cover_if_supplier_stops",
            ]

        cases.append(
            Case(
                question=f'What happens if "{supplier.name}" shuts down?',
                about="three steps: resolve the supplier, who is hit, how much cover",
                check=shutdown_right,
                expect_steps=(
                    "find_supplier",
                    "customers_exposed_to_supplier",
                    "cover_if_supplier_stops",
                ),
            )
        )

        def lead_time_right(answer: Any, quoted: int = supplier.quoted_lead_time_days) -> bool:
            rows = _rows(answer, "supplier_lead_time")
            return len(rows) == 1 and rows[0]["quoted_days"] == quoted

        cases.append(
            Case(
                question=f'What is the lead time for "{supplier.name}"?',
                about="quoted against actual, over real deliveries",
                check=lead_time_right,
                expect_steps=("find_supplier", "supplier_lead_time"),
            )
        )

    shutting = session.scalar(
        select(func.count(Supplier.id)).where(Supplier.shutdown_from.is_not(None))
    )

    def shutdowns_right(answer: Any) -> bool:
        return len(_rows(answer, "supplier_shutdowns")) == shutting

    cases.append(
        Case(
            question="When do suppliers shut for new year?",
            about="the shutdown calendar",
            check=shutdowns_right,
            expect_steps=("supplier_shutdowns",),
        )
    )

    # ------------------------------------------------------------------
    # The desk.
    # ------------------------------------------------------------------
    def held_right(answer: Any) -> bool:
        return len(_rows(answer, "shipments_held")) == held

    cases.append(
        Case(
            question="Which shipments are stuck?",
            about="held shipments and the reason on each",
            check=held_right,
            expect_steps=("shipments_held",),
        )
    )

    def tickets_right(answer: Any) -> bool:
        return len(_rows(answer, "open_tickets")) == open_tickets

    cases.append(
        Case(
            question="What tickets are open?",
            about="the service desk queue",
            check=tickets_right,
            expect_steps=("open_tickets",),
        )
    )

    late_customers = session.execute(
        select(Order.customer_id)
        .where(Order.promised_on < today, Order.status.notin_(closed))
        .group_by(Order.customer_id)
    ).all()

    def late_list_right(answer: Any) -> bool:
        return len(_rows(answer, "customers_with_late_orders")) == len(late_customers)

    cases.append(
        Case(
            question="Which customers have late orders?",
            about="every account with something past its promise",
            check=late_list_right,
            expect_steps=("customers_with_late_orders",),
        )
    )

    # ------------------------------------------------------------------
    # The refusals. A system that answers everything invents things.
    # ------------------------------------------------------------------
    cases.append(
        Case(
            question="What is the weather in Taipei tomorrow?",
            about="nothing in the catalogue answers it, so it says so",
            expect_refusal=True,
        )
    )
    cases.append(
        Case(
            question='Which of "Zzyzx Holdings Limited" orders are late?',
            about="a plan that cannot resolve its first step stops there",
            expect_refusal=True,
        )
    )
    cases.append(
        Case(
            question="Write a letter to our biggest customer apologising.",
            about="it answers questions about the business; it does not draft post",
            expect_refusal=True,
        )
    )

    return cases
