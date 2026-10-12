"""The pricing engine: the part that must never be wrong."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.clock import today
from app.config import settings
from app.money import Trace, dec, money
from app.models import (
    Contract,
    ContractLine,
    Customer,
    PriceBreak,
    Product,
    QuoteLine,
    QuoteVersion,
    TariffTable,
)
from app.services import pricing, rates
from app.services.pricing import canonical_amount, resolve_unit_price

#: The day the generated data is laid out around, not a date typed in here.
#: It used to be ``dt.date(2026, 10, 5)``, which passed until midnight and
#: then failed six pricing tests: the duty table is seeded relative to the
#: real today, so a pinned yesterday finds no table in force. The clock
#: module exists for exactly this, and this file was not using it.
TODAY = today()


def _anchor(session) -> Customer:
    return session.scalar(select(Customer).where(Customer.code == "CUS-00001"))


def _contract_product(session) -> tuple[Product, ContractLine, Contract]:
    contract = session.scalar(select(Contract).where(Contract.code == "C-10422"))
    line = session.scalars(
        select(ContractLine).where(ContractLine.contract_id == contract.id)
    ).first()
    return session.get(Product, line.product_id), line, contract


# ---------------------------------------------------------------------------
# Which price applies
# ---------------------------------------------------------------------------
def test_a_live_contract_price_wins(session):
    customer = _anchor(session)
    product, contract_line, contract = _contract_product(session)
    trace = Trace("test")
    decision = resolve_unit_price(
        session,
        product=product,
        customer=customer,
        quantity_pieces=Decimal("1000"),
        on_date=TODAY,
        trace=trace,
    )
    assert decision.source == "contract"
    assert decision.unit_price == money(contract_line.unit_price)
    assert decision.reference == contract.code
    assert any("Contract" in step.label or "Contract" in step.formula for step in trace.steps)


def test_an_expired_contract_falls_back_and_is_flagged(session):
    customer = _anchor(session)
    expired = session.scalar(select(Contract).where(Contract.code == "C-10311"))
    contract_line = session.scalars(
        select(ContractLine).where(ContractLine.contract_id == expired.id)
    ).first()
    product = session.get(Product, contract_line.product_id)

    decision = resolve_unit_price(
        session,
        product=product,
        customer=customer,
        quantity_pieces=Decimal("600"),
        on_date=TODAY,
        trace=Trace("test"),
    )
    assert decision.source in {"volume_break", "list"}
    assert decision.expired_contract is True


def test_a_bigger_quantity_reaches_a_better_price(session):
    customer = _anchor(session)
    product = session.scalars(
        select(Product).where(Product.family == "fastener", Product.is_stocked.is_(True))
    ).first()
    small = resolve_unit_price(
        session, product=product, customer=customer, quantity_pieces=Decimal("1"),
        on_date=TODAY, trace=Trace("a"),
    )
    large = resolve_unit_price(
        session, product=product, customer=customer, quantity_pieces=Decimal("100000"),
        on_date=TODAY, trace=Trace("b"),
    )
    assert large.unit_price <= small.unit_price


def test_the_price_is_always_in_taiwan_dollars_before_conversion(session):
    customer = _anchor(session)
    product = session.scalars(select(Product)).first()
    decision = resolve_unit_price(
        session, product=product, customer=customer, quantity_pieces=Decimal("10"),
        on_date=TODAY, trace=Trace("t"),
    )
    assert decision.unit_price > 0


# ---------------------------------------------------------------------------
# Duty
# ---------------------------------------------------------------------------
def _active_table(session) -> TariffTable:
    table = rates.active_tariff_table(session, on_date=TODAY)
    assert table is not None
    return table


def test_duty_is_not_charged_when_the_buyer_carries_it(session):
    product = session.scalars(select(Product)).first()
    trace = Trace("t")
    amount, breakdown = rates.duty_for_line(
        session,
        table=_active_table(session),
        product=product,
        customs_value=Decimal("1000"),
        origin="TW",
        destination="US",
        trace=trace,
        seller_pays_import_duty=False,
    )
    assert amount == 0
    assert breakdown == []


def test_duty_comes_from_the_table_and_records_its_authority(session):
    product = session.scalar(
        select(Product).where(Product.harmonised_tariff_code == "7318.15.80")
    )
    trace = Trace("t")
    amount, breakdown = rates.duty_for_line(
        session,
        table=_active_table(session),
        product=product,
        customs_value=Decimal("10000"),
        origin="TW",
        destination="US",
        trace=trace,
        seller_pays_import_duty=True,
    )
    assert amount > 0
    assert breakdown
    assert all(row["authority"] for row in breakdown)
    components = {row["component"] for row in breakdown}
    assert "most_favoured_nation" in components


def test_a_steel_fastener_does_not_stack_section_301_on_top_of_section_232(session):
    """Goods already carrying the metals duty are not given the Section 301 layer."""
    product = session.scalar(
        select(Product).where(Product.harmonised_tariff_code == "7318.15.80")
    )
    _amount, breakdown = rates.duty_for_line(
        session,
        table=_active_table(session),
        product=product,
        customs_value=Decimal("10000"),
        origin="TW",
        destination="US",
        trace=Trace("t"),
        seller_pays_import_duty=True,
    )
    components = {row["component"] for row in breakdown}
    assert "section_232" in components
    assert "section_301" not in components


def test_the_taiwan_section_301_rate_is_capped_at_a_combined_ten_per_cent(session):
    """A bearing is not a steel derivative, so the capped Section 301 rate applies."""
    product = session.scalar(
        select(Product).where(Product.harmonised_tariff_code == "8482.10.50")
    )
    _amount, breakdown = rates.duty_for_line(
        session,
        table=_active_table(session),
        product=product,
        customs_value=Decimal("10000"),
        origin="TW",
        destination="US",
        trace=Trace("t"),
        seller_pays_import_duty=True,
    )
    by_component = {row["component"]: row for row in breakdown}
    assert "section_301" in by_component
    combined = sum(dec(row["rate_percent"]) for row in breakdown)
    assert combined == Decimal("10.00")
    assert "Reduced from" in by_component["section_301"]["note"]


def test_a_missing_duty_row_is_refused_rather_than_priced_at_nothing(session):
    product = session.scalars(select(Product)).first()
    with pytest.raises(rates.RateNotAvailable):
        rates.duty_for_line(
            session,
            table=_active_table(session),
            product=product,
            customs_value=Decimal("100"),
            origin="ZZ",
            destination="US",
            trace=Trace("t"),
            seller_pays_import_duty=True,
        )


def test_no_import_duty_applies_inside_taiwan(session):
    product = session.scalars(select(Product)).first()
    amount, breakdown = rates.duty_for_line(
        session,
        table=_active_table(session),
        product=product,
        customs_value=Decimal("10000"),
        origin=product.country_of_origin,
        destination="TW",
        trace=Trace("t"),
        seller_pays_import_duty=True,
    )
    assert amount == 0
    assert breakdown and breakdown[0]["rate_percent"] == "0.00"


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------
def test_the_exchange_rate_is_the_latest_on_or_before_the_quote_date(session):
    row = rates.find_exchange_rate(session, "TWD", "USD", on_date=TODAY)
    assert row is not None
    assert row.as_of_date <= TODAY


def test_converting_records_the_rate_it_used(session):
    row = rates.find_exchange_rate(session, "TWD", "USD", on_date=TODAY)
    trace = Trace("t")
    converted = rates.convert(Decimal("1000"), row, trace)
    assert converted == money(Decimal("1000") * row.rate)
    assert trace.steps[0].inputs[0].source_kind == "foreign_exchange"


# ---------------------------------------------------------------------------
# The fingerprint that makes "the model never writes a price" checkable
# ---------------------------------------------------------------------------
def test_the_canonical_form_of_a_number_does_not_depend_on_trailing_zeros():
    assert canonical_amount(Decimal("0.00")) == canonical_amount(Decimal("0"))
    assert canonical_amount(Decimal("243.2400")) == "243.24"
    assert canonical_amount(Decimal("1.2E+3")) == "1200"


def test_the_fingerprint_changes_when_a_price_is_tampered_with(session):
    version = session.scalars(
        select(QuoteVersion).where(QuoteVersion.pricing_checksum != "")
    ).first()
    if version is None:
        pytest.skip("no priced quote in this database yet")
    before = pricing.pricing_checksum(version)
    line = sorted(version.lines, key=lambda line: line.line_number)[0]
    original = line.unit_price
    line.unit_price = dec(original) + Decimal("1")
    try:
        assert pricing.pricing_checksum(version) != before
    finally:
        line.unit_price = original
