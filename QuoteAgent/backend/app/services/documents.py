"""The quote document and the line export.

Both have a fallback, because a demonstration that cannot produce a document
because one optional library is missing is a demonstration that fails in the
room. If the PDF writer is installed the quote is a PDF; if not it is a printable
page with exactly the same content. The same goes for the spreadsheet export and
its comma separated fallback.
"""

from __future__ import annotations

import csv
import datetime as dt
import html
import io
from typing import Any

from ..config import DATA_DIR
from ..domain.incoterms import get_incoterm
from ..money import dec, money
from ..models import Case, QuoteVersion

DOCUMENT_DIR = DATA_DIR / "documents"
DOCUMENT_DIR.mkdir(parents=True, exist_ok=True)

LABELS = {
    "en": {
        "title": "Quotation",
        "reference": "Our reference",
        "date": "Date",
        "valid": "Valid until",
        "customer": "Customer",
        "terms": "Delivery terms",
        "currency": "Currency",
        "line": "Line",
        "part": "Part",
        "description": "Description",
        "quantity": "Quantity",
        "unit_price": "Unit price",
        "amount": "Amount",
        "lead_time": "Lead time",
        "goods": "Goods",
        "freight": "Freight",
        "insurance": "Insurance",
        "duty": "Import duty",
        "total": "Total",
        "days": "days",
        "from_stock": "from stock",
        "notes": "Notes",
    },
    "zh": {
        "title": "報價單",
        "reference": "我方編號",
        "date": "日期",
        "valid": "有效期限",
        "customer": "客戶",
        "terms": "貿易條件",
        "currency": "幣別",
        "line": "項次",
        "part": "料號",
        "description": "品名規格",
        "quantity": "數量",
        "unit_price": "單價",
        "amount": "金額",
        "lead_time": "交期",
        "goods": "貨款",
        "freight": "運費",
        "insurance": "保險",
        "duty": "進口關稅",
        "total": "總計",
        "days": "天",
        "from_stock": "現貨",
        "notes": "備註",
    },
}


def _language(case: Case) -> str:
    return case.language if case.language in LABELS else "en"


def quote_payload(case: Case, version: QuoteVersion) -> dict[str, Any]:
    language = _language(case)
    words = LABELS[language]
    incoterm = get_incoterm(version.incoterm)
    lines = []
    for line in sorted(version.lines, key=lambda line: line.line_number):
        if line.status in {"needs_clarification", "withdrawn"}:
            continue
        lines.append(
            {
                "line_number": line.line_number,
                "part": line.product.sku if line.product else "to be confirmed",
                "description": (
                    (line.product.description_zh or line.product.description_en)
                    if line.product and language == "zh"
                    else (line.product.description_en if line.product else line.request_text)
                ),
                "customer_reference": line.customer_reference,
                "quantity": str(line.quantity_billed),
                "unit_price": str(line.unit_price),
                "amount": str(line.extended_price),
                "lead_time": (
                    words["from_stock"]
                    if line.lead_time_days == 0
                    else f"{line.lead_time_days} {words['days']}"
                ),
                "rounding_note": line.rounding_note,
            }
        )
    return {
        "language": language,
        "words": words,
        "case": case,
        "version": version,
        "incoterm": incoterm,
        "lines": lines,
    }


