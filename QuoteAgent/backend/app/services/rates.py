"""Currency, freight and duty: the three numbers nobody should ever guess.

Each one is read from a dated table that a named person owns. The quote records
which row and which table version priced it, so a quote can be defended months
later, and loading a newer duty table flags every open quote priced on an older
one.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import PERCENT_PLACES, Trace, TraceInput, dec, money, percent
from ..models import ExchangeRate, FreightRate, Product, QuoteVersion, TariffLine, TariffTable


class RateNotAvailable(Exception):
    """Raised when a rate is missing. Never quietly defaulted to zero."""


# ---------------------------------------------------------------------------
# Currency
# ---------------------------------------------------------------------------
def find_exchange_rate(
    session: Session, base: str, quote: str, *, on_date: dt.date | None = None
) -> ExchangeRate | None:
    """The most recent published rate on or before the quote date."""
    if base == quote:
        return None
    on_date = on_date or dt.date.today()
    return session.scalar(
        select(ExchangeRate)
        .where(
            ExchangeRate.base_currency == base,
            ExchangeRate.quote_currency == quote,
            ExchangeRate.as_of_date <= on_date,
        )
        .order_by(ExchangeRate.as_of_date.desc())
        .limit(1)
    )


def convert(
    amount: Decimal, rate_row: ExchangeRate | None, trace: Trace, *, label: str = "Convert currency"
) -> Decimal:
    if rate_row is None:
        return money(amount)
    converted = money(dec(amount) * rate_row.rate)
    trace.add(
        label,
        f"{amount} {rate_row.base_currency} x {rate_row.rate} = {converted} {rate_row.quote_currency}",
        converted,
        unit=rate_row.quote_currency,
        inputs=[
            TraceInput(
                "Exchange rate",
                f"1 {rate_row.base_currency} = {rate_row.rate} {rate_row.quote_currency}",
                f"{rate_row.source}, {rate_row.as_of_date.isoformat()}",
                "foreign_exchange",
                str(rate_row.id),
            )
        ],
        note=(
            "The rate is locked on the quote date and holds for the validity "
            "period printed on the quote."
        ),
    )
    return converted


def exchange_rate_is_stale(version: QuoteVersion, *, today: dt.date | None = None) -> bool:
    if version.exchange_rate is None or version.exchange_rate_locked_at is None:
        return False
    today = today or dt.date.today()
    from ..config import settings

    locked_on = version.exchange_rate_locked_at.date()
    return (today - locked_on).days > settings.foreign_exchange_lock_days


# ---------------------------------------------------------------------------
# Freight
# ---------------------------------------------------------------------------
def find_freight_rate(
    session: Session, origin: str, destination: str, mode: str = "sea"
) -> FreightRate | None:
    row = session.scalar(
        select(FreightRate).where(
            FreightRate.origin_country == origin,
            FreightRate.destination_country == destination,
            FreightRate.mode == mode,
        )
    )
    if row is None:
        row = session.scalar(
            select(FreightRate).where(
                FreightRate.origin_country == origin,
                FreightRate.destination_country == destination,
            )
        )
    return row


def freight_for_shipment(
    rate_row: FreightRate | None, total_weight_kilograms: Decimal, goods_value: Decimal, trace: Trace
) -> tuple[Decimal, Decimal]:
    """Return freight and insurance in the freight table's currency."""
    if rate_row is None:
        trace.add(
            "Freight",
            "No freight is included because the agreed trade rule leaves it to the buyer",
            money(0),
            unit="",
        )
        return money(0), money(0)

    by_weight = money(dec(total_weight_kilograms) * rate_row.price_per_kilogram)
    chargeable = max(by_weight, rate_row.minimum_charge)
    freight = money(chargeable + rate_row.handling_per_shipment)
    trace.add(
        "Freight",
        (
            f"max({total_weight_kilograms} kg x {rate_row.price_per_kilogram}, "
            f"minimum {rate_row.minimum_charge}) + handling {rate_row.handling_per_shipment} "
            f"= {freight}"
        ),
        freight,
        unit=rate_row.currency,
        inputs=[
            TraceInput("Freight table", f"{rate_row.origin_country} to {rate_row.destination_country} by {rate_row.mode}",
                       "Logistics freight table", "policy", str(rate_row.id)),
            TraceInput("Shipment weight", f"{total_weight_kilograms} kg", "Sum of line weights", "catalogue"),
        ],
        note=f"Transit time {rate_row.transit_days} days.",
    )

    insurance = money(dec(goods_value) * rate_row.insurance_percent / Decimal("100"))
    return freight, insurance


# ---------------------------------------------------------------------------
# Duty
# ---------------------------------------------------------------------------
COMPONENT_LABELS: dict[str, str] = {
    "most_favoured_nation": "Normal trade relations rate",
    "section_232": "Section 232 metals duty",
    "section_301": "Section 301 duty",
    "section_122": "Section 122 temporary duty",
    "reciprocal": "Reciprocal trade agreement rate",
}


def active_tariff_table(
    session: Session, *, on_date: dt.date | None = None
) -> TariffTable | None:
    on_date = on_date or dt.date.today()
    return session.scalar(
        select(TariffTable)
        .where(
            TariffTable.status == "active",
            TariffTable.effective_from <= on_date,
        )
        .order_by(TariffTable.effective_from.desc())
        .limit(1)
    )


