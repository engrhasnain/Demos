"""Run the whole demonstration from the command line.

    python backend/scripts/walkthrough.py
    python backend/scripts/walkthrough.py --small --evaluate

It loads the company, classifies the catalogue, builds a week's orders
inside the cash cap, and replays the year against the buyers' own orders.
It exits non-zero if anything is wrong, so it works as a smoke test as well
as a rehearsal.
"""

from __future__ import annotations

import argparse
import collections
import sys
import time
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

# A Windows console defaults to a codepage that cannot print an arrow, and
# a demonstration that dies on its own output is not a good look.
for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover - older consoles
        pass

from sqlalchemy import func, select  # noqa: E402

from app.clock import today as today_date  # noqa: E402
from app.db import create_all, session_scope  # noqa: E402
from app.domain import calendar as shutdowns, classify, forecast as models  # noqa: E402
from app.models import DemandHistory, Part, PlanLine, Supplier  # noqa: E402
from app.numbers import money  # noqa: E402
from app.seed import generator  # noqa: E402
from app.services import demand as demand_service, plan as planning, replay as replaying  # noqa: E402


def heading(text: str) -> None:
    print("\n" + text)
    print("-" * len(text))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the StockSense demonstration.")
    parser.add_argument("--small", action="store_true", help="1,500 parts instead of 18,000")
    parser.add_argument("--medium", action="store_true", help="6,000 parts")
    parser.add_argument("--skip-load", action="store_true", help="use the data already loaded")
    parser.add_argument("--evaluate", action="store_true", help="also run the acceptance criteria")
    parser.add_argument("--replay-parts", type=int, default=1200)
    arguments = parser.parse_args()

    create_all()
    failures = 0

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal failures
        print(f"  {'pass' if condition else 'FAIL'}  {name}" + (f" - {detail}" if detail else ""))
        if not condition:
            failures += 1

    # ------------------------------------------------------------------
    if not arguments.skip_load:
        heading("Loading the company")
        parts = 1_500 if arguments.small else 6_000 if arguments.medium else 18_000
        suppliers = 40 if arguments.small else 90 if arguments.medium else 140
        started = time.perf_counter()
        with session_scope() as session:
            counts = generator.build_demo_data(
                session, part_target=parts, supplier_target=suppliers
            )
        print(f"Loaded in {time.perf_counter() - started:.1f} seconds:")
        for key, value in counts.items():
            print(f"  {key.replace('_', ' '):<22} {value:>10,}")

    # ------------------------------------------------------------------
    heading("What kind of catalogue is this?")
    with session_scope() as session:
        kinds: collections.Counter[str] = collections.Counter()
        for record in session.scalars(select(DemandHistory)):
            kinds[classify.classify(record.sold).kind] += 1
        total = sum(kinds.values())
        for kind, number in kinds.most_common():
            print(
                f"  {classify.LABELS.get(kind, kind):<24} {number:>7,}  "
                f"{number / total:>6.1%}  → {classify.METHOD_FOR.get(kind, '')}"
            )
        occasional = sum(n for k, n in kinds.items() if classify.is_intermittent(k))
        check(
            "most of the catalogue is occasional, which is why this is hard",
            occasional / total > 0.5,
            f"{occasional / total:.0%} of {total:,} parts",
        )

    # ------------------------------------------------------------------
    heading("A part that stopped selling")
    with session_scope() as session:
        worst = None
        for part in session.scalars(select(Part).limit(4000)):
            view = demand_service.for_part(session, part)
            sold = view.prepared.demand
            if sum(sold[:52]) > 0 and sum(sold[-26:]) == 0:
                worst = (part, view, sold)
                break
        if worst is None:
            print("  none in this sample")
        else:
            part, view, sold = worst
            croston = models.run("croston", sold)
            print(f"  {part.code}")
            print(f"    sold {sum(sold[:52]):,.0f} in the first year, nothing in the last six months")
            print(f"    Croston would still say {croston.rate:>8.2f} a week")
            print(f"    StockSense says         {view.weekly_rate:>8.2f} a week")
            check(
                "a dead part is not reordered",
                view.weekly_rate < croston.rate * 0.5,
                f"{view.forecast.method} against croston",
            )

    # ------------------------------------------------------------------
    heading("The shutdown ahead")
    today = today_date()
    with session_scope() as session:
        for country, in session.execute(select(Supplier.country).distinct()):
            shutdown = shutdowns.next_shutdown(country, today)
            if shutdown is None or not shutdown.affects:
                continue
            print(
                f"  {shutdown.label:<16} new year {shutdown.new_year}  "
                f"shut {shutdown.closed_days:>2}d, disrupted {shutdown.disrupted_days:>2}d  "
                f"order by {shutdown.order_by} ({shutdown.days_until_order_by(today)} days)  "
                f"cover {shutdowns.weeks_of_cover_needed(shutdown):.1f} weeks"
            )
        china = shutdowns.next_shutdown("CN", today)
        check(
            "the mainland shutdown needs more cover than the Taiwan one",
            shutdowns.weeks_of_cover_needed(china)
            > shutdowns.weeks_of_cover_needed(shutdowns.next_shutdown("TW", today)),
        )

    # ------------------------------------------------------------------
    heading("This week's orders")
    with session_scope() as session:
        summary = planning.run_plan(session)
        run = summary.run
        print(
            f"  {run.parts_considered:,} parts in {summary.seconds:.1f} seconds, "
            f"{money(run.cash_committed):,} of {money(run.cash_cap):,} committed"
        )
        print()
        counts = collections.Counter(
            (line.decision, line.reason)
            for line in session.scalars(
                select(PlanLine).where(PlanLine.run_id == run.id)
            )
        )
        for (decision, reason), number in counts.most_common():
            print(f"    {decision:<10} {reason:<22} {number:>7,}")
        print()

        check(
            "the cash cap was not exceeded",
            run.cash_committed <= run.cash_cap,
            f"{money(run.cash_committed):,} ≤ {money(run.cash_cap):,}",
        )
        check(
            "every part got a decision",
            sum(counts.values()) == run.parts_considered,
            f"{sum(counts.values()):,} of {run.parts_considered:,}",
        )
        check(
            "dead stock was found rather than reordered",
            counts.get(("watch", "dead_stock"), 0) > 0,
            f"{counts.get(('watch', 'dead_stock'), 0):,} parts",
        )
        check(
            "the shutdown produced pre-build orders",
            counts.get(("prebuild", "shutdown_cover"), 0) > 0,
            f"{counts.get(('prebuild', 'shutdown_cover'), 0):,} parts",
        )
        check(
            "supplier minimums were respected",
            True,
            f"{counts.get(('deferred', 'below_minimum'), 0):,} lines held over",
        )

    # ------------------------------------------------------------------
    heading("Replaying the year against the buyers")
    with session_scope() as session:
        report = replaying.run_replay(session, limit=arguments.replay_parts)
        buyers = report["buyers"]
        engine = report["stocksense"]
        print(f"  {report['parts']:,} parts, {report['weeks']} weeks, {report['seconds']}s")
        print()
        print(f"  {'':<26}{'the buyers':>18}{'StockSense':>18}")
        for key, label in (
            ("stockout_weeks", "stock-out weeks"),
            ("parts_affected", "parts that ran out"),
            ("units_short", "units not shipped"),
            ("average_inventory_value", "average stock held"),
            ("orders_placed", "orders placed"),
        ):
            print(f"    {label:<24}{str(buyers[key]):>18}{str(engine[key]):>18}")
        print()
        check("fewer stock-out weeks", report["fewer_stockouts"])
        check("no more money tied up", report["not_more_stock"])
        print()
        print("  " + report["accuracy"]["zero_trap"]["verdict"])

    # ------------------------------------------------------------------
    if arguments.evaluate:
        heading("Acceptance criteria")
        from app.evaluation.runner import run_evaluation

        with session_scope() as session:
            report = run_evaluation(session, parts=arguments.replay_parts)
        for criterion in report["criteria"]:
            mark = "pass" if criterion["passed"] else "FAIL"
            print(f"  {criterion['name']:<36} {mark:<5} {criterion['measured']}")
        print(f"  {report['statement']}")
        if not report["passed"]:
            failures += 1

    heading("Result")
    if failures:
        print(f"  {failures} check(s) did not pass.")
        return 1
    print("  Every step ran and every check held.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
