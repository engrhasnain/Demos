"""Replaying the year.

Forecast accuracy is not the question. The question is whether the shelves
would have been emptier or fuller, and whether more or less money would
have been tied up. So the last twelve months are run again, week by week,
twice: once with the orders the buyers actually placed, and once with the
orders StockSense would have recommended. Both face exactly the same
demand, start from exactly the same stock, and wait exactly the same lead
times.

The one rule that makes this honest
-----------------------------------
At week W, the StockSense arm may only see weeks 0 to W-1. Not W, and
certainly not the rest of the year. A backtest that lets the model see the
answer is a very good way to prove something untrue, and it is the most
common fault in a forecasting demonstration. The slicing is done in one
place, below, and it is the only place history is read.
"""

from __future__ import annotations

import datetime as dt
import math
import time
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..config import settings
from ..domain import classify, forecast as models, leadtime as leadtimes, metrics, safetystock
from ..models import DemandHistory, HistoricOrder, Part
from ..numbers import dec, mean, money, round_to_pack
from . import history as preparation

#: How many weeks of the history are replayed. The weeks before them are
#: the training period, which both arms are allowed to know about.
REPLAY_WEEKS = 52


@dataclass(slots=True)
class ArmResult:
    """What one way of ordering would have produced."""

    name: str
    stockout_weeks: int = 0
    units_short: float = 0.0
    parts_affected: int = 0
    orders_placed: int = 0
    units_ordered: float = 0.0
    spend: Decimal = Decimal("0")
    #: Averaged over the weeks, which is what carrying cost is charged on.
    average_inventory_value: Decimal = Decimal("0")
    closing_inventory_value: Decimal = Decimal("0")
    weekly_inventory: list[float] = field(default_factory=list)
    weekly_stockouts: list[int] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "stockout_weeks": self.stockout_weeks,
            "units_short": round(self.units_short, 1),
            "parts_affected": self.parts_affected,
            "orders_placed": self.orders_placed,
            "units_ordered": round(self.units_ordered, 1),
            "spend": str(money(self.spend)),
            "average_inventory_value": str(money(self.average_inventory_value)),
            "closing_inventory_value": str(money(self.closing_inventory_value)),
            "weekly_inventory": [round(v, 2) for v in self.weekly_inventory],
            "weekly_stockouts": self.weekly_stockouts,
        }


@dataclass(slots=True)
class PartOutcome:
    part_id: int
    pattern: str
    buyers_stockout_weeks: int
    stocksense_stockout_weeks: int
    buyers_average_value: float
    stocksense_average_value: float


def _true_demand(record: DemandHistory) -> list[float]:
    """What customers wanted, which is not always what was sold.

    Both arms are judged against this. Judging against recorded sales
    would reward whichever arm ran out more, because a week with an empty
    shelf records no demand at all.
    """
    prepared = preparation.prepare(record.sold, record.stocked_out, record.was_project)
    return prepared.demand


def _simulate(
    *,
    demand: list[float],
    start_week: int,
    opening: float,
    unit_cost: float,
    arrivals: dict[int, float],
    policy_for_week=None,
    lead_weeks: int = 4,
    pack_size: int = 1,
    minimum: int = 0,
) -> tuple[ArmResult, list[float], list[int]]:
    """Run one part through one arm of the replay.

    ``arrivals`` is used for the buyers' arm, where the orders are known.
    ``policy_for_week`` is used for the StockSense arm, where they are not.
    """
    on_hand = opening
    pipeline: dict[int, float] = dict(arrivals)
    inventory_by_week: list[float] = []
    stockouts_by_week: list[int] = []

    stockout_weeks = 0
    units_short = 0.0
    orders = 0
    units_ordered = 0.0
    spend = 0.0

    for week in range(start_week, len(demand)):
        on_hand += pipeline.pop(week, 0.0)

        wanted = demand[week]
        shipped = min(on_hand, wanted)
        on_hand -= shipped
        short = wanted - shipped
        if short > 0:
            stockout_weeks += 1
            units_short += short

        if policy_for_week is not None:
            on_order = sum(value for due, value in pipeline.items() if due > week)
            quantity = policy_for_week(week, on_hand, on_order)
            if quantity > 0:
                quantity = round_to_pack(quantity, pack_size, minimum)
                due = week + lead_weeks
                pipeline[due] = pipeline.get(due, 0.0) + quantity
                orders += 1
                units_ordered += quantity
                spend += quantity * unit_cost

        inventory_by_week.append(on_hand * unit_cost)
        stockouts_by_week.append(1 if short > 0 else 0)

    result = ArmResult(
        name="",
        stockout_weeks=stockout_weeks,
        units_short=units_short,
        parts_affected=1 if stockout_weeks else 0,
        orders_placed=orders,
        units_ordered=units_ordered,
        spend=dec(spend),
        average_inventory_value=dec(mean(inventory_by_week)),
        closing_inventory_value=dec(inventory_by_week[-1] if inventory_by_week else 0),
    )
    return result, inventory_by_week, stockouts_by_week


