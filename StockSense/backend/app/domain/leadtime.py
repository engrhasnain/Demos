"""How long a supplier actually takes.

Every supplier quotes a lead time. Almost none of them meet it every time,
and the quoted figure is usually the best case rather than the typical one.
Sizing safety stock from the quoted figure is a reliable way to be out of
stock on exactly the parts that matter.

So the quoted figure is kept, and ignored. What is used is the distribution
of what actually happened: the mean, the spread, and the long tail. The
screen shows all three next to the quote, because the gap between them is
usually the most persuasive number in the whole product.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..numbers import mean, quantile, standard_deviation


@dataclass(slots=True)
class LeadTimeProfile:
    """What a supplier's deliveries have actually looked like."""

    quoted_days: int
    average_days: float
    deviation_days: float
    median_days: float
    #: The figure a cautious buyer would plan on.
    ninetieth_percentile_days: float
    worst_days: float
    deliveries: int

    @property
    def slippage_days(self) -> float:
        """How much later than quoted the average delivery really is."""
        return self.average_days - self.quoted_days

    @property
    def is_reliable(self) -> bool:
        """Tight enough that the quoted figure is worth anything."""
        return self.deviation_days <= max(2.0, 0.15 * self.average_days)

    def to_dict(self) -> dict[str, object]:
        return {
            "quoted_days": self.quoted_days,
            "average_days": round(self.average_days, 1),
            "deviation_days": round(self.deviation_days, 1),
            "median_days": round(self.median_days, 1),
            "ninetieth_percentile_days": round(self.ninetieth_percentile_days, 1),
            "worst_days": round(self.worst_days, 1),
            "deliveries": self.deliveries,
            "slippage_days": round(self.slippage_days, 1),
            "is_reliable": self.is_reliable,
        }


def profile(quoted_days: int, actual_days: Sequence[float]) -> LeadTimeProfile:
    """Build the profile from the deliveries on record.

    With fewer than three deliveries there is no distribution to speak of,
    so the quoted figure is used with a deliberately pessimistic spread
    rather than a flattering one. Being honest about not knowing is the
    whole reason a buyer would trust the rest of it.
    """
    samples = [float(d) for d in actual_days if d and d > 0]

    if len(samples) < 3:
        assumed = float(quoted_days)
        return LeadTimeProfile(
            quoted_days=quoted_days,
            average_days=assumed,
            # A quarter of the lead time, as the spread we cannot measure.
            deviation_days=max(2.0, assumed * 0.25),
            median_days=assumed,
            ninetieth_percentile_days=assumed * 1.4,
            worst_days=assumed * 1.6,
            deliveries=len(samples),
        )

    return LeadTimeProfile(
        quoted_days=quoted_days,
        average_days=mean(samples),
        deviation_days=standard_deviation(samples),
        median_days=quantile(samples, 0.5),
        ninetieth_percentile_days=quantile(samples, 0.9),
        worst_days=max(samples),
        deliveries=len(samples),
    )
