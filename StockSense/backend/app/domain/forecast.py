"""The forecasting methods.

Four of them, each suited to a different kind of demand, all producing the
same thing: a **rate per week**, not a prediction of next week's sales. For
an occasional part the rate is the honest answer. Saying "we expect 4.7 next
week" about a part that sells 0, 0, 0, 40 is a worse answer than 4.7 a week,
because the first invites somebody to believe it.

Written out rather than taken from a library. Each is about fifteen lines,
and a buyer being shown the arithmetic behind a recommendation is the whole
proposition; "the library did it" is not an explanation.

Methods
-------
zero      Nothing has ever sold. Forecast nothing, and say so.
ses       Simple exponential smoothing. For parts that sell most weeks.
croston   Smooths the sizes and the gaps separately, and divides. The
          classic for occasional demand, and known to run high.
sba       Croston with the Syntetos-Boylan correction of (1 - alpha/2),
          which takes out most of that bias.
tsb       Smooths the size and the *probability* of selling, and multiplies.
          Unlike Croston it updates every week, including the weeks that
          sold nothing, so a part that has stopped selling decays towards
          zero instead of holding its last rate for ever. That property is
          what makes it the right default for a catalogue with dying parts
          in it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..numbers import Trace, TraceInput, mean, show, standard_deviation

DEFAULT_ALPHA = 0.2
DEFAULT_BETA = 0.1

METHOD_LABELS: dict[str, str] = {
    "zero": "No demand",
    "ses": "Exponential smoothing",
    "croston": "Croston",
    "sba": "Croston, bias corrected",
    "tsb": "Size and probability",
    "analogue": "From similar parts",
}

METHOD_NOTES: dict[str, str] = {
    "zero": "Nothing has sold, so nothing is forecast.",
    "ses": "Recent weeks weighted more heavily than older ones.",
    "croston": "Sizes and gaps smoothed separately, then divided.",
    "sba": "Croston runs high on occasional demand; this takes the bias out.",
    "tsb": "Updated every week, so a part that stops selling decays to zero.",
    "analogue": "Too little history of its own, so similar parts were used.",
}


@dataclass(slots=True)
class Forecast:
    """A rate per period, with an honest range around it."""

    method: str
    rate: float
    #: Standard deviation of demand in one period, used for safety stock.
    deviation: float
    #: The chance that any given period sells anything at all.
    probability_of_demand: float
    #: The typical size when it does sell.
    typical_size: float
    periods_used: int
    trace: Trace | None = None
    notes: list[str] = field(default_factory=list)
    #: Set when the forecast rests on something other than this part's own
    #: history, so the screen can widen the range and say why.
    borrowed: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "method": self.method,
            "method_label": METHOD_LABELS.get(self.method, self.method),
            "method_note": METHOD_NOTES.get(self.method, ""),
            "rate": round(self.rate, 3),
            "deviation": round(self.deviation, 3),
            "probability_of_demand": round(self.probability_of_demand, 3),
            "typical_size": round(self.typical_size, 2),
            "periods_used": self.periods_used,
            "borrowed": self.borrowed,
            "notes": self.notes,
            "trace": self.trace.to_dict() if self.trace else None,
        }


# ---------------------------------------------------------------------------
# The methods
# ---------------------------------------------------------------------------
def forecast_zero(series: Sequence[float]) -> Forecast:
    trace = Trace("Weekly demand")
    trace.add(
        "Nothing has sold",
        f"{len(series)} weeks of history, none with a sale",
        0,
        unit="a week",
        note="A part with no history is not a part with no demand, but it is "
        "not something to buy on a forecast either.",
    )
    return Forecast(
        method="zero",
        rate=0.0,
        deviation=0.0,
        probability_of_demand=0.0,
        typical_size=0.0,
        periods_used=len(series),
        trace=trace,
    )


def forecast_ses(series: Sequence[float], alpha: float = DEFAULT_ALPHA) -> Forecast:
    """Simple exponential smoothing, for parts that sell most weeks."""
    if not series:
        return forecast_zero(series)

    level = series[0]
    for value in series[1:]:
        level = alpha * value + (1 - alpha) * level

    residuals = []
    running = series[0]
    for value in series[1:]:
        residuals.append(value - running)
        running = alpha * value + (1 - alpha) * running

    deviation = standard_deviation(residuals) if residuals else standard_deviation(series)
    non_zero = [v for v in series if v > 0]

    trace = Trace("Weekly demand")
    trace.add(
        "Smooth the weekly sales",
        f"each week counts {alpha:.0%}, everything before it {1 - alpha:.0%}",
        show(level, 2),
        unit="a week",
        inputs=[
            TraceInput("Weeks of history", str(len(series)), "sales history", "history"),
            TraceInput("Average over the period", show(mean(series), 2), "sales history", "history"),
        ],
    )
    trace.add(
        "How far off it usually is",
        "standard deviation of the week-to-week forecast error",
        show(deviation, 2),
        unit="a week",
        note="This is what the safety stock is sized from.",
    )
    return Forecast(
        method="ses",
        rate=max(0.0, level),
        deviation=deviation,
        probability_of_demand=len(non_zero) / len(series),
        typical_size=mean(non_zero) if non_zero else 0.0,
        periods_used=len(series),
        trace=trace,
    )


def forecast_croston(
    series: Sequence[float],
    alpha: float = DEFAULT_ALPHA,
    *,
    bias_corrected: bool = True,
) -> Forecast:
    """Croston's method, with the Syntetos-Boylan correction by default.

    Sizes and gaps are smoothed as two separate series, updated only in the
    weeks that actually sold something, and the rate is one divided by the
    other. Croston is known to run high; multiplying by (1 - alpha/2) is the
    published correction, and it is on unless somebody asks for the original.
    """
    non_zero_positions = [i for i, value in enumerate(series) if value > 0]
    if not non_zero_positions:
        return forecast_zero(series)
    if len(non_zero_positions) == 1:
        # One sale is not a pattern. Spread it over the history and say so.
        only = series[non_zero_positions[0]]
        rate = only / len(series)
        trace = Trace("Weekly demand")
        trace.add(
            "One sale in the whole history",
            f"{show(only)} over {len(series)} weeks",
            show(rate, 3),
            unit="a week",
            note="Too little to call a pattern.",
        )
        return Forecast(
            method="sba" if bias_corrected else "croston",
            rate=rate,
            deviation=only,
            probability_of_demand=1 / len(series),
            typical_size=only,
            periods_used=len(series),
            trace=trace,
            notes=["Only one week in the history sold anything."],
        )

    size = series[non_zero_positions[0]]
    interval = float(non_zero_positions[0] + 1)
    last = non_zero_positions[0]
    for position in non_zero_positions[1:]:
        gap = position - last
        size = alpha * series[position] + (1 - alpha) * size
        interval = alpha * gap + (1 - alpha) * interval
        last = position

    raw_rate = size / interval if interval > 0 else 0.0
    correction = (1 - alpha / 2) if bias_corrected else 1.0
    rate = raw_rate * correction

    sizes = [series[i] for i in non_zero_positions]
    gaps = [b - a for a, b in zip(non_zero_positions, non_zero_positions[1:])]

    trace = Trace("Weekly demand")
    trace.add(
        "Typical size when it sells",
        f"smoothed over {len(sizes)} sales",
        show(size, 2),
        inputs=[
            TraceInput("Sales in the history", str(len(sizes)), "sales history", "history"),
            TraceInput("Plain average size", show(mean(sizes), 2), "sales history", "history"),
        ],
    )
    trace.add(
        "Typical gap between sales",
        f"smoothed over {len(gaps)} gaps" if gaps else "first sale",
        show(interval, 2),
        unit="weeks",
    )
    trace.add(
        "Demand a week",
        f"{show(size, 2)} ÷ {show(interval, 2)}",
        show(raw_rate, 3),
        unit="a week",
    )
    if bias_corrected:
        trace.add(
            "Take out the known bias",
            f"{show(raw_rate, 3)} × (1 − {alpha:.2f} ÷ 2)",
            show(rate, 3),
            unit="a week",
            note="Croston runs high on occasional demand. This is the "
            "published correction for it.",
        )

    return Forecast(
        method="sba" if bias_corrected else "croston",
        rate=max(0.0, rate),
        deviation=standard_deviation(sizes) if len(sizes) > 1 else size,
        probability_of_demand=len(non_zero_positions) / len(series),
        typical_size=mean(sizes),
        periods_used=len(series),
        trace=trace,
    )


def forecast_tsb(
    series: Sequence[float],
    alpha: float = DEFAULT_ALPHA,
    beta: float = DEFAULT_BETA,
) -> Forecast:
    """Size and probability, updated every week.

    The difference from Croston that matters in a real catalogue: the
    probability is updated in the weeks that sold nothing too. A part that
    has stopped selling decays towards zero instead of holding the rate it
    had on the day it died, which is how dead stock gets reordered.
    """
    if not series:
        return forecast_zero(series)
    non_zero = [v for v in series if v > 0]
    if not non_zero:
        return forecast_zero(series)

    size = non_zero[0]
    probability = 1.0 / max(1.0, series.index(non_zero[0]) + 1)
    for value in series:
        if value > 0:
            size = alpha * value + (1 - alpha) * size
            probability = beta * 1.0 + (1 - beta) * probability
        else:
            probability = beta * 0.0 + (1 - beta) * probability

    rate = probability * size

    trace = Trace("Weekly demand")
    trace.add(
        "Typical size when it sells",
        f"smoothed at {alpha:.0%} over {len(non_zero)} sales",
        show(size, 2),
        inputs=[
            TraceInput("Sales in the history", str(len(non_zero)), "sales history", "history"),
            TraceInput("Plain average size", show(mean(non_zero), 2), "sales history", "history"),
        ],
    )
    trace.add(
        "Chance of selling in any week",
        f"smoothed at {beta:.0%} over all {len(series)} weeks, "
        f"{len(non_zero)} of which sold",
        f"{probability:.0%}",
        note="Updated in the quiet weeks as well, so a part that has stopped "
        "selling falls towards zero instead of holding its old rate.",
    )
    trace.add(
        "Demand a week",
        f"{show(size, 2)} × {probability:.0%}",
        show(rate, 3),
        unit="a week",
    )

    return Forecast(
        method="tsb",
        rate=max(0.0, rate),
        deviation=standard_deviation(non_zero) if len(non_zero) > 1 else size,
        probability_of_demand=probability,
        typical_size=mean(non_zero),
        periods_used=len(series),
        trace=trace,
    )


# ---------------------------------------------------------------------------
# Choosing
# ---------------------------------------------------------------------------
METHODS = {
    "zero": forecast_zero,
    "ses": forecast_ses,
    "croston": lambda s: forecast_croston(s, bias_corrected=False),
    "sba": forecast_croston,
    "tsb": forecast_tsb,
}


def run(method: str, series: Sequence[float]) -> Forecast:
    return METHODS.get(method, forecast_tsb)(series)
