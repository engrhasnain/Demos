"""The demonstration data, checked against the business it claims to be.

Synthetic data is where a demonstration quietly stops being worth
anything. An order book five times the company's stated revenue, or
invoices that bear no relation to the orders they came from, survives a
demo and does not survive the first person who opens one account and
adds it up. These are the sums that person would do.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import func, select

from app.models import Customer, Invoice, Order, OrderLine, Part, Supplier, User
from app.seed.generator import MARGIN, PARTS, order_quantity, part_catalogue

#: The window the generator fills.
WINDOW_DAYS = 150


def test_the_catalogue_is_the_size_a_distributor_lists():
    assert 800 <= len(PARTS) <= 4000
    codes = [code for code, _, _ in PARTS]
    assert len(codes) == len(set(codes)), "duplicate part codes"


def test_the_catalogue_is_the_same_every_time():
    assert part_catalogue() == part_catalogue()


def test_part_codes_follow_the_convention():
    for code, description, cost in PARTS:
        assert code.startswith("HT-")
        assert code == code.upper()
        assert description
        assert cost > 0


def test_the_order_book_is_about_the_right_size(session):
    """Roughly US$45M a year, which is what this company is said to turn over."""
    booked = float(session.scalar(select(func.sum(Order.total))) or 0)
    annualised = booked * 365 / WINDOW_DAYS
    # The test dataset is smaller than the demonstration one, so the
    # check is on the shape rather than the absolute figure: an average
    # order somewhere in the range an industrial distributor writes.
    orders = session.scalar(select(func.count(Order.id)))
    average = booked / orders
    assert 2_000 < average < 120_000, f"average order {average:,.0f}"
    assert annualised > 0


def test_every_order_total_is_the_sum_of_its_lines(session):
    costs = {p.code: p.unit_cost for p in session.scalars(select(Part))}
    orders = session.scalars(select(Order).limit(40)).all()
    for order in orders:
        lines = session.scalars(
            select(OrderLine).where(OrderLine.order_id == order.id)
        ).all()
        assert lines, f"{order.number} has no lines"
        by_hand = sum(
            (costs[line.part_code] * MARGIN * line.quantity).quantize(Decimal("0.01"))
            for line in lines
        )
        assert abs(order.total - by_hand) < Decimal("0.05"), order.number


def test_quantities_are_sized_by_what_the_part_costs(session):
    import random

    chooser = random.Random(1)
    cheap = [order_quantity(2.0, chooser) for _ in range(200)]
    dear = [order_quantity(1400.0, chooser) for _ in range(200)]
    assert min(cheap) > max(dear)


def test_every_invoice_belongs_to_an_order_that_was_delivered(session):
    """Receivables and the order book have to be the same business."""
    delivered = {
        (o.customer_id, o.total)
        for o in session.scalars(select(Order).where(Order.status == "delivered"))
    }
    invoices = session.scalars(select(Invoice).limit(60)).all()
    assert invoices
    for invoice in invoices:
        assert (invoice.customer_id, invoice.total) in delivered, invoice.number


def test_an_invoice_is_never_issued_before_its_terms_make_sense(session):
    for invoice in session.scalars(select(Invoice).limit(80)):
        assert invoice.due_on > invoice.issued_on
        assert (invoice.due_on - invoice.issued_on).days in {30, 45, 60}
        if invoice.paid_on:
            assert invoice.paid_on >= invoice.issued_on


def test_receivables_sit_near_the_payment_terms(session):
    booked = float(session.scalar(select(func.sum(Order.total))) or 0)
    owed = float(
        session.scalar(
            select(func.sum(Invoice.total)).where(Invoice.paid_on.is_(None))
        )
        or 0
    )
    annualised = booked * 365 / WINDOW_DAYS
    days_outstanding = owed / annualised * 365
    assert 15 < days_outstanding < 90, f"{days_outstanding:.0f} days"


def test_parts_are_spread_across_suppliers(session):
    """One supplier holding the whole catalogue makes the exposure
    questions meaningless."""
    counts = [
        n
        for _, n in session.execute(
            select(Part.supplier_id, func.count(Part.id)).group_by(Part.supplier_id)
        )
    ]
    assert len(counts) >= 10
    assert max(counts) < sum(counts) * 0.4


def test_weekly_demand_comes_from_the_order_lines(session):
    sold: dict[str, int] = {}
    for code, quantity in session.execute(
        select(OrderLine.part_code, OrderLine.quantity)
    ):
        sold[code] = sold.get(code, 0) + quantity

    checked = 0
    for part in session.scalars(select(Part).where(Part.weekly_demand > 0).limit(50)):
        expected = sold.get(part.code, 0) / (WINDOW_DAYS / 7.0)
        assert abs(part.weekly_demand - expected) < 0.02, part.code
        checked += 1
    assert checked > 0


def test_a_part_that_never_sold_has_no_demand(session):
    sold = {code for (code,) in session.execute(select(OrderLine.part_code).distinct())}
    for part in session.scalars(select(Part).where(Part.weekly_demand == 0).limit(30)):
        assert part.code not in sold


def test_some_parts_are_short_and_most_are_not(session):
    short = 0
    comfortable = 0
    for part in session.scalars(select(Part).where(Part.weekly_demand > 0)):
        cover = part.on_hand / part.weekly_demand
        if cover < 4:
            short += 1
        else:
            comfortable += 1
    assert short > 0, "nothing is ever short, so the question has no answer"
    assert comfortable > short, "everything is short, which is not a business"


def test_the_people_have_the_grants_the_demonstration_needs(session):
    roles = {u.role for u in session.scalars(select(User))}
    assert {"salesperson", "account_manager", "manager", "director"} <= roles


def test_suppliers_shut_and_the_dates_make_sense(session):
    shutting = session.scalars(
        select(Supplier).where(Supplier.shutdown_from.is_not(None))
    ).all()
    assert shutting
    for supplier in shutting:
        assert supplier.shutdown_to > supplier.shutdown_from
        days = (supplier.shutdown_to - supplier.shutdown_from).days
        assert 5 <= days <= 60, f"{supplier.name} shuts for {days} days"


def test_customers_are_in_the_countries_the_business_trades_with(session):
    countries = {c.country for c in session.scalars(select(Customer))}
    assert countries <= {"TW", "US", "JP"}
    assert "TW" in countries and "US" in countries
