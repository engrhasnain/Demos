"""Checks the reading engine cannot talk its way past.

Everything here is arithmetic and lookup. It runs after the page has been
read, on the figures that were read, and it has no idea what produced them.
That is the point: the engine reports, the checks decide.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from ..config import settings
from ..domain.taxid import check_tax_identifier
from ..domain.uniforminvoice import (
    check_business_tax,
    check_totals,
    is_uniform_invoice_number,
    normalise_uniform_invoice_number,
)
from ..money import Trace, TraceInput, dec, money
from ..models import Entity, Vendor
from .extraction import Reading

#: Without these an invoice cannot be processed at all.
REQUIRED_FIELDS = ("invoice_number", "invoice_date", "total_amount")


@dataclass(slots=True)
class Finding:
    kind: str
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "summary": self.summary, "detail": self.detail}


@dataclass(slots=True)
class ValidationResult:
    findings: list[Finding] = field(default_factory=list)
    trace: Trace | None = None
    checks_run: list[dict[str, Any]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.findings

    def add(self, kind: str, summary: str, **detail: Any) -> None:
        self.findings.append(Finding(kind=kind, summary=summary, detail=detail))

    def note(self, name: str, passed: bool, detail: str) -> None:
        self.checks_run.append({"check": name, "passed": passed, "detail": detail})

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "findings": [f.to_dict() for f in self.findings],
            "checks": self.checks_run,
        }


def validate(
    reading: Reading,
    *,
    vendor: Vendor | None,
    entity: Entity | None,
    today: dt.date | None = None,
) -> ValidationResult:
    """Run every check that does not need the purchase order."""
    today = today or dt.date.today()
    result = ValidationResult()
    trace = Trace("Checks on the invoice as read")

    # --- 1. is anything missing -------------------------------------------
    missing = reading.unread_fields(REQUIRED_FIELDS)
    if missing:
        result.add(
            "missing_field",
            "Could not read: " + ", ".join(m.replace("_", " ") for m in missing),
            fields=missing,
        )
    result.note(
        "Everything needed was read",
        not missing,
        "nothing missing" if not missing else ", ".join(missing),
    )

    weak = reading.weak_fields()
    if weak:
        result.note(
            "Fields read with low confidence",
            False,
            ", ".join(f"{name} ({reading.confidence.get(name, 0):.0%})" for name in weak),
        )

    # --- 2. does the arithmetic hold --------------------------------------
    net = dec(reading.value("net_amount") or 0)
    tax = dec(reading.value("tax_amount") or 0)
    total = dec(reading.value("total_amount") or 0)
    line_total = sum((line.line_total for line in reading.lines), Decimal("0"))

    if reading.lines or total:
        totals = check_totals(
            line_total=line_total if reading.lines else net,
            net_amount=net,
            tax_amount=tax,
            total_amount=total,
        )
        trace.add(
            "Lines add to the amount before tax",
            f"{len(reading.lines)} lines add to {money(line_total)}",
            money(line_total),
        )
        trace.add(
            "Amount before tax plus tax",
            f"{money(net)} + {money(tax)} = {money(net + tax)}",
            money(net + tax),
            note=f"The invoice says the total is {money(total)}.",
        )
        if not totals.ok:
            result.add("arithmetic", totals.problems[0], problems=totals.problems)
        result.note(
            "The numbers add up",
            totals.ok,
            "; ".join(totals.problems) if totals.problems else "lines, tax and total agree",
        )

    # --- 3. business tax, for a Taiwan invoice ----------------------------
    is_taiwan = (entity.country == "TW") if entity else False
    if is_taiwan and net > 0 and tax > 0:
        tax_check = check_business_tax(
            net, tax, rate_percent=dec(settings.business_tax_percent)
        )
        trace.add(
            "Business tax",
            f"{money(net)} at {settings.business_tax_percent}% = {tax_check.expected_tax}",
            tax_check.expected_tax,
            note=tax_check.explanation,
        )
        if not tax_check.ok:
            result.add(
                "arithmetic",
                f"Tax {tax_check.stated_tax}, should be {tax_check.expected_tax}",
                **tax_check.to_dict(),
            )
        result.note("Business tax at the right rate", tax_check.ok, tax_check.explanation)

    # --- 4. the buyer is us ------------------------------------------------
    buyer = (reading.value("buyer_tax_identifier") or "").strip()
    if entity is not None and buyer:
        ours = entity.tax_identifier.replace("-", "")
        theirs = buyer.replace("-", "")
        matches = ours == theirs
        trace.add(
            "Buyer business number",
            f"invoice says {buyer}, our {entity.name} number is {entity.tax_identifier}",
            "matches" if matches else "does not match",
            inputs=[
                TraceInput("Our number", entity.tax_identifier, entity.name, "policy", entity.code)
            ],
        )
        if not matches:
            result.add(
                "wrong_buyer_tax_id",
                f"Billed to {buyer}, not {entity.tax_identifier}",
                on_invoice=buyer,
                ours=entity.tax_identifier,
                entity=entity.name,
            )
        result.note("Billed to our business number", matches, f"{buyer} against {ours}")

    # --- 5. are the identifiers themselves valid --------------------------
    for name, country in (
        ("buyer_tax_identifier", entity.country if entity else ""),
        ("seller_tax_identifier", vendor.country if vendor else ""),
    ):
        value = (reading.value(name) or "").strip()
        if not value or not country:
            continue
        check = check_tax_identifier(value, country)
        result.note(
            f"{name.replace('_', ' ').replace('tax identifier', 'business number')} is valid",
            check.valid,
            check.explanation,
        )
        if not check.valid and name == "seller_tax_identifier":
            result.add(
                "missing_field",
                f"Supplier number {value} fails the check",
                field=name,
                value=value,
                rule=check.rule_applied,
            )

    # --- 6. a uniform invoice number is two letters and eight digits ------
    number = (reading.value("invoice_number") or "").strip()
    if is_taiwan and number:
        looks_uniform = is_uniform_invoice_number(number)
        result.note(
            "Uniform invoice number is well formed",
            looks_uniform,
            normalise_uniform_invoice_number(number)
            if looks_uniform
            else f"{number} is not two letters and eight digits",
        )

    # --- 7. the barcode and the page agree --------------------------------
    if reading.barcode and reading.barcode.get("well_formed"):
        disagreements = _barcode_disagreements(reading)
        if disagreements:
            result.add(
                "barcode_mismatch",
                "; ".join(disagreements),
                disagreements=disagreements,
            )
        result.note(
            "Barcode agrees with the page",
            not disagreements,
            "; ".join(disagreements) if disagreements else "every field matches",
        )

    # --- 8. how old is it --------------------------------------------------
    invoice_date = _as_date(reading.value("invoice_date"))
    if invoice_date:
        age = (today - invoice_date).days
        if age > settings.late_arrival_days:
            result.add(
                "late_arrival",
                f"{age} days old",
                days_old=age,
            )
        if invoice_date > today:
            result.add(
                "future_date",
                f"Dated {invoice_date.isoformat()}",
                invoice_date=invoice_date.isoformat(),
            )
        result.note(
            "Dated sensibly",
            0 <= age <= settings.late_arrival_days,
            f"{age} days old",
        )

    result.trace = trace
    return result


def _barcode_disagreements(reading: Reading) -> list[str]:
    """Compare the decoded barcode with whatever the page said."""
    barcode = reading.barcode or {}
    out: list[str] = []

    pairs = [
        ("invoice_number", "invoice number"),
        ("buyer_tax_identifier", "buyer business number"),
        ("seller_tax_identifier", "seller business number"),
    ]
    for key, label in pairs:
        on_page = str(reading.header.get(f"page_{key}") or "").strip()
        in_code = str(barcode.get(key) or "").strip()
        if on_page and in_code and on_page.replace("-", "") != in_code.replace("-", ""):
            out.append(f"{label}: barcode {in_code}, page {on_page}")

    for key, label in (("total_amount", "total"), ("net_amount", "amount before tax")):
        on_page = reading.header.get(f"page_{key}")
        in_code = barcode.get(key)
        if on_page and in_code and abs(dec(on_page) - dec(in_code)) > Decimal("1"):
            out.append(f"{label}: barcode {in_code}, page {on_page}")
    return out


def _as_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.date):
        return value
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
