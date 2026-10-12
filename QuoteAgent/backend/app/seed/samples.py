"""The sample requests the demonstration runs on.

The forty line bill of materials is built from the catalogue that was just
generated, so every line points at a part that really exists, or deliberately
does not. It contains, by construction:

* eight lines written to a published standard (DIN or ISO) rather than a
  Hengtai number;
* five competitor part numbers, including bearings where only the seal suffix
  differs between makers;
* four lines missing an attribute that has to be asked about;
* one line whose written specification contradicts itself;
* two lines for parts Hengtai does not stock, which go to a supplier;
* lines whose quantity does not divide into a whole number of boxes;
* lines on a live contract and lines on a contract that has run out;
* a line whose quantity is split across the Taichung and Ontario warehouses.

The spreadsheet is also deliberately untidy: a letterhead, a blank row and the
column headings on row six, which is where they sit in real life.
"""

from __future__ import annotations

import datetime as dt
import io
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.partnumbers import FINISH_DISPLAY
from ..models import Contract, ContractLine, CrossReference, Product, StockLevel


@dataclass(slots=True)
class SampleRequest:
    key: str
    title: str
    description: str
    sender: str
    subject: str
    body: str
    external_message_id: str
    attachments: list[tuple[str, bytes, str]] = field(default_factory=list)
    expected: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Building the bill of materials
# ---------------------------------------------------------------------------
def _contract_products(session: Session, contract_code: str, limit: int) -> list[Product]:
    contract = session.scalar(select(Contract).where(Contract.code == contract_code))
    if contract is None:
        return []
    product_ids = [
        line.product_id
        for line in session.scalars(
            select(ContractLine).where(ContractLine.contract_id == contract.id).limit(limit)
        )
    ]
    return list(session.scalars(select(Product).where(Product.id.in_(product_ids))))


def _split_stock_product(session: Session) -> Product | None:
    """A part with stock in both warehouses but not enough in either alone."""
    rows = session.execute(
        select(StockLevel.product_id)
        .where(StockLevel.warehouse_code == "ONTARIO", StockLevel.quantity_on_hand > 100)
        .limit(400)
    ).all()
    for (product_id,) in rows:
        levels = {
            level.warehouse_code: level.available
            for level in session.scalars(
                select(StockLevel).where(StockLevel.product_id == product_id)
            )
        }
        taichung, ontario = levels.get("TAICHUNG", 0), levels.get("ONTARIO", 0)
        if taichung > 100 and ontario > 100:
            product = session.get(Product, product_id)
            if product is not None and product.family == "fastener":
                return product
    return None


def _standard_designation(product: Product) -> str:
    attributes = product.attributes or {}
    legacy = attributes.get("legacy_standard") or product.standard
    thread = attributes.get("thread", "")
    length = attributes.get("length_mm", "")
    size = f"{thread}x{length}" if length else thread
    finish_word = {
        "plain": "plain",
        "zinc_blue": "zinc",
        "zinc_yellow": "yellow zinc",
        "hot_dip_galvanised": "hot dip galvanised",
        "black_oxide": "black",
        "stainless_plain": "stainless",
    }.get(attributes.get("finish", ""), "")
    return f"{legacy} {size} {attributes.get('property_class', '')} {finish_word}".strip()


def _competitor_number(session: Session, product: Product, brand: str) -> str:
    row = session.scalar(
        select(CrossReference).where(
            CrossReference.product_id == product.id, CrossReference.brand == brand
        )
    )
    return row.external_number if row else ""


