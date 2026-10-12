"""What kind of demand is this?

Most industrial parts do not sell a steady amount every week. They sell
nothing for a month and then four hundred at once. Fitting one model to
eighteen thousand parts of that kind is the reason buyers go back to the
spreadsheet.

The split used here is the Syntetos-Boylan-Croston one, on two numbers:

* **ADI**, the average interval between weeks that had any demand at all.
  1.0 means it sells every week.
* **CV squared**, the squared coefficient of variation of the sizes of the
  demands that did happen, which says how uneven those sales are.

The published cut-offs are ADI 1.32 and CV² 0.49. They are not laws of
nature, they are where the error of one method crosses the error of the
other, and they are the cut-offs the literature compares against, so they
are the ones used here rather than something invented.

    CV² ≥ 0.49 │   erratic        lumpy
               │
    CV² < 0.49 │   smooth         intermittent
               └──────────────────────────────
                 ADI < 1.32      ADI ≥ 1.32
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from ..numbers import mean, standard_deviation

ADI_CUTOFF = 1.32
CV_SQUARED_CUTOFF = 0.49

SMOOTH = "smooth"
ERRATIC = "erratic"
INTERMITTENT = "intermittent"
LUMPY = "lumpy"
NO_DEMAND = "no_demand"

LABELS: dict[str, str] = {
    SMOOTH: "Steady",
    ERRATIC: "Uneven sizes",
    INTERMITTENT: "Occasional",
    LUMPY: "Occasional and uneven",
    NO_DEMAND: "Nothing sold",
}

DESCRIPTIONS: dict[str, str] = {
    SMOOTH: "Sells most weeks, in similar quantities.",
    ERRATIC: "Sells most weeks, but the quantity jumps about.",
    INTERMITTENT: "Long gaps, then a fairly predictable quantity.",
    LUMPY: "Long gaps, and no telling how much when it does sell.",
    NO_DEMAND: "No sales in the history at all.",
}

#: Which forecasting method suits which pattern. The whole point of
#: classifying is that this mapping exists.
METHOD_FOR: dict[str, str] = {
    SMOOTH: "ses",
    ERRATIC: "ses",
    INTERMITTENT: "tsb",
    LUMPY: "tsb",
    NO_DEMAND: "zero",
}


@dataclass(slots=True)
class Pattern:
    kind: str
    label: str
    description: str
    average_demand_interval: float
    coefficient_of_variation_squared: float
    periods: int
    periods_with_demand: int
    suggested_method: str

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "label": self.label,
            "description": self.description,
            "average_demand_interval": round(self.average_demand_interval, 2),
            "coefficient_of_variation_squared": round(
                self.coefficient_of_variation_squared, 2
            ),
            "periods": self.periods,
            "periods_with_demand": self.periods_with_demand,
            "suggested_method": self.suggested_method,
        }


def classify(series: Sequence[float]) -> Pattern:
    """Put one demand series into one of the four quadrants."""
    periods = len(series)
    non_zero = [value for value in series if value > 0]
    with_demand = len(non_zero)

    if with_demand == 0:
        return Pattern(
            kind=NO_DEMAND,
            label=LABELS[NO_DEMAND],
            description=DESCRIPTIONS[NO_DEMAND],
            average_demand_interval=float(periods),
            coefficient_of_variation_squared=0.0,
            periods=periods,
            periods_with_demand=0,
            suggested_method=METHOD_FOR[NO_DEMAND],
        )

    # ADI counts every period against the periods that sold something, so a
    # part selling every week scores 1.0.
    adi = periods / with_demand

    average_size = mean(non_zero)
    deviation = standard_deviation(non_zero)
    cv_squared = (deviation / average_size) ** 2 if average_size > 0 else 0.0

    occasional = adi >= ADI_CUTOFF
    uneven = cv_squared >= CV_SQUARED_CUTOFF
    kind = (
        LUMPY if occasional and uneven
        else INTERMITTENT if occasional
        else ERRATIC if uneven
        else SMOOTH
    )

    return Pattern(
        kind=kind,
        label=LABELS[kind],
        description=DESCRIPTIONS[kind],
        average_demand_interval=adi,
        coefficient_of_variation_squared=cv_squared,
        periods=periods,
        periods_with_demand=with_demand,
        suggested_method=METHOD_FOR[kind],
    )


def is_intermittent(kind: str) -> bool:
    """Parts whose accuracy has to be reported separately, and why.

    An average taken across steady and occasional parts together hides the
    occasional ones, which are the majority of the catalogue and all of the
    difficulty.
    """
    return kind in {INTERMITTENT, LUMPY, NO_DEMAND}