# ---------------------------------------------------------------------------
# The quote document
# ---------------------------------------------------------------------------
def render_html(case: Case, version: QuoteVersion) -> str:
    payload = quote_payload(case, version)
    words = payload["words"]
    rows = "".join(
        "<tr>"
        f"<td class='num'>{line['line_number']}</td>"
        f"<td>{html.escape(line['part'])}</td>"
        f"<td>{html.escape(line['description'])}"
        + (
            f"<div class='note'>{html.escape(line['rounding_note'])}</div>"
            if line["rounding_note"]
            else ""
        )
        + "</td>"
        f"<td class='num'>{line['quantity']}</td>"
        f"<td class='num'>{line['unit_price']}</td>"
        f"<td class='num'>{line['amount']}</td>"
        f"<td>{html.escape(line['lead_time'])}</td>"
        "</tr>"
        for line in payload["lines"]
    )

    def total_row(label: str, value: Any, strong: bool = False) -> str:
        if dec(value) == 0 and not strong:
            return ""
        tag = "strong" if strong else "span"
        return (
            f"<tr class='{'grand' if strong else ''}'><td colspan='5' class='label'>"
            f"<{tag}>{html.escape(label)}</{tag}></td>"
            f"<td class='num'><{tag}>{value}</{tag}></td><td></td></tr>"
        )

    customer_name = case.customer.name if case.customer else case.contact_email
    return f"""<!doctype html>
<html lang="{payload['language']}">
<head>
<meta charset="utf-8">
<title>{words['title']} {html.escape(case.reference)}</title>
<style>
  :root {{ color-scheme: light; }}
  body {{ font-family: "Segoe UI", "Noto Sans TC", system-ui, sans-serif;
         margin: 32px; color: #15202b; }}
  header {{ display:flex; justify-content:space-between; align-items:flex-start;
            border-bottom:2px solid #15202b; padding-bottom:12px; }}
  h1 {{ font-size: 22px; margin:0 0 4px; }}
  .company {{ font-size: 13px; line-height:1.5; }}
  table {{ width:100%; border-collapse:collapse; margin-top:20px; font-size:13px; }}
  th {{ text-align:left; background:#f2f5f8; padding:8px; border-bottom:1px solid #cfd8e3; }}
  td {{ padding:8px; border-bottom:1px solid #e7ecf2; vertical-align:top; }}
  td.num, th.num {{ text-align:right; font-variant-numeric: tabular-nums; }}
  td.label {{ text-align:right; }}
  tr.grand td {{ border-top:2px solid #15202b; font-size:15px; }}
  .note {{ color:#64748b; font-size:11px; margin-top:2px; }}
  .meta {{ margin-top:16px; font-size:13px; display:grid;
           grid-template-columns:max-content 1fr; gap:4px 16px; }}
  footer {{ margin-top:28px; font-size:11px; color:#64748b; line-height:1.6; }}
</style>
</head>
<body>
<header>
  <div>
    <h1>{words['title']}</h1>
    <div>{words['reference']}: <strong>{html.escape(case.reference)}</strong>
      &nbsp;|&nbsp; v{version.version_number}</div>
  </div>
  <div class="company">
    <strong>Hengtai Industrial Supply</strong><br>
    No. 128, Gongyequ 1st Road, Taichung 407, Taiwan<br>
    sales@hengtai-industrial.example
  </div>
</header>

<div class="meta">
  <div>{words['customer']}</div><div>{html.escape(customer_name)}</div>
  <div>{words['date']}</div><div>{dt.date.today().isoformat()}</div>
  <div>{words['valid']}</div><div>{version.valid_until or ''}</div>
  <div>{words['terms']}</div>
  <div>{version.incoterm} {html.escape(version.named_place)} (Incoterms 2020)</div>
  <div>{words['currency']}</div><div>{version.currency}</div>
</div>

<table>
<thead><tr>
  <th class="num">{words['line']}</th><th>{words['part']}</th><th>{words['description']}</th>
  <th class="num">{words['quantity']}</th><th class="num">{words['unit_price']}</th>
  <th class="num">{words['amount']}</th><th>{words['lead_time']}</th>
</tr></thead>
<tbody>
{rows}
{total_row(words['goods'], version.goods_total)}
{total_row(words['freight'], version.freight_total)}
{total_row(words['insurance'], version.insurance_total)}
{total_row(words['duty'], version.duty_total)}
{total_row(words['total'] + ' (' + version.currency + ')', version.grand_total, strong=True)}
</tbody>
</table>

<footer>
  {html.escape(payload['incoterm'].plain_summary())}<br>
  Prices hold until {version.valid_until or 'the date shown above'}. Currency converted at the
  rate locked on the quote date.
  {"Import duty priced from duty table " + html.escape(version.tariff_table.version) + ". Confirm current duty with a licensed customs broker before shipment." if version.tariff_table else ""}
</footer>
</body>
</html>"""


