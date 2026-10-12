"""The pricing engine.

This module is the only place in the product that decides what something costs.
The reasoning engine cannot write a price; if it ever did, the integrity check
at the bottom of this file would refuse to save the quote.

Order of work for one line:

1. turn the requested quantity into something Hengtai can sell (pack and
   minimum order quantity);
2. find the unit price: a live contract first, then the volume break for the
   customer's price tier, then the list price;
3. apply any discount the customer asked for and test it against the margin
   floor;
4. work out how the line will actually be supplied, across both warehouses;
5. add the line's share of freight and insurance, and its import duty;
6. convert to the quote currency at the locked rate.

Every one of those steps writes a line into the calculation trace, so any
number on screen can be opened and read back to its source.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..domain.incoterms import get_incoterm
from ..domain.units import plan_quantity
from ..money import ZERO, Trace, TraceInput, dec, money, percent
from ..models import (
    Contract,
    ContractLine,
    Customer,
    PriceBreak,
    Product,
    QuoteLine,
    QuoteVersion,
    StockLevel,
)
from . import rates
from ..text import count


class PricingError(Exception):
    """Something needed to price the line is missing. Never guessed."""


class PricingIntegrityError(Exception):
    """A stored price does not equal what the engine produces. Nothing is saved."""


# ---------------------------------------------------------------------------
# Unit price
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class PriceDecision:
    unit_price: Decimal
    source: str            # contract | volume_break | list
    reference: str
    note: str = ""
    expired_contract: bool = False


def resolve_unit_price(
    session: Session,
    *,
    product: Product,
    customer: Customer | None,
    quantity_pieces: Decimal,
    on_date: dt.date,
    trace: Trace,
) -> PriceDecision:
    """Contract first, then volume break, then list. Always in Taiwan dollars."""
    expired_contract = False

    if customer is not None:
        row = session.execute(
            select(ContractLine, Contract)
            .join(Contract, ContractLine.contract_id == Contract.id)
            .where(
                Contract.customer_id == customer.id,
                ContractLine.product_id == product.id,
            )
            .order_by(Contract.valid_to.desc())
        ).first()

        if row is not None:
            contract_line, contract = row
            live = contract.valid_from <= on_date <= contract.valid_to
            if live and quantity_pieces >= dec(contract_line.minimum_quantity):
                trace.add(
                    "Unit price",
                    f"Contract {contract.code} line price",
                    contract_line.unit_price,
                    unit="TWD per piece",
                    inputs=[
                        TraceInput(
                            "Contract",
                            f"{contract.code}, valid {contract.valid_from} to {contract.valid_to}",
                            f"Contract {contract.code}",
                            "contract",
                            str(contract.id),
                        ),
                        TraceInput(
                            "Minimum quantity on the contract",
                            f"{contract_line.minimum_quantity} pieces",
                            f"Contract {contract.code}",
                            "contract",
                            str(contract.id),
                        ),
                    ],
                )
                return PriceDecision(
                    unit_price=money(contract_line.unit_price),
                    source="contract",
                    reference=contract.code,
                    note=f"Contract price under {contract.code}.",
                )
            if not live:
                expired_contract = True
                trace.add(
                    "Contract checked",
                    f"Contract {contract.code} ran out on {contract.valid_to}",
                    "not applied",
                    inputs=[
                        TraceInput(
                            "Contract",
                            f"{contract.code}, valid to {contract.valid_to}",
                            f"Contract {contract.code}",
                            "contract",
                            str(contract.id),
                        )
                    ],
                    note=(
                        "The contract price was not used because the contract has "
                        "expired. The line falls back to tier pricing and is flagged."
                    ),
                )

    tier = customer.price_tier if customer else "standard"
    breaks = list(
        session.scalars(
            select(PriceBreak)
            .where(PriceBreak.product_id == product.id, PriceBreak.price_tier == tier)
            .order_by(PriceBreak.minimum_quantity.desc())
        )
    )
    for row in breaks:
        if quantity_pieces >= dec(row.minimum_quantity):
            trace.add(
                "Unit price",
                f"Volume price for {tier} customers at {row.minimum_quantity} pieces or more",
                row.unit_price,
                unit="TWD per piece",
                inputs=[
                    TraceInput(
                        "Price tier",
                        tier,
                        customer.name if customer else "no customer record",
                        "catalogue",
                        str(customer.id) if customer else "",
                    ),
                    TraceInput(
                        "Quantity break",
                        f"{row.minimum_quantity} pieces or more",
                        f"{product.sku} price list",
                        "catalogue",
                        str(product.id),
                    ),
                ],
            )
            return PriceDecision(
                unit_price=money(row.unit_price),
                source="volume_break",
                reference=f"{tier} tier, {row.minimum_quantity}+",
                note=f"Volume price for {row.minimum_quantity} pieces or more.",
                expired_contract=expired_contract,
            )

    trace.add(
        "Unit price",
        "List price, because no contract and no volume break applies",
        product.list_price,
        unit="TWD per piece",
        inputs=[
            TraceInput("List price", str(product.list_price), product.sku, "catalogue", str(product.id))
        ],
    )
    return PriceDecision(
        unit_price=money(product.list_price),
        source="list",
        reference="list price",
        note="List price.",
        expired_contract=expired_contract,
    )


# ---------------------------------------------------------------------------
# How the line gets supplied
# ---------------------------------------------------------------------------
def fulfilment_options(
    session: Session, product: Product, pieces: Decimal, *, destination_country: str
) -> list[dict[str, Any]]:
    """Stock is in two warehouses and the rest is weeks away. Show the choices."""
    levels = list(session.scalars(select(StockLevel).where(StockLevel.product_id == product.id)))
    by_site = {level.warehouse_code: level.available for level in levels}
    taichung = dec(by_site.get("TAICHUNG", 0))
    ontario = dec(by_site.get("ONTARIO", 0))
    on_hand = taichung + ontario
    today = dt.date.today()
    lead = product.replenishment_lead_time_days

    options: list[dict[str, Any]] = []

    if on_hand >= pieces:
        nearest = "ONTARIO" if destination_country == "US" and ontario >= pieces else "TAICHUNG"
        options.append(
            {
                "code": "from_stock",
                "label": "Ship the whole quantity from stock",
                "detail": (
                    f"{int(pieces)} pieces are available now "
                    f"({int(taichung)} in Taichung, {int(ontario)} in Ontario)."
                ),
                "ready_date": today.isoformat(),
                "lead_time_days": 0,
                "warehouse": nearest,
                "split": False,
            }
        )
    elif on_hand > 0:
        shortfall = pieces - on_hand
        options.append(
            {
                "code": "split_shipment",
                "label": "Split the shipment",
                "detail": (
                    f"{int(on_hand)} pieces now ({int(taichung)} in Taichung, "
                    f"{int(ontario)} in Ontario), and {int(shortfall)} in about "
                    f"{lead} days."
                ),
                "ready_date": today.isoformat(),
                "lead_time_days": lead,
                "warehouse": "TAICHUNG",
                "split": True,
            }
        )
        options.append(
            {
                "code": "wait_for_full",
                "label": "Wait and ship complete",
                "detail": f"One shipment of {int(pieces)} pieces in about {lead} days.",
                "ready_date": (today + dt.timedelta(days=lead)).isoformat(),
                "lead_time_days": lead,
                "warehouse": "TAICHUNG",
                "split": False,
            }
        )
    else:
        options.append(
            {
                "code": "on_order",
                "label": "Buy in for this order",
                "detail": (
                    f"Nothing is in stock. The supplier lead time is about {lead} days."
                ),
                "ready_date": (today + dt.timedelta(days=lead)).isoformat(),
                "lead_time_days": lead,
                "warehouse": "TAICHUNG",
                "split": False,
            }
        )
    return options


# ---------------------------------------------------------------------------
# One line
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class LinePricing:
    quantity_billed: Decimal
    unit_of_sale: str
    rounding_note: str
    unit_price: Decimal
    price_source: str
    price_source_reference: str
    discount_percent: Decimal
    extended_price: Decimal
    unit_cost: Decimal
    margin_percent: Decimal
    below_margin_floor: bool
    weight_kilograms: Decimal
    lead_time_days: int
    fulfilment_options: list[dict[str, Any]]
    trace: Trace
    expired_contract: bool = False
    warnings: list[str] = field(default_factory=list)


def price_line(
    session: Session,
    *,
    line: QuoteLine,
    product: Product,
    customer: Customer | None,
    on_date: dt.date,
    discount_percent: Decimal = ZERO,
    destination_country: str = "TW",
) -> LinePricing:
    trace = Trace(f"Line {line.line_number}: {product.sku}")
    margin_floor = (
        dec(customer.margin_floor_percent)
        if customer is not None
        else dec(settings.default_margin_floor_percent)
    )

    plan = plan_quantity(
        requested_quantity=line.requested_quantity,
        requested_unit=line.requested_unit,
        pack_size=product.pack_size,
        minimum_order_quantity=(
            product.supplier.minimum_order_quantity if product.supplier else 1
        ),
        is_stocked=product.is_stocked,
        product_label=product.sku,
    )
    trace.add(
        "Quantity to bill",
        " ".join(plan.notes) or f"{plan.pieces_billed} pieces as asked for",
        plan.pieces_billed,
        unit="pieces",
        inputs=plan.trace_inputs,
    )

    decision = resolve_unit_price(
        session,
        product=product,
        customer=customer,
        quantity_pieces=plan.pieces_billed,
        on_date=on_date,
        trace=trace,
    )

    net_unit_price = decision.unit_price
    if discount_percent > 0:
        net_unit_price = money(decision.unit_price * (Decimal("100") - discount_percent) / Decimal("100"))
        trace.add(
            "Discount applied",
            f"{decision.unit_price} less {discount_percent}% = {net_unit_price}",
            net_unit_price,
            unit="TWD per piece",
            inputs=[
                TraceInput("Discount asked for", f"{discount_percent}%", "Customer request", "request")
            ],
        )

    extended = money(net_unit_price * plan.pieces_billed)
    trace.add(
        "Line value",
        f"{net_unit_price} x {plan.pieces_billed} pieces = {extended}",
        extended,
        unit="TWD",
    )

    unit_cost = money(product.standard_cost)
    line_cost = money(unit_cost * plan.pieces_billed)
    margin = (
        percent((extended - line_cost) / extended * Decimal("100")) if extended > 0 else ZERO
    )
    below_floor = margin < margin_floor
    trace.add(
        "Margin on this line",
        f"({extended} - {line_cost}) / {extended} x 100 = {margin}%",
        margin,
        unit="%",
        inputs=[
            TraceInput("Standard cost", f"{unit_cost} TWD per piece", product.sku, "catalogue", str(product.id)),
            TraceInput(
                "Margin floor",
                f"{margin_floor}%",
                customer.name if customer else "company default",
                "policy",
                str(customer.id) if customer else "",
            ),
        ],
        note=(
            f"This line is below the {margin_floor}% floor and needs a sales manager."
            if below_floor
            else "This line is above the margin floor."
        ),
    )

    options = fulfilment_options(
        session, product, plan.pieces_billed, destination_country=destination_country
    )
    weight = money(dec(product.weight_grams) * plan.pieces_billed / Decimal("1000"))

    warnings: list[str] = []
    if decision.expired_contract:
        warnings.append(
            "The customer's contract for this part has expired, so tier pricing was used."
        )
    if not product.is_stocked:
        warnings.append("This part is not stocked and has to be bought in.")

    return LinePricing(
        quantity_billed=plan.pieces_billed,
        unit_of_sale=plan.unit_of_sale,
        rounding_note=plan.rounding_note,
        unit_price=net_unit_price,
        price_source=decision.source,
        price_source_reference=decision.reference,
        discount_percent=percent(discount_percent),
        extended_price=extended,
        unit_cost=unit_cost,
        margin_percent=margin,
        below_margin_floor=below_floor,
        weight_kilograms=weight,
        lead_time_days=max((o["lead_time_days"] for o in options), default=0),
        fulfilment_options=options,
        trace=trace,
        expired_contract=decision.expired_contract,
        warnings=warnings,
    )


# ---------------------------------------------------------------------------
# A whole quote version
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class PricingReport:
    priced_lines: int
    skipped_lines: int
    goods_total: Decimal
    freight_total: Decimal
    insurance_total: Decimal
    duty_total: Decimal
    grand_total: Decimal
    total_cost: Decimal
    margin_percent: Decimal
    currency: str
    warnings: list[str] = field(default_factory=list)
    totals_trace: dict[str, Any] = field(default_factory=dict)
    duty_table_gaps: list[dict[str, Any]] = field(default_factory=list)


def price_quote_version(
    session: Session, version: QuoteVersion, *, on_date: dt.date | None = None
) -> PricingReport:
    """Price every line that can be priced, then the shipment-level costs."""
    on_date = on_date or dt.date.today()
    case = version.case
    customer = case.customer
    incoterm = get_incoterm(version.incoterm)
    totals_trace = Trace("Quote totals")
    warnings: list[str] = []

    goods_total_twd = ZERO
    cost_total_twd = ZERO
    total_weight = ZERO
    priced = 0
    skipped = 0
    priceable: list[tuple[QuoteLine, LinePricing]] = []

    for line in version.lines:
        if line.status in {"needs_clarification", "non_catalogue", "withdrawn"} or line.product is None:
            skipped += 1
            line.quantity_billed = ZERO
            line.unit_price = ZERO
            line.extended_price = ZERO
            line.duty_amount = ZERO
            line.landed_total = ZERO
            continue

        result = price_line(
            session,
            line=line,
            product=line.product,
            customer=customer,
            on_date=on_date,
            discount_percent=dec(version.requested_discount_percent),
            destination_country=version.destination_country,
        )
        priceable.append((line, result))
        goods_total_twd += result.extended_price
        cost_total_twd += money(result.unit_cost * result.quantity_billed)
        total_weight += result.weight_kilograms
        priced += 1
        warnings.extend(result.warnings)

    # --- shipment level: freight, insurance -------------------------------
    origin = "TW"
    destination = version.destination_country
    freight_rate = (
        rates.find_freight_rate(session, origin, destination)
        if incoterm.seller_pays_main_carriage or incoterm.seller_pays_destination_delivery
        else None
    )
    freight_twd, insurance_twd = rates.freight_for_shipment(
        freight_rate, total_weight, goods_total_twd, totals_trace
    )
    if not incoterm.seller_pays_insurance:
        insurance_twd = ZERO

    # --- duty, per line, because commodity codes differ -------------------
    tariff_table = rates.active_tariff_table(session, on_date=on_date)
    duty_total_twd = ZERO
    duty_table_gaps: list[dict[str, Any]] = []
    for line, result in priceable:
        share = (
            money(freight_twd * result.extended_price / goods_total_twd)
            if goods_total_twd > 0
            else ZERO
        )
        insurance_share = (
            money(insurance_twd * result.extended_price / goods_total_twd)
            if goods_total_twd > 0
            else ZERO
        )
        # Customs value for an import into the United States is the transaction
        # value of the goods; freight and insurance are not added for a free on
        # board valuation, which is what the United States uses.
        customs_value = result.extended_price
        try:
            duty, breakdown = rates.duty_for_line(
                session,
                table=tariff_table,
                product=line.product,
                customs_value=customs_value,
                origin=line.product.country_of_origin,
                destination=destination,
                trace=result.trace,
                seller_pays_import_duty=incoterm.seller_pays_import_duty,
            )
        except rates.RateNotAvailable as exc:
            # A gap in the duty table is a job for the pricing owner, not a
            # question for the customer, and it must never quietly drop a line
            # off the quote. The line stays priced on goods value, the duty is
            # recorded as unknown, and the quote is blocked from being sent.
            duty, breakdown = ZERO, [
                {
                    "component": "unknown",
                    "label": "Import duty could not be priced",
                    "rate_percent": "",
                    "amount": "0",
                    "note": str(exc),
                }
            ]
            warnings.append(str(exc))
            duty_table_gaps.append(
                {
                    "line_number": line.line_number,
                    "part": line.product.sku if line.product else "",
                    "commodity_code": line.product.harmonised_tariff_code if line.product else "",
                    "origin": line.product.country_of_origin if line.product else "",
                    "destination": destination,
                    "reason": str(exc),
                }
            )

        duty_total_twd += duty
        _write_line(line, result, share, insurance_share, duty, breakdown)

    grand_total_twd = money(goods_total_twd + freight_twd + insurance_twd + duty_total_twd)
    totals_trace.add(
        "Quote total before currency conversion",
        f"goods {goods_total_twd} + freight {freight_twd} + insurance {insurance_twd} "
        f"+ duty {duty_total_twd} = {grand_total_twd}",
        grand_total_twd,
        unit="TWD",
        note=incoterm.plain_summary(),
    )

    # --- currency ---------------------------------------------------------
    rate_row = None
    if version.currency != settings.base_currency:
        rate_row = version.exchange_rate or rates.find_exchange_rate(
            session, settings.base_currency, version.currency, on_date=on_date
        )
        if rate_row is None:
            raise PricingError(
                f"No published exchange rate from {settings.base_currency} to "
                f"{version.currency} on or before {on_date}. The quote cannot be priced."
            )
        if version.exchange_rate_id != rate_row.id:
            version.exchange_rate_id = rate_row.id
            version.exchange_rate_locked_at = dt.datetime.now(dt.timezone.utc)

    def to_quote_currency(amount: Decimal) -> Decimal:
        if rate_row is None:
            return money(amount)
        return money(dec(amount) * rate_row.rate)

    for line, _ in priceable:
        line.unit_price = to_quote_currency(line.unit_price)
        line.extended_price = to_quote_currency(line.extended_price)
        line.unit_cost = to_quote_currency(line.unit_cost)
        line.freight_share = to_quote_currency(line.freight_share)
        line.insurance_share = to_quote_currency(line.insurance_share)
        line.duty_amount = to_quote_currency(line.duty_amount)
        line.landed_total = money(
            line.extended_price + line.freight_share + line.insurance_share + line.duty_amount
        )

    goods_total = to_quote_currency(goods_total_twd)
    freight_total = to_quote_currency(freight_twd)
    insurance_total = to_quote_currency(insurance_twd)
    duty_total = to_quote_currency(duty_total_twd)
    grand_total = money(goods_total + freight_total + insurance_total + duty_total)
    total_cost = to_quote_currency(cost_total_twd)
    if rate_row is not None:
        rates.convert(grand_total_twd, rate_row, totals_trace, label="Quote total in quote currency")

    overall_margin = (
        percent((goods_total - total_cost) / goods_total * Decimal("100"))
        if goods_total > 0
        else ZERO
    )
    totals_trace.add(
        "Margin on the whole quote",
        f"(goods {goods_total} - cost {total_cost}) / goods {goods_total} x 100 = {overall_margin}%",
        overall_margin,
        unit="%",
    )

    version.goods_total = goods_total
    version.freight_total = freight_total
    version.insurance_total = insurance_total
    version.duty_total = duty_total
    version.grand_total = grand_total
    version.total_cost = total_cost
    version.margin_percent = overall_margin
    version.tariff_table_id = tariff_table.id if tariff_table else None
    version.valid_until = on_date + dt.timedelta(days=settings.quote_validity_days)
    version.totals_trace = totals_trace.to_dict()
    if duty_table_gaps:
        version.needs_repricing = True
        version.repricing_reason = (
            f"No duty rate for {count(len(duty_table_gaps), 'line')} in table "
            f"{tariff_table.version if tariff_table else 'none'}"
        )
    else:
        version.needs_repricing = False
        version.repricing_reason = ""
    version.pricing_checksum = pricing_checksum(version)

    if tariff_table is not None and not tariff_table.is_signed_off and incoterm.seller_pays_import_duty:
        warnings.append(
            f"Duty table {tariff_table.version} has not been signed off by a customs "
            "broker, so the duty on this quote is provisional."
        )

    return PricingReport(
        priced_lines=priced,
        skipped_lines=skipped,
        goods_total=goods_total,
        freight_total=freight_total,
        insurance_total=insurance_total,
        duty_total=duty_total,
        grand_total=grand_total,
        total_cost=total_cost,
        margin_percent=overall_margin,
        currency=version.currency,
        warnings=list(dict.fromkeys(warnings)),
        totals_trace=totals_trace.to_dict(),
        duty_table_gaps=duty_table_gaps,
    )


def _write_line(
    line: QuoteLine,
    result: LinePricing,
    freight_share: Decimal,
    insurance_share: Decimal,
    duty: Decimal,
    breakdown: list[dict[str, Any]],
) -> None:
    line.quantity_billed = result.quantity_billed
    line.unit_of_sale = result.unit_of_sale
    line.rounding_note = result.rounding_note[:255]
    line.unit_price = result.unit_price
    line.price_source = result.price_source
    line.price_source_reference = result.price_source_reference[:80]
    line.discount_percent = result.discount_percent
    line.extended_price = result.extended_price
    line.unit_cost = result.unit_cost
    line.margin_percent = result.margin_percent
    line.below_margin_floor = result.below_margin_floor
    line.freight_share = freight_share
    line.insurance_share = insurance_share
    line.duty_amount = duty
    line.duty_breakdown = breakdown
    line.landed_total = money(
        result.extended_price + freight_share + insurance_share + duty
    )
    line.lead_time_days = result.lead_time_days
    line.fulfilment_options = result.fulfilment_options
    if not line.chosen_fulfilment and result.fulfilment_options:
        line.chosen_fulfilment = result.fulfilment_options[0]["code"]
    line.calculation_trace = result.trace.to_dict()
    if line.status == "matched":
        line.status = "priced"


# ---------------------------------------------------------------------------
# Integrity: the model never writes a price
# ---------------------------------------------------------------------------
def canonical_amount(value: Any) -> str:
    """One spelling per number.

    Decimal("0.00") and Decimal("0") are the same number but different text,
    and the database does not rewrite a column whose value compares equal. A
    fingerprint built from raw text would then report a difference where there
    is none, which would block every quote for no reason.
    """
    quantised = dec(value).quantize(Decimal("0.000001"))
    text = format(quantised, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def pricing_checksum(version: QuoteVersion) -> str:
    """A fingerprint of every number the engine produced for this version."""
    payload = {
        "version": version.version_number,
        "currency": version.currency,
        "incoterm": version.incoterm,
        "goods_total": canonical_amount(version.goods_total),
        "freight_total": canonical_amount(version.freight_total),
        "insurance_total": canonical_amount(version.insurance_total),
        "duty_total": canonical_amount(version.duty_total),
        "grand_total": canonical_amount(version.grand_total),
        "lines": [
            {
                "line": line.line_number,
                "sku": line.product.sku if line.product else "",
                "quantity": canonical_amount(line.quantity_billed),
                "unit_price": canonical_amount(line.unit_price),
                "extended": canonical_amount(line.extended_price),
                "duty": canonical_amount(line.duty_amount),
            }
            for line in sorted(version.lines, key=lambda line: line.line_number)
        ],
    }
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


@dataclass(slots=True)
class IntegrityReport:
    ok: bool
    stored_checksum: str
    recomputed_checksum: str
    differences: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "stored_checksum": self.stored_checksum,
            "recomputed_checksum": self.recomputed_checksum,
            "differences": self.differences,
            "statement": (
                "Every price on this quote equals the pricing engine's own output."
                if self.ok
                else "At least one figure on this quote does not match the pricing "
                "engine. The quote cannot be approved or sent."
            ),
        }


def verify_pricing_integrity(session: Session, version: QuoteVersion) -> IntegrityReport:
    """Re-run the engine and compare, line by line, before anything is sent.

    This is what makes the claim "the model never writes a price" checkable
    rather than a promise.
    """
    stored = {
        line.line_number: {
            "unit_price": canonical_amount(line.unit_price),
            "extended_price": canonical_amount(line.extended_price),
            "quantity_billed": canonical_amount(line.quantity_billed),
        }
        for line in version.lines
    }
    stored_totals = {
        "goods_total": canonical_amount(version.goods_total),
        "grand_total": canonical_amount(version.grand_total),
        "duty_total": canonical_amount(version.duty_total),
    }
    stored_checksum = version.pricing_checksum

    session.expire_all()
    refreshed = session.get(QuoteVersion, version.id)
    assert refreshed is not None
    report = price_quote_version(session, refreshed)
    recomputed_checksum = refreshed.pricing_checksum

    differences: list[dict[str, str]] = []
    for line in refreshed.lines:
        before = stored.get(line.line_number)
        if before is None:
            continue
        for field_name, value in (
            ("unit_price", canonical_amount(line.unit_price)),
            ("extended_price", canonical_amount(line.extended_price)),
            ("quantity_billed", canonical_amount(line.quantity_billed)),
        ):
            if before[field_name] != value:
                differences.append(
                    {
                        "where": f"line {line.line_number}",
                        "field": field_name.replace("_", " "),
                        "stored": before[field_name],
                        "engine": value,
                    }
                )
    for field_name, value in (
        ("goods_total", canonical_amount(report.goods_total)),
        ("grand_total", canonical_amount(report.grand_total)),
        ("duty_total", canonical_amount(report.duty_total)),
    ):
        if stored_totals[field_name] != value:
            differences.append(
                {
                    "where": "quote total",
                    "field": field_name.replace("_", " "),
                    "stored": stored_totals[field_name],
                    "engine": value,
                }
            )

    return IntegrityReport(
        ok=not differences and stored_checksum in ("", recomputed_checksum),
        stored_checksum=stored_checksum,
        recomputed_checksum=recomputed_checksum,
        differences=differences,
    )
