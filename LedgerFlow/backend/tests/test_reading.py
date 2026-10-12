"""Reading an invoice into fields and lines."""

from __future__ import annotations

from decimal import Decimal

from app.services.extraction import read_built_in, read_invoice


def read(text: str, barcode: str = ""):
    return read_built_in(text, barcode)


class TestHeaderFields:
    def test_the_labelled_fields_are_found(self):
        reading = read(
            "Acme Fastener Co., Ltd.\n"
            "Seller tax id: 20005302\n"
            "\n"
            "INVOICE\n"
            "Invoice No: INV-204417\n"
            "Invoice Date: 2026-09-18\n"
            "Purchase Order: PO-26104\n"
            "Buyer tax id: 88124403\n"
            "Currency: TWD\n"
        )
        assert reading.header["invoice_number"] == "INV-204417"
        assert reading.header["invoice_date"] == "2026-09-18"
        assert reading.header["purchase_order_number"] == "PO-26104"
        assert reading.header["buyer_tax_identifier"] == "88124403"
        assert reading.header["seller_tax_identifier"] == "20005302"

    def test_prose_mentioning_a_field_does_not_overwrite_it(self):
        """The bug this exists to stop.

        A sentence in the footer mentions the bank account in passing. A
        naive matcher takes the last thing that looks like a label and pays
        the wrong account.
        """
        reading = read(
            "INVOICE\n"
            "Invoice No: INV-204417\n"
            "Bank account: 581002556171\n"
            "\n"
            "Should you need to change the bank account: contact our office.\n"
        )
        assert reading.header["bank_account"] == "581002556171"

    def test_the_first_answer_wins(self):
        reading = read(
            "Invoice No: INV-000001\nInvoice No: INV-999999\n"
        )
        assert reading.header["invoice_number"] == "INV-000001"

    def test_a_field_that_is_not_there_is_left_empty(self):
        reading = read("INVOICE\nInvoice No: INV-1\n")
        assert reading.header.get("purchase_order_number", "") == ""
        assert reading.confidence.get("purchase_order_number", 0) == 0


class TestLines:
    def test_a_part_code_with_a_hyphen_is_not_read_as_a_negative_number(self):
        """The other bug this exists to stop.

        ``HT-SHC-M8X030-12.9-ZNB`` contains ``-12.9``. Reading that as an
        amount turns a 4 dollar screw into a credit.
        """
        reading = read(
            "Item  Description                Qty    Unit price    Amount\n"
            "1. HT-SHC-M8X030-12.9-ZNB Socket head cap screw 2000 4.00 8000.00\n"
        )
        assert len(reading.lines) == 1
        line = reading.lines[0]
        assert line.part_code == "HT-SHC-M8X030-12.9-ZNB"
        assert line.quantity == Decimal("2000")
        assert line.unit_price == Decimal("4.00")
        assert line.line_total == Decimal("8000.00")

    def test_every_page_of_a_long_statement_is_read(self):
        pages = []
        for page in range(1, 5):
            pages.append(f"Page {page} of 4")
            for item in range(4):
                number = page * 10 + item
                pages.append(f"{item + 1}. FWD-{number} Ocean freight {1} 1200.00 1200.00")
            pages.append("Page subtotal: 4800.00")
        reading = read("\n".join(pages))
        assert len(reading.lines) == 16
        assert sorted(reading.page_subtotals) == [1, 2, 3, 4]


class TestBarcodeOutranksText:
    def test_the_barcode_wins_and_says_so(self):
        import datetime as dt

        from app.domain.uniforminvoice import build_barcode

        payload = build_barcode(
            invoice_number="AB45120073",
            invoice_date=dt.date(2026, 9, 18),
            random_code="7788",
            net_amount=Decimal("18000"),
            total_amount=Decimal("18900"),
            buyer_tax_identifier="88124403",
            seller_tax_identifier="20005302",
        )
        # The page says something different on purpose.
        reading = read("Invoice No: AB-99999999\nTotal: 1.00\n", payload)
        assert reading.header["invoice_number"] == "AB-45120073"
        assert reading.header["total_amount"] == "18900"
        assert reading.confidence["invoice_number"] == 1.0
        assert any("barcode" in note.lower() for note in reading.notes)


class TestEngineChoice:
    def test_the_built_in_engine_is_the_default(self):
        reading = read_invoice("Invoice No: INV-1\n")
        assert reading.engine == "built-in"
        assert not reading.fell_back

    def test_asking_for_an_engine_that_is_not_configured_falls_back_and_says_so(self):
        reading = read_invoice("Invoice No: INV-1\n", force_engine="external")
        assert reading.fell_back
        assert reading.header["invoice_number"] == "INV-1"
        assert any("external" in note.lower() for note in reading.notes)
