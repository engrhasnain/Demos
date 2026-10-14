"""Get the database ready before the first request is answered.

Creates the tables and, where storage is temporary (serverless plus SQLite),
fills an empty database with a small demonstration dataset, so a fresh
deployment opens with data and a working sign-in and nothing to set up.

Runs at most once per process. Requests that arrive while it runs wait for it.
Two cold starts on Vercel each have their own /tmp and so their own database;
two processes sharing one data folder take turns through a lock file, and the
second finds the data already there.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from sqlalchemy import func, select

from .config import DATA_DIR, settings
from .db import create_all, session_scope
from .models import Shipment

log = logging.getLogger("portalbot")

_lock = threading.Lock()
_ready = False

#: A lock file older than this belongs to a process that died mid-load.
_STALE_SECONDS = 300

#: Soft budget for the heavier shipment/simulation phase, once the fast
#: accounts phase has already committed. A cold start that blows through
#: this still leaves sign-in working; it only trades away the
#: freshly-generated dashboard data for that one process's lifetime.
_SHIPMENT_TIME_BUDGET_SECONDS = 20.0


def is_ready() -> bool:
    return _ready


def ensure_ready() -> None:
    global _ready
    if _ready:
        return
    with _lock:
        if _ready:
            return
        create_all()
        if settings.should_auto_load_demo_data:
            try:
                _load_if_empty()
            except Exception:  # pragma: no cover - the app still starts, empty
                log.exception("Loading the demonstration data on start-up failed.")
        _ready = True


def _database_is_empty(session) -> bool:
    return not session.scalar(select(func.count(Shipment.id)))


def _load_if_empty() -> None:
    from .seed.generator import Builder
    from .services import runner
    from .systems.carrier import Behaviour, CarrierPortal

    with session_scope() as session:
        if not _database_is_empty(session):
            return

    with _file_lock():
        with session_scope() as session:
            if not _database_is_empty(session):  # another process got there first
                return

            started = time.perf_counter()

            # Phase 1 — demo sign-in accounts. Small (five rows), no
            # randomness, nothing that can run long. Committed on its own,
            # on purpose: a serverless cold start has a hard wall-clock
            # limit, and if the heavier phase below is cut short by it,
            # sign-in must still work. Committing here, before any of that
            # heavier work even starts, is what makes that true.
            user_builder = Builder(
                session, shipment_target=settings.auto_load_shipment_target
            )
            user_counts = user_builder.build_users()
        log.warning(
            "Seeded demo sign-in accounts in %.1f s: %s",
            time.perf_counter() - started,
            user_counts,
        )

        # Phase 2 — the heavier business data: a day of shipments plus the
        # scripted bot runs through them. Bounded by a soft time budget; on
        # a slow cold start this degrades to "sign-in works, the dashboard
        # fills in on the next request" instead of taking the request down.
        deadline = time.perf_counter() + _SHIPMENT_TIME_BUDGET_SECONDS
        try:
            with session_scope() as session:
                shipment_builder = Builder(
                    session, shipment_target=settings.auto_load_shipment_target
                )
                shipment_counts = shipment_builder.build_shipments()

                if time.perf_counter() > deadline:
                    log.warning(
                        "Demo shipment data exceeded its %.0f s budget; "
                        "committing the rows and skipping the scripted runs.",
                        _SHIPMENT_TIME_BUDGET_SECONDS,
                    )
                    return

                # Make every screen meaningful rather than opening on a
                # blank history: run most of the day through, pausing twice
                # so the first run shown is a real resume-after-crash
                # (stop_after cuts the process off mid-sequence; the next
                # run picks up exactly where it left off, with no duplicate
                # booking), then change the portal's form version so the
                # final shipments show the bot stopping, by design, because
                # the screen it drives has changed.
                legacy = Builder.legacy_for(session)
                behaviour = Behaviour(tracking_delay_seconds=0.0)
                carrier = CarrierPortal(behaviour=behaviour)
                runner.run_once(session, carrier, legacy, stop_after=8)

                if time.perf_counter() > deadline:
                    log.warning(
                        "Demo shipment data exceeded its %.0f s budget "
                        "mid-script; committing what ran so far.",
                        _SHIPMENT_TIME_BUDGET_SECONDS,
                    )
                    return

                runner.run_once(session, carrier, legacy, limit=30)
                behaviour.version = "v2"
                runner.run_once(session, carrier, legacy, limit=10)
            log.warning(
                "Loaded the demonstration shipment data in %.1f s: %s",
                time.perf_counter() - started,
                shipment_counts,
            )
        except Exception:  # pragma: no cover - accounts are already seeded
            log.exception(
                "Seeding the demonstration shipment data failed; "
                "demo accounts are already committed and sign-in still works."
            )


class _file_lock:
    """A lock between processes that share the data folder. Standard library only."""

    def __init__(self) -> None:
        self.path = DATA_DIR / "demo-data.lock"
        self.handle: int | None = None

    def __enter__(self) -> "_file_lock":
        deadline = time.monotonic() + _STALE_SECONDS
        while True:
            try:
                self.handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.handle, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > _STALE_SECONDS:
                        self.path.unlink(missing_ok=True)
                        continue
                except FileNotFoundError:
                    continue
                if time.monotonic() > deadline:
                    raise TimeoutError(f"Waited too long for {self.path}")
                time.sleep(0.2)

    def __exit__(self, *_exc: object) -> None:
        if self.handle is not None:
            os.close(self.handle)
        self.path.unlink(missing_ok=True)
