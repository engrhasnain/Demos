"""Asking a supplier for a price, without stopping the rest of the quote.

A forty line bill of materials with two parts Hengtai does not stock should not
wait four days. Those two lines are marked as waiting for a supplier, the sub
request goes out, and the other thirty-eight carry on and get priced. When the
supplier answers, those two lines are priced with Hengtai's own margin on top
and the quote completes.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import dec, money, percent
from ..models import Case, QuoteLine, QuoteVersion, Supplier, SupplierRequest
from ..text import count

#: Margin Hengtai adds to a bought-in part when it has no standard cost.
DEFAULT_BUY_IN_MARGIN_PERCENT = Decimal("28")


@dataclass(slots=True)
class SupplierResponse:
    unit_price: Decimal
    currency: str
    lead_time_days: int
    minimum_order_quantity: int
    valid_until: str = ""
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_price": str(self.unit_price),
            "currency": self.currency,
            "lead_time_days": self.lead_time_days,
            "minimum_order_quantity": self.minimum_order_quantity,
            "valid_until": self.valid_until,
            "note": self.note,
        }


def choose_supplier(session: Session, line: QuoteLine) -> Supplier | None:
    if line.product is not None and line.product.supplier is not None:
        return line.product.supplier
    # A line with no catalogue part goes to the most reliable Taiwan supplier.
    return session.scalar(
        select(Supplier)
        .where(Supplier.country == "TW")
        .order_by(Supplier.reliability_percent.desc())
        .limit(1)
    )


def next_reference(session: Session, case: Case) -> str:
    count = session.scalar(
        select(SupplierRequest).where(SupplierRequest.case_id == case.id).order_by(
            SupplierRequest.id.desc()
        )
    )
    sequence = 1 if count is None else int(count.reference.rsplit("-", 1)[-1]) + 1
    return f"{case.reference}-S{sequence:02d}"


def compose_request_email(case: Case, lines: list[QuoteLine], reference: str) -> tuple[str, str]:
    body = [
        "Dear supplier,",
        "",
        f"Please quote the following for our enquiry {case.reference} "
        f"(our sub request {reference}).",
        "",
    ]
    for line in lines:
        quantity = line.requested_quantity
        body.append(
            f"- Line {line.line_number}: {line.request_text} "
            f"- quantity {quantity} {line.requested_unit}"
        )
    body += [
        "",
        "Please confirm unit price, currency, minimum order quantity, lead time in "
        "days, and how long the price holds.",
        "",
        "Kind regards,",
        "Hengtai Industrial Supply - purchasing",
    ]
    return f"Price request {reference} - {count(len(lines), 'item')}", "\n".join(body)


def create_request(
    session: Session, case: Case, lines: list[QuoteLine], supplier: Supplier
) -> SupplierRequest:
    request = SupplierRequest(
        case_id=case.id,
        supplier_id=supplier.id,
        reference=next_reference(session, case),
        line_numbers=[line.line_number for line in lines],
        status="sent",
    )
    session.add(request)
    for line in lines:
        line.status = "awaiting_supplier"
        line.blocking_reason = (
            f"Waiting for a price from {supplier.name}. The rest of the quote carries on."
        )
    session.flush()
    return request


def record_response(
    session: Session, request: SupplierRequest, response: SupplierResponse
) -> SupplierRequest:
    request.response = response.to_dict()
    request.status = "answered"
    request.responded_at = dt.datetime.now(dt.timezone.utc)
    session.flush()
    return request


def apply_response(
    session: Session,
    version: QuoteVersion,
    request: SupplierRequest,
    response: SupplierResponse,
    *,
    exchange_rate_to_base: Decimal | None = None,
    margin_percent: Decimal = DEFAULT_BUY_IN_MARGIN_PERCENT,
) -> list[dict[str, Any]]:
    """Price the waiting lines from the supplier's answer, with margin on top.

    The supplier's price is a cost, not a selling price. It is converted into
    Taiwan dollars, Hengtai's margin is applied, and the result goes through the
    same pricing engine fields as every other line, so nothing about these lines
    is special-cased later.
    """
    cost_in_base = dec(response.unit_price)
    if response.currency != "TWD":
        if exchange_rate_to_base is None:
            raise ValueError(
                f"The supplier quoted in {response.currency} and no rate to Taiwan "
                "dollars is available, so the line cannot be priced."
            )
        cost_in_base = money(cost_in_base * exchange_rate_to_base)

    selling = money(cost_in_base / ((Decimal("100") - margin_percent) / Decimal("100")))
    applied: list[dict[str, Any]] = []

    for line in version.lines:
        if line.line_number not in (request.line_numbers or []):
            continue
        if line.product is not None:
            # Keep the catalogue record but use the live supplier cost.
            line.unit_cost = cost_in_base
        line.unit_price = selling
        line.price_source = "supplier_quote"
        line.price_source_reference = f"{request.reference} / {request.supplier.name}"
        line.quantity_billed = dec(line.requested_quantity)
        if response.minimum_order_quantity > line.quantity_billed:
            line.quantity_billed = dec(response.minimum_order_quantity)
            line.rounding_note = (
                f"Raised to the supplier minimum of {response.minimum_order_quantity} pieces."
            )
        line.extended_price = money(selling * line.quantity_billed)
        line.unit_cost = cost_in_base
        line.margin_percent = percent(margin_percent)
        line.below_margin_floor = False
        line.lead_time_days = response.lead_time_days
        line.status = "priced"
        line.blocking_reason = ""
        line.fulfilment_options = [
            {
                "code": "buy_in",
                "label": "Buy in from the supplier",
                "detail": (
                    f"{request.supplier.name} quoted {response.unit_price} "
                    f"{response.currency} per piece with a {response.lead_time_days} day "
                    "lead time."
                ),
                "ready_date": (
                    dt.date.today() + dt.timedelta(days=response.lead_time_days)
                ).isoformat(),
                "lead_time_days": response.lead_time_days,
                "warehouse": "TAICHUNG",
                "split": False,
            }
        ]
        line.chosen_fulfilment = "buy_in"
        line.calculation_trace = {
            "subject": f"Line {line.line_number}: bought in",
            "steps": [
                {
                    "label": "Supplier cost",
                    "formula": f"{response.unit_price} {response.currency} per piece",
                    "result": str(cost_in_base),
                    "unit": "TWD per piece",
                    "note": response.note,
                    "inputs": [
                        {
                            "label": "Supplier",
                            "value": request.supplier.name,
                            "source": request.reference,
                            "source_kind": "request",
                            "source_id": str(request.id),
                        }
                    ],
                },
                {
                    "label": "Selling price",
                    "formula": (
                        f"{cost_in_base} / (1 - {margin_percent}%) = {selling}"
                    ),
                    "result": str(selling),
                    "unit": "TWD per piece",
                    "note": "Hengtai's standard margin for bought-in parts.",
                    "inputs": [],
                },
                {
                    "label": "Line value",
                    "formula": f"{selling} x {line.quantity_billed} = {line.extended_price}",
                    "result": str(line.extended_price),
                    "unit": "TWD",
                    "note": line.rounding_note,
                    "inputs": [],
                },
            ],
        }
        applied.append(
            {
                "line_number": line.line_number,
                "unit_price": str(selling),
                "lead_time_days": response.lead_time_days,
            }
        )

    session.flush()
    return applied


def open_requests(session: Session, case: Case) -> list[SupplierRequest]:
    return list(
        session.scalars(
            select(SupplierRequest).where(
                SupplierRequest.case_id == case.id, SupplierRequest.status == "sent"
            )
        )
    )
