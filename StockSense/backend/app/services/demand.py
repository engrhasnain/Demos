"""From a part to a forecast, with everything in between.

This is the one place that decides what a part's demand is. Everything
downstream — safety stock, the order quantity, the cash it consumes — rests
on the number this produces, so the whole route is recorded: what the raw
history was, what was corrected and why, which pattern it turned out to be,
which method that implies, and what the method then said.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import classify, forecast as models
from ..models import DemandHistory, Part
from ..numbers import Trace, TraceInput, mean, show
from ..text import count
from . import history as preparation

#: A part with fewer weeks than this of its own selling history cannot be
#: forecast from itself, however much of it there is.
MINIMUM_SELLING_WEEKS = 4


@dataclass(slots=True)
class DemandView:
    """Everything known about one part's demand."""

    part_id: int
    prepared: preparation.Prepared
    pattern: classify.Pattern
    forecast: models.Forecast
    #: Set when the forecast came from the family rather than this part.
    analogue_of: list[str] | None = None

    @property
    def weekly_rate(self) -> float:
        return self.forecast.rate

    @property
    def weekly_deviation(self) -> float:
        return self.forecast.deviation

    def to_dict(self) -> dict[str, object]:
        return {
            "part_id": self.part_id,
            "prepared": self.prepared.to_dict(),
            "pattern": self.pattern.to_dict(),
            "forecast": self.forecast.to_dict(),
            "analogue_of": self.analogue_of,
            "weekly_rate": round(self.weekly_rate, 3),
            "sold": self.prepared.sold,
            "demand": [round(v, 2) for v in self.prepared.demand],
        }


def _series_for(session: Session, part: Part) -> tuple[list[float], list[bool], list[bool]]:
    """This part's history, with a predecessor's spliced on if there is one."""
    record = session.scalar(
        select(DemandHistory).where(DemandHistory.part_id == part.id)
    )
    if record is None:
        return [], [], []

    sold = [float(v) for v in record.sold]
    empty = [bool(v) for v in record.stocked_out]
    project = [bool(v) for v in record.was_project]

    if part.replaces_part_id:
        older = session.scalar(
            select(DemandHistory).where(DemandHistory.part_id == part.replaces_part_id)
        )
        if older is not None:
            sold = preparation.carry_forward(sold, [float(v) for v in older.sold])
            # The flags belong to whichever part supplied the week, and the
            # safe assumption for a borrowed week is that nothing was wrong
            # with it; a false stock-out would inflate the forecast.
            empty = (empty + [False] * len(sold))[: len(sold)]
            project = (project + [False] * len(sold))[: len(sold)]

    return sold, empty, project


def _family_analogue(
    session: Session, part: Part, limit: int = 12
) -> tuple[list[float], list[str]]:
    """The average weekly shape of the part's established siblings.

    Only parts with enough history of their own, so a family of new parts
    does not borrow from itself.
    """
    siblings = session.scalars(
        select(Part)
        .where(
            Part.family == part.family,
            Part.id != part.id,
            Part.is_active.is_(True),
        )
        .limit(120)
    )
    gathered: list[list[float]] = []
    names: list[str] = []
    for sibling in siblings:
        record = session.scalar(
            select(DemandHistory).where(DemandHistory.part_id == sibling.id)
        )
        if record is None:
            continue
        series = [float(v) for v in record.sold]
        if sum(1 for v in series if v > 0) < MINIMUM_SELLING_WEEKS * 2:
            continue
        gathered.append(series)
        names.append(sibling.code)
        if len(gathered) >= limit:
            break

    if not gathered:
        return [], []

    weeks = min(len(s) for s in gathered)
    averaged = [mean([s[w] for s in gathered]) for w in range(weeks)]
    return averaged, names


#: A part counts as newly listed when everything it has ever sold happened
#: inside this many recent weeks. Anything older than that has had its
#: chance, however little it sold.
NEW_PART_WINDOW_WEEKS = 26