def write_quote_document(case: Case, version: QuoteVersion) -> tuple[str, str]:
    """Return (path, format). PDF when the writer is installed, HTML otherwise."""
    stem = f"{case.reference}-v{version.version_number}"
    html_text = render_html(case, version)

    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.lib.units import mm
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError:
        path = DOCUMENT_DIR / f"{stem}.html"
        path.write_text(html_text, encoding="utf-8")
        return str(path), "html"

    payload = quote_payload(case, version)
    words = payload["words"]
    path = DOCUMENT_DIR / f"{stem}.pdf"
    styles = getSampleStyleSheet()
    document = SimpleDocTemplate(
        str(path), pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
        title=f"{words['title']} {case.reference}",
    )

    customer_name = case.customer.name if case.customer else case.contact_email
    story: list[Any] = [
        Paragraph(f"<b>Hengtai Industrial Supply</b>", styles["Title"]),
        Paragraph(
            f"{words['title']} {case.reference} v{version.version_number}", styles["Heading2"]
        ),
        Paragraph(
            f"{words['customer']}: {html.escape(customer_name)}<br/>"
            f"{words['date']}: {dt.date.today().isoformat()}<br/>"
            f"{words['valid']}: {version.valid_until or ''}<br/>"
            f"{words['terms']}: {version.incoterm} {html.escape(version.named_place)} "
            "(Incoterms 2020)<br/>"
            f"{words['currency']}: {version.currency}",
            styles["BodyText"],
        ),
        Spacer(1, 8),
    ]

    data: list[list[Any]] = [
        [words["line"], words["part"], words["description"], words["quantity"],
         words["unit_price"], words["amount"], words["lead_time"]]
    ]
    body_style = styles["BodyText"].clone("cell")
    body_style.fontSize = 8
    body_style.leading = 10
    for line in payload["lines"]:
        data.append(
            [
                str(line["line_number"]),
                Paragraph(html.escape(line["part"]), body_style),
                Paragraph(html.escape(line["description"]), body_style),
                line["quantity"],
                line["unit_price"],
                line["amount"],
                Paragraph(html.escape(line["lead_time"]), body_style),
            ]
        )
    for label, value in (
        (words["goods"], version.goods_total),
        (words["freight"], version.freight_total),
        (words["insurance"], version.insurance_total),
        (words["duty"], version.duty_total),
    ):
        if dec(value) != 0:
            data.append(["", "", "", "", label, str(money(value)), ""])
    data.append(["", "", "", "", f"{words['total']} ({version.currency})",
                 str(money(version.grand_total)), ""])

    table = Table(data, repeatRows=1,
                  colWidths=[14 * mm, 30 * mm, 60 * mm, 18 * mm, 22 * mm, 24 * mm, 18 * mm])
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f2f5f8")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#15202b")),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (3, 0), (5, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.HexColor("#cfd8e3")),
                ("GRID", (0, 1), (-1, -1), 0.25, colors.HexColor("#e7ecf2")),
                ("LINEABOVE", (0, -1), (-1, -1), 1.0, colors.HexColor("#15202b")),
            ]
        )
    )
    story.append(table)
    story.append(Spacer(1, 10))
    story.append(Paragraph(payload["incoterm"].plain_summary(), styles["BodyText"]))
    if version.tariff_table is not None:
        story.append(
            Paragraph(
                f"Import duty priced from duty table {version.tariff_table.version}. "
                "Confirm current duty with a licensed customs broker before shipment.",
                styles["BodyText"],
            )
        )
    document.build(story)

    # Keep the printable page beside the PDF so both are always available.
    (DOCUMENT_DIR / f"{stem}.html").write_text(html_text, encoding="utf-8")
    return str(path), "pdf"


# ---------------------------------------------------------------------------
# Line export
# ---------------------------------------------------------------------------
EXPORT_COLUMNS = [
    "Line", "Hengtai part", "Customer reference", "Description", "Quantity",
    "Unit of sale", "Unit price", "Line total", "Price source", "Margin %",
    "Lead time days", "Import duty", "Landed total", "Status",
]


def export_rows(version: QuoteVersion) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for line in sorted(version.lines, key=lambda line: line.line_number):
        rows.append(
            [
                line.line_number,
                line.product.sku if line.product else "",
                line.customer_reference,
                line.product.description_en if line.product else line.request_text,
                str(line.quantity_billed),
                line.unit_of_sale,
                str(line.unit_price),
                str(line.extended_price),
                line.price_source,
                str(line.margin_percent),
                line.lead_time_days,
                str(line.duty_amount),
                str(line.landed_total),
                line.status,
            ]
        )
    return rows


def write_line_export(case: Case, version: QuoteVersion) -> tuple[str, str]:
    stem = f"{case.reference}-v{version.version_number}-lines"
    rows = export_rows(version)
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font
    except ImportError:
        path = DOCUMENT_DIR / f"{stem}.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(EXPORT_COLUMNS)
            writer.writerows(rows)
        return str(path), "csv"

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Quote lines"
    sheet.append(EXPORT_COLUMNS)
    for cell in sheet[1]:
        cell.font = Font(bold=True)
    for row in rows:
        sheet.append(row)
    widths = [6, 22, 20, 52, 10, 12, 12, 14, 14, 10, 14, 12, 14, 18]
    for index, width in enumerate(widths, start=1):
        sheet.column_dimensions[chr(64 + index) if index <= 26 else "A"].width = width
    sheet.freeze_panes = "A2"

    path = DOCUMENT_DIR / f"{stem}.xlsx"
    workbook.save(path)
    return str(path), "xlsx"


def csv_bytes(version: QuoteVersion) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    writer.writerows(export_rows(version))
    return buffer.getvalue().encode("utf-8-sig")
