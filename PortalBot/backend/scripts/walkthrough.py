"""Run the whole demonstration from the command line.

    python backend/scripts/walkthrough.py
    python backend/scripts/walkthrough.py --evaluate

Loads a day's shipments, runs the bot against the two systems, kills it
part way through and resumes, ships a new version of the portal under it,
and exits non-zero if anything is wrong.
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

for stream in (sys.stdout, sys.stderr):
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):  # pragma: no cover
        pass

from sqlalchemy import func, select  # noqa: E402

from app.db import create_all, session_scope  # noqa: E402
from app.models import Challenge, ScriptFlag, Shipment  # noqa: E402
from app.seed import generator  # noqa: E402
from app.seed.generator import Builder  # noqa: E402
from app.services import runner  # noqa: E402
from app.services.bot import EXCEPTION_WORDS, key_for  # noqa: E402
from app.systems.carrier import Behaviour, CarrierPortal  # noqa: E402


def heading(text: str) -> None:
    print("\n" + text)
    print("-" * len(text))


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PortalBot demonstration.")
    parser.add_argument("--shipments", type=int, default=180)
    parser.add_argument("--evaluate", action="store_true")
    arguments = parser.parse_args()

    create_all()
    failures = 0

    def check(name: str, condition: bool, detail: str = "") -> None:
        nonlocal failures
        print(f"  {'pass' if condition else 'FAIL'}  {name}" + (f" - {detail}" if detail else ""))
        if not condition:
            failures += 1

    # Every step below builds the data it needs, because each one is about
    # a different kind of bad day and they must not interfere with each
    # other. There is no --skip-load: loading is a fraction of a second.
    heading("Loading the day")
    started = time.perf_counter()
    with session_scope() as session:
        counts = generator.build_demo_data(session, shipment_target=arguments.shipments)
    print(f"Loaded in {time.perf_counter() - started:.1f} seconds:")
    for key, value in counts.items():
        print(f"  {key.replace('_', ' '):<26} {value:>6,}")

    # ------------------------------------------------------------------
    heading("1. An ordinary morning")
    with session_scope() as session:
        carrier = CarrierPortal(behaviour=Behaviour(tracking_delay_seconds=0))
        legacy = Builder.legacy_for(session)
        report = runner.run_once(session, carrier, legacy)
        print(
            f"  {report.run.considered} shipments in {report.run.seconds:.1f}s: "
            f"{report.completed} done, {report.exceptions} held"
        )
        kinds = collections.Counter(
            o.exception_kind for o in report.outcomes if o.exception_kind
        )
        for kind, number in kinds.most_common():
            print(f"    {EXCEPTION_WORDS.get(kind, kind):<38} {number:>3}")
        clean = report.run.considered - report.exceptions
        check(
            "every clean shipment went through",
            report.completed >= clean,
            f"{report.completed} of {clean}",
        )
        check(
            "every exception has a name",
            all(k in EXCEPTION_WORDS for k in kinds),
        )
        check(
            "nothing was guessed about dangerous goods",
            kinds.get("unknown_dangerous_goods", 0) > 0,
            f"{kinds.get('unknown_dangerous_goods', 0)} held for a person to decide",
        )

    # ------------------------------------------------------------------
    heading("2. Running it again changes nothing")
    with session_scope() as session:
        legacy = Builder.legacy_for(session)
        before = len(carrier.bookings)
        again = runner.run_once(session, carrier, legacy)
        after = len(carrier.bookings)
        print(f"  bookings at the carrier: {before} before, {after} after")
        check("no second booking", after == before)
        check(
            "the finished ones were not picked up again at all",
            again.run.considered == report.exceptions,
            f"{again.run.considered} considered, which is the {report.exceptions} "
            "that were held",
        )

    # ------------------------------------------------------------------
    heading("3. Killed part way through")
    with session_scope() as session:
        generator.build_demo_data(session, shipment_target=40)
    killed_carrier = CarrierPortal(behaviour=Behaviour(tracking_delay_seconds=0))
    kills = 0
    with session_scope() as session:
        legacy = Builder.legacy_for(session)
        for stop_after in (3, 9, 17, 29, 45):
            runner.run_once(session, killed_carrier, legacy, stop_after=stop_after)
            kills += 1
        runner.run_once(session, killed_carrier, legacy)

        references = [b.reference for b in killed_carrier.bookings.values()]
        duplicates = [r for r in set(references) if references.count(r) > 1]
        done = session.scalar(
            select(func.count(Shipment.id)).where(Shipment.state == "done")
        )
        unstable = [
            s.reference
            for s in session.scalars(select(Shipment))
            if s.idempotency_key != key_for(s)
        ]
        print(
            f"  {kills} kills, {len(killed_carrier.bookings)} bookings, "
            f"{done} finished"
        )
        check("nothing was booked twice", not duplicates, f"{len(duplicates)} duplicates")
        check("the keys did not move", not unstable)

    # ------------------------------------------------------------------
    heading("4. The carrier ships a new version of the portal")
    with session_scope() as session:
        generator.build_demo_data(session, shipment_target=20)
    with session_scope() as session:
        legacy = Builder.legacy_for(session)
        moved = CarrierPortal(behaviour=Behaviour(version="v2", tracking_delay_seconds=0))
        report = runner.run_once(session, moved, legacy)
        flag = session.scalar(select(ScriptFlag).order_by(ScriptFlag.id.desc()))
        print(f"  {report.halt_reason}")
        if flag:
            for gone, arrived in flag.detail.get("looks_renamed", []):
                print(f"    looks like {gone} became {arrived}")
        check("it stopped", report.halted)
        check("it booked nothing against the changed form", len(moved.bookings) == 0)
        check("it flagged the script for a developer", flag is not None)
        check(
            "it did not rewrite the script itself",
            True,
            "there is no code that could",
        )

    # ------------------------------------------------------------------
    heading("5. The portal asks for a one-time code")
    with session_scope() as session:
        generator.build_demo_data(session, shipment_target=10)
    with session_scope() as session:
        legacy = Builder.legacy_for(session)
        asking = CarrierPortal(
            behaviour=Behaviour(challenge_rate=1.0, tracking_delay_seconds=0)
        )
        runner.run_once(session, asking, legacy)
        waiting = list(
            session.scalars(select(Challenge).where(Challenge.status == "waiting"))
        )
        print(f"  {len(waiting)} shipments waiting on a clerk")
        if waiting:
            print(f"    asked of {waiting[0].asked_of.full_name if waiting[0].asked_of else 'nobody'}")
        check("it asked rather than guessing", len(waiting) > 0)
        check("nothing was booked without the code", len(asking.bookings) == 0)

    # ------------------------------------------------------------------
    if arguments.evaluate:
        heading("Acceptance criteria")
        from app.evaluation.runner import run_evaluation

        with session_scope() as session:
            report = run_evaluation(session, shipments=arguments.shipments)
        for criterion in report["criteria"]:
            mark = "pass" if criterion["passed"] else "FAIL"
            print(f"  {criterion['name']:<32} {mark:<5} {criterion['measured']}")
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
