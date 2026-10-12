"""The weekly ordering round.

Every part is looked at, every one gets a decision, and the decisions that
cost money are fitted inside the cash available. The parts that are fine
are recorded as fine: a buyer needs to know the engine looked at all
eighteen thousand and found nothing wrong with most of them, not just see
the four hundred it wants to buy.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..clock import today as today_date
from ..config import settings
from ..models import Part, PlanLine, PlanRun, User
from ..numbers import dec, money
from . import cashcap, demand as demand_service, reorder


@dataclass(slots=True)
class PlanSummary:
    run: PlanRun
    allocation: cashcap.Allocation
    seconds: float


def run_plan(
    session: Session,
    *,
    as_of: dt.date | None = None,
    cash_cap: float | None = None,
    limit: int | None = None,
    by: User | None = None,
) -> PlanSummary:
    """Look at everything and decide what to buy this week."""
    started = time.perf_counter()
    as_of = as_of or today_date()
    cap = dec(cash_cap if cash_cap is not None else settings.weekly_cash_cap_twd)

    query = (
        select(Part)
        .options(selectinload(Part.supplier))
        .order_by(Part.id)
    )
    if limit:
        query = query.limit(limit)
    parts = list(session.scalars(query))

    recommendations: list[reorder.Recommendation] = []
    for part in parts:
        view = demand_service.for_part(session, part)
        recommendations.append(reorder.build(session, part, view, as_of=as_of))

    allocation = cashcap.allocate(recommendations, cap)

    run = PlanRun(
        as_of=as_of,
        created_by_id=by.id if by else None,
        cash_cap=money(cap),
        cash_committed=money(allocation.committed),
        parts_considered=len(parts),
        lines_recommended=len(allocation.accepted),
        lines_deferred=len(allocation.deferred),
    )
    session.add(run)
    session.flush()

    # Store every decision, including the ones that cost nothing. A plan
    # that only lists what to buy cannot answer "what about this part?",
    # which is the first thing a buyer asks.
    rows = []
    for recommendation in recommendations:
        rows.append(
            {
                "run_id": run.id,
                "part_id": recommendation.part.id,
                "decision": recommendation.decision,
                "reason": recommendation.reason,
                "quantity": recommendation.quantity
                if recommendation.decision in {reorder.ORDER, reorder.PREBUILD}
                else 0,
                "raw_quantity": money(recommendation.raw_quantity),
                "value": money(
                    recommendation.value
                    if recommendation.decision in {reorder.ORDER, reorder.PREBUILD}
                    else 0
                ),
                "demand_method": recommendation.view.forecast.method,
                "demand_pattern": recommendation.view.pattern.kind,
                "weekly_rate": money(recommendation.policy.demand_per_day * 7),
                "reorder_point": money(recommendation.policy.reorder_point),
                "order_up_to": money(recommendation.policy.order_up_to),
                "safety_stock": money(recommendation.policy.safety_stock),
                "position": money(recommendation.position),
                "lead_time_days": money(recommendation.policy.lead_time_days),
                "service_level": money(recommendation.policy.service_level),
                "urgency": money(recommendation.urgency),
                "days_of_cover": money(min(9999.0, recommendation.days_of_cover)),
                "shutdown_note": recommendation.shutdown_note,
                "flags": recommendation.flags,
                "trace": recommendation.trace.to_dict() if recommendation.trace else {},
            }
        )
    session.bulk_insert_mappings(PlanLine, rows)

    seconds = time.perf_counter() - started
    run.seconds = money(seconds)
    run.notes = (
        f"{len(parts):,} parts considered, {len(allocation.accepted):,} to order, "
        f"{money(allocation.committed):,} of {money(cap):,} committed."
    )
    session.flush()

    return PlanSummary(run=run, allocation=allocation, seconds=seconds)
