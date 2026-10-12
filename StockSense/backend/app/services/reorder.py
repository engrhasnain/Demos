"""From a forecast to something a buyer can send to a supplier.

The forecast says 4.7 a week. Nobody can order 4.7 a week. Between the two
sit the supplier's lead time and how badly they keep to it, the pack size,
the minimum order quantity, what is already on the water, the shutdown that
closes the factory in January, and the question of whether this part is
worth holding at all.

Each of those is a step with a number attached, and the screen shows all of
them, because "the system says order 2,000" is not something a buyer will
sign their name to.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy.orm import Session

from ..config import settings
from ..domain import calendar as shutdowns, leadtime as leadtimes, safetystock
from ..models import Part
from ..numbers import Trace, TraceInput, dec, money, round_to_pack, show
from ..text import count
from .demand import DemandView

#: What a line is telling the buyer to do.
ORDER = "order"
PREBUILD = "prebuild"
DEFERRED = "deferred"
WATCH = "watch"

DECISION_LABELS: dict[str, str] = {
    ORDER: "Order",
    PREBUILD: "Order before the shutdown",
    DEFERRED: "Not this week",
    WATCH: "Watch",
}

REASON_LABELS: dict[str, str] = {
    "below_reorder_point": "Below the reorder point",
    "shutdown_cover": "Shutdown cover",
    "covered": "Covered",
    "no_demand": "Nothing selling",
    "replaced": "Replaced by another part",
    "dead_stock": "Not moving",
    "no_cash": "Cash ran out",
    "below_minimum": "Under the supplier minimum",
}


@dataclass(slots=True)
class Recommendation:
    part: Part
    #: The demand work this rests on, carried so nothing downstream has to
    #: forecast the same part a second time.
    view: DemandView
    decision: str
    reason: str
    quantity: int
    raw_quantity: float
    value: Decimal
    policy: safetystock.Policy
    position: float
    days_of_cover: float
    urgency: float
    shutdown: shutdowns.Shutdown | None
    shutdown_note: str = ""
    flags: list[str] = field(default_factory=list)
    trace: Trace | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "decision": self.decision,
            "decision_label": DECISION_LABELS.get(self.decision, self.decision),
            "reason": self.reason,
            "reason_label": REASON_LABELS.get(self.reason, self.reason),
            "quantity": self.quantity,
            "raw_quantity": round(self.raw_quantity, 2),
            "value": str(money(self.value)),
            "position": round(self.position, 2),
            "days_of_cover": round(self.days_of_cover, 1),
            "urgency": round(self.urgency, 4),
            "shutdown_note": self.shutdown_note,
            "flags": self.flags,
            "policy": self.policy.to_dict(),
            "trace": self.trace.to_dict() if self.trace else None,
        }


def _days_of_cover(position: float, daily: float) -> float:
    if daily <= 0:
        return 999.0 if position > 0 else 0.0
    return position / daily


def build(
    session: Session,
    part: Part,
    view: DemandView,
    *,
    as_of: dt.date,
    review_period_days: int | None = None,
) -> Recommendation:
    """Decide what to do about one part this week."""
    review = review_period_days or settings.review_period_days
    supplier = part.supplier

    lead_time = leadtimes.profile(
        supplier.quoted_lead_time_days, supplier.lead_time_samples or []
    )
    service_level = settings.service_level_for(part.abc_class)
    policy = safetystock.build(
        weekly_rate=view.weekly_rate,
        weekly_deviation=view.weekly_deviation,
        lead_time=lead_time,
        review_period_days=review,
        service_level=service_level,
        supplier_name=supplier.name,
        history=view.prepared.demand,
    )

    position = float(part.on_hand) + float(part.on_order)
    cover = _days_of_cover(position, policy.demand_per_day)
    shutdown = shutdowns.next_shutdown(supplier.country, as_of)

    trace = Trace(f"What to do about {part.code}")
    trace.add(
        "What we have",
        f"{part.on_hand:,} on the shelf + {part.on_order:,} on order",
        f"{position:,.0f}",
        inputs=[
            TraceInput("On the shelf", f"{part.on_hand:,}", "stock record", "catalogue"),
            TraceInput(
                "On order",
                f"{part.on_order:,}"
                + (f", due {part.on_order_due}" if part.on_order_due else ""),
                supplier.name,
                "supplier",
            ),
        ],
    )
    trace.add(
        "How long that lasts",
        f"{position:,.0f} ÷ {show(policy.demand_per_day, 3)} a day",
        f"{cover:,.0f}",
        unit="days",
        note=(
            "Nothing is selling, so it lasts indefinitely."
            if policy.demand_per_day <= 0
            else f"Against {show(policy.cover_days, 0)} days that have to be covered."
        ),
    )

    flags: list[str] = []
    if view.forecast.borrowed:
        flags.append("borrowed_forecast")
    if view.prepared.censored_weeks:
        flags.append("was_out_of_stock")
    if view.prepared.project_weeks:
        flags.append("had_project_orders")
    if not lead_time.is_reliable:
        flags.append("unreliable_supplier")
    if safetystock.share_from_lead_time(policy) > 0.5:
        flags.append("supplier_timing_dominates")

    # ------------------------------------------------------------------
    # The reasons not to order anything at all
    # ------------------------------------------------------------------
    if part.replaced_by_part_id:
        trace.add(
            "Replaced",
            "a newer part supersedes this one",
            "do not reorder",
            note="Its remaining stock is sold down; the successor is bought instead.",
        )
        return Recommendation(
            part, view, WATCH, "replaced", 0, 0.0, Decimal("0"), policy, position,
            cover, 0.0, shutdown, flags=flags, trace=trace,
        )

    if view.weekly_rate <= 0:
        dead = position > 0
        if dead:
            flags.append("dead_stock")
        trace.add(
            "Nothing is selling",
            f"{view.pattern.periods} weeks of history, "
            f"{view.pattern.periods_with_demand} with a sale",
            "do not reorder",
            note=(
                f"{position:,.0f} on the shelf worth "
                f"{money(dec(position) * part.unit_cost):,} and not moving."
                if dead
                else "Nothing on the shelf either."
            ),
        )
        return Recommendation(
            part, view, WATCH, "dead_stock" if dead else "no_demand", 0, 0.0,
            Decimal("0"), policy, position, cover, 0.0, shutdown,
            flags=flags, trace=trace,
        )

    # ------------------------------------------------------------------
    # The shutdown, which can make an order urgent weeks before the
    # reorder point would
    # ------------------------------------------------------------------
    shutdown_note = ""
    shutdown_target = 0.0
    if shutdown is not None and shutdown.affects:
        days_left = shutdown.days_until_order_by(as_of)
        weeks_needed = shutdowns.weeks_of_cover_needed(shutdown)
        shutdown_target = view.weekly_rate * (
            weeks_needed + settings.shutdown_prebuild_weeks
        )
        # The test is not "is the cut-off close". It is: on the last day we
        # can order, will what is on the shelf carry us through the
        # shutdown? Anything bought after that date arrives after the
        # factory is back, which is too late by definition.
        position_at_cutoff = position - policy.demand_per_day * max(0, days_left)
        short_at_cutoff = shutdown_target - position_at_cutoff
        # Ordering now still has to arrive before the plant shuts.
        arrives_in_time = days_left >= 0
        if arrives_in_time and short_at_cutoff > 0:
            shutdown_note = (
                f"{shutdown.label} closes {shutdown.closes_on:%d %b}; "
                f"{count(days_left, 'day')} left to order."
            )
            trace.add(
                "Where this lands on the last order date",
                f"{position:,.0f} now − {show(policy.demand_per_day, 3)} a day "
                f"× {count(days_left, 'day')}",
                show(position_at_cutoff, 1),
                note=f"Against the {show(shutdown_target, 1)} needed to get "
                "through the shutdown.",
            )
            trace.add(
                "Shutdown ahead",
                f"{shutdown.label} shuts {shutdown.closes_on:%d %b} and is back "
                f"to normal {shutdown.back_to_normal_on:%d %b}",
                f"{weeks_needed:.1f} weeks of cover needed",
                inputs=[
                    TraceInput(
                        "Last order date",
                        shutdown.order_by.isoformat(),
                        shutdown.label,
                        "calendar",
                    ),
                ],
                note="An order placed after that date does not ship late, it "
                "waits for the factory to come back.",
            )
            flags.append("shutdown_ahead")

    # ------------------------------------------------------------------
    # The ordinary decision
    # ------------------------------------------------------------------
    target = max(policy.order_up_to, shutdown_target)
    is_prebuild = shutdown_target > policy.order_up_to and bool(shutdown_note)
    needed = target - position

    trace.add(
        "Order when it falls to",
        f"{show(policy.demand_over_cover, 1)} expected + "
        f"{show(policy.safety_stock, 1)} safety stock",
        show(policy.reorder_point, 1),
    )

    if position > policy.reorder_point and not is_prebuild:
        trace.add(
            "Nothing to do",
            f"{position:,.0f} on hand is above the reorder point "
            f"{show(policy.reorder_point, 1)}",
            "covered",
        )
        return Recommendation(
            part, view, WATCH, "covered", 0, 0.0, Decimal("0"), policy, position,
            cover, 0.0, shutdown, shutdown_note, flags, trace,
        )

    if needed <= 0:
        return Recommendation(
            part, view, WATCH, "covered", 0, 0.0, Decimal("0"), policy, position,
            cover, 0.0, shutdown, shutdown_note, flags, trace,
        )

    if is_prebuild:
        trace.add(
            "Fill up for the shutdown instead",
            f"{show(view.weekly_rate, 2)} a week × "
            f"({shutdowns.weeks_of_cover_needed(shutdown):.1f} weeks shut + "
            f"{settings.shutdown_prebuild_weeks} spare)",
            show(shutdown_target, 1),
        )
    else:
        trace.add(
            "Fill up to",
            f"{show(policy.reorder_point, 1)} + "
            f"{show(policy.demand_per_day, 3)} × {review} days",
            show(policy.order_up_to, 1),
        )

    trace.add(
        "So we need",
        f"{show(target, 1)} − {position:,.0f}",
        show(needed, 1),
    )

    quantity = round_to_pack(needed, part.pack_size, part.minimum_order_quantity)
    if quantity != round(needed):
        trace.add(
            "Rounded to something orderable",
            f"packs of {part.pack_size:,}"
            + (
                f", minimum {part.minimum_order_quantity:,}"
                if part.minimum_order_quantity
                else ""
            ),
            f"{quantity:,}",
            note="Rounded up. Rounding an order down to save a little is how a "
            "part that was going to be covered is not.",
        )

    value = money(dec(quantity) * part.unit_cost)
    trace.add(
        "What that costs",
        f"{quantity:,} × {part.unit_cost}",
        f"{value:,}",
        unit=settings.base_currency,
        inputs=[TraceInput("Unit cost", str(part.unit_cost), part.code, "catalogue")],
    )

    # How badly this is needed, which is the only fair way to spend a
    # limited amount of cash. Lower cover is more urgent; an A part is
    # more urgent than a C part at the same cover.
    shortfall = max(0.0, policy.reorder_point - position)
    class_weight = {"A": 1.0, "B": 0.6, "C": 0.35}.get(part.abc_class, 0.35)
    cover_pressure = 1.0 / (1.0 + max(0.0, cover))
    urgency = class_weight * cover_pressure * (1.0 + min(2.0, shortfall / max(1.0, policy.reorder_point)))
    if is_prebuild:
        urgency *= 1.6

    return Recommendation(
        part=part,
        view=view,
        decision=PREBUILD if is_prebuild else ORDER,
        reason="shutdown_cover" if is_prebuild else "below_reorder_point",
        quantity=quantity,
        raw_quantity=needed,
        value=value,
        policy=policy,
        position=position,
        days_of_cover=cover,
        urgency=urgency,
        shutdown=shutdown,
        shutdown_note=shutdown_note,
        flags=flags,
        trace=trace,
    )