def build_bill_of_materials(session: Session) -> list[dict[str, Any]]:
    """Forty rows, each one chosen to exercise something that breaks prototypes."""
    rows: list[dict[str, Any]] = []
    on_contract = _contract_products(session, "C-10422", 30)
    expired = _contract_products(session, "C-10311", 4)

    standards_pool = [p for p in on_contract if p.family == "fastener"][:8]
    bearings = list(
        session.scalars(
            select(Product).where(Product.family == "bearing").order_by(Product.sku).limit(40)
        )
    )
    sealed = [b for b in bearings if (b.attributes or {}).get("seal") == "sealed_both"][:3]
    shielded = [b for b in bearings if (b.attributes or {}).get("seal") == "shielded_both"][:1]
    cylinders = list(
        session.scalars(
            select(Product)
            .where(Product.family == "pneumatic", Product.is_stocked.is_(True))
            .order_by(Product.sku)
            .limit(4)
        )
    )
    split_product = _split_stock_product(session)

    def add(
        description: str,
        quantity: int,
        unit: str = "pcs",
        *,
        reference: str = "",
        note: str = "",
        tag: str = "",
        expect: str = "",
    ) -> None:
        rows.append(
            {
                "item": len(rows) + 1,
                "part_number": reference,
                "description": description,
                "quantity": quantity,
                "unit": unit,
                "note": note,
                "tag": tag,
                "expect": expect,
            }
        )

    # 1-8: written to a published standard rather than a Hengtai number.
    for product in standards_pool:
        add(
            _standard_designation(product),
            quantity=[2500, 1800, 900, 6000, 1200, 450, 3200, 750][len(rows) % 8],
            tag="published_standard",
            expect=product.sku,
        )

    # 9-11: competitor bearing numbers. Only the seal suffix differs.
    for product, brand in zip(sealed, ["SKF", "NSK", "NTN"]):
        number = _competitor_number(session, product, brand)
        if number:
            add(
                f"{brand} {number}",
                quantity=40,
                unit="pcs",
                reference=number,
                tag="competitor_number",
                expect=product.sku,
            )

    # 12-13: competitor fastener numbers from the cross-reference table.
    for product, brand in zip(on_contract[8:10], ["Fastbolt", "Nordwerk"]):
        number = _competitor_number(session, product, brand)
        if number:
            add(
                f"{brand} {number}",
                quantity=5000,
                reference=number,
                tag="competitor_number",
                expect=product.sku,
            )

    # 14-17: four lines that do not say enough.
    add("M10 bolt, class 8.8, zinc", 1000, tag="missing_attribute", expect="question:length_mm")
    add("Socket head cap screw M8x30, zinc plated", 2000, tag="missing_attribute",
        expect="question:property_class")
    add("Hexagon head bolt M12x60 class 10.9", 800, tag="missing_attribute",
        expect="question:finish")
    if shielded:
        add("Deep groove ball bearing 6205", 60, tag="missing_attribute", expect="question:seal")
    else:
        add("Deep groove ball bearing 6205", 60, tag="missing_attribute", expect="question:seal")

    # 18: the drawing and the text disagree.
    add(
        "Socket head cap screw M8x40 A2-70 stainless, zinc plated per drawing D-4471",
        1500,
        reference="D-4471",
        note="See drawing revision C",
        tag="conflicting_specification",
        expect="question:finish",
    )

    # 19-20: parts Hengtai does not list at all.
    add(
        "Shoulder bolt ISO 7379 12x50 M10 class 12.9 plain",
        250,
        tag="non_catalogue",
        expect="supplier",
    )
    add(
        "Trapezoidal lead screw Tr20x4 right hand, 1000 mm, C7",
        12,
        tag="non_catalogue",
        expect="supplier",
    )

    # 21: quantity in boxes rather than pieces.
    if on_contract:
        product = on_contract[10 % len(on_contract)]
        add(
            product.description_en,
            quantity=14,
            unit="boxes",
            tag="unit_conversion",
            expect=product.sku,
        )

    # 22: a quantity that does not divide into whole boxes.
    if on_contract:
        product = on_contract[11 % len(on_contract)]
        add(
            product.description_en,
            quantity=1_234,
            tag="pack_rounding",
            expect=product.sku,
        )

    # 23-26: lines sitting on the contract that has run out.
    for product in expired:
        add(product.description_en, quantity=600, tag="expired_contract", expect=product.sku)

    # 27: stock split across the two warehouses.
    if split_product is not None:
        levels = {
            level.warehouse_code: level.available
            for level in session.scalars(
                select(StockLevel).where(StockLevel.product_id == split_product.id)
            )
        }
        wanted = int(levels.get("TAICHUNG", 0) + levels.get("ONTARIO", 0) + 500)
        add(split_product.description_en, quantity=wanted, tag="split_stock",
            expect=split_product.sku)

    # 28-31: pneumatic parts, quoted by Hengtai number.
    for product in cylinders:
        add(product.description_en, quantity=6, reference=product.sku,
            tag="catalogue_number", expect=product.sku)

    # 32: a bearing quoted with its own Hengtai number.
    if bearings:
        add(bearings[0].description_en, quantity=25, reference=bearings[0].sku,
            tag="catalogue_number", expect=bearings[0].sku)

    # Fill to forty with ordinary catalogue lines, which is what most of a real
    # bill of materials looks like.
    filler = [p for p in on_contract if p not in standards_pool][:40]
    index = 0
    while len(rows) < 40 and index < len(filler):
        product = filler[index]
        index += 1
        if any(r["expect"] == product.sku for r in rows):
            continue
        add(product.description_en, quantity=[400, 1500, 250, 3000, 120][len(rows) % 5],
            reference=product.sku, tag="catalogue_number", expect=product.sku)

    while len(rows) < 40:
        add("M6x20 socket head cap screw class 12.9 plain", 500, tag="attribute_match",
            expect="attribute")

    return rows[:40]


