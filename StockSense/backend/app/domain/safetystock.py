"""How much to hold, and when to order.

Two sources of uncertainty, not one. Demand varies, and so does the lead
time, and the second is usually the bigger of the two for an importer. The
standard formula combines them:

    sigma over the lead time = sqrt( L × sigma_d²  +  d² × sigma_L² )

where ``d`` is demand per day, ``sigma_d`` its standard deviation, ``L`` the
average lead time in days and ``sigma_L`` its standard deviation. The first
term is demand varying over a fixed wait; the second is the wait itself
varying around an average demand. Dropping the second term is the single
most common mistake in a home-built reorder spreadsheet, and it is why a
supplier that slips two weeks empties a shelf that was "covered".

The cover has to last the lead time **plus the review period**: if the
buyers order on Mondays, a part that drops below its reorder point on
Tuesday waits six days before anyone even looks at it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..numbers import Trace, TraceInput, show, z_for_service_level
from .leadtime import LeadTimeProfile
from .uncertainty import CoverDistribution, from_history


@dataclass(slots=True)
class Policy:
    """When to order and how far to fill up."""

    demand_per_day: float
    deviation_per_day: float
    lead_time_days: float
    lead_time_deviation_days: float
    review_period_days: int
    service_level: float
    z: float

    #: Expected demand across the lead time and the wait for the next review.
    demand_over_cover: float
    #: Standard deviation of that demand.
    deviation_over_cover: float
    safety_stock: float
    reorder_point: float
    order_up_to: float
    #: "normal" when the textbook formula was used, "history" when the
    #: distribution was taken from the part's own past instead.
    method: str = "normal"
    distribution: CoverDistribution | None = None
    trace: Trace | None = None

    @property
    def cover_days(self) -> float:
        return self.lead_time_days + self.review_period_days

    def to_dict(self) -> dict[str, object]:
        return {
            "demand_per_day": round(self.demand_per_day, 4),
            "deviation_per_day": round(self.deviation_per_day, 4),
            "lead_time_days": round(self.lead_time_days, 1),
            "lead_time_deviation_days": round(self.lead_time_deviation_days, 1),
            "review_period_days": self.review_period_days,
            "cover_days": round(self.cover_days, 1),
            "service_level": self.service_level,
            "z": round(self.z, 3),
            "demand_over_cover": round(self.demand_over_cover, 2),
            "deviation_over_cover": round(self.deviation_over_cover, 2),
            "safety_stock": round(self.safety_stock, 2),
            "reorder_point": round(self.reorder_point, 2),
            "order_up_to": round(self.order_up_to, 2),
            "method": self.method,
            "distribution": self.distribution.to_dict() if self.distribution else None,
            "trace": self.trace.to_dict() if self.trace else None,
        }


def build(
    *,
    weekly_rate: float,
    weekly_deviation: float,
    lead_time: LeadTimeProfile,
    review_period_days: int,
    service_level: float,
    supplier_name: str = "",
    history: list[float] | None = None,
) -> Policy:
    """Turn a weekly forecast and a supplier's record into a policy.

    When ``history`` is given and long enough, the cover is sized from the
    part's own past rather than from the normal approximation. For an
    occasional part that is not a refinement, it is the difference between
    a sensible buffer and an absurd one.
    """
    demand_per_day = weekly_rate / 7.0
    deviation_per_day = weekly_deviation / math.sqrt(7.0)

    lead_days = lead_time.average_days
    lead_deviation = lead_time.deviation_days
    cover_days = lead_days + review_period_days

    demand_over_cover = demand_per_day * cover_days

    from_demand = cover_days * deviation_per_day**2
    from_lead_time = (demand_per_day**2) * (lead_deviation**2)
    deviation_over_cover = math.sqrt(from_demand + from_lead_time)

    z = z_for_service_level(service_level)
    safety_stock = z * deviation_over_cover
    reorder_point = demand_over_cover + safety_stock
    order_up_to = reorder_point + demand_per_day * review_period_days

    trace = Trace("When to order and how much to hold")
    trace.add(
        "Demand a day",
        f"{show(weekly_rate, 3)} a week ÷ 7",
        show(demand_per_day, 3),
        unit="a day",
        inputs=[TraceInput("Forecast", f"{show(weekly_rate, 3)} a week", "the forecast", "forecast")],
    )
    trace.add(
        "How long we have to cover",
        f"{show(lead_days, 1)} days of lead time + {review_period_days} days "
        "until the next ordering round",
        show(cover_days, 1),
        unit="days",
        inputs=[
            TraceInput(
                "Lead time actually seen",
                f"{show(lead_days, 1)} days over {lead_time.deliveries} deliveries",
                supplier_name or "this supplier",
                "supplier",
            ),
            TraceInput(
                "Lead time quoted",
                f"{lead_time.quoted_days} days",
                supplier_name or "this supplier",
                "supplier",
            ),
        ],
        note=(
            f"The supplier quotes {lead_time.quoted_days} days and averages "
            f"{show(lead_days, 1)}. The figure used is the one that happened."
            if abs(lead_time.slippage_days) >= 1
            else "The supplier keeps to the quoted lead time."
        ),
    )
    trace.add(
        "Expected demand over that",
        f"{show(demand_per_day, 3)} × {show(cover_days, 1)}",
        show(demand_over_cover, 2),
    )
    trace.add(
        "Uncertainty over that",
        f"√({show(cover_days, 1)} × {show(deviation_per_day, 3)}² + "
        f"{show(demand_per_day, 3)}² × {show(lead_deviation, 1)}²)",
        show(deviation_over_cover, 2),
        note=(
            "Two things vary: how much sells, and how long the supplier takes. "
            f"Here the supplier's timing accounts for "
            f"{(from_lead_time / (from_demand + from_lead_time) * 100) if (from_demand + from_lead_time) > 0 else 0:.0f}% of it."
        ),
    )
    trace.add(
        "Safety stock",
        f"{show(z, 3)} × {show(deviation_over_cover, 2)}",
        show(safety_stock, 2),
        note=f"{service_level:.0%} of cycles without running out.",
        inputs=[
            TraceInput("Service level", f"{service_level:.0%}", "company policy", "policy"),
            TraceInput("Normal deviate", show(z, 3), "standard table", "policy"),
        ],
    )
    trace.add(
        "Order when stock falls to",
        f"{show(demand_over_cover, 2)} + {show(safety_stock, 2)}",
        show(reorder_point, 2),
    )
    trace.add(
        "And fill up to",
        f"{show(reorder_point, 2)} + {show(demand_per_day, 3)} × {review_period_days}",
        show(order_up_to, 2),
    )

    # --- the part's own past, where there is enough of it ---------------
    method = "normal"
    distribution = None
    if history:
        distribution = from_history(
            history,
            lead_time=lead_time,
            review_period_days=review_period_days,
            service_level=service_level,
        )
    if distribution is not None:
        method = "history"
        demand_over_cover = distribution.average
        safety_stock = distribution.safety_stock
        reorder_point = distribution.at_service_level
        order_up_to = reorder_point + demand_per_day * review_period_days
        trace.add(
            "Taken from this part's own past instead",
            f"every run of {distribution.cover_weeks_low}"
            + (
                f" to {distribution.cover_weeks_high}"
                if distribution.cover_weeks_high != distribution.cover_weeks_low
                else ""
            )
            + f" weeks in the history, {distribution.windows:,} of them",
            show(reorder_point, 1),
            note=(
                "Occasional demand is not a bell curve, and the textbook "
                f"formula asks for {show(z * deviation_over_cover, 1)} of safety "
                f"stock here against the {show(safety_stock, 1)} the history "
                "actually calls for. The history is used."
            ),
        )

    return Policy(
        demand_per_day=demand_per_day,
        deviation_per_day=deviation_per_day,
        lead_time_days=lead_days,
        lead_time_deviation_days=lead_deviation,
        review_period_days=review_period_days,
        service_level=service_level,
        z=z,
        demand_over_cover=demand_over_cover,
        deviation_over_cover=deviation_over_cover,
        safety_stock=safety_stock,
        reorder_point=reorder_point,
        order_up_to=order_up_to,
        method=method,
        distribution=distribution,
        trace=trace,
    )


def share_from_lead_time(policy: Policy) -> float:
    """How much of the uncertainty is the supplier's timing rather than demand.

    Worth showing on its own: when this is over half, the useful conversation
    is with the supplier, not with the forecast.
    """
    from_demand = policy.cover_days * policy.deviation_per_day**2
    from_lead = (policy.demand_per_day**2) * (policy.lead_time_deviation_days**2)
    total = from_demand + from_lead
    return (from_lead / total) if total > 0 else 0.0
