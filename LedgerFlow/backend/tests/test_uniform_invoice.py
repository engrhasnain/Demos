"""The Taiwan uniform invoice rules."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest

from app.domain.taxid import check_unified_business_number
from app.domain.uniforminvoice import (
    build_barcode,
    check_business_tax,
    check_totals,
    is_uniform_invoice_number,
    normalise_invoice_number,
    normalise_uniform_invoice_number,
    read_barcode,
)


class TestBusinessNumber:
    """The unified business number: eight digits with a weighted checksum."""

    def test_a_known_good_number_is_accepted(self):
        assert check_unified_business_number("88124403").valid

    @pytest.mark.parametrize("value", ["8812440", "881244033", "8812440A", "", "   "])
    def test_wrong_shapes_are_refused(self, value):
        assert not check_unified_business_number(value).valid

    def test_most_single_digit_changes_are_caught(self):
        """How strong the checksum actually is, stated rather than assumed.

        Since April 2023 the weighted sum only has to divide by 5 rather than
        by 10, so the rule is weaker than it was: of the 72 ways to change one
        digit of a valid number, it rejects 63. That is worth writing down,
        because it is the reason the product never treats a valid business
        number as proof on its own.
        """
        good = "88124403"
        caught = sum(
            1
            for position in range(8)
            for digit in "0123456789"
            if digit != good[position]
            and not check_unified_business_number(
                good[:position] + digit + good[position + 1 :]
            ).valid
        )
        assert caught == 63


class TestInvoiceNumber:
    def test_two_letters_and_eight_digits(self):
        assert is_uniform_invoice_number("ab-45120073")
        assert normalise_uniform_invoice_number("ab-45120073") == "AB-45120073"

    @pytest.mark.parametrize("value", ["A45120073", "AB4512007", "ABC45120073", ""])
    def test_other_shapes_are_not_uniform_invoice_numbers(self, value):
        assert not is_uniform_invoice_number(value)

    def test_a_prefix_and_leading_zeros_do_not_make_a_different_invoice(self):
        # This is what makes "0042" and "INV-0042" the same bill.
        assert normalise_invoice_number("INV-0042") == normalise_invoice_number("0042")
        assert normalise_invoice_number("inv 42") == normalise_invoice_number("42")

    def test_two_real_numbers_stay_different(self):
        assert normalise_invoice_number("INV-204417") != normalise_invoice_number("INV-204418")


class TestBarcode:
    def test_what_is_written_is_what_is_read(self):
        payload = build_barcode(
            invoice_number="AB45120073",
            invoice_date=dt.date(2026, 9, 18),
            random_code="7788",
            net_amount=Decimal("18000"),
            total_amount=Decimal("18900"),
            buyer_tax_identifier="88124403",
            seller_tax_identifier="20005302",
        )
        assert len(payload) == 53
        decoded = read_barcode(payload)
        assert decoded is not None and decoded.well_formed
        assert decoded.invoice_number == "AB-45120073"  # the canonical, hyphenated form
        assert decoded.invoice_date == dt.date(2026, 9, 18)
        assert decoded.net_amount == Decimal("18000")
        assert decoded.total_amount == Decimal("18900")
        assert decoded.buyer_tax_identifier == "88124403"
        assert decoded.seller_tax_identifier == "20005302"

    def test_a_short_payload_is_reported_not_guessed(self):
        decoded = read_barcode("AB451200731150918")
        assert decoded is not None
        assert not decoded.well_formed
        assert decoded.problem

    def test_nothing_in_nothing_out(self):
        assert read_barcode("") is None


class TestArithmetic:
    def test_five_percent_business_tax(self):
        assert check_business_tax(Decimal("18000"), Decimal("900")).ok

    def test_a_rounding_difference_of_one_is_tolerated(self):
        # Suppliers round per line; one dollar either way is not a dispute.
        assert check_business_tax(Decimal("18000"), Decimal("901")).ok
        assert not check_business_tax(Decimal("18000"), Decimal("1000")).ok

    def test_the_total_has_to_be_the_net_plus_the_tax(self):
        assert check_totals(
            line_total=Decimal("18000"),
            net_amount=Decimal("18000"),
            tax_amount=Decimal("900"),
            total_amount=Decimal("18900"),
        ).ok

    def test_a_total_that_does_not_add_up_is_reported(self):
        result = check_totals(
            line_total=Decimal("18000"),
            net_amount=Decimal("18000"),
            tax_amount=Decimal("900"),
            total_amount=Decimal("19900"),
        )
        assert not result.ok and result.problems
