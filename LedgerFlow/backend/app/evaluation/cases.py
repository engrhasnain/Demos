"""Test invoices with a known right answer.

Nothing here is hand written. Every case is printed from a real supplier, a
real order and a real delivery, so the answer we are checking against is the
database's own answer rather than a number somebody typed into a fixture.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import dec, money
from ..models import Entity, GoodsReceiptLine, PurchaseOrder, PurchaseOrderLine, Vendor
from ..seed.invoices import TODAY, _render


@dataclass(slots=True)
class Case:
    """One document plus the answer it should produce."""

    key: str
    filename: str
    text: str
    barcode_payload: str = ""
    received_from: str = ""
    kind: str = "bill"

    #: What the reading step should come back with.
    header_truth: dict[str, str] = field(default_factory=dict)
    line_truth: list[dict[str, str]] = field(default_factory=list)

    #: What the checking step should come back with.
    expect_duplicate: bool = False
    expect_bank_block: bool = False
    expect_clean: bool = False

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")


def _delivered(session: Session, line: PurchaseOrderLine) -> Decimal:
    rows = session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.purchase_order_line_id == line.id)
    )
    return sum((dec(row.quantity_received) for row in rows), Decimal("0"))


def _usable_orders(session: Session, wanted: int) -> list[tuple[PurchaseOrder, list[dict[str, Any]]]]:
    """Orders with something delivered, billed for exactly what arrived."""
    out: list[tuple[PurchaseOrder, list[dict[str, Any]]]] = []
    for order in session.scalars(
        select(PurchaseOrder)
        .where(PurchaseOrder.entity_code == "TW", PurchaseOrder.status == "open")
        .order_by(PurchaseOrder.id)
    ):
        if order.vendor is None or order.vendor.bank_change_pending:
            continue
        lines: list[dict[str, Any]] = []
        for line in order.lines:
            quantity = _delivered(session, line)
            if quantity <= 0:
                continue
            price = dec(line.unit_price)
            lines.append(
                {
                    "part_code": line.part_code,
                    "description": line.description,
                    "quantity": quantity,
                    "unit_price": price,
                    "amount": money(quantity * price),
                }
            )
        if not lines:
            continue
        out.append((order, lines))
        if len(out) >= wanted:
            break
    return out


def build_cases(
    session: Session,
    *,
    clean_count: int = 120,
    duplicate_count: int = 40,
    bank_change_count: int = 20,
    seed: int = 20261006,
) -> list[Case]:
    """The measured set: ordinary invoices, planted repeats, planted fraud."""
    random.seed(seed)
    taiwan = session.get(Entity, "TW")
    if taiwan is None:
        raise RuntimeError("No Taiwan entity; load the demonstration data first.")

    orders = _usable_orders(session, clean_count + bank_change_count)
    if not orders:
        raise RuntimeError("No orders with deliveries; load the demonstration data first.")

    cases: list[Case] = []
    counter = 900000

    # ---------------------------------------------------- ordinary invoices
    clean: list[Case] = []
    for order, lines in orders[:clean_count]:
        counter += 1
        number = f"EV-{counter}"
        invoice_date = TODAY - dt.timedelta(days=random.randint(1, 25))
        vendor = order.vendor
        text, net, tax, total = _render(
            vendor=vendor,
            entity=taiwan,
            number=number,
            invoice_date=invoice_date,
            order_number=order.number,
            lines=lines,
            bank_account=(
                vendor.bank_accounts[0].account_number if vendor.bank_accounts else ""
            ),
        )
        case = Case(
            key=f"clean_{counter}",
            filename=f"{number}.pdf",
            text=text,
            received_from=vendor.email,
            header_truth={
                "invoice_number": number,
                "invoice_date": invoice_date.isoformat(),
                "purchase_order_number": order.number,
                "seller_tax_identifier": vendor.tax_identifier,
                "buyer_tax_identifier": taiwan.tax_identifier,
                "net_amount": str(net),
                "tax_amount": str(tax),
                "total_amount": str(total),
            },
            line_truth=[
                {
                    "part_code": row["part_code"],
                    "quantity": str(row["quantity"]),
                    "unit_price": str(row["unit_price"]),
                    "line_total": str(row["amount"]),
                }
                for row in lines
            ],
            expect_clean=True,
        )
        cases.append(case)
        clean.append(case)

    # ------------------------------------------------- planted repeats
    # Each one is a real earlier invoice sent again, disguised the way they
    # arrive in life: a different file name, the number written another way,
    # a date a day out, or the whole thing re-sent untouched.
    for position in range(duplicate_count):
        source = clean[position % len(clean)]
        disguise = position % 4
        text = source.text
        number = source.header_truth["invoice_number"]
        if disguise == 1:
            text = text.replace(f"Invoice No: {number}", f"Invoice No: {number.split('-')[-1]}")
        elif disguise == 2:
            text = text.replace("INVOICE", "INVOICE - COPY", 1)
        elif disguise == 3:
            original = source.header_truth["invoice_date"]
            shifted = (dt.date.fromisoformat(original) + dt.timedelta(days=1)).isoformat()
            text = text.replace(f"Invoice Date: {original}", f"Invoice Date: {shifted}")
            text = text.replace(f"Invoice No: {number}", f"Invoice No: {number} R1")
        cases.append(
            Case(
                key=f"duplicate_{position}",
                filename=f"reminder-{position}-{source.filename}",
                text=text,
                received_from=source.received_from,
                expect_duplicate=True,
            )
        )

    # --------------------------------------------- planted bank changes
    for position, (order, lines) in enumerate(orders[clean_count:]):
        if position >= bank_change_count:
            break
        counter += 1
        number = f"EV-{counter}"
        vendor = order.vendor
        text, _net, _tax, _total = _render(
            vendor=vendor,
            entity=taiwan,
            number=number,
            invoice_date=TODAY - dt.timedelta(days=2),
            order_number=order.number,
            lines=lines,
            bank_account=f"77{random.randint(100000000, 999999999)}",
        )
        cases.append(
            Case(
                key=f"bank_change_{position}",
                filename=f"{number}.pdf",
                text=text + "\n\nPlease update your records with our new account.",
                received_from=vendor.email,
                expect_bank_block=True,
            )
        )

    return cases


def retry_cases(session: Session, *, count: int = 50) -> list[Case]:
    """Ordinary invoices used only to crash the ledger halfway through."""
    taiwan = session.get(Entity, "TW")
    if taiwan is None:
        raise RuntimeError("No Taiwan entity; load the demonstration data first.")
    cases: list[Case] = []
    counter = 700000
    for order, lines in _usable_orders(session, count):
        counter += 1
        number = f"RT-{counter}"
        vendor = order.vendor
        text, _net, _tax, _total = _render(
            vendor=vendor,
            entity=taiwan,
            number=number,
            invoice_date=TODAY - dt.timedelta(days=4),
            order_number=order.number,
            lines=lines,
            bank_account=(
                vendor.bank_accounts[0].account_number if vendor.bank_accounts else ""
            ),
        )
        cases.append(
            Case(
                key=f"retry_{counter}",
                filename=f"{number}.pdf",
                text=text,
                received_from=vendor.email,
            )
        )
    return cases
