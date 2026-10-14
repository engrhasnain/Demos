"""The acceptance criteria, run as code.

Four bars. The second one is the one worth watching: it kills the run part
way through, over and over, at every point in the sequence, and then
checks the carrier's own books for a shipment booked twice.

That is not a test of a retry decorator. It is a test of whether the state
machine and the derived key actually hold when the process disappears
between the booking and the write-back, which is the moment that costs
money.
"""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..domain import drift
from ..models import ScriptFlag, Shipment, Step
from ..seed.generator import Builder
from ..services import runner
from ..services.bot import EXCEPTION_WORDS, key_for
from ..systems.carrier import Behaviour, CarrierPortal

CRITERIA: list[dict[str, Any]] = [
    {
        "name": "clean shipments automated",
        "question": "Of the shipments with nothing wrong, how many went through untouched?",
        "bar": 95.0,
        "unit": "%",
    },
    {
        "name": "duplicates",
        "question": "Killing the run part way through, did anything get booked twice?",
        "bar": 0.0,
        "unit": "bookings",
        "lower_is_better": True,
    },
    {
        "name": "every exception classified",
        "question": "Does every failure have a named kind and a trace to replay?",
        "bar": 100.0,
        "unit": "%",
    },
    {
        "name": "the portal changing is noticed",
        "question": "When the form moves, does it stop and flag, or carry on regardless?",
        "bar": 100.0,
        "unit": "%",
    },
]

#: A shipment is "clean" when nothing about it should stop a careful clerk
#: either. These are the planted defects, and they are excluded from the
#: first bar and reported separately rather than quietly counted as
#: successes.
PLANTED = {
    "bad_postcode",
    "bad_address",
    "overweight_package",
    "unknown_dangerous_goods",
    "mixed_dangerous_goods",
    "bad_weight",
    "bad_packages",
}


def _fresh(session: Session, shipments: int) -> None:
    from ..seed.generator import build_demo_data

    build_demo_data(session, shipment_target=shipments)


# ---------------------------------------------------------------------------
# 1 and 3: a clean run
# ---------------------------------------------------------------------------
def _ordinary_run(session: Session, shipments: int) -> dict[str, Any]:
    _fresh(session, shipments)
    carrier = CarrierPortal(behaviour=Behaviour(tracking_delay_seconds=0))
    legacy = Builder.legacy_for(session)
    report = runner.run_once(session, carrier, legacy)

    total = report.run.considered
    defective = [o for o in report.outcomes if o.exception_kind in PLANTED]
    clean = [o for o in report.outcomes if o.exception_kind not in PLANTED]
    clean_done = [o for o in clean if o.state == "done"]

    # Every exception has to be named and have a trace behind it.
    unclassified: list[str] = []
    traceless: list[str] = []
    for outcome in report.outcomes:
        if not outcome.exception_kind:
            continue
        if outcome.exception_kind not in EXCEPTION_WORDS:
            unclassified.append(f"{outcome.shipment.reference}: {outcome.exception_kind}")
        steps = session.scalar(
            select(func.count(Step.id)).where(Step.shipment_id == outcome.shipment.id)
        )
        if not steps:
            traceless.append(outcome.shipment.reference)

    with_exceptions = [o for o in report.outcomes if o.exception_kind]
    classified = len(with_exceptions) - len(unclassified) - len(traceless)

    return {
        "total": total,
        "clean": len(clean),
        "clean_done": len(clean_done),
        "clean_share": round(100.0 * len(clean_done) / len(clean), 1) if clean else 0.0,
        "defective": len(defective),
        "exceptions": len(with_exceptions),
        "classified": classified,
        "classified_share": (
            round(100.0 * classified / len(with_exceptions), 1)
            if with_exceptions
            else 100.0
        ),
        "unclassified": unclassified[:10],
        "traceless": traceless[:10],
        "by_kind": [
            {
                "kind": kind,
                "label": EXCEPTION_WORDS.get(kind, kind),
                "count": sum(1 for o in report.outcomes if o.exception_kind == kind),
                "planted": kind in PLANTED,
            }
            for kind in sorted({o.exception_kind for o in report.outcomes if o.exception_kind})
        ],
        "seconds": round(report.run.seconds, 2),
    }


