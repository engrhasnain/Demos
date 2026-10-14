"""A run: every shipment that is not finished, once.

Resumable by construction. There is no "resume" mode and no separate
recovery path, because a second run *is* the recovery path — it reads each
row's state and carries on from there. A code path that only executes
after a crash is a code path nobody has tested.

The run stops itself for exactly one reason: the booking form has changed
shape. Everything else is recorded against the shipment it happened to and
the run carries on, because one bad address should not hold up a hundred
and seventy-nine good ones.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Run, Shipment
from ..systems.carrier import CarrierPortal
from ..systems.legacy import LegacySystem
from .bot import Bot, Outcome, Stopped, key_for

#: States that still have work left in them.
UNFINISHED = ("pending", "booked", "written_back", "failed", "needs_a_person")


@dataclass
class Report:
    run: Run
    outcomes: list[Outcome] = field(default_factory=list)
    halted: bool = False
    halt_reason: str = ""
    drift: dict[str, Any] = field(default_factory=dict)

    @property
    def completed(self) -> int:
        return sum(1 for o in self.outcomes if o.state == "done" and not o.skipped)

    @property
    def already_done(self) -> int:
        return sum(1 for o in self.outcomes if o.skipped)

    @property
    def exceptions(self) -> int:
        return sum(1 for o in self.outcomes if o.exception_kind)


def run_once(
    session: Session,
    carrier: CarrierPortal,
    legacy: LegacySystem,
    *,
    limit: int | None = None,
    stop_after: int | None = None,
) -> Report:
    """Work through the shipments.

    ``stop_after`` is how the demonstration kills a run part way: it is not
    a graceful shutdown, it is the process disappearing, which is the case
    that has to be safe.
    """
    started = time.perf_counter()
    run = Run(status="running")
    session.add(run)
    session.flush()

    query = (
        select(Shipment)
        .where(Shipment.state.in_(UNFINISHED))
        .order_by(Shipment.id)
    )
    if limit:
        query = query.limit(limit)
    shipments = list(session.scalars(query))
    run.considered = len(shipments)

    bot = Bot(session, carrier, legacy, run=run)
    report = Report(run=run)

    # One check for the whole run, before anything is sent.
    try:
        bot.check_the_form()
    except Stopped as stopped:
        run.status = "halted"
        run.halted_reason = str(stopped)
        run.drift = stopped.detail
        run.finished_at = dt.datetime.now(dt.timezone.utc)
        run.seconds = time.perf_counter() - started
        run.notes = (
            "Stopped before sending anything. The form has moved and the "
            "script has been flagged. Nothing was booked against a form "
            "nobody has checked."
        )
        session.flush()
        report.halted = True
        report.halt_reason = str(stopped)
        report.drift = stopped.detail
        return report

    for index, shipment in enumerate(shipments):
        if stop_after is not None and index >= stop_after:
            # The process is gone. Whatever is committed, is committed.
            run.status = "stopped"
            run.notes = f"Killed after {index} shipments."
            break
        shipment.run_id = run.id
        report.outcomes.append(bot.handle(shipment))

    if run.status == "running":
        run.status = "finished"
    run.completed = report.completed
    run.exceptions = report.exceptions
    run.skipped_already_done = report.already_done
    run.finished_at = dt.datetime.now(dt.timezone.utc)
    run.seconds = time.perf_counter() - started
    if not run.notes:
        run.notes = (
            f"{report.completed} of {run.considered} completed, "
            f"{report.exceptions} exceptions, {report.already_done} already done."
        )
    session.flush()
    return report


def ensure_keys(session: Session) -> int:
    """Give every shipment its derived key. Idempotent, like everything here."""
    changed = 0
    for shipment in session.scalars(select(Shipment)):
        wanted = key_for(shipment)
        if shipment.idempotency_key != wanted:
            shipment.idempotency_key = wanted
            changed += 1
    session.flush()
    return changed
