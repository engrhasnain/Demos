"""Spending a limited amount of money as well as it can be spent.

Every reorder tool will happily recommend forty million dollars of stock on
a week when there is six million to spend. What the buyer needs is not the
list, it is the line through the list: these, and not those, and here is
why.

That is a knapsack problem, and the exact answer is not worth computing.
Items are taken in order of how much good they do per dollar, which is the
standard greedy approximation and is within a hair of optimal when no
single line is a large share of the budget. Where it matters is that the
rule is one sentence long and a buyer can argue with it.

Two things stop it being a pure sort:

**Supplier minimums.** A supplier with a hundred-thousand minimum either
gets an order worth a hundred thousand or gets nothing. Half an order is
not a cheaper order, it is a rejected one.

**Urgency is not value.** The most urgent line is often cheap. Sorting by
value buys the expensive things first and runs out before the part that
stops a production line. Sorting by urgency per dollar does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from ..numbers import Trace, dec, money
from ..text import count
from .reorder import DEFERRED, ORDER, PREBUILD, Recommendation


@dataclass(slots=True)
class Allocation:
    """What survived the budget, and what did not."""

    accepted: list[Recommendation] = field(default_factory=list)
    deferred: list[Recommendation] = field(default_factory=list)
    cap: Decimal = Decimal("0")
    committed: Decimal = Decimal("0")
    #: Suppliers whose whole order was dropped for failing their minimum.
    below_minimum: list[str] = field(default_factory=list)
    trace: Trace | None = None

    @property
    def remaining(self) -> Decimal:
        return self.cap - self.committed

    def to_dict(self) -> dict[str, object]:
        return {
            "cap": str(money(self.cap)),
            "committed": str(money(self.committed)),
            "remaining": str(money(self.remaining)),
            "accepted": len(self.accepted),
            "deferred": len(self.deferred),
            "below_minimum": self.below_minimum,
            "trace": self.trace.to_dict() if self.trace else None,
        }


def _enforce_minimums(
    accepted: list[Recommendation], deferred: list[Recommendation]
) -> list[str]:
    """Drop whole any supplier whose surviving lines miss their minimum.

    Mutates both lists and returns the suppliers that were dropped.
    """
    by_supplier: dict[int, list[Recommendation]] = {}
    for recommendation in accepted:
        by_supplier.setdefault(recommendation.part.supplier_id, []).append(recommendation)

    dropped: list[str] = []
    for lines in by_supplier.values():
        supplier = lines[0].part.supplier
        minimum = dec(getattr(supplier, "minimum_order_value", 0) or 0)
        if minimum <= 0:
            continue
        if sum((line.value for line in lines), Decimal("0")) >= minimum:
            continue
        for line in lines:
            line.decision = DEFERRED
            line.reason = "below_minimum"
            accepted.remove(line)
            deferred.append(line)
        dropped.append(supplier.name)
    return dropped


def allocate(
    recommendations: list[Recommendation], cap: Decimal | float
) -> Allocation:
    """Fit the week's orders inside the cash available."""
    cap = dec(cap)
    wanted = [r for r in recommendations if r.decision in {ORDER, PREBUILD} and r.quantity > 0]
    total_wanted = sum((r.value for r in wanted), Decimal("0"))

    trace = Trace("How the week's money was spent")
    trace.add(
        "What the engine would buy",
        f"{count(len(wanted), 'line')}",
        f"{money(total_wanted):,}",
    )
    trace.add("What there is to spend", "this week's cash cap", f"{money(cap):,}")

    if total_wanted <= cap:
        trace.add(
            "Everything fits",
            f"{money(total_wanted):,} <= {money(cap):,}",
            "nothing held over for cash",
        )
        # Having the money does not mean the supplier will take the order.
        # A minimum is a minimum whether or not the budget is tight.
        accepted = list(wanted)
        deferred: list[Recommendation] = []
        dropped = _enforce_minimums(accepted, deferred)
        committed = sum((r.value for r in accepted), Decimal("0"))
        if dropped:
            trace.add(
                "Suppliers under their minimum",
                f"{count(len(dropped), 'supplier')} could not reach the order "
                "value they insist on",
                "held over to next week",
                note="Part of a minimum order is not a cheaper order, it is a "
                "rejected one.",
            )
        return Allocation(
            accepted=accepted,
            deferred=deferred,
            cap=cap,
            committed=committed,
            below_minimum=dropped,
            trace=trace,
        )

    # Most good per dollar first.
    ranked = sorted(
        wanted,
        key=lambda r: (r.urgency / float(r.value) if r.value > 0 else 0.0),
        reverse=True,
    )
    trace.add(
        "Not everything fits",
        f"{money(total_wanted):,} wanted against {money(cap):,}",
        f"{money(total_wanted - cap):,} over",
        note="Lines are taken in order of how much good each does per dollar, "
        "so the cheap urgent part is bought before the expensive comfortable one.",
    )

    accepted: list[Recommendation] = []
    deferred: list[Recommendation] = []
    committed = Decimal("0")

    for recommendation in ranked:
        if committed + recommendation.value <= cap:
            accepted.append(recommendation)
            committed += recommendation.value
        else:
            recommendation.decision = DEFERRED
            recommendation.reason = "no_cash"
            deferred.append(recommendation)

    # --- supplier minimums ---------------------------------------------
    # Having chosen, check that each supplier's surviving lines still add
    # up to an order they will accept. One that does not is dropped whole
    # and its money handed back, which may let other lines in.
    before = sum((line.value for line in accepted), Decimal("0"))
    dropped_names = _enforce_minimums(accepted, deferred)
    committed -= before - sum((line.value for line in accepted), Decimal("0"))

    if dropped_names:
        trace.add(
            "Suppliers under their minimum",
            f"{count(len(dropped_names), 'supplier')} could not reach the order "
            "value they insist on",
            "held over to next week",
            note="Part of a minimum order is not a cheaper order, it is a "
            "rejected one.",
        )

    # The money handed back may now cover something that was deferred.
    recovered = 0
    for recommendation in sorted(
        [d for d in deferred if d.reason == "no_cash"],
        key=lambda r: (r.urgency / float(r.value) if r.value > 0 else 0.0),
        reverse=True,
    ):
        if committed + recommendation.value > cap:
            continue
        supplier = recommendation.part.supplier
        minimum = dec(supplier.minimum_order_value or 0)
        if minimum > 0 and recommendation.value < minimum:
            continue
        recommendation.decision = ORDER
        recommendation.reason = "below_reorder_point"
        deferred.remove(recommendation)
        accepted.append(recommendation)
        committed += recommendation.value
        recovered += 1

    if recovered:
        trace.add(
            "Money handed back was re-spent",
            f"{count(recovered, 'line')} brought back in",
            f"{money(committed):,} committed",
        )

    trace.add(
        "Committed",
        f"{count(len(accepted), 'line')} of {len(wanted)}",
        f"{money(committed):,}",
        note=f"{money(cap - committed):,} left unspent.",
    )

    return Allocation(
        accepted=accepted,
        deferred=deferred,
        cap=cap,
        committed=committed,
        below_minimum=dropped_names,
        trace=trace,
    )
