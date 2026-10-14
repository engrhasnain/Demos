"""Get the database ready before the first request is answered.

Creates the tables and, where storage is temporary (serverless plus SQLite),
fills an empty database with a small demonstration company, so a fresh
deployment opens with data and a working sign-in and nothing to set up.

Runs at most once per process. Requests that arrive while it runs wait for
it. It only ever fills an *empty* database, so running it again against data
that is already there does nothing.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time

from .config import DATA_DIR, settings
from .db import create_all, session_scope

log = logging.getLogger("frontdesk")

_lock = threading.Lock()
_ready = False

# How long the automatic, cold-start demo-data load is allowed before it
# stops adding the heavier, optional stages (orders, quotations,
# technicians, sample conversations) and hands back what it has. The demo
# accounts are seeded first and are unaffected by this, so sign-in keeps
# working even when the budget is hit. Comfortably under Vercel's function
# `maxDuration` (60s in vercel.json) with room for cold start + imports.
SEED_TIME_BUDGET_SECONDS = 22.0


def is_ready() -> bool:
    return _ready


def _under_pytest() -> bool:
    # Belt and suspenders: the settings gate below already keeps this out of
    # a pytest run, because pytest never sets VERCEL or AWS_LAMBDA_FUNCTION_NAME
    # and so never sees storage as temporary. This is a second check so a
    # test harness that *does* set one of those still gets a database with
    # nothing auto-loaded into it.
    return bool(os.getenv("PYTEST_CURRENT_TEST")) or "pytest" in sys.modules


def ensure_ready() -> None:
    global _ready
    if _ready:
        return
    with _lock:
        if _ready:
            return
        create_all()
        if settings.should_auto_load_demo_data and not _under_pytest():
            try:
                _load_if_empty()
            except Exception:  # pragma: no cover - the app still starts, empty
                log.exception("Loading the demonstration data on start-up failed.")
        _ready = True


def _load_if_empty() -> None:
    from .routers.desk import _database_is_empty, load_straight_through

    with session_scope() as session:
        if not _database_is_empty(session):
            return

    with _file_lock():
        with session_scope() as session:
            if not _database_is_empty(session):  # another process got there first
                return
            started = time.perf_counter()
            deadline = time.monotonic() + SEED_TIME_BUDGET_SECONDS
            counts = load_straight_through(
                session,
                settings.auto_load_customer_target,
                settings.auto_load_order_target,
                deadline=deadline,
            )
        elapsed = time.perf_counter() - started
        if elapsed >= SEED_TIME_BUDGET_SECONDS:
            log.warning(
                "Demonstration data load hit its %.0f s time budget and "
                "stopped early after %.1f s; the demo accounts are in place "
                "but some sample business data may be missing: %s",
                SEED_TIME_BUDGET_SECONDS,
                elapsed,
                counts,
            )
        else:
            log.warning(
                "Loaded the demonstration data on start-up in %.1f s: %s",
                elapsed,
                counts,
            )


class _file_lock:
    """A lock between processes that share the data folder. Standard library only."""

    _STALE_SECONDS = 300

    def __init__(self) -> None:
        self.path = DATA_DIR / "demo-data.lock"
        self.handle: int | None = None

    def __enter__(self) -> "_file_lock":
        deadline = time.monotonic() + self._STALE_SECONDS
        while True:
            try:
                self.handle = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(self.handle, str(os.getpid()).encode())
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > self._STALE_SECONDS:
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
