"""Tax identifier checks for the two entities Hengtai trades as.

Taiwan's unified business number is eight digits with a weighted check. The
Ministry of Finance relaxed the rule on 1 April 2023: the weighted sum now only
has to divide by 5, where it previously had to divide by 10. Validators written
before that date reject numbers issued after it, which is exactly the kind of
quiet breakage that stops a real quote going out.

Weights are 1, 2, 1, 2, 1, 2, 4, 1. Each product has its own digits summed
before being added. The seventh digit being 7 is a special case: either the sum
or the sum plus one may satisfy the rule.
"""

from __future__ import annotations

import datetime as dt
import re
from dataclasses import dataclass

UBN_WEIGHTS = (1, 2, 1, 2, 1, 2, 4, 1)
UBN_RULE_CHANGE_DATE = dt.date(2023, 4, 1)


@dataclass(slots=True)
class TaxIdentifierCheck:
    identifier: str
    kind: str
    valid: bool
    explanation: str
    rule_applied: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "identifier": self.identifier,
            "kind": self.kind,
            "valid": self.valid,
            "explanation": self.explanation,
            "rule_applied": self.rule_applied,
        }


def _digit_sum(value: int) -> int:
    return sum(int(c) for c in str(value))


def unified_business_number_checksum(number: str) -> int | None:
    digits = re.sub(r"\D", "", number or "")
    if len(digits) != 8:
        return None
    return sum(_digit_sum(int(digits[i]) * UBN_WEIGHTS[i]) for i in range(8))


def check_unified_business_number(
    number: str, *, on_date: dt.date | None = None
) -> TaxIdentifierCheck:
    """Validate a Taiwan unified business number."""
    on_date = on_date or dt.date.today()
    digits = re.sub(r"\D", "", number or "")
    divisor = 5 if on_date >= UBN_RULE_CHANGE_DATE else 10
    rule = (
        f"weighted sum divides by {divisor} "
        f"(rule in force from {UBN_RULE_CHANGE_DATE.isoformat()})"
        if divisor == 5
        else "weighted sum divides by 10 (rule before 1 April 2023)"
    )

    if len(digits) != 8:
        return TaxIdentifierCheck(
            number, "taiwan_unified_business_number", False,
            "A Taiwan unified business number has exactly eight digits.", rule,
        )

    total = unified_business_number_checksum(digits)
    assert total is not None
    ok = total % divisor == 0
    # The seventh digit being 7 allows the sum plus one as well.
    if not ok and digits[6] == "7":
        ok = (total + 1) % divisor == 0

    return TaxIdentifierCheck(
        digits,
        "taiwan_unified_business_number",
        ok,
        (
            f"Weighted sum is {total}, which divides by {divisor}."
            if ok
            else f"Weighted sum is {total}, which does not divide by {divisor}."
        ),
        rule,
    )


_EIN_RE = re.compile(r"^\d{2}-?\d{7}$")


def check_employer_identification_number(number: str) -> TaxIdentifierCheck:
    """United States employer identification number: two digits, then seven."""
    cleaned = (number or "").strip()
    ok = bool(_EIN_RE.match(cleaned))
    return TaxIdentifierCheck(
        cleaned,
        "united_states_employer_identification_number",
        ok,
        "Nine digits written as two, a dash, then seven."
        if ok
        else "This is not in the nine digit form 12-3456789.",
        "format check only; there is no published check digit",
    )


def check_tax_identifier(
    number: str, country: str, *, on_date: dt.date | None = None
) -> TaxIdentifierCheck:
    country = (country or "").upper()
    if country == "TW":
        return check_unified_business_number(number, on_date=on_date)
    if country == "US":
        return check_employer_identification_number(number)
    return TaxIdentifierCheck(
        number or "", "unknown", True,
        f"No check is defined for {country or 'this country'}; the number is accepted as given.",
    )


def generate_unified_business_number(seed: int, *, on_date: dt.date | None = None) -> str:
    """Produce a valid eight digit number, used only by the demo data loader."""
    on_date = on_date or dt.date.today()
    divisor = 5 if on_date >= UBN_RULE_CHANGE_DATE else 10
    base = f"{seed % 10_000_000:07d}"
    for last in range(10):
        candidate = base + str(last)
        total = unified_business_number_checksum(candidate)
        if total is not None and total % divisor == 0:
            return candidate
    # Every seven digit prefix has at least one valid last digit under the
    # divide-by-5 rule, so this line is unreachable in practice.
    return base + "0"
