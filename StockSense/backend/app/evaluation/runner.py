"""The acceptance criteria, run as code.

Four bars. Three of them are measured by replaying the
year; the fourth is measured by looking at every recommendation the engine
produced and checking it can account for itself.

Nothing here is asserted. Each criterion reports the figure it measured and
what it measured it on, and a criterion that cannot be measured says so
rather than passing quietly.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

from sqlalchemy.orm import Session

from ..config import settings
from ..domain import classify
from ..numbers import dec
from ..services import plan as planning, replay as replaying

CRITERIA: list[dict[str, Any]] = [
    {
        "name": "stock-out weeks",
        "question": "Over the last twelve months, would the shelves have been empty less often?",
        "bar": "fewer than the buyers",
        "unit": "weeks",
    },
    {
        "name": "inventory value",
        "question": "And would that have taken more money to achieve?",
        "bar": "the same or less",
        "unit": "TWD",
    },
    {
        "name": "occasional parts",
        "question": "Are the parts that are hard to forecast reported on their own?",
        "bar": "reported separately",
        "unit": "",
    },
    {
        "name": "every recommendation explains itself",
        "question": "Does each one name its demand model, its lead time and its cash?",
        "bar": "100%",
        "unit": "%",
    },
]


def run_evaluation(
    session: Session,
    *,
    parts: int | None = 1200,
    weeks: int = replaying.REPLAY_WEEKS,
    save: bool = True,
) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = dt.datetime.now(dt.timezone.utc)

    # --- the replay, which answers the first three ---------------------
    report = replaying.run_replay(session, weeks=weeks, limit=parts)
    buyers = report["buyers"]
    engine = report["stocksense"]

    # --- the fourth: can every line account for itself? ----------------
    savepoint = session.begin_nested()
    try:
        summary = planning.run_plan(session, limit=parts)
        lines = list(summary.run.lines)
        explained = 0
        unexplained: list[str] = []
        for line in lines:
            has_method = bool(line.demand_method)
            has_lead_time = dec(line.lead_time_days) > 0
            has_cash = (
                dec(line.value) > 0
                if line.decision in {"order", "prebuild"}
                else True
            )
            has_working = bool(line.trace and line.trace.get("steps"))
            if has_method and has_lead_time and has_cash and has_working:
                explained += 1
            elif len(unexplained) < 20:
                missing = [
                    name
                    for name, ok in (
                        ("demand model", has_method),
                        ("lead time", has_lead_time),
                        ("cash", has_cash),
                        ("working", has_working),
                    )
                    if not ok
                ]
                unexplained.append(f"{line.part.code}: no {', '.join(missing)}")
        considered = len(lines)
    finally:
        savepoint.rollback()
        session.expunge_all()

    explained_share = round(100.0 * explained / considered, 2) if considered else 0.0

    # --- occasional parts, reported on their own -----------------------
    occasional = [row for row in report["by_pattern"] if row["intermittent"]]
    occasional_parts = sum(row["parts"] for row in occasional)
    occasional_buyers = sum(row["buyers_stockout_weeks"] for row in occasional)
    occasional_engine = sum(row["stocksense_stockout_weeks"] for row in occasional)

    results: list[dict[str, Any]] = [
        {
            **CRITERIA[0],
            "value": engine["stockout_weeks"],
            "against": buyers["stockout_weeks"],
            "measured": (
                f"{engine['stockout_weeks']:,} against the buyers' "
                f"{buyers['stockout_weeks']:,}, over {report['parts']:,} parts "
                f"and {report['weeks']} weeks"
            ),
            "passed": report["fewer_stockouts"],
        },
        {
            **CRITERIA[1],
            "value": engine["average_inventory_value"],
            "against": buyers["average_inventory_value"],
            "measured": (
                f"{float(engine['average_inventory_value']):,.0f} against the "
                f"buyers' {float(buyers['average_inventory_value']):,.0f}, "
                "averaged over the year"
            ),
            "passed": report["not_more_stock"],
        },
        {
            **CRITERIA[2],
            "value": occasional_parts,
            "against": report["parts"],
            "measured": (
                f"{occasional_parts:,} of {report['parts']:,} parts are "
                f"occasional or lumpy; {occasional_engine:,} stock-out weeks "
                f"against the buyers' {occasional_buyers:,}"
            ),
            "passed": bool(occasional) and occasional_engine <= occasional_buyers,
        },
        {
            **CRITERIA[3],
            "value": explained_share,
            "against": 100.0,
            "measured": f"{explained:,} of {considered:,} recommendations",
            "passed": explained_share >= 100.0,
        },
    ]

    everything_held = all(row["passed"] for row in results)
    seconds = round(time.perf_counter() - started, 2)

    return {
        "started_at": started_at.isoformat(),
        "seconds": seconds,
        "parts": report["parts"],
        "weeks": report["weeks"],
        "criteria": results,
        "passed": everything_held,
        "accuracy": report["accuracy"],
        "by_pattern": report["by_pattern"],
        "misses": unexplained,
        "statement": (
            f"{report['parts']:,} parts replayed over {report['weeks']} weeks "
            f"in {seconds} seconds."
        ),
    }
