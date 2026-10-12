"""Demonstration data on a cold start.

On Vercel with no DATABASE_URL the database is a SQLite file in the
function's scratch space, which starts empty every time a new instance starts.
Rather than open on a screen nobody can sign in to, the instance builds the
smaller company and puts the morning's post through it before it answers its
first request. It takes a few seconds, and the data resets when the instance
does.

It never runs anywhere else: not on a laptop, not in the tests, and not
against a real database. AUTO_LOAD_DEMO_DATA=false turns it off.
"""

from __future__ import annotations

import logging
import sys
import threading
import time

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import create_all, session_scope
from ..models import Entity, User, Vendor
from ..services import pipeline
from . import generator
from .invoices import build_batch

log = logging.getLogger("ledgerflow")

#: The smaller set the load screen offers: every screen has something on it.
VENDORS = 40
ORDERS = 60

_lock = threading.Lock()
ready = False


def wanted() -> bool:
    if not settings.auto_load_demo_data or "pytest" in sys.modules:
        return False
    return settings.storage_is_temporary


def _is_empty(session: Session) -> bool:
    return all(
        not session.scalar(select(func.count()).select_from(model))
        for model in (User, Entity, Vendor)
    )


def _load(session: Session) -> dict[str, int] | None:
    # Take SQLite's write lock before looking, so a second process sharing the
    # file waits here and then finds the data instead of loading it again.
    session.connection().exec_driver_sql("BEGIN IMMEDIATE")
    if not _is_empty(session):
        return None
    counts = generator.build_demo_data(session, vendor_target=VENDORS, order_target=ORDERS)
    documents = build_batch(session)
    for document in documents:
        invoice, _created = pipeline.receive(
            session,
            filename=document.filename,
            content=document.content,
            content_type=document.content_type,
            text=document.text,
            barcode_payload=document.barcode_payload,
            received_from=document.received_from,
            kind=document.kind,
        )
        try:
            pipeline.run(session, invoice)
        except pipeline.PipelineError:
            pass  # stopping is what some of these documents are there to show
    counts["documents"] = len(documents)
    return counts


def prepare() -> None:
    """Create the tables and, on a fresh serverless instance, the data. Once."""
    global ready
    if ready:
        return
    with _lock:
        if ready:
            return
        create_all()
        if wanted():
            started = time.perf_counter()
            try:
                with session_scope() as session:
                    counts = _load(session)
                if counts:
                    log.warning(
                        "Loaded the demonstration data in %.1f s: %s",
                        time.perf_counter() - started,
                        counts,
                    )
            except Exception:  # pragma: no cover - the app still answers
                log.exception("Could not load the demonstration data")
        ready = True