def _combine(name: str, parts: list[ArmResult], weeks: int) -> ArmResult:
    total = ArmResult(name=name)
    total.weekly_inventory = [0.0] * weeks
    total.weekly_stockouts = [0] * weeks
    for row in parts:
        total.stockout_weeks += row.stockout_weeks
        total.units_short += row.units_short
        total.parts_affected += row.parts_affected
        total.orders_placed += row.orders_placed
        total.units_ordered += row.units_ordered
        total.spend += row.spend
        total.average_inventory_value += row.average_inventory_value
        total.closing_inventory_value += row.closing_inventory_value
    return total


def run_replay(
    session: Session,
    *,
    weeks: int = REPLAY_WEEKS,
    limit: int | None = None,
) -> dict[str, object]:
    """Replay the year both ways and report what each would have cost."""
    started = time.perf_counter()

    query = select(Part).options(selectinload(Part.supplier)).order_by(Part.id)
    if limit:
        query = query.limit(limit)
    parts = list(session.scalars(query))

    histories = {
        record.part_id: record for record in session.scalars(select(DemandHistory))
    }
    orders_by_part: dict[int, list[HistoricOrder]] = {}
    for order in session.scalars(select(HistoricOrder)):
        orders_by_part.setdefault(order.part_id, []).append(order)

    buyer_rows: list[ArmResult] = []
    engine_rows: list[ArmResult] = []
    buyer_inventory = [0.0] * weeks
    engine_inventory = [0.0] * weeks
    buyer_stockouts = [0] * weeks
    engine_stockouts = [0] * weeks
    outcomes: list[PartOutcome] = []
    accuracy_cases: list[tuple[list[float], list[float], list[float]]] = []

    for part in parts:
        record = histories.get(part.id)
        if record is None or not record.sold:
            continue
        demand = _true_demand(record)
        total_weeks = len(demand)
        start_week = max(1, total_weeks - weeks)
        if start_week >= total_weeks:
            continue

        unit_cost = float(part.unit_cost)
        supplier = part.supplier
        lead_time = leadtimes.profile(
            supplier.quoted_lead_time_days, supplier.lead_time_samples or []
        )
        lead_weeks = max(1, round(lead_time.average_days / 7))

        # Both arms start from the same shelf: six weeks of what the part
        # was selling before the replay began. Giving either arm a better
        # opening position would decide the result before it started.
        training = demand[:start_week]
        opening_rate = mean([v for v in training[-26:]] or [0.0])
        opening = opening_rate * 6

        # --- the buyers' arm ------------------------------------------
        arrivals: dict[int, float] = {}
        for order in orders_by_part.get(part.id, []):
            arrival_week = (
                (order.arrived_on - record.starts_on).days // 7
                if order.arrived_on
                else None
            )
            if arrival_week is None or arrival_week < start_week:
                continue
            if arrival_week >= total_weeks:
                continue
            arrivals[arrival_week] = arrivals.get(arrival_week, 0.0) + order.quantity

        buyers, buyers_inv, buyers_out = _simulate(
            demand=demand,
            start_week=start_week,
            opening=opening,
            unit_cost=unit_cost,
            arrivals=arrivals,
        )
        buyers.spend = dec(
            sum(
                float(o.quantity) * float(o.unit_cost)
                for o in orders_by_part.get(part.id, [])
                if o.ordered_on
                and (o.ordered_on - record.starts_on).days // 7 >= start_week
            )
        )
        buyers.orders_placed = len(
            [
                o
                for o in orders_by_part.get(part.id, [])
                if o.ordered_on
                and (o.ordered_on - record.starts_on).days // 7 >= start_week
            ]
        )

        # --- the StockSense arm ---------------------------------------
        # Re-forecast every four weeks rather than every week. A buyer does
        # not rebuild a model nightly, and re-forecasting weekly on two
        # years of history would make the replay forty times slower for a
        # result that moves in the third decimal place.
        service_level = settings.service_level_for(part.abc_class)
        cached: dict[str, float] = {}
        forecast_track: list[float] = []

        def policy_for_week(week: int, on_hand: float, on_order: float) -> float:
            # THE rule of this whole module: only weeks before this one.
            if week % 4 == 0 or not cached:
                seen = demand[:week]
                pattern = classify.classify(seen)
                forecast = models.run(pattern.suggested_method, seen)
                policy = safetystock.build(
                    weekly_rate=forecast.rate,
                    weekly_deviation=forecast.deviation,
                    lead_time=lead_time,
                    review_period_days=settings.review_period_days,
                    service_level=service_level,
                    history=seen,
                )
                cached["rate"] = forecast.rate
                cached["reorder_point"] = policy.reorder_point
                cached["order_up_to"] = policy.order_up_to
            forecast_track.append(cached["rate"])
            position = on_hand + on_order
            if position >= cached["reorder_point"]:
                return 0.0
            return max(0.0, cached["order_up_to"] - position)

        engine, engine_inv, engine_out = _simulate(
            demand=demand,
            start_week=start_week,
            opening=opening,
            unit_cost=unit_cost,
            arrivals={},
            policy_for_week=policy_for_week,
            lead_weeks=lead_weeks,
            pack_size=part.pack_size,
            minimum=part.minimum_order_quantity,
        )

        buyer_rows.append(buyers)
        engine_rows.append(engine)
        for index in range(min(weeks, len(buyers_inv))):
            buyer_inventory[index] += buyers_inv[index]
            buyer_stockouts[index] += buyers_out[index]
        for index in range(min(weeks, len(engine_inv))):
            engine_inventory[index] += engine_inv[index]
            engine_stockouts[index] += engine_out[index]

        outcomes.append(
            PartOutcome(
                part_id=part.id,
                pattern=classify.classify(training).kind,
                buyers_stockout_weeks=buyers.stockout_weeks,
                stocksense_stockout_weeks=engine.stockout_weeks,
                buyers_average_value=float(buyers.average_inventory_value),
                stocksense_average_value=float(engine.average_inventory_value),
            )
        )
        if forecast_track:
            actual = demand[start_week:]
            accuracy_cases.append(
                (training, actual, forecast_track[: len(actual)])
            )

    buyers_total = _combine("The buyers", buyer_rows, weeks)
    engine_total = _combine("StockSense", engine_rows, weeks)
    buyers_total.weekly_inventory = buyer_inventory
    buyers_total.weekly_stockouts = buyer_stockouts
    engine_total.weekly_inventory = engine_inventory
    engine_total.weekly_stockouts = engine_stockouts

    # --- by pattern, because the averages hide the hard parts -----------
    by_pattern: dict[str, dict[str, float]] = {}
    for outcome in outcomes:
        row = by_pattern.setdefault(
            outcome.pattern,
            {"parts": 0, "buyers_stockouts": 0, "stocksense_stockouts": 0,
             "buyers_value": 0.0, "stocksense_value": 0.0},
        )
        row["parts"] += 1
        row["buyers_stockouts"] += outcome.buyers_stockout_weeks
        row["stocksense_stockouts"] += outcome.stocksense_stockout_weeks
        row["buyers_value"] += outcome.buyers_average_value
        row["stocksense_value"] += outcome.stocksense_average_value

    pattern_rows = [
        {
            "pattern": kind,
            "label": classify.LABELS.get(kind, kind),
            "intermittent": classify.is_intermittent(kind),
            "parts": int(row["parts"]),
            "buyers_stockout_weeks": int(row["buyers_stockouts"]),
            "stocksense_stockout_weeks": int(row["stocksense_stockouts"]),
            "buyers_value": str(money(row["buyers_value"])),
            "stocksense_value": str(money(row["stocksense_value"])),
        }
        for kind, row in sorted(by_pattern.items(), key=lambda kv: -kv[1]["parts"])
    ]

    # --- the accuracy figures, and the trap in them ---------------------
    trap = metrics.zero_forecast_beats(accuracy_cases)
    scored = [
        metrics.score(actual, forecast, training=training)
        for training, actual, forecast in accuracy_cases
    ]
    usable = [s for s in scored if s.scoreable and s.mase is not None]

    fewer_stockouts = engine_total.stockout_weeks < buyers_total.stockout_weeks
    not_more_stock = (
        engine_total.average_inventory_value <= buyers_total.average_inventory_value
    )

    seconds = time.perf_counter() - started
    return {
        "weeks": weeks,
        "parts": len(buyer_rows),
        "seconds": round(seconds, 2),
        "buyers": buyers_total.to_dict(),
        "stocksense": engine_total.to_dict(),
        "by_pattern": pattern_rows,
        "weekly": [
            {
                "week": index,
                "buyers_inventory": round(buyer_inventory[index], 2),
                "stocksense_inventory": round(engine_inventory[index], 2),
                "buyers_stockouts": buyer_stockouts[index],
                "stocksense_stockouts": engine_stockouts[index],
            }
            for index in range(weeks)
        ],
        "accuracy": {
            "parts_scored": len(usable),
            "mase": round(mean([s.mase for s in usable]), 3) if usable else None,
            "bias": round(mean([s.bias for s in usable]), 3) if usable else None,
            "zero_trap": trap.to_dict(),
        },
        "fewer_stockouts": fewer_stockouts,
        "not_more_stock": not_more_stock,
        "passed": fewer_stockouts and not_more_stock,
    }