def duty_components(
    session: Session,
    table: TariffTable,
    harmonised_tariff_code: str,
    origin: str,
    destination: str,
) -> list[TariffLine]:
    rows = list(
        session.scalars(
            select(TariffLine).where(
                TariffLine.tariff_table_id == table.id,
                TariffLine.harmonised_tariff_code == harmonised_tariff_code,
                TariffLine.origin_country == origin,
                TariffLine.destination_country == destination,
            )
        )
    )
    present = {r.component for r in rows}
    # Stacking: a component is dropped when the component that excludes it is present.
    return [r for r in rows if not (r.excluded_by and r.excluded_by in present)]


def duty_for_line(
    session: Session,
    *,
    table: TariffTable | None,
    product: Product,
    customs_value: Decimal,
    origin: str,
    destination: str,
    trace: Trace,
    seller_pays_import_duty: bool,
) -> tuple[Decimal, list[dict[str, Any]]]:
    """Work out import duty for one line from the dated table, never from a model."""
    if not seller_pays_import_duty:
        trace.add(
            "Import duty",
            "The agreed trade rule leaves import duty with the buyer, so none is quoted",
            money(0),
        )
        return money(0), []

    if table is None:
        raise RateNotAvailable(
            "No duty table is active for this date. A quote that has to include duty "
            "cannot be produced until the pricing owner loads and signs off a table."
        )

    rows = duty_components(session, table, product.harmonised_tariff_code, origin, destination)
    if not rows:
        raise RateNotAvailable(
            f"Duty table {table.version} has no entry for commodity code "
            f"{product.harmonised_tariff_code} from {origin} to {destination}. "
            "The pricing owner has to add it and the customs broker has to sign it off."
        )

    metal_content = dec(product.attributes.get("metal_content_percent", 100))
    breakdown: list[dict[str, Any]] = []
    running_percent = Decimal("0")
    total = Decimal("0")

    # Most favoured nation first, because caps are expressed against it.
    rows.sort(key=lambda r: 0 if r.component == "most_favoured_nation" else 1)

    for row in rows:
        applied_percent = percent(row.rate_percent)
        capped_note = ""
        if row.combined_cap_percent is not None:
            allowed = percent(row.combined_cap_percent) - running_percent
            if allowed < Decimal("0"):
                allowed = Decimal("0")
            if applied_percent > allowed:
                capped_note = (
                    f"Reduced from {row.rate_percent}% so the combined rate stops at "
                    f"{row.combined_cap_percent}%."
                )
                applied_percent = allowed

        basis_value = (
            money(dec(customs_value) * metal_content / Decimal("100"))
            if row.basis == "metal_content_value"
            else money(customs_value)
        )
        amount = money(basis_value * applied_percent / Decimal("100"))
        running_percent += applied_percent
        total += amount

        basis_words = (
            "the full customs value"
            if row.basis == "customs_value"
            else f"the metal content, {metal_content}% of the customs value"
        )
        trace.add(
            COMPONENT_LABELS.get(row.component, row.component),
            f"{basis_value} x {applied_percent}% = {amount}",
            amount,
            inputs=[
                TraceInput(
                    "Duty table version",
                    table.version,
                    f"Owned by {table.owned_by}; signed off by {table.customs_broker or 'not yet signed off'}",
                    "tariff_table",
                    str(table.id),
                ),
                TraceInput(
                    "Commodity code",
                    product.harmonised_tariff_code,
                    product.sku,
                    "catalogue",
                    str(product.id),
                ),
                TraceInput("Authority", row.authority or "not recorded", table.version, "tariff_table", str(row.id)),
            ],
            note=(f"Charged on {basis_words}. " + capped_note + " " + (row.note or "")).strip(),
        )
        breakdown.append(
            {
                "component": row.component,
                "label": COMPONENT_LABELS.get(row.component, row.component),
                "rate_percent": str(applied_percent),
                "published_rate_percent": str(percent(row.rate_percent)),
                "basis": row.basis,
                "basis_value": str(basis_value),
                "amount": str(amount),
                "authority": row.authority,
                "note": (capped_note + " " + (row.note or "")).strip(),
                "tariff_line_id": row.id,
            }
        )

    return money(total), breakdown


def tariff_table_summary(table: TariffTable | None) -> dict[str, Any]:
    if table is None:
        return {"version": "", "is_signed_off": False, "warning": "No duty table is active."}
    return {
        "id": table.id,
        "version": table.version,
        "title": table.title,
        "effective_from": table.effective_from.isoformat(),
        "effective_to": table.effective_to.isoformat() if table.effective_to else None,
        "owned_by": table.owned_by,
        "customs_broker": table.customs_broker,
        "is_signed_off": table.is_signed_off,
        "signed_off_at": table.broker_signed_off_at.isoformat() if table.broker_signed_off_at else None,
        "source_note": table.source_note,
        "warning": (
            ""
            if table.is_signed_off
            else "This duty table has not been signed off by a customs broker. "
            "Quotes priced on it are marked as provisional."
        ),
    }
