"""Exact money, and the statistics the rest of the product needs.

Money is `Decimal` everywhere and leaves the API as a string, for the same
reason as always: a float that has been through JSON is no longer the number
the finance system holds.

Quantities are a different matter. You cannot order 4.7 screws, so an order
quantity is an integer by the time it is a recommendation. Forecasts in
between are floats on purpose: a demand rate of 4.7 a week is a true
statement, and rounding it early is how a forecast quietly becomes wrong.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable, Sequence

ZERO = Decimal("0")
CENTS = Decimal("0.01")


def dec(value: Any) -> Decimal:
    """Anything sane into a Decimal, never via float arithmetic."""
    if isinstance(value, Decimal):
        return value
    if value is None or value == "":
        return ZERO
    if isinstance(value, float):
        # repr() keeps the shortest round-trip form, so 0.1 stays "0.1".
        return Decimal(repr(value))
    try:
        return Decimal(str(value))
    except InvalidOperation as exc:  # pragma: no cover - defensive
        raise ValueError(f"{value!r} is not a number") from exc


def money(value: Any) -> Decimal:
    return dec(value).quantize(CENTS, rounding=ROUND_HALF_UP)


# ---------------------------------------------------------------------------
# Statistics, written out rather than imported, so the deployment stays small
# and every figure on screen can be traced to a line of code here.
# ---------------------------------------------------------------------------
def mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def standard_deviation(values: Sequence[float]) -> float:
    """The sample standard deviation. Zero for fewer than two values."""
    if len(values) < 2:
        return 0.0
    average = mean(values)
    variance = sum((v - average) ** 2 for v in values) / (len(values) - 1)
    return math.sqrt(variance)


def quantile(values: Sequence[float], share: float) -> float:
    """Linear interpolation between the closest ranks, as most tools do."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    position = max(0.0, min(1.0, share)) * (len(ordered) - 1)
    low = math.floor(position)
    high = math.ceil(position)
    if low == high:
        return ordered[int(position)]
    return ordered[low] + (ordered[high] - ordered[low]) * (position - low)


#: The normal deviate for a cycle service level, which is what turns "95 per
#: cent of cycles without a stock-out" into a quantity of safety stock.
#: Tabulated rather than computed so the figure on screen is one a buyer can
#: look up and check.
_Z: list[tuple[float, float]] = [
    (0.50, 0.00), (0.75, 0.674), (0.80, 0.842), (0.85, 1.036), (0.90, 1.282),
    (0.925, 1.440), (0.95, 1.645), (0.96, 1.751), (0.975, 1.960), (0.98, 2.054),
    (0.99, 2.326), (0.995, 2.576), (0.999, 3.090),
]


def z_for_service_level(level: float) -> float:
    """Interpolated between tabulated points, clamped at the ends."""
    level = max(0.50, min(0.999, level))
    for (low_level, low_z), (high_level, high_z) in zip(_Z, _Z[1:]):
        if low_level <= level <= high_level:
            if high_level == low_level:
                return low_z
            share = (level - low_level) / (high_level - low_level)
            return low_z + share * (high_z - low_z)
    return _Z[-1][1]


def round_to_pack(quantity: float, pack_size: int, minimum: int) -> int:
    """A real order quantity: whole packs, and never below the minimum.

    Rounded up, not to nearest. Rounding an order down to save a few hundred
    dollars is how a part that was going to be covered is not.
    """
    if quantity <= 0:
        return 0
    pack = max(1, int(pack_size or 1))
    packs = math.ceil(quantity / pack)
    ordered = packs * pack
    if minimum and ordered < minimum:
        ordered = math.ceil(minimum / pack) * pack
    return int(ordered)


# ---------------------------------------------------------------------------
# Traces: the arithmetic behind every figure the screens show
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class TraceInput:
    label: str
    value: str
    source: str = ""
    #: history | supplier | policy | catalogue | forecast | calendar | cash
    source_kind: str = ""
    source_id: str = ""

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
        inputs: Iterable[TraceInput] | None = None,
        note: str = "",
    ) -> Any:
        self.steps.append(
            TraceStep(
                label=label,
                formula=formula,
                result=str(result),
                unit=unit,
                inputs=list(inputs or []),
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


def show(value: float, places: int = 1) -> str:
    """A number as a person would write it, without trailing noise."""
    if value == int(value):
        return str(int(value))
    return f"{value:.{places}f}"