# ---------------------------------------------------------------------------
# 2: killed part way through, repeatedly
# ---------------------------------------------------------------------------
def _kill_and_resume(session: Session, shipments: int = 40) -> dict[str, Any]:
    """Kill the run at every point and check the carrier's own books.

    The carrier is kept across the kills, because a real portal does not
    forget what it booked just because our process died. That is the whole
    point: the duplicate would be ours to cause and ours to prevent.
    """
    _fresh(session, shipments)
    carrier = CarrierPortal(behaviour=Behaviour(tracking_delay_seconds=0))
    legacy = Builder.legacy_for(session)

    kills = 0
    # Stop after 3, then 7, then 11... until everything is through.
    for stop_after in range(3, shipments + 6, 4):
        report = runner.run_once(session, carrier, legacy, stop_after=stop_after)
        kills += 1
        left = session.scalar(
            select(func.count(Shipment.id)).where(
                Shipment.state.in_(("pending", "booked", "written_back"))
            )
        )
        if not left:
            break

    # One more, uninterrupted, to finish anything outstanding.
    runner.run_once(session, carrier, legacy)

    # Now the question: did the carrier take the same reference twice?
    booked_references = [b.reference for b in carrier.bookings.values()]
    duplicates = [
        reference
        for reference in set(booked_references)
        if booked_references.count(reference) > 1
    ]

    # And did any shipment end up with two consignments against it?
    double_consignments = []
    for shipment in session.scalars(select(Shipment)):
        bookings = [
            b for b in carrier.bookings.values() if b.reference == shipment.reference
        ]
        if len(bookings) > 1:
            double_consignments.append(shipment.reference)

    # The derived key has to be stable across all of that.
    unstable = [
        s.reference
        for s in session.scalars(select(Shipment))
        if s.idempotency_key != key_for(s)
    ]

    done = session.scalar(
        select(func.count(Shipment.id)).where(Shipment.state == "done")
    )
    return {
        "shipments": shipments,
        "kills": kills,
        "bookings_made": len(carrier.bookings),
        "duplicates": len(duplicates) + len(double_consignments),
        "duplicate_detail": (duplicates + double_consignments)[:10],
        "unstable_keys": unstable[:10],
        "finished": done or 0,
        "refused_by_the_portal": sum(
            1 for row in carrier.log if row.get("what") == "duplicate_refused"
        ),
    }


# ---------------------------------------------------------------------------
# 4: the portal moves
# ---------------------------------------------------------------------------
def _drift(session: Session, shipments: int = 20) -> dict[str, Any]:
    """Change the form under the script and see what happens.

    Two things have to be true. It must stop before sending anything, and
    it must raise a flag a developer can act on. It must not rewrite its
    own script, which is why there is no code here that could.
    """
    _fresh(session, shipments)
    legacy = Builder.legacy_for(session)

    before = session.scalar(select(func.count(ScriptFlag.id))) or 0
    moved = CarrierPortal(behaviour=Behaviour(version="v2", tracking_delay_seconds=0))
    report = runner.run_once(session, moved, legacy)

    flags = list(session.scalars(select(ScriptFlag).order_by(ScriptFlag.id.desc())))
    raised = len(flags) - before
    flag = flags[0] if flags else None

    booked_anyway = len(moved.bookings)
    renames = flag.detail.get("looks_renamed", []) if flag else []

    return {
        "halted": report.halted,
        "booked_anyway": booked_anyway,
        "flag_raised": raised > 0,
        "flag": flag.detail if flag else None,
        "suggested_renames": renames,
        "reason": report.halt_reason,
        "held": report.halted and booked_anyway == 0 and raised > 0,
    }


# ---------------------------------------------------------------------------
def run_evaluation(
    session: Session, *, shipments: int = 180, save: bool = True
) -> dict[str, Any]:
    started = time.perf_counter()
    started_at = dt.datetime.now(dt.timezone.utc)

    savepoint = session.begin_nested()
    try:
        ordinary = _ordinary_run(session, shipments)
        killing = _kill_and_resume(session, min(shipments, 40))
        moving = _drift(session, 20)
    finally:
        savepoint.rollback()
        session.expunge_all()

    results = [
        {
            **CRITERIA[0],
            "value": ordinary["clean_share"],
            "measured": (
                f"{ordinary['clean_done']} of {ordinary['clean']} clean shipments "
                f"booked and written back; {ordinary['defective']} had a real "
                "problem and were held"
            ),
            "passed": ordinary["clean_share"] >= CRITERIA[0]["bar"],
        },
        {
            **CRITERIA[1],
            "value": killing["duplicates"],
            "measured": (
                f"{killing['kills']} kills part way through {killing['shipments']} "
                f"shipments, {killing['bookings_made']} bookings made, "
                f"{killing['duplicates']} duplicates"
            ),
            "passed": killing["duplicates"] == 0 and not killing["unstable_keys"],
        },
        {
            **CRITERIA[2],
            "value": ordinary["classified_share"],
            "measured": (
                f"{ordinary['classified']} of {ordinary['exceptions']} exceptions "
                "named and traceable"
            ),
            "passed": ordinary["classified_share"] >= 100.0,
        },
        {
            **CRITERIA[3],
            "value": 100.0 if moving["held"] else 0.0,
            "measured": (
                "stopped before sending anything and flagged the script"
                if moving["held"]
                else f"booked {moving['booked_anyway']} against a changed form"
            ),
            "passed": moving["held"],
        },
    ]

    everything_held = all(row["passed"] for row in results)
    seconds = round(time.perf_counter() - started, 2)

    return {
        "started_at": started_at.isoformat(),
        "seconds": seconds,
        "criteria": results,
        "passed": everything_held,
        "ordinary": ordinary,
        "killing": killing,
        "drift": moving,
        "statement": (
            f"{ordinary['total']} shipments, {killing['kills']} kills and one "
            f"portal release, in {seconds} seconds."
        ),
    }
