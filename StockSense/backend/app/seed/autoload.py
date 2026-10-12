"""Load the demonstration company on boot, when nothing else can.

On Vercel the database is a SQLite file in /tmp: it starts empty on every
cold start and nobody is there to run the walkthrough. So the first request
builds a compact company (600 parts, 25 suppliers, the full two years of
history), works out this week's orders and replays a slice of the year,
and every screen has something real on it within a few seconds.

It only runs when all of these hold:

* the app is serverless *and* on SQLite (a PostgreSQL database keeps its
  data, so it is loaded once, by the administrator, as usual);
* ``AUTO_LOAD_DEMO_DATA`` is not switched off;
* the database is empty (no people, no parts);
* this is not a test run.

It is safe under concurrency: a lock in this process, and a lock file next
to the database for any other process sharing the same scratch disk.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

from sqlalchemy import func, select

from ..config import DATA_DIR, settings

log = logging.getLogger("stocksense")

#: Small enough to build in a few seconds on a cold function, large enough
#: that every pattern, a mainland shutdown and pre-build orders all appear.
PARTS = 600
SUPPLIERS = 25
REPLAY_PARTS = 150

_LOCK = threading.Lock()
_LOCK_FILE = DATA_DIR / "autoload.lock"
_done = False


def wanted() -> bool:
    if not settings.auto_load_demo_data:
        return False
    if not settings.storage_is_temporary:
        return False
    # Never in a test run, whatever the environment says.
    if "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST"):
        return False
    return True


def _is_empty() -> bool:
    from ..db import session_scope
    from ..models import Part, User

    with session_scope() as session:
        people = session.scalar(select(func.count(User.id))) or 0
        parts = session.scalar(select(func.count(Part.id))) or 0
    return people == 0 and parts == 0


def _acquire_file_lock(timeout: float = 90.0) -> bool:
    """True if this process now owns the lock; False if another finished first."""
    deadline = time.monotonic() + timeout
    while True:
        try:
            handle = os.open(str(_LOCK_FILE), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(handle, str(os.getpid()).encode())
            os.close(handle)
            return True
        except FileExistsError:
            # A lock older than the timeout belongs to a process that died.
            try:
                if time.time() - _LOCK_FILE.stat().st_mtime > timeout:
                    _LOCK_FILE.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > deadline:
                return False
            time.sleep(0.25)


def _build() -> None:
    from ..db import session_scope
    from ..models import ReplayRun
    from ..numbers import money
    from ..services import plan as planning, replay as replaying
    from . import generator

    started = time.perf_counter()
    with session_scope() as session:
        counts = generator.build_demo_data(
            session, part_target=PARTS, supplier_target=SUPPLIERS
        )
    with session_scope() as session:
        planning.run_plan(session)
    with session_scope() as session:
        report = replaying.run_replay(session, limit=REPLAY_PARTS)
        session.add(
            ReplayRun(
                weeks=report["weeks"],
                parts=report["parts"],
                seconds=money(report["seconds"]),
                buyers=report["buyers"],
                stocksense=report["stocksense"],
                by_pattern=report["by_pattern"],
                weekly=report["weekly"],
                accuracy=report["accuracy"],
                passed=report["passed"],
                notes=(
                    f"{report['parts']:,} parts over {report['weeks']} weeks in "
                    f"{report['seconds']}s."
                ),
            )
        )
    log.warning(
        "Demonstration data loaded into temporary storage in %.1fs (%s parts). "
        "It resets when the server restarts.",
        time.perf_counter() - started,
        counts.get("parts"),
    )


def ensure_demo_data() -> None:
    """Idempotent and cheap after the first call."""
    global _done
    if _done:
        return
    if not wanted():
        _done = True
        return
    with _LOCK:
        if _done:
            return
        try:
            if _is_empty():
                if not _acquire_file_lock():
                    return  # still being built elsewhere; the next request checks again
                try:
                    # Another process may have built it while this one waited.
                    if _is_empty():
                        _build()
                finally:
                    _LOCK_FILE.unlink(missing_ok=True)
        except Exception:  # pragma: no cover - never stop the app from serving
            log.exception("Could not load the demonstration data on boot.")
            return
        _done = True
