"""The batch the demonstration runs on.

Twelve documents, each one chosen because it breaks a prototype:

1.  a clean order-backed invoice that should post with nobody touching it
2.  a photograph taken on a telephone, with the text crooked and spaced out
3.  a Taiwan uniform invoice on paper
4.  the same kind of invoice as electronic data, with its square barcode
5.  a four page forwarder statement with a subtotal on every page
6.  an invoice for the whole order when only part of it has arrived
7.  one of the above sent again as "0042" instead of "INV-0042"
8.  an invoice asking to be paid into a different bank account
9.  a credit note against an earlier bill
10. a uniform invoice made out to the wrong business number
11. a freight charge that is not on the order, inside the supplier's allowance
12. an invoice in United States dollars billed to the Taiwan company

Every one is built from the generated suppliers, orders and deliveries, so the
figures on them are real figures and the matching has something true to check.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.uniforminvoice import build_barcode, normalise_uniform_invoice_number
from ..clock import today
from ..money import dec, money
from ..models import (
    Entity,
    GoodsReceiptLine,
    PurchaseOrder,
    PurchaseOrderLine,
    Vendor,
)

TODAY = today()


@dataclass(slots=True)
class SampleDocument:
    key: str
    title: str
    what_it_tests: str
    filename: str
    content_type: str
    text: str
    barcode_payload: str = ""
    received_from: str = ""
    kind: str = "bill"
    expect: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def content(self) -> bytes:
        return self.text.encode("utf-8")


# ---------------------------------------------------------------------------
# Finding orders in a known state
# ---------------------------------------------------------------------------
def _delivered(session: Session, line: PurchaseOrderLine) -> Decimal:
    rows = session.scalars(
        select(GoodsReceiptLine).where(GoodsReceiptLine.purchase_order_line_id == line.id)
    )
    return sum((dec(row.quantity_received) for row in rows), Decimal("0"))


def _ordinary_orders(
    session: Session, entity: str, *, ceiling: Decimal, wanted: int
) -> list[tuple[PurchaseOrder, list[dict[str, Any]]]]:
    """Orders billed for exactly what arrived, and small enough to post on sight.

    These are the ordinary invoices: the ones nobody should have to look at.
    A demonstration made only of hard cases makes the product look like it
    never agrees with anything.
    """
    out: list[tuple[PurchaseOrder, list[dict[str, Any]]]] = []
    seen_vendors: set[int] = set()
    for order in session.scalars(
        select(PurchaseOrder)
        .where(PurchaseOrder.entity_code == entity, PurchaseOrder.status == "open")
        .order_by(PurchaseOrder.id)
        .limit(500)
    ):
        if order.vendor_id in seen_vendors or len(order.lines) > 3:
            continue
        lines: list[dict[str, Any]] = []
        value = Decimal("0")
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
            value += quantity * price
        if not lines or value <= 0 or value * Decimal("1.05") > ceiling:
            continue
        seen_vendors.add(order.vendor_id)
        out.append((order, lines))
        if len(out) >= wanted:
            break
    return out


def _orders_by_delivery(session: Session, entity: str) -> dict[str, PurchaseOrder]:
    """One order fully delivered, one part delivered, one not delivered."""
    found: dict[str, PurchaseOrder] = {}
    orders = list(
        session.scalars(
            select(PurchaseOrder)
            .where(PurchaseOrder.entity_code == entity, PurchaseOrder.status == "open")
            .order_by(PurchaseOrder.id)
            .limit(400)
        )
    )
    for order in orders:
        lines = list(order.lines)
        if not lines or len(lines) > 4:
            continue
        ratios = []
        for line in lines:
            ordered = dec(line.quantity_ordered)
            if ordered <= 0:
                continue
            ratios.append(_delivered(session, line) / ordered)
        if not ratios:
            continue
        lowest = min(ratios)
        if lowest >= Decimal("1") and "complete" not in found:
            found["complete"] = order
        elif Decimal("0.5") <= lowest < Decimal("0.95") and "partial" not in found:
            found["partial"] = order
        elif lowest == 0 and "none" not in found:
            found["none"] = order
        if len(found) == 3:
            break
    return found


def _order_with_deliveries(
    session: Session, *, exclude: set[int], entity: str = "TW"
) -> PurchaseOrder | None:
    """An order from a supplier nobody else in the batch is using.

    Picked by the delivery, not by the supplier, because a supplier whose
    goods have not arrived cannot be used to demonstrate anything except a
    delivery shortfall.
    """
    for order in session.scalars(
        select(PurchaseOrder)
        .where(PurchaseOrder.entity_code == entity, PurchaseOrder.status == "open")
        .order_by(PurchaseOrder.id)
    ):
        if order.vendor_id in exclude or order.vendor is None:
            continue
        if order.vendor.bank_change_pending:
            continue
        if any(_delivered(session, line) > 0 for line in order.lines):
            return order
    return None


def _delivered_lines(
    session: Session, order: PurchaseOrder | None, *, share: Decimal = Decimal("1")
) -> list[dict[str, Any]]:
    """Bill only what has actually arrived, so the three way match agrees.

    Most of the documents below exist to show one particular problem. If they
    also billed for goods that have not turned up, every one of them would
    carry a delivery exception on top, and the thing each is meant to
    demonstrate would be buried under it.
    """
    if order is None:
        return []
    out: list[dict[str, Any]] = []
    for line in order.lines:
        arrived = _delivered(session, line)
        quantity = (arrived * share).quantize(Decimal("1"))
        if quantity <= 0:
            continue
        price = dec(line.unit_price)
        out.append(
            {
                "part_code": line.part_code,
                "description": line.description,
                "quantity": quantity,
                "unit_price": price,
                "amount": money(quantity * price),
            }
        )
    return out


def _lines_for(session: Session, order: PurchaseOrder, *, share: Decimal) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in order.lines:
        quantity = (dec(line.quantity_ordered) * share).quantize(Decimal("1"))
        if quantity <= 0:
            continue
        out.append(
            {
                "part_code": line.part_code,
                "description": line.description,
                "quantity": quantity,
                "unit_price": dec(line.unit_price),
                "amount": money(quantity * dec(line.unit_price)),
            }
        )
    return out


def _render(
    *,
    vendor: Vendor,
    entity: Entity,
    number: str,
    invoice_date: dt.date,
    order_number: str,
    lines: list[dict[str, Any]],
    tax_percent: Decimal = Decimal("5"),
    currency: str = "TWD",
    bank_account: str = "",
    buyer_tax_identifier: str = "",
    extra_lines: list[dict[str, Any]] | None = None,
    spaced: bool = False,
) -> tuple[str, Decimal, Decimal, Decimal]:
    """Lay an invoice out the way a supplier's system would print it."""
    rows = list(lines) + list(extra_lines or [])
    net = money(sum((dec(row["amount"]) for row in rows), Decimal("0")))
    tax = money(net * tax_percent / Decimal("100")) if tax_percent else Decimal("0")
    total = money(net + tax)

    gap = "   " if spaced else " "
    body = [
        vendor.name_on_invoices or vendor.name,
        f"Seller tax id: {vendor.tax_identifier}",
        "",
        "INVOICE",
        f"Invoice No: {number}",
        f"Invoice Date: {invoice_date.isoformat()}",
        f"Purchase Order: {order_number}",
        f"Buyer tax id: {buyer_tax_identifier or entity.tax_identifier}",
        f"Currency: {currency}",
        "",
        "Item  Description                                        Qty    Unit price      Amount",
    ]
    for position, row in enumerate(rows, start=1):
        body.append(
            f"{position}.{gap}{row['part_code']} {row['description']}"
            f"{gap}{row['quantity']}{gap}{row['unit_price']}{gap}{row['amount']}"
        )
    body += [
        "",
        f"Subtotal: {net}",
        f"Business tax: {tax}",
        f"Total: {total}",
    ]
    if bank_account:
        body += ["", f"Bank account: {bank_account}"]
    return "\n".join(body), net, tax, total