def _is_newly_listed(demand: list[float], part: Part) -> bool:
    """Did this part only arrive recently?

    Judged on when its sales start, not on how many there are. A part that
    first sold four weeks ago is new. A part that sold twice, eighteen
    months apart, is slow — and buying for it as though it were new would
    be buying on somebody else's demand.
    """
    if part.replaces_part_id:
        # Its predecessor's history was spliced on, so it is not new.
        return False
    first = next((week for week, value in enumerate(demand) if value > 0), None)
    if first is None:
        # Never sold at all. Not new, just not wanted.
        return False
    return (len(demand) - first) <= NEW_PART_WINDOW_WEEKS


def for_part(session: Session, part: Part) -> DemandView:
    """The demand view for one part, by whichever route is honest for it."""
    sold, empty, project = _series_for(session, part)
    prepared = preparation.prepare(sold, empty, project)

    selling_weeks = sum(1 for value in prepared.demand if value > 0)
    pattern = classify.classify(prepared.demand)

    # --- enough history of its own? ------------------------------------
    if selling_weeks >= MINIMUM_SELLING_WEEKS:
        forecast = models.run(pattern.suggested_method, prepared.demand)
        return DemandView(part.id, prepared, pattern, forecast)

    # A part that has sold almost nothing is not the same as a part that
    # has not existed long. Two years of history with no sales in it is an
    # answer, and the answer is "nobody wants this" — borrowing the
    # family's demand for it is how dead stock gets reordered for ever.
    if not _is_newly_listed(prepared.demand, part):
        forecast = models.run(pattern.suggested_method, prepared.demand)
        if selling_weeks == 0:
            forecast.notes.append(
                f"{len(prepared.demand)} weeks of history and not one sale. "
                "Nothing is forecast, and nothing should be bought."
            )
        else:
            forecast.notes.append(
                f"Only {count(selling_weeks, 'week')} with a sale in "
                f"{len(prepared.demand)} weeks of being listed, so this is a "
                "slow part rather than a new one."
            )
        return DemandView(part.id, prepared, pattern, forecast)

    # --- borrow from the family ----------------------------------------
    analogue, names = _family_analogue(session, part)
    if not analogue:
        forecast = models.run(pattern.suggested_method, prepared.demand)
        forecast.notes.append(
            "Too little history to forecast, and no established parts in the "
            "family to borrow from."
        )
        return DemandView(part.id, prepared, pattern, forecast)

    borrowed_pattern = classify.classify(analogue)
    forecast = models.run(borrowed_pattern.suggested_method, analogue)
    forecast.method = "analogue"
    forecast.borrowed = True
    # A borrowed forecast is a guess about a part nobody has sold yet. The
    # range around it has to be wider than the family's own, or the safety
    # stock pretends to a confidence that is not there.
    forecast.deviation = max(forecast.deviation, forecast.rate) * 1.5
    forecast.notes.append(
        f"Only {selling_weeks} weeks of its own sales, so the shape of "
        f"{len(names)} established parts in the family was used instead, "
        "with a wider range."
    )

    trace = Trace("Weekly demand")
    trace.add(
        "Not enough history of its own",
        f"{selling_weeks} weeks with a sale, {MINIMUM_SELLING_WEEKS} needed",
        "borrow from the family",
        note="A forecast off four weeks of a new part is a number, not a forecast.",
    )
    trace.add(
        "Average the family",
        f"{len(names)} established parts in {part.family.replace('_', ' ')}",
        show(forecast.rate, 3),
        unit="a week",
        inputs=[
            TraceInput("Parts used", ", ".join(names[:4]) + ("…" if len(names) > 4 else ""),
                       part.family.replace("_", " "), "catalogue")
        ],
    )
    trace.add(
        "Widen the range",
        "the spread of the family, at least the rate itself, then half as much again",
        show(forecast.deviation, 2),
        note="Buying against a borrowed forecast deserves more cover, not the same.",
    )
    forecast.trace = trace

    return DemandView(part.id, prepared, borrowed_pattern, forecast, analogue_of=names)
