"""How much could actually turn up while we wait.

The textbook safety stock is ``z × sigma``, which assumes demand over the
lead time is normally distributed. For a part that sells every week that is
close enough to true. For a part that sells nothing for a month and then
four hundred, it is not true at all, and it fails in a specific and
expensive direction: the standard deviation of a lumpy series is large, so
``z × sigma`` demands an enormous buffer for a part that mostly needs none.
That is how an inventory tool ends up holding more stock than the buyers it
replaced while claiming to be more efficient.

So for those parts the distribution is not assumed, it is taken from the
history. Slide a window the length of the cover period along the past two
years and add up each window: that set of sums *is* the distribution of
demand over a lead time, with the real gaps and the real spikes in it. The
reorder point is then simply the point below which that demand fell in, say,
95 per cent of those windows.

The lead time varies too, so the window length is varied with it rather than
held at the average. A supplier that usually takes four weeks and sometimes
takes seven is two different risks, and averaging them away is the thing the
quoted lead time already does wrong.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..numbers import mean, quantile
from .leadtime import LeadTimeProfile

#: Below this many weeks of history there is nothing to take a distribution
#: from, and the normal approximation is the better of two poor options.
MINIMUM_WEEKS = 26


@dataclass(slots=True)
class CoverDistribution:
    """What demand over the cover period has actually looked like."""

    windows: int
    average: float
    at_service_level: float
    median: float
    worst: float
    cover_weeks_low: int
    cover_weeks_high: int
    method: str

    @property
    def safety_stock(self) -> float:
        return max(0.0, self.at_service_level - self.average)

    def to_dict(self) -> dict[str, object]:
        return {
            "windows": self.windows,
            "average": round(self.average, 2),
            "at_service_level": round(self.at_service_level, 2),
            "median": round(self.median, 2),
            "worst": round(self.worst, 2),
            "cover_weeks_low": self.cover_weeks_low,
            "cover_weeks_high": self.cover_weeks_high,
            "safety_stock": round(self.safety_stock, 2),
            "method": self.method,
        }


def _windows_of(series: Sequence[float], length: int) -> list[float]:
    """Every run of ``length`` consecutive weeks, totalled."""
    if length <= 0 or len(series) < length:
        return []
    running = sum(series[:length])
    totals = [running]
    for index in range(length, len(series)):
        running += series[index] - series[index - length]
        totals.append(running)
    return totals


def from_history(
    series: Sequence[float],
    *,
    lead_time: LeadTimeProfile,
    review_period_days: int,
    service_level: float,
) -> CoverDistribution | None:
    """The empirical distribution, or None when there is too little history.

    The window length is swept from a short lead time to a long one, so the
    supplier's unreliability is represented by the windows themselves rather
    than by a separate term added on top.
    """
    usable = [float(value) for value in series]
    if len(usable) < MINIMUM_WEEKS:
        return None

    def weeks_for(days: float) -> int:
        return max(1, round((days + review_period_days) / 7.0))

    low = weeks_for(max(1.0, lead_time.median_days))
    high = weeks_for(lead_time.ninetieth_percentile_days)
    if high < low:
        low, high = high, low

    totals: list[float] = []
    for length in range(low, high + 1):
        totals.extend(_windows_of(usable, length))

    if not totals:
        return None

    return CoverDistribution(
        windows=len(totals),
        average=mean(totals),
        at_service_level=quantile(totals, service_level),
        median=quantile(totals, 0.5),
        worst=max(totals),
        cover_weeks_low=low,
        cover_weeks_high=high,
        method="history",
    )
