"""Get the database ready before the first request is answered.

Creates the tables and, where storage is temporary (serverless plus
SQLite), fills an empty database with the demonstration data and a
handful of asked questions, so a fresh deployment opens with data, a
working sign-in and every screen meaningful rather than empty. The data
is generated rather than copied from a snapshot so every date is relative
to today.

Runs at most once per process. Requests that arrive while it runs wait
for it. Two cold starts on Vercel each have their own /tmp and so their
own database; two processes sharing one data folder take turns through a
lock file, and the second finds the data already there.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from .config import DATA_DIR, settings
from .db import create_all, session_scope

log = logging.getLogger("opsagent")

_lock = threading.Lock()
_ready = False

#: A lock file older than this belongs to a process that died mid-load.
_STALE_SECONDS = 300


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
    from sqlalchemy import func, select

    from .models import Customer

    return not session.scalar(select(func.count(Customer.id)))


def _load_if_empty() -> None:
    from .seed.autoload import ask_example_questions
    from .seed.generator import build_demo_data

    with session_scope() as session:
        if not _database_is_empty(session):
            return

    with _file_lock():
        with session_scope() as session:
            if not _database_is_empty(session):  # another process got there first
                return
            started = time.perf_counter()
            counts = build_demo_data(
                session,
                customer_target=settings.auto_load_customer_target,
                order_target=settings.auto_load_order_target,
            )
            counts["example_questions"] = ask_example_questions(session)
        log.warning(
            "Loaded the demonstration data on start-up in %.1f s: %s",
            time.perf_counter() - started,
            counts,
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
