"""Matching an invoice to what was ordered and what actually arrived.

The three-way match. For every line:

1. find the order line it belongs to;
2. add up everything that has been **delivered** against that order line, and
   everything that has already been **billed** against it;
3. the payable quantity is whatever is left of the delivery that has not been
   billed yet, and never more than the invoice asks for;
4. the price is checked against the order, within the supplier's tolerance;
5. anything not on the order at all is either inside the supplier's allowance
   for things like freight, or it is held.

A supplier who invoices ten thousand pieces when three thousand have arrived
gets paid for three thousand. That is the single most useful thing in this
module and the reason it is arithmetic rather than judgement.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import Trace, TraceInput, ZERO, dec, money, percent
from ..models import (
    GoodsReceiptLine,
    Invoice,
    InvoiceLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
)

#: Statuses whose lines count as already billed against an order.
COUNTS_AS_BILLED = ("posted", "approved", "awaiting_approval", "checked")


@dataclass(slots=True)
class LineOutcome:
    line: InvoiceLine
    result: str
    payable_quantity: Decimal
    payable_amount: Decimal
    held_amount: Decimal
    note: str
    trace: Trace


@dataclass(slots=True)
class MatchResult:
    purchase_order: PurchaseOrder | None
    payable_total: Decimal
    held_total: Decimal
    findings: list[dict[str, Any]] = field(default_factory=list)
    outcomes: list[LineOutcome] = field(default_factory=list)
    trace: Trace | None = None

    def add(self, kind: str, summary: str, **detail: Any) -> None:
        self.findings.append({"kind": kind, "summary": summary, "detail": detail})


# ---------------------------------------------------------------------------
# Finding the order
# ---------------------------------------------------------------------------
def find_purchase_order(
    session: Session, invoice: Invoice, vendor: Vendor | None
) -> PurchaseOrder | None:
    """By the number on the invoice, or by the only open order for that supplier."""
    number = (invoice.purchase_order_number_read or "").strip()
    if number:
        order = session.scalar(
            select(PurchaseOrder).where(PurchaseOrder.number == number.upper())
        )
        if order is not None:
            return order

    if vendor is None:
        return None
    open_orders = list(
        session.scalars(
            select(PurchaseOrder).where(
                PurchaseOrder.vendor_id == vendor.id, PurchaseOrder.status == "open"
            )
        )
    )
    return open_orders[0] if len(open_orders) == 1 else None


# ---------------------------------------------------------------------------
# Cumulative delivery and billing
# ---------------------------------------------------------------------------
def _count(many: int, noun: str) -> str:
    """``1 line`` rather than ``1 line(s)``."""
    return f"{many} {noun}" if many == 1 else f"{many} {noun}s"


def received_to_date(session: Session, order_line: PurchaseOrderLine) -> Decimal:
    rows = session.scalars(
        select(GoodsReceiptLine).where(
            GoodsReceiptLine.purchase_order_line_id == order_line.id
        )
    )
    return sum((dec(row.quantity_received) for row in rows), ZERO)


def billed_to_date(
    session: Session, order_line: PurchaseOrderLine, *, excluding_invoice_id: int
) -> Decimal:
    rows = session.execute(
        select(InvoiceLine, Invoice)
        .join(Invoice, InvoiceLine.invoice_id == Invoice.id)
        .where(
            InvoiceLine.purchase_order_line_id == order_line.id,
            InvoiceLine.invoice_id != excluding_invoice_id,
            Invoice.status.in_(COUNTS_AS_BILLED),
            Invoice.kind == "bill",
        )
    ).all()
    return sum((dec(line.payable_quantity) for line, _invoice in rows), ZERO)


# ---------------------------------------------------------------------------
# Matching one line to an order line
# ---------------------------------------------------------------------------
def _normalise(text: str) -> str:
    return "".join(ch for ch in (text or "").upper() if ch.isalnum())


def pair_lines(
    invoice_lines: list[InvoiceLine], order_lines: list[PurchaseOrderLine]
) -> dict[int, PurchaseOrderLine]:
    """Pair invoice lines with order lines: part code first, then wording."""
    by_part: dict[str, list[PurchaseOrderLine]] = {}
    by_text: dict[str, list[PurchaseOrderLine]] = {}
    for order_line in order_lines:
        if order_line.part_code:
            by_part.setdefault(_normalise(order_line.part_code), []).append(order_line)
        by_text.setdefault(_normalise(order_line.description), []).append(order_line)

    used: set[int] = set()
    pairs: dict[int, PurchaseOrderLine] = {}

    def take(bucket: dict[str, list[PurchaseOrderLine]], key: str):
        for candidate in bucket.get(key, []):
            if candidate.id not in used:
                return candidate
        return None

    for line in invoice_lines:
        found = take(by_part, _normalise(line.part_code)) if line.part_code else None
        if found is None:
            found = take(by_text, _normalise(line.description))
        if found is None:
            # A description that contains the order's wording, or the reverse.
            target = _normalise(line.description)
            for order_line in order_lines:
                if order_line.id in used:
                    continue
                other = _normalise(order_line.description)
                if other and (other in target or target in other):
                    found = order_line
                    break
        if found is not None:
            used.add(found.id)
            pairs[line.id] = found
    return pairs


# ---------------------------------------------------------------------------
# The match
# ---------------------------------------------------------------------------
def match(
    session: Session,
    invoice: Invoice,
    *,
    vendor: Vendor | None,
    order: PurchaseOrder | None,
) -> MatchResult:
    overall = Trace("What is payable on this invoice")
    result = MatchResult(purchase_order=order, payable_total=ZERO, held_total=ZERO)

    tolerance_percent = dec(vendor.tolerance_percent) if vendor else Decimal("2")
    tolerance_absolute = dec(vendor.tolerance_absolute) if vendor else Decimal("500")
    unordered_allowance = dec(vendor.unordered_allowance) if vendor else Decimal("1000")

    if order is None:
        # Nothing to match against, so nothing is automatically payable.
        for line in invoice.lines:
            trace = Trace(f"Line {line.line_number}")
            trace.add(
                "No purchase order",
                "there is no order to check this against",
                money(line.line_total),
                note="The whole line is held until somebody confirms it.",
            )
            result.outcomes.append(
                LineOutcome(
                    line=line,
                    result="not_ordered",
                    payable_quantity=ZERO,
                    payable_amount=ZERO,
                    held_amount=money(line.line_total),
                    note="No purchase order to check against.",
                    trace=trace,
                )
            )
            result.held_total += money(line.line_total)
        result.add(
            "no_purchase_order",
            "Nothing to check it against",
            number_on_invoice=invoice.purchase_order_number_read,
        )
        result.trace = overall
        return result

    pairs = pair_lines(list(invoice.lines), list(order.lines))
    unordered_total = ZERO
    over_tolerance_lines: list[int] = []
    partly_received_lines: list[int] = []
    not_received_lines: list[int] = []

    for line in invoice.lines:
        order_line = pairs.get(line.id)
        trace = Trace(f"Line {line.line_number}: {line.description[:50]}")

        # ---------------------------------------------------- not ordered
        if order_line is None:
            amount = money(line.line_total)
            unordered_total += amount
            inside = unordered_total <= unordered_allowance
            trace.add(
                "Not on the order",
                f"{amount} of charges not on order {order.number}",
                amount,
                inputs=[
                    TraceInput(
                        "Allowance for this supplier",
                        str(money(unordered_allowance)),
                        vendor.name if vendor else "company default",
                        "policy",
                        str(vendor.id) if vendor else "",
                    )
                ],
                note=(
                    "Inside the allowance, so it is accepted."
                    if inside
                    else "Above the allowance, so it is held."
                ),
            )
            result.outcomes.append(
                LineOutcome(
                    line=line,
                    result="not_ordered",
                    payable_quantity=dec(line.quantity),
                    payable_amount=amount if inside else ZERO,
                    held_amount=ZERO if inside else amount,
                    note=(
                        f"Not on the order, but inside the {money(unordered_allowance)} "
                        "allowance."
                        if inside
                        else f"Not on the order and above the "
                        f"{money(unordered_allowance)} allowance."
                    ),
                    trace=trace,
                )
            )
            if inside:
                result.payable_total += amount
            else:
                result.held_total += amount
                over_tolerance_lines.append(line.line_number)
            continue

        line.purchase_order_line_id = order_line.id

        # ------------------------------------------------------- the price
        ordered_price = dec(order_line.unit_price)
        invoiced_price = dec(line.unit_price)
        difference = money(invoiced_price - ordered_price)
        allowed = max(
            money(ordered_price * tolerance_percent / Decimal("100")),
            tolerance_absolute / max(dec(line.quantity) or Decimal("1"), Decimal("1")),
        )
        price_ok = difference <= allowed

        trace.add(
            "Price against the order",
            f"invoice {invoiced_price}, order {ordered_price}, difference {difference}",
            difference,
            inputs=[
                TraceInput(
                    "Order",
                    f"{order.number} line {order_line.line_number}",
                    f"Purchase order {order.number}",
                    "purchase_order",
                    str(order.id),
                ),
                TraceInput(
                    "Tolerance",
                    f"{tolerance_percent}% or {money(tolerance_absolute)}",
                    vendor.name if vendor else "company default",
                    "policy",
                    str(vendor.id) if vendor else "",
                ),
            ],
            note="Within tolerance." if price_ok else "Above what the order allows.",
        )

        # --------------------------------------------- delivered and billed
        delivered = received_to_date(session, order_line)
        already = billed_to_date(session, order_line, excluding_invoice_id=invoice.id)
        available = max(delivered - already, ZERO)
        invoiced_quantity = dec(line.quantity)
        payable_quantity = min(invoiced_quantity, available)

        trace.add(
            "Delivered so far",
            f"{delivered} received, {already} already billed, so {available} may be billed",
            available,
            unit=line.unit,
            inputs=[
                TraceInput(
                    "Goods receipts",
                    f"{delivered} against order line {order_line.line_number}",
                    f"Purchase order {order.number}",
                    "goods_receipt",
                    str(order_line.id),
                )
            ],
        )

        unit_for_payment = ordered_price if not price_ok else invoiced_price
        payable_amount = money(payable_quantity * unit_for_payment)
        held_amount = money(dec(line.line_total) - payable_amount)
        if held_amount < 0:
            held_amount = ZERO

        trace.add(
            "Payable on this line",
            f"{payable_quantity} x {unit_for_payment} = {payable_amount}",
            payable_amount,
            note=(
                ""
                if held_amount == 0
                else f"{held_amount} is held back."
            ),
        )

        if payable_quantity == 0 and invoiced_quantity > 0:
            outcome = "not_received"
            note = "Nothing has been delivered against this line yet."
            not_received_lines.append(line.line_number)
        elif payable_quantity < invoiced_quantity:
            outcome = "partly_received"
            note = (
                f"{payable_quantity} of {invoiced_quantity} has been delivered, so "
                f"{held_amount} is held."
            )
            partly_received_lines.append(line.line_number)
        elif not price_ok:
            outcome = "over_tolerance"
            note = (
                f"Invoiced at {invoiced_price} against {ordered_price} on the order. "
                f"Paid at the order price; {held_amount} held."
            )
            over_tolerance_lines.append(line.line_number)
        else:
            outcome = "matched"
            note = ""

        result.outcomes.append(
            LineOutcome(
                line=line,
                result=outcome,
                payable_quantity=payable_quantity,
                payable_amount=payable_amount,
                held_amount=held_amount,
                note=note,
                trace=trace,
            )
        )
        result.payable_total += payable_amount
        result.held_total += held_amount

    # --------------------------------------------------------- the findings
    if over_tolerance_lines:
        result.add(
            "over_tolerance",
            _count(len(over_tolerance_lines), "line") + " above the order",
            lines=over_tolerance_lines,
        )
    if not_received_lines:
        result.add(
            "not_received",
            _count(len(not_received_lines), "line") + " not delivered",
            lines=not_received_lines,
        )
    if partly_received_lines:
        result.add(
            "partly_received",
            _count(len(partly_received_lines), "line")
            + f" short, {money(result.held_total)} held",
            lines=partly_received_lines,
        )

    overall.add(
        "Payable in total",
        " + ".join(
            str(money(outcome.payable_amount))
            for outcome in result.outcomes
            if outcome.payable_amount
        )
        or "nothing",
        money(result.payable_total),
        unit=invoice.currency,
    )
    if result.held_total:
        overall.add(
            "Held back",
            f"{money(dec(invoice.total_amount))} invoiced less "
            f"{money(result.payable_total)} payable",
            money(result.held_total),
            unit=invoice.currency,
            note="Held until the rest arrives or the supplier corrects the invoice.",
        )

    result.payable_total = money(result.payable_total)
    result.held_total = money(result.held_total)
    result.trace = overall
    return result


def apply(result: MatchResult, invoice: Invoice) -> None:
    """Write the match onto the invoice and its lines."""
    for outcome in result.outcomes:
        line = outcome.line
        line.match_result = outcome.result
        line.payable_quantity = outcome.payable_quantity
        line.payable_amount = outcome.payable_amount
        line.held_amount = outcome.held_amount
        line.note = outcome.note[:255]
        line.calculation_trace = outcome.trace.to_dict()

    invoice.purchase_order_id = result.purchase_order.id if result.purchase_order else None
    invoice.approved_amount = result.payable_total
    invoice.held_amount = result.held_total
    if result.held_total > 0:
        reasons = {o.result for o in result.outcomes if o.held_amount > 0}
        invoice.hold_reason = ", ".join(sorted(r.replace("_", " ") for r in reasons))[:255]
    else:
        invoice.hold_reason = ""
    if result.trace is not None:
        invoice.calculation_trace = result.trace.to_dict()