def workbook_bytes(rows: list[dict[str, Any]], *, title: str, revision: str = "A") -> bytes:
    """A spreadsheet that looks like one a buyer actually sends."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, Side

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "BOM"

    sheet["A1"] = "PACIFIC MOTION CONTROLS, INC."
    sheet["A1"].font = Font(size=14, bold=True)
    sheet["A2"] = "4120 East Airport Drive, Ontario, California 91761"
    sheet["A3"] = f"{title}    Revision {revision}    {dt.date(2026, 10, 5).isoformat()}"
    sheet["A4"] = "Please quote delivered duty paid Ontario, in US dollars."

    headings = ["Item", "Part No.", "Description", "Qty", "UOM", "Required date", "Remarks"]
    for column, heading in enumerate(headings, start=1):
        cell = sheet.cell(row=6, column=column, value=heading)
        cell.font = Font(bold=True)
        cell.border = Border(bottom=Side(style="thin"))
        cell.alignment = Alignment(horizontal="left")

    required = (dt.date(2026, 10, 5) + dt.timedelta(days=45)).isoformat()
    for offset, row in enumerate(rows, start=7):
        sheet.cell(row=offset, column=1, value=row["item"])
        sheet.cell(row=offset, column=2, value=row["part_number"])
        sheet.cell(row=offset, column=3, value=row["description"])
        sheet.cell(row=offset, column=4, value=row["quantity"])
        sheet.cell(row=offset, column=5, value=row["unit"])
        sheet.cell(row=offset, column=6, value=required)
        sheet.cell(row=offset, column=7, value=row["note"])

    for column, width in zip("ABCDEFG", [8, 20, 68, 10, 8, 16, 28]):
        sheet.column_dimensions[column].width = width
    sheet.freeze_panes = "A7"

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# The sample messages
# ---------------------------------------------------------------------------
def build_samples(session: Session) -> list[SampleRequest]:
    rows = build_bill_of_materials(session)
    attachment = workbook_bytes(rows, title="Request for quotation RFQ-2026-4471")

    main_body = """Hi,

Please quote the attached bill of materials, RFQ-2026-4471, 40 lines.

We need this delivered duty paid to our Ontario, California warehouse, priced
in USD. Required date is 45 days from your quotation.

Some of the part numbers on the list are our previous supplier's numbers and
some are DIN numbers from the drawings, so please cross-reference them to your
own range and tell us if anything is not a direct equivalent.

Thanks,
Rosa Mendez
Purchasing, Pacific Motion Controls, Inc.
"""

    revision_rows = [dict(row) for row in rows]
    for position in (2, 5, 9, 14, 21, 27):
        if position < len(revision_rows):
            revision_rows[position]["quantity"] = int(revision_rows[position]["quantity"] * 1.5) + 100
    revision_rows.append(
        {
            "item": len(revision_rows) + 1,
            "part_number": "",
            "description": "Hexagon nut ISO 4032 M12 class 10 zinc plated",
            "quantity": 4000,
            "unit": "pcs",
            "note": "New line added in revision B",
            "tag": "added",
            "expect": "",
        }
    )
    revision_rows.append(
        {
            "item": len(revision_rows) + 1,
            "part_number": "",
            "description": "Flat washer ISO 7089 M12 200 HV zinc plated",
            "quantity": 4000,
            "unit": "pcs",
            "note": "New line added in revision B",
            "tag": "added",
            "expect": "",
        }
    )
    revision_attachment = workbook_bytes(
        revision_rows, title="Request for quotation RFQ-2026-4471", revision="B"
    )

    return [
        SampleRequest(
            key="main_request",
            title="Forty line bill of materials from Pacific Motion Controls",
            description=(
                "The request the whole demonstration runs on. Forty lines with "
                "published standards, competitor numbers, four lines that do not say "
                "enough, one line that contradicts itself and two parts Hengtai does "
                "not stock."
            ),
            sender="Rosa Mendez <r.mendez@pacificmotion.example>",
            subject="RFQ-2026-4471 - 40 line BOM - DDP Ontario",
            body=main_body,
            external_message_id="<rfq-2026-4471-a@pacificmotion.example>",
            attachments=[
                (
                    "RFQ-2026-4471-rev-A.xlsx",
                    attachment,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            ],
            expected={
                "line_count": len(rows),
                "published_standard_lines": sum(1 for r in rows if r["tag"] == "published_standard"),
                "competitor_number_lines": sum(1 for r in rows if r["tag"] == "competitor_number"),
                "lines_needing_a_question": sum(
                    1 for r in rows if r["tag"] in {"missing_attribute", "conflicting_specification"}
                ),
                "non_catalogue_lines": sum(1 for r in rows if r["tag"] == "non_catalogue"),
            },
        ),
        SampleRequest(
            key="customer_reply_chinese",
            title="Customer reply in Traditional Chinese, answering three of four questions",
            description=(
                "The same case resumes. Three questions are answered, one is not, and "
                "the follow-up asks only for the one that is still open."
            ),
            sender="Rosa Mendez <r.mendez@pacificmotion.example>",
            subject="Re: RFQ-2026-4471 - 回覆您的問題",
            body="""您好：

