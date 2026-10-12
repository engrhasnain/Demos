"""Money, rounding and the calculation trace.

Two rules hold everywhere in this product:

1. Money is :class:`decimal.Decimal`, never ``float``. Floats lose cents on
   large bills of material and make a quote impossible to defend.
2. Every figure a person can see on screen carries a *trace*: the inputs, the
   formula in words, the result, and where each input came from. The interface
   turns that into a "how was this worked out" panel behind every number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

MONEY_PLACES = Decimal("0.01")
RATE_PLACES = Decimal("0.000001")
PERCENT_PLACES = Decimal("0.01")

ZERO = Decimal("0")


def dec(value: Any) -> Decimal:
    """Convert anything sane into a Decimal without going through float."""
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return ZERO
    if isinstance(value, float):
        # repr() keeps the shortest round-trip form, e.g. 0.1 -> "0.1"
        return Decimal(repr(value))
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise ValueError(f"{value!r} is not a number") from exc


def money(value: Any) -> Decimal:
    """Round to two places, half up, the way an invoice rounds."""
    return dec(value).quantize(MONEY_PLACES, rounding=ROUND_HALF_UP)


def rate(value: Any) -> Decimal:
    return dec(value).quantize(RATE_PLACES, rounding=ROUND_HALF_UP)


def percent(value: Any) -> Decimal:
    return dec(value).quantize(PERCENT_PLACES, rounding=ROUND_HALF_UP)


def money_str(value: Any) -> str:
    return str(money(value))


@dataclass(slots=True)
class TraceInput:
    """One input to a calculation, with the record it was read from."""

    label: str
    value: str
    source: str = ""          # e.g. "Contract C-10422, line 7"
    source_kind: str = ""     # contract | tariff_table | foreign_exchange | catalogue | policy | request
    source_id: str = ""       # so the interface can link straight to the record

    def to_dict(self) -> dict[str, str]:
        return {
            "label": self.label,
            "value": self.value,
            "source": self.source,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
        }


@dataclass(slots=True)
class TraceStep:
    """One step of a calculation, in the order it happened."""

    label: str
    formula: str
    result: str
    unit: str = ""
    inputs: list[TraceInput] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "formula": self.formula,
            "result": self.result,
            "unit": self.unit,
            "note": self.note,
            "inputs": [i.to_dict() for i in self.inputs],
        }


class Trace:
    """Collects the steps behind one number."""

    def __init__(self, subject: str) -> None:
        self.subject = subject
        self.steps: list[TraceStep] = []

    def add(
        self,
        label: str,
        formula: str,
        result: Any,
        *,
        unit: str = "",
        inputs: list[TraceInput] | None = None,
        note: str = "",
    ) -> Decimal | Any:
        self.steps.append(
            TraceStep(
                label=label,
                formula=formula,
                result=str(result),
                unit=unit,
                inputs=inputs or [],
                note=note,
            )
        )
        return result

    def extend(self, other: "Trace") -> None:
        self.steps.extend(other.steps)

    def to_dict(self) -> dict[str, Any]:
        return {"subject": self.subject, "steps": [s.to_dict() for s in self.steps]}

    def __len__(self) -> int:  # pragma: no cover - convenience
        return len(self.steps)
