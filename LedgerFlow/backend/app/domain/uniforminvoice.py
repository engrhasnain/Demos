"""Taiwan uniform invoices (統一發票).

Three things matter to accounts payable, and all three are checkable without
reading a word of the page:

* the **number** is two letters and eight digits, issued in two-month periods;
* the **square barcode** carries the number, the date, the amounts and both
  parties' business numbers, so it can be cross-checked against whatever was
  read off the page;
* **business tax is 5 per cent**, so the arithmetic either holds or it does not.

The barcode layout below is the published left-hand code: positions 1-10 the
invoice number, 11-17 the date as a Republic of China year and month and day,
18-21 a random code, 22-29 the amount before tax and 30-37 the amount with
tax, both as eight hexadecimal digits, then 38-45 the buyer's business number
and 46-53 the seller's.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal

from ..money import dec, money

#: Two letters, then eight digits. Written with or without a dash.
UNIFORM_INVOICE_NUMBER = re.compile(r"^([A-Z]{2})[-\s]?(\d{8})$")

#: The rate has been 5 per cent for a long time, but it is a setting, not a
#: constant, because a rate written into code is a rate nobody can change.
DEFAULT_BUSINESS_TAX_PERCENT = Decimal("5")

#: Uniform invoices are issued in two-month periods: January and February are
#: period 1, and so on.
PERIOD_MONTHS = {1: (1, 2), 2: (3, 4), 3: (5, 6), 4: (7, 8), 5: (9, 10), 6: (11, 12)}


def is_uniform_invoice_number(value: str) -> bool:
    return bool(UNIFORM_INVOICE_NUMBER.match((value or "").strip().upper()))


def normalise_uniform_invoice_number(value: str) -> str:
    """``ab12345678`` and ``AB-12345678`` both become ``AB-12345678``."""
    match = UNIFORM_INVOICE_NUMBER.match((value or "").strip().upper())
    if not match:
        return (value or "").strip().upper()
    return f"{match.group(1)}-{match.group(2)}"


def period_of(when: dt.date) -> int:
    return (when.month + 1) // 2


def roc_year(year: int) -> int:
    """The Republic of China calendar runs 1911 years behind."""
    return year - 1911


def from_roc(text: str) -> dt.date | None:
    """``1151003`` is the third of October, 2026."""
    digits = re.sub(r"\D", "", text or "")
    if len(digits) != 7:
        return None
    try:
        return dt.date(int(digits[:3]) + 1911, int(digits[3:5]), int(digits[5:7]))
    except ValueError:
        return None


def to_roc(when: dt.date) -> str:
    return f"{roc_year(when.year):03d}{when.month:02d}{when.day:02d}"


# ---------------------------------------------------------------------------
# The square barcode
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class BarcodePayload:
    invoice_number: str
    invoice_date: dt.date | None
    random_code: str
    net_amount: Decimal
    total_amount: Decimal
    buyer_tax_identifier: str
    seller_tax_identifier: str
    well_formed: bool = True
    problem: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "invoice_number": self.invoice_number,
            "invoice_date": self.invoice_date.isoformat() if self.invoice_date else "",
            "random_code": self.random_code,
            "net_amount": str(self.net_amount),
            "total_amount": str(self.total_amount),
            "buyer_tax_identifier": self.buyer_tax_identifier,
            "seller_tax_identifier": self.seller_tax_identifier,
            "well_formed": self.well_formed,
            "problem": self.problem,
        }


def build_barcode(
    *,
    invoice_number: str,
    invoice_date: dt.date,
    random_code: str,
    net_amount: Decimal,
    total_amount: Decimal,
    buyer_tax_identifier: str,
    seller_tax_identifier: str,
) -> str:
    """Produce a payload in the published layout, used by the data generator."""
    number = normalise_uniform_invoice_number(invoice_number).replace("-", "")
    return (
        f"{number:<10}"
        f"{to_roc(invoice_date)}"
        f"{random_code:0>4}"
        f"{int(dec(net_amount)):08X}"
        f"{int(dec(total_amount)):08X}"
        f"{buyer_tax_identifier:0>8}"
        f"{seller_tax_identifier:0>8}"
    )


def read_barcode(payload: str) -> BarcodePayload | None:
    """Decode the payload. Returns None when there is nothing to decode."""
    raw = (payload or "").strip()
    if not raw:
        return None
    if len(raw) < 53:
        return BarcodePayload(
            invoice_number="",
            invoice_date=None,
            random_code="",
            net_amount=Decimal("0"),
            total_amount=Decimal("0"),
            buyer_tax_identifier="",
            seller_tax_identifier="",
            well_formed=False,
            problem=f"The barcode holds {len(raw)} characters; at least 53 are needed.",
        )

    def amount(start: int, end: int) -> Decimal:
        try:
            return Decimal(int(raw[start:end], 16))
        except ValueError:
            return Decimal("-1")

    net = amount(21, 29)
    total = amount(29, 37)
    decoded = BarcodePayload(
        invoice_number=normalise_uniform_invoice_number(raw[0:10].strip()),
        invoice_date=from_roc(raw[10:17]),
        random_code=raw[17:21],
        net_amount=net,
        total_amount=total,
        buyer_tax_identifier=raw[37:45].strip(),
        seller_tax_identifier=raw[45:53].strip(),
    )
    if net < 0 or total < 0:
        decoded.well_formed = False
        decoded.problem = "The amounts in the barcode are not readable."
    elif decoded.invoice_date is None:
        decoded.well_formed = False
        decoded.problem = "The date in the barcode is not a real date."
    return decoded


# ---------------------------------------------------------------------------
# Arithmetic
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TaxCheck:
    ok: bool
    expected_tax: Decimal
    stated_tax: Decimal
    difference: Decimal
    explanation: str
    rate_percent: Decimal = DEFAULT_BUSINESS_TAX_PERCENT

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "expected_tax": str(self.expected_tax),
            "stated_tax": str(self.stated_tax),
            "difference": str(self.difference),
            "rate_percent": str(self.rate_percent),
            "explanation": self.explanation,
        }


def check_business_tax(
    net_amount: Decimal,
    tax_amount: Decimal,
    *,
    rate_percent: Decimal = DEFAULT_BUSINESS_TAX_PERCENT,
    tolerance: Decimal = Decimal("1"),
) -> TaxCheck:
    """Business tax on a Taiwan invoice, allowing a dollar of rounding."""
    expected = money(dec(net_amount) * dec(rate_percent) / Decimal("100"))
    stated = money(tax_amount)
    difference = money(stated - expected)
    ok = abs(difference) <= tolerance
    return TaxCheck(
        ok=ok,
        expected_tax=expected,
        stated_tax=stated,
        difference=difference,
        rate_percent=dec(rate_percent),
        explanation=(
            f"{net_amount} at {rate_percent}% is {expected}, and the invoice says {stated}."
            + ("" if ok else f" That is {difference} out.")
        ),
    )


@dataclass(slots=True)
class TotalsCheck:
    ok: bool
    problems: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {"ok": self.ok, "problems": self.problems}


def check_totals(
    *,
    line_total: Decimal,
    net_amount: Decimal,
    tax_amount: Decimal,
    total_amount: Decimal,
    tolerance: Decimal = Decimal("1"),
) -> TotalsCheck:
    """The lines add to the net, and the net plus tax adds to the total."""
    problems: list[str] = []
    if abs(money(line_total) - money(net_amount)) > tolerance:
        problems.append(
            f"The lines add up to {money(line_total)}, but the invoice says the amount "
            f"before tax is {money(net_amount)}."
        )
    if abs(money(dec(net_amount) + dec(tax_amount)) - money(total_amount)) > tolerance:
        problems.append(
            f"{money(net_amount)} plus tax of {money(tax_amount)} is "
            f"{money(dec(net_amount) + dec(tax_amount))}, but the invoice total says "
            f"{money(total_amount)}."
        )
    return TotalsCheck(ok=not problems, problems=problems)


# ---------------------------------------------------------------------------
# Invoice numbers in general
# ---------------------------------------------------------------------------
_NOT_ALPHANUMERIC = re.compile(r"[^A-Z0-9]")


def normalise_invoice_number(value: str) -> str:
    """Strip everything a human might vary, so the same invoice twice matches.

    ``INV-0042``, ``inv 42`` and ``0042`` all become ``42``. The leading
    letters are kept when they carry meaning, as they do on a Taiwan uniform
    invoice, and dropped when they are only a prefix such as "INV".
    """
    text = _NOT_ALPHANUMERIC.sub("", (value or "").upper())
    if not text:
        return ""

    # A uniform invoice number is two letters and eight digits; keep it whole.
    if re.fullmatch(r"[A-Z]{2}\d{8}", text):
        return text

    # Otherwise drop a common documentary prefix and any leading zeros.
    text = re.sub(r"^(INVOICE|INV|BILL|NO|FACTURA|RECHNUNG)", "", text)
    letters = re.match(r"^([A-Z]*)(\d.*)$", text)
    if letters:
        prefix, rest = letters.group(1), letters.group(2)
        return (prefix + rest.lstrip("0")) or rest or text
    return text