謝謝您的確認，以下依項次回覆：

14. 六角頭螺栓，長度請用 40 mm。
15. 強度等級請用 12.9。
16. 表面處理請用鍍鋅（藍白鋅）。

第 17 項我再跟工程確認後回覆。

謝謝
Rosa Mendez
Pacific Motion Controls
""",
            external_message_id="<rfq-2026-4471-reply-1@pacificmotion.example>",
            expected={"answers": 3},
        ),
        SampleRequest(
            key="incoterm_change",
            title="Customer switches from free on board Taichung to delivered duty paid Ontario",
            description=(
                "Freight, insurance and import duty all change. The quote is re-priced "
                "and the before and after is shown side by side."
            ),
            sender="Rosa Mendez <r.mendez@pacificmotion.example>",
            subject="Re: RFQ-2026-4471 - change to DDP Ontario",
            body=(
                "Hi, please change the terms to DDP Ontario, California in USD rather "
                "than FOB Taichung. Everything else stays the same.\n\nRosa"
            ),
            external_message_id="<rfq-2026-4471-incoterm@pacificmotion.example>",
            expected={"incoterm": "DDP"},
        ),
        SampleRequest(
            key="discount_request",
            title="Customer asks for twelve per cent off",
            description=(
                "Lines fall below the margin floor and are routed to the sales manager "
                "with the price build-up behind each one."
            ),
            sender="Rosa Mendez <r.mendez@pacificmotion.example>",
            subject="Re: RFQ-2026-4471 - commercial",
            body=(
                "Thanks for the quotation. To place the order this quarter we need 12% "
                "off the total. Please confirm.\n\nRosa"
            ),
            external_message_id="<rfq-2026-4471-discount@pacificmotion.example>",
            expected={"discount_percent": 12},
        ),
        SampleRequest(
            key="revision_b",
            title="Revision B of the bill of materials",
            description=(
                "Six quantities change and two lines are added. Only those lines are "
                "re-quoted; the rest are carried over with their prices intact."
            ),
            sender="Rosa Mendez <r.mendez@pacificmotion.example>",
            subject="RFQ-2026-4471 Revision B",
            body=(
                "Hi, please see revision B attached. Six quantities have moved and we "
                "have added two lines at the bottom. Everything else is unchanged.\n\n"
                "Rosa"
            ),
            external_message_id="<rfq-2026-4471-rev-b@pacificmotion.example>",
            attachments=[
                (
                    "RFQ-2026-4471-rev-B.xlsx",
                    revision_attachment,
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            ],
            expected={"quantity_changes": 6, "added_lines": 2},
        ),
        SampleRequest(
            key="taiwan_domestic",
            title="Taiwan customer, written in Chinese, ex works Taichung",
            description=(
                "A short domestic request. The reply goes back in Chinese, the price is "
                "in Taiwan dollars and no import duty applies."
            ),
            sender="林佑成 <lin.yc@tcprecision.example>",
            subject="詢價 - 內六角螺絲與軸承",
            body="""您好：

麻煩報價以下品項，交貨條件 EXW 台中，報價請用新台幣。

1. ISO 4762 M8x30 12.9 鍍鋅  數量 5000 pcs
2. ISO 4017 M10x40 8.8 鍍鋅  數量 3000 pcs
3. 深溝球軸承 6204-2RS C3  數量 50 pcs
4. M12 螺帽 10 級 鍍鋅  數量 2000 pcs

謝謝
林佑成
台中精機
""",
            external_message_id="<tw-2026-0918@tcprecision.example>",
            expected={"language": "zh", "currency": "TWD"},
        ),
    ]


def supplier_reply(line_numbers: list[int]) -> dict[str, Any]:
    """What the supplier sends back for the two non-catalogue lines."""
    return {
        "unit_price": Decimal("268.00"),
        "currency": "TWD",
        "lead_time_days": 35,
        "minimum_order_quantity": 250,
        "valid_until": (dt.date(2026, 10, 5) + dt.timedelta(days=30)).isoformat(),
        "note": (
            "Five week lead time. Price holds for thirty days. Minimum order "
            "quantity 250 pieces."
        ),
        "line_numbers": line_numbers,
    }
