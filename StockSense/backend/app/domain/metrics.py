"""Scoring a forecast, and why that is not how this product is graded.

The usual measures do not work on occasional demand.

**Percentage error** divides by the actual, and the actual is zero most
weeks. It is undefined whenever it matters, and dropping those weeks throws
away exactly the weeks that make the part difficult.

**Scaled error** fixes the division by comparing against a naive forecast
instead. It is the right measure of the two, and it is reported here. But
it has a trap of its own that is specific to this kind of demand: absolute
error is smallest at the *median*, and the median of a series that is zero
four weeks in five is zero. **A forecast that always says zero wins.**

A forecast of zero also empties the warehouse. So accuracy is reported,
because somebody will ask for it, and the product is not graded on it. It
is graded by replaying the year and counting stock-out days and the money
tied up — which is the only question the buyer actually has.

``zero_forecast_beats`` exists to make that argument on the demonstration's
own data rather than asserting it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..numbers import mean


def naive_scale(series: Sequence[float], seasonality: int = 1) -> float:
    """The denominator for a scaled error: how wrong "same as last time" is.

    Zero when the series never changes, which would divide by zero, so the
    caller has to treat a zero scale as "not scoreable" rather than perfect.
    """
    if len(series) <= seasonality:
        return 0.0
    differences = [
        abs(series[i] - series[i - seasonality]) for i in range(seasonality, len(series))
    ]
    return mean(differences)


@dataclass(slots=True)
class Score:
    mase: float | None
    rmsse: float | None
    bias: float
    mean_actual: float
    mean_forecast: float
    periods: int
    scoreable: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "mase": round(self.mase, 3) if self.mase is not None else None,
            "rmsse": round(self.rmsse, 3) if self.rmsse is not None else None,
            "bias": round(self.bias, 3),
            "mean_actual": round(self.mean_actual, 3),
            "mean_forecast": round(self.mean_forecast, 3),
            "periods": self.periods,
            "scoreable": self.scoreable,
        }


def score(
    actual: Sequence[float],
    forecast: Sequence[float],
    *,
    training: Sequence[float] | None = None,
) -> Score:
    """Scaled error against a naive benchmark, plus the bias.

    Bias matters more than accuracy here and is usually left out. A forecast
    that is wrong by the same amount in both directions costs nothing in
    inventory terms; one that is wrong by the same amount in one direction
    silently builds or drains stock every week.
    """
    periods = min(len(actual), len(forecast))
    if periods == 0:
        return Score(None, None, 0.0, 0.0, 0.0, 0, False)

    actual = list(actual[:periods])
    forecast = list(forecast[:periods])
    scale_series = list(training) if training else actual
    scale = naive_scale(scale_series)

    errors = [f - a for a, f in zip(actual, forecast)]
    mean_actual = mean(actual)
    mean_forecast = mean(forecast)
    bias = mean(errors)

    if scale <= 0:
        return Score(None, None, bias, mean_actual, mean_forecast, periods, False)

    mase = mean([abs(e) for e in errors]) / scale
    squared_scale = mean(
        [
            (scale_series[i] - scale_series[i - 1]) ** 2
            for i in range(1, len(scale_series))
        ]
    )
    rmsse = (
        (mean([e**2 for e in errors]) / squared_scale) ** 0.5
        if squared_scale > 0
        else None
    )
    return Score(mase, rmsse, bias, mean_actual, mean_forecast, periods, True)


@dataclass(slots=True)
class ZeroTrap:
    """The demonstration that accuracy is the wrong way to grade this."""

    parts_scored: int
    parts_where_zero_wins: int
    zero_mase: float
    model_mase: float

    @property
    def share(self) -> float:
        return (
            self.parts_where_zero_wins / self.parts_scored if self.parts_scored else 0.0
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "parts_scored": self.parts_scored,
            "parts_where_zero_wins": self.parts_where_zero_wins,
            "share": round(self.share, 3),
            "zero_mase": round(self.zero_mase, 3),
            "model_mase": round(self.model_mase, 3),
            "verdict": (
                "A forecast of nothing scores better than the real one on "
                f"{self.share:.0%} of parts, and would empty the warehouse. "
                "That is why this is graded on stock-outs and money, not accuracy."
            ),
        }


def zero_forecast_beats(
    cases: Sequence[tuple[Sequence[float], Sequence[float], Sequence[float]]],
) -> ZeroTrap:
    """Score the real forecast against an all-zero one, part by part.

    Each case is (training, actual, forecast). The point of the function is
    to lose: on occasional demand the zero forecast should win often, and
    saying so first is more convincing than being caught by it later.
    """
    scored = 0
    zero_wins = 0
    zero_total = 0.0
    model_total = 0.0

    for training, actual, forecast in cases:
        real = score(actual, forecast, training=training)
        flat = score(actual, [0.0] * len(actual), training=training)
        if not real.scoreable or not flat.scoreable:
            continue
        scored += 1
        zero_total += flat.mase or 0.0
        model_total += real.mase or 0.0
        if (flat.mase or 0.0) < (real.mase or 0.0):
            zero_wins += 1

    return ZeroTrap(
        parts_scored=scored,
        parts_where_zero_wins=zero_wins,
        zero_mase=zero_total / scored if scored else 0.0,
        model_mase=model_total / scored if scored else 0.0,
    )