# ---------------------------------------------------------------------------
# The batch
# ---------------------------------------------------------------------------
def build_batch(session: Session) -> list[SampleDocument]:
    taiwan = session.get(Entity, "TW")
    united_states = session.get(Entity, "US")
    assert taiwan is not None and united_states is not None

    orders = _orders_by_delivery(session, "TW")
    us_orders = _orders_by_delivery(session, "US")
    complete = orders.get("complete")
    partial = orders.get("partial")
    if complete is None or partial is None:
        raise RuntimeError("The generated data has no suitable orders; reload it.")

    documents: list[SampleDocument] = []

    # ----------------------------------------------- the ordinary ones
    ordinary = _ordinary_orders(session, "TW", ceiling=Decimal("180000"), wanted=8)
    if not ordinary:
        ordinary = [(complete, _lines_for(session, complete, share=Decimal("1")))]
    used_vendor_ids: set[int] = set()

    for position, (order, order_lines) in enumerate(ordinary, start=1):
        order_vendor = order.vendor
        used_vendor_ids.add(order_vendor.id)
        text_n, _n, _t, _total_n = _render(
            vendor=order_vendor,
            entity=taiwan,
            number=f"INV-20441{position}",
            invoice_date=TODAY - dt.timedelta(days=2 + position),
            order_number=order.number,
            lines=order_lines,
            bank_account=(
                order_vendor.bank_accounts[0].account_number
                if order_vendor.bank_accounts
                else ""
            ),
        )
        documents.append(
            SampleDocument(
                key="clean" if position == 1 else f"ordinary_{position}",
                title="An invoice that agrees with the order and the delivery",
                what_it_tests="Everything agrees, so it should reach the ledger untouched.",
                filename=f"INV-20441{position}.pdf",
                content_type="application/pdf",
                text=text_n,
                received_from=order_vendor.email,
                expect="posted untouched",
            )
        )

    # The hard cases below start from the first of those orders.
    complete = ordinary[0][0]
    vendor = complete.vendor
    lines = _lines_for(session, complete, share=Decimal("1"))

    # -------------------------------------------- 2. a telephone photograph
    order2 = _order_with_deliveries(session, exclude=used_vendor_ids)
    vendor2 = order2.vendor if order2 is not None else vendor
    used_vendor_ids.add(vendor2.id)
    photo_lines = _delivered_lines(session, order2) or lines
    text2, _n, _t, _total2 = _render(
        vendor=vendor2,
        entity=taiwan,
        number="INV-0042",
        invoice_date=TODAY - dt.timedelta(days=6),
        order_number=order2.number if order2 else complete.number,
        lines=photo_lines,
        spaced=True,
    )
    documents.append(
        SampleDocument(
            key="photograph",
            title="A photograph taken on a telephone",
            what_it_tests="Crooked spacing and no file structure; it still has to be read.",
            filename="IMG_4471.jpg",
            content_type="image/jpeg",
            text=text2,
            received_from=vendor2.email,
            expect="read and checked",
        )
    )

    # ----------------------------------------- 3. a paper uniform invoice
    order3 = _order_with_deliveries(session, exclude=used_vendor_ids)
    vendor3 = order3.vendor if order3 is not None else vendor
    used_vendor_ids.add(vendor3.id)
    uniform_lines = _delivered_lines(session, order3) or lines
    text3, net3, tax3, total3 = _render(
        vendor=vendor3,
        entity=taiwan,
        number="AB-45120073",
        invoice_date=TODAY - dt.timedelta(days=9),
        order_number=order3.number if order3 else complete.number,
        lines=uniform_lines,
    )
    documents.append(
        SampleDocument(
            key="uniform_paper",
            title="A uniform invoice on paper",
            what_it_tests="Two letters and eight digits, 5 per cent business tax, our業 number.",
            filename="AB-45120073.pdf",
            content_type="application/pdf",
            text=text3,
            received_from=vendor3.email,
            expect="read and checked",
        )
    )

    # ------------------------------- 4. the same, as data with a barcode
    order4 = _order_with_deliveries(session, exclude=used_vendor_ids)
    vendor4 = order4.vendor if order4 is not None else vendor
    used_vendor_ids.add(vendor4.id)
    e_lines = _delivered_lines(session, order4) or lines
    text4, net4, tax4, total4 = _render(
        vendor=vendor4,
        entity=taiwan,
        number="CD-88102294",
        invoice_date=TODAY - dt.timedelta(days=2),
        order_number=order4.number if order4 else complete.number,
        lines=e_lines,
    )
    barcode = build_barcode(
        invoice_number="CD-88102294",
        invoice_date=TODAY - dt.timedelta(days=2),
        random_code="7781",
        net_amount=net4,
        total_amount=total4,
        buyer_tax_identifier=taiwan.tax_identifier,
        seller_tax_identifier=vendor4.tax_identifier,
    )
    documents.append(
        SampleDocument(
            key="uniform_electronic",
            title="An electronic uniform invoice with its barcode",
            what_it_tests="The barcode is decoded by code and used as the truth.",
            filename="CD-88102294.xml",
            content_type="application/xml",
            text=text4,
            barcode_payload=barcode,
            received_from=vendor4.email,
            expect="read from the barcode",
        )
    )

    # -------------------------------- 5. a four page forwarder statement
    # The forwarder has to bill the company this statement is addressed to.
    # A freight bill sent to the wrong entity is a real exception, but it is
    # not the one this four page document is here to demonstrate.
    forwarder = (
        session.scalar(
            select(Vendor)
            .where(Vendor.name.like("%Logistics%"), Vendor.entity_code == "TW")
            .limit(1)
        )
        or session.scalar(
            select(Vendor).where(Vendor.entity_code == "TW", Vendor.country == "TW").limit(1)
        )
        or vendor
    )
    used_vendor_ids.add(forwarder.id)
    pages: list[str] = [
        forwarder.name_on_invoices or forwarder.name,
        f"Seller tax id: {forwarder.tax_identifier}",
        "",
        "STATEMENT OF CHARGES",
        "Invoice No: FWD-2026-0918",
        f"Invoice Date: {(TODAY - dt.timedelta(days=12)).isoformat()}",
        f"Buyer tax id: {taiwan.tax_identifier}",
        "Currency: TWD",
        "",
    ]
    running = Decimal("0")
    page_totals: list[Decimal] = []
    position = 0
    for page in range(1, 5):
        pages.append(f"Page {page} of 4")
        pages.append("Item  Description                              Qty   Unit price    Amount")
        page_total = Decimal("0")
        for entry in range(4):
            position += 1
            quantity = Decimal(str(1 + entry))
            price = money(Decimal(str(1850 + page * 230 + entry * 40)))
            amount = money(quantity * price)
            page_total += amount
            pages.append(
                f"{position}. FREIGHT-{page}{entry} Ocean freight consignment "
                f"{page}{entry} {quantity} {price} {amount}"
            )
        page_totals.append(money(page_total))
        running += page_total
        pages.append(f"Page subtotal: {money(page_total)}")
        pages.append("")
    net5 = money(running)
    tax5 = money(net5 * Decimal("5") / Decimal("100"))
    pages += [f"Subtotal: {net5}", f"Business tax: {tax5}", f"Total: {money(net5 + tax5)}"]
    documents.append(
        SampleDocument(
            key="forwarder_statement",
            title="A four page forwarder statement",
            what_it_tests="Every page has a subtotal, and they have to add to the total.",
            filename="FWD-2026-0918.pdf",
            content_type="application/pdf",
            text="\n".join(pages),
            received_from=forwarder.email,
            expect="read across four pages",
        )
    )

    # ------------------- 6. billed in full, only part of it has arrived
    partial_vendor = partial.vendor
    used_vendor_ids.add(partial_vendor.id)
    full_lines = _lines_for(session, partial, share=Decimal("1"))
    text6, _n6, _t6, total6 = _render(
        vendor=partial_vendor,
        entity=taiwan,
        number="INV-771204",
        invoice_date=TODAY - dt.timedelta(days=4),
        order_number=partial.number,
        lines=full_lines,
    )
    documents.append(
        SampleDocument(
            key="partial_delivery",
            title="Billed for the whole order when part of it has arrived",
            what_it_tests="Only the delivered part is payable; the rest is held.",
            filename="INV-771204.pdf",
            content_type="application/pdf",
            text=text6,
            received_from=partial_vendor.email,
            expect="part posted, part held",
        )
    )

    # ------------------------------------ 7. the same invoice, in disguise
    documents.append(
        SampleDocument(
            key="duplicate",
            title="The same invoice again, as a photograph, numbered 0042",
            what_it_tests="The same document under a different number and format.",
            filename="IMG_4480.jpg",
            content_type="image/jpeg",
            text=text2.replace("Invoice No: INV-0042", "Invoice No: 0042"),
            received_from=vendor2.email,
            expect="blocked as a duplicate",
        )
    )

    # ------------------------------------------------- 9. a credit note
    credit_lines = [
        {
            "part_code": lines[0]["part_code"],
            "description": "Returned goods, credit",
            "quantity": Decimal("50"),
            "unit_price": lines[0]["unit_price"],
            "amount": money(Decimal("50") * dec(lines[0]["unit_price"])),
        }
    ] if lines else []
    text9, _n9, _t9, total9 = _render(
        vendor=vendor,
        entity=taiwan,
        number="CN-204411",
        invoice_date=TODAY,
        order_number=complete.number,
        lines=credit_lines,
    )
    documents.append(
        SampleDocument(
            key="credit_note",
            title="A credit note against an earlier bill",
            what_it_tests="Recognised as a credit and linked to the invoice it cancels.",
            filename="CN-204411.pdf",
            content_type="application/pdf",
            text=text9.replace("INVOICE", "CREDIT NOTE")
            + "\n\nCredit against invoice INV-204411.",
            received_from=vendor.email,
            kind="credit_note",
            expect="applied as a credit",
        )
    )

    # ------------------------------------- 10. the wrong business number
    text10, _n10, _t10, _total10 = _render(
        vendor=vendor3,
        entity=taiwan,
        number="AB-45120099",
        invoice_date=TODAY - dt.timedelta(days=5),
        order_number=order3.number if order3 else complete.number,
        lines=uniform_lines[:1],
        buyer_tax_identifier="24681357",
    )
    documents.append(
        SampleDocument(
            key="wrong_buyer",
            title="A uniform invoice made out to the wrong business number",
            what_it_tests="It is not billed to us, so it cannot be claimed or posted.",
            filename="AB-45120099.pdf",
            content_type="application/pdf",
            text=text10,
            received_from=vendor3.email,
            expect="rejected, wrong buyer",
        )
    )

    # -------------------------- 11. freight not on the order, but allowed
    allowance_order = _order_with_deliveries(session, exclude=used_vendor_ids)
    allowance_vendor = allowance_order.vendor if allowance_order is not None else vendor
    # The charge has to sit inside this supplier's own allowance, or the
    # document would be showing the rule failing rather than working.
    if dec(allowance_vendor.unordered_allowance) < Decimal("1000"):
        allowance_vendor.unordered_allowance = Decimal("1000")
        session.flush()
    used_vendor_ids.add(allowance_vendor.id)
    allowance_lines = _delivered_lines(session, allowance_order)
    text11, _n11, _t11, _total11 = _render(
        vendor=allowance_vendor,
        entity=taiwan,
        number="INV-660213",
        invoice_date=TODAY - dt.timedelta(days=7),
        order_number=allowance_order.number,
        lines=allowance_lines,
        extra_lines=[
            {
                "part_code": "FREIGHT",
                "description": "Delivery charge",
                "quantity": Decimal("1"),
                "unit_price": Decimal("850"),
                "amount": Decimal("850"),
            }
        ],
    )
    documents.append(
        SampleDocument(
            key="freight_allowance",
            title="A delivery charge of 850 that is not on the order",
            what_it_tests=(
                "Inside this supplier's allowance, so it is accepted and the rule is shown."
            ),
            filename="INV-660213.pdf",
            content_type="application/pdf",
            text=text11,
            received_from=allowance_vendor.email,
            expect="accepted inside the allowance",
        )
    )

    # ------------------------------ 12. dollars billed to the Taiwan company
    # A dollar supplier whose goods have arrived, so the only thing left for
    # this document to show is the conversion.
    dollar_order = None
    for candidate in session.scalars(
        select(PurchaseOrder)
        .where(PurchaseOrder.entity_code == "TW", PurchaseOrder.currency == "USD")
        .order_by(PurchaseOrder.id)
    ):
        if candidate.vendor_id in used_vendor_ids or candidate.vendor is None:
            continue
        if any(_delivered(session, line) > 0 for line in candidate.lines):
            dollar_order = candidate
            break
    dollar_vendor = (
        dollar_order.vendor
        if dollar_order is not None
        else session.scalar(select(Vendor).where(Vendor.currency == "USD").limit(1)) or vendor
    )
    used_vendor_ids.add(dollar_vendor.id)
    dollar_lines = _delivered_lines(session, dollar_order) or lines[:2]
    text12, _n12, _t12, _total12 = _render(
        vendor=dollar_vendor,
        entity=taiwan,
        number="INV-US-33108",
        invoice_date=TODAY - dt.timedelta(days=8),
        order_number=dollar_order.number if dollar_order else complete.number,
        lines=dollar_lines,
        tax_percent=Decimal("0"),
        currency="USD",
    )
    documents.append(
        SampleDocument(
            key="foreign_currency",
            title="An invoice in United States dollars",
            what_it_tests="Converted at the rate for the invoice date and held in both.",
            filename="INV-US-33108.pdf",
            content_type="application/pdf",
            text=text12,
            received_from=dollar_vendor.email,
            expect="converted and checked",
        )
    )

    # ------------------------------------------- a new bank account
    # A supplier of its own, because blocking a supplier blocks every invoice
    # from them, and that would hide the ordinary ones behind this one.
    bank_order = _order_with_deliveries(session, exclude=used_vendor_ids)
    bank_vendor = bank_order.vendor if bank_order is not None else vendor
    used_vendor_ids.add(bank_vendor.id)
    bank_lines = _delivered_lines(session, bank_order) or lines[:1]
    text8, _n8, _t8, _total8 = _render(
        vendor=bank_vendor,
        entity=taiwan,
        number="INV-556021",
        invoice_date=TODAY - dt.timedelta(days=1),
        order_number=bank_order.number if bank_order else complete.number,
        lines=bank_lines,
        bank_account="992847165503",
    )
    documents.append(
        SampleDocument(
            key="bank_change",
            title="An invoice asking to be paid into a different account",
            what_it_tests="A hard stop and a call-back to the number already on file.",
            filename="INV-556021.pdf",
            content_type="application/pdf",
            text=text8 + "\n\nPlease note our new bank account from this month.",
            received_from=bank_vendor.email,
            expect="blocked, call-back raised",
        )
    )

    return documents
