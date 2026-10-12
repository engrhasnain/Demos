"""Preparing a history before anything is forecast from it.

Raw sales are not demand. Three things have to be dealt with first, and
every one of them changes the answer:

**The shelf was empty.** A week that sold nothing because there was nothing
to sell is not a week nobody wanted any. Feeding that in as a zero teaches
the forecast that demand is falling, so it orders less, so the shelf is
empty more often. It is a loop, and it is the reason a part that keeps
running out keeps running out.

**A project came through.** One customer building a plant orders twenty
thousand once. Leaving it in the baseline makes the part look twenty times
more popular than it is for the next two years.

**The part is new, or replaced an older one.** Six weeks of history is not
a forecast. Either carry the history of the part it replaced, or borrow the
shape of the family and say plainly that is what was done.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from ..config import settings
from ..numbers import mean, quantile
from ..text import count


@dataclass(slots=True)
class Prepared:
    """A history that is fit to forecast from, and a record of what changed."""

    demand: list[float]
    #: What was actually sold, untouched, for the screen to show alongside.
    sold: list[float]
    weeks: int

    censored_weeks: list[int] = field(default_factory=list)
    recovered_units: float = 0.0
    project_weeks: list[int] = field(default_factory=list)
    project_units: float = 0.0
    notes: list[str] = field(default_factory=list)

    @property
    def was_adjusted(self) -> bool:
        return bool(self.censored_weeks or self.project_weeks)

    def to_dict(self) -> dict[str, object]:
        return {
            "weeks": self.weeks,
            "censored_weeks": self.censored_weeks,
            "recovered_units": round(self.recovered_units, 1),
            "project_weeks": self.project_weeks,
            "project_units": round(self.project_units, 1),
            "was_adjusted": self.was_adjusted,
            "notes": self.notes,
        }


def _uncensored_rate(demand: Sequence[float], empty: Sequence[bool]) -> float:
    """The rate over the weeks we could actually have sold in."""
    usable = [d for d, out in zip(demand, empty) if not out]
    non_zero = [d for d in usable if d > 0]
    if non_zero:
        return mean(non_zero)
    return mean(usable) if usable else 0.0


def prepare(
    sold: Sequence[float],
    stocked_out: Sequence[bool] | None = None,
    was_project: Sequence[bool] | None = None,
    *,
    spike_multiple: float | None = None,
) -> Prepared:
    """Turn what was sold into what was wanted."""
    series = [float(value) for value in sold]
    weeks = len(series)
    empty = list(stocked_out or [False] * weeks)
    flagged = list(was_project or [False] * weeks)
    empty += [False] * (weeks - len(empty))
    flagged += [False] * (weeks - len(flagged))

    demand = list(series)
    notes: list[str] = []

    # --- the shelf was empty -------------------------------------------
    # Lifted to the rate seen in the weeks we could sell. Not to the
    # maximum: we know demand was at least what sold, and the honest
    # estimate of the rest is the ordinary rate, not the best case.
    censored: list[int] = []
    recovered = 0.0
    rate = _uncensored_rate(series, empty)
    for week in range(weeks):
        if not empty[week]:
            continue
        censored.append(week)
        if rate > demand[week]:
            recovered += rate - demand[week]
            demand[week] = rate
    if censored:
        notes.append(
            f"{count(len(censored), 'week')} had an empty shelf, so demand in "
            f"them was raised to the usual rate, adding {recovered:,.0f} units."
        )

    # --- one-off project orders -----------------------------------------
    # Either the generator marked them, or they are found: a week more than
    # a few times the usual size, against a part that normally sells far
    # less, is not the usual trade.
    multiple = spike_multiple if spike_multiple is not None else settings.project_spike_multiple
    projects: list[int] = []
    project_units = 0.0

    positive = [d for d in demand if d > 0]
    if positive:
        typical = quantile(positive, 0.5)
        ceiling = typical * multiple
        for week in range(weeks):
            is_project = flagged[week] or (typical > 0 and demand[week] > ceiling)
            if not is_project or demand[week] <= 0:
                continue
            projects.append(week)
            project_units += demand[week] - typical
            demand[week] = typical
    if projects:
        notes.append(
            f"{count(len(projects), 'week')} were one-off project orders, "
            f"{project_units:,.0f} units in all, kept out of the baseline."
        )

    return Prepared(
        demand=demand,
        sold=series,
        weeks=weeks,
        censored_weeks=censored,
        recovered_units=recovered,
        project_weeks=projects,
        project_units=project_units,
        notes=notes,
    )


def carry_forward(
    successor: Sequence[float], predecessor: Sequence[float]
) -> list[float]:
    """Splice a replaced part's history onto the part that replaced it.

    The successor's own weeks win wherever it has them. The predecessor
    fills the weeks before. Without this a supersession looks like a brand
    new part with six weeks of history, and the forecast is useless for the
    better part of a year.
    """
    weeks = max(len(successor), len(predecessor))
    joined: list[float] = []
    for week in range(weeks):
        own = successor[week] if week < len(successor) else 0.0
        before = predecessor[week] if week < len(predecessor) else 0.0
        started = any(successor[: week + 1]) if week < len(successor) else True
        joined.append(float(own) if started else float(before))
    return joined
