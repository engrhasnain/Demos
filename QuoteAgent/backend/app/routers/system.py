"""System status and the guided "load the demonstration data" screen."""

from __future__ import annotations

import datetime as dt
import logging
import threading
import time
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session, session_scope
from ..domain.incoterms import INCOTERMS
from ..models import (
    Case,
    Contract,
    CrossReference,
    Customer,
    EvaluationRun,
    ExchangeRate,
    Product,
    Supplier,
    TariffTable,
    User,
    Warehouse,
)
from ..security import get_current_user, oauth2_scheme, require_role
from ..seed import casebook, generator
from ..services import casestate, matching, reasoning

router = APIRouter(prefix="/api/system", tags=["System"])

log = logging.getLogger("quoteagent.system")

#: Vercel's own function timeout is set to 60 seconds (see backend/vercel.json).
#: The accounts and catalogue that `generator.build_demo_data` seeds first are
#: what sign-in and a quote actually need; the worked case book that comes
#: after it is a nice-to-have inbox, not a requirement. Giving it its own
#: budget, measured from when the synchronous (serverless) load started,
#: means a slow cold start can cut it short without the request itself
#: timing out and taking the whole response down with it.
SEED_TIME_BUDGET_SECONDS = 25.0


# ---------------------------------------------------------------------------
# Loading progress, held in memory because it only has to survive the load
# ---------------------------------------------------------------------------
class LoadState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.stage = ""
        self.stage_label = ""
        self.done = 0
        self.total = 0
        self.completed_stages: list[str] = []
        self.finished_at: str | None = None
        self.error: str = ""
        self.counts: dict[str, int] = {}

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            stage_index = len(self.completed_stages)
            return {
                "running": self.running,
                "stage": self.stage,
                "stage_label": self.stage_label,
                "stage_number": min(stage_index + (1 if self.running else 0), len(generator.STAGES)),
                "stage_count": len(generator.STAGES),
                "done": self.done,
                "total": self.total,
                "percent": round(self.done / self.total * 100, 1) if self.total else 0.0,
                "completed_stages": list(self.completed_stages),
                "finished_at": self.finished_at,
                "error": self.error,
                "counts": dict(self.counts),
                "stages": [
                    {"key": key, "label": label, "done": key in self.completed_stages}
                    for key, label in generator.STAGES
                ],
            }


LOAD_STATE = LoadState()
STAGE_LABELS = dict(generator.STAGES)


def _progress(stage: str, done: int, total: int) -> None:
    with LOAD_STATE.lock:
        if stage != LOAD_STATE.stage and LOAD_STATE.stage:
            if LOAD_STATE.stage not in LOAD_STATE.completed_stages:
                LOAD_STATE.completed_stages.append(LOAD_STATE.stage)
        LOAD_STATE.stage = stage
        LOAD_STATE.stage_label = STAGE_LABELS.get(stage, stage)
        LOAD_STATE.done = done
        LOAD_STATE.total = max(total, 1)


def _load(product_target: int, customer_target: int) -> None:
    try:
        with session_scope() as session:
            counts = generator.build_demo_data(
                session,
                product_target=product_target,
                customer_target=customer_target,
                progress=_progress,
            )
        matching.reset_index()
        with session_scope() as session:
            matching.get_index(session, rebuild=True)
            built = casebook.build_case_book(session, progress=_progress)
            counts["worked_cases"] = len(built)
        with LOAD_STATE.lock:
            LOAD_STATE.counts = counts
            for key, _label in generator.STAGES:
                if key not in LOAD_STATE.completed_stages:
                    LOAD_STATE.completed_stages.append(key)
            LOAD_STATE.stage = "samples"
            LOAD_STATE.stage_label = "Finished"
    except Exception as exc:  # pragma: no cover - surfaced on the screen
        with LOAD_STATE.lock:
            LOAD_STATE.error = f"{type(exc).__name__}: {exc}"
    finally:
        with LOAD_STATE.lock:
            LOAD_STATE.running = False
            LOAD_STATE.finished_at = dt.datetime.now(dt.timezone.utc).isoformat()


def _database_is_empty(session: Session) -> bool:
    """No accounts and no company yet: a brand new database."""
    return all(
        not session.scalar(select(func.count()).select_from(model))
        for model in (User, Warehouse, Product)
    )


def administrator_unless_first_run(
    token: str | None = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User | None:
    """An administrator, except on a brand new database.

    The demonstration accounts are created by the load itself, so on an empty
    database nobody can sign in to start it and the first run could never be
    reached. In that one state the load is open to anyone. As soon as an
    account or any of the company exists it needs an administrator again, so
    this cannot be used to wipe or replace data that is already there.
    """
    if _database_is_empty(session):
        return None
    return require_role("administrator")(get_current_user(token, session))


class LoadRequest(BaseModel):
    product_target: int = Field(default=18_000, ge=200, le=40_000)
    customer_target: int = Field(default=1_200, ge=10, le=5_000)
    #: Also put two dozen worked requests in the inbox, in every state a
    #: request can be in, so the product does not open on an empty screen.
    with_case_book: bool = True


@router.post("/load-demo-data")
def load_demo_data(
    payload: LoadRequest | None = None,
    _user: User | None = Depends(administrator_unless_first_run),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    payload = payload or LoadRequest()

    # On Vercel a background thread does not outlive the request that started
    # it, so there would be nothing to report progress on. The load runs
    # inside the request instead and the interface is told not to poll.
    if settings.is_serverless:
        started = time.monotonic()
        counts = generator.build_demo_data(
            session,
            product_target=payload.product_target,
            customer_target=payload.customer_target,
        )
        # Accounts (and the rest of the catalogue sign-in and pricing need)
        # are seeded inside build_demo_data before anything else, specifically
        # so that a slow cold start which only gets this far still leaves
        # sign-in working. See generator.DemoDataBuilder.build for the order.
        matching.reset_index()
        matching.get_index(session, rebuild=True)

        elapsed = time.monotonic() - started
        if payload.with_case_book:
            remaining = SEED_TIME_BUDGET_SECONDS - elapsed
            if remaining > 0:
                counts["worked_cases"] = len(casebook.build_case_book(session))
            else:
                log.warning(
                    "Skipping the demonstration case book: the catalogue and "
                    "account seed already took %.1fs, over the %.1fs budget "
                    "left for the heavier, optional worked inbox. Sign-in and "
                    "the catalogue are already loaded; load the case book "
                    "again afterwards if it is needed.",
                    elapsed,
                    SEED_TIME_BUDGET_SECONDS,
                )
                counts["worked_cases"] = 0
                counts["case_book_skipped"] = True
        return {"started": True, "mode": "synchronous", "counts": counts}

    with LOAD_STATE.lock:
        if LOAD_STATE.running:
            raise HTTPException(status_code=409, detail="The data is already being loaded.")
        LOAD_STATE.running = True
        LOAD_STATE.error = ""
        LOAD_STATE.counts = {}
        LOAD_STATE.completed_stages = []
        LOAD_STATE.stage = ""
        LOAD_STATE.done = 0
        LOAD_STATE.total = 1
        LOAD_STATE.finished_at = None

    thread = threading.Thread(
        target=_load, args=(payload.product_target, payload.customer_target), daemon=True
    )
    thread.start()
    return {
        "started": True,
        "mode": "background",
        "stages": [{"key": k, "label": v} for k, v in generator.STAGES],
    }


@router.post("/load-demo-data-now")
def load_demo_data_now(
    payload: LoadRequest | None = None,
    _user: User | None = Depends(administrator_unless_first_run),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """The same load, run straight through. Used by tests and by scripts."""
    payload = payload or LoadRequest()
    counts = generator.build_demo_data(
        session, product_target=payload.product_target, customer_target=payload.customer_target
    )
    matching.reset_index()
    matching.get_index(session, rebuild=True)
    return {"loaded": True, "counts": counts}


@router.get("/load-progress")
def load_progress() -> dict[str, Any]:
    return LOAD_STATE.snapshot()


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------
def _counts(session: Session) -> dict[str, int]:
    def count(model: Any) -> int:
        return int(session.scalar(select(func.count()).select_from(model)) or 0)

    return {
        "products": count(Product),
        "customers": count(Customer),
        "suppliers": count(Supplier),
        "cross_references": count(CrossReference),
        "contracts": count(Contract),
        "tariff_tables": count(TariffTable),
        "exchange_rates": count(ExchangeRate),
        "cases": count(Case),
        "users": count(User),
        "evaluation_runs": count(EvaluationRun),
    }


@router.get("/status")
def status(session: Session = Depends(get_session)) -> dict[str, Any]:
    counts = _counts(session)
    return {
        "application": settings.app_name,
        "environment": settings.environment,
        "database": "SQLite" if settings.uses_sqlite else "PostgreSQL",
        "hosting": "serverless" if settings.is_serverless else "a long running server",
        "storage_is_temporary": settings.storage_is_temporary,
        "storage_warning": (
            "This deployment is running on serverless functions with a SQLite "
            "file in temporary storage, so the demonstration data is lost when "
            "the function is recycled. Set DATABASE_URL to a PostgreSQL database "
            "to keep it."
            if settings.storage_is_temporary
            else ""
        ),
        "recommended_product_target": 2_000 if settings.is_serverless else 18_000,
        "data_loaded": counts["products"] > 0 and counts["users"] > 0,
        "counts": counts,
        "reasoning_engine": reasoning.engine_status(),
        "company": {
            "name": "Hengtai Industrial Supply",
            "description": (
                "A fictional Taiwan and United States distributor of industrial "
                "fasteners, bearings and pneumatic components, used so every part of "
                "this demonstration refers to one real-feeling business."
            ),
            "warehouses": ["Taichung, Taiwan", "Ontario, California"],
            "base_currency": settings.base_currency,
        },
        "policies": {
            "quote_validity_days": settings.quote_validity_days,
            "exchange_rate_lock_days": settings.foreign_exchange_lock_days,
            "director_approval_threshold_twd": settings.director_approval_threshold_twd,
            "default_margin_floor_percent": settings.default_margin_floor_percent,
        },
    }


@router.get("/reference")
def reference(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """Lists the screens need: statuses, trade rules, roles."""
    return {
        "case_statuses": casestate.all_statuses(),
        "incoterms": [
            {
                "code": rule.code,
                "name": rule.name,
                "transport": (
                    "any mode of transport"
                    if rule.transport == "any_mode"
                    else "sea and inland waterway only"
                ),
                "seller_pays": rule.cost_components(),
                "explained": rule.plain_summary(),
            }
            for rule in INCOTERMS.values()
        ],
    }


# ---------------------------------------------------------------------------
# The dashboard
# ---------------------------------------------------------------------------
#: What each queue means, in the order a sales desk works them.
QUEUES: list[tuple[str, str, str, str]] = [
    ("awaiting_approval", "Waiting for approval", "yours", "A manager or director has to decide."),
    ("priced", "Priced, ready to send", "yours", "Nothing is blocking these. Check and send."),
    ("received", "Not read yet", "yours", "Just arrived. Run the agent."),
    ("matched", "Parts identified", "yours", "Read and matched, not yet priced."),
    ("revised", "Revised request in", "yours", "The customer changed the bill of materials."),
    ("awaiting_customer", "Waiting on a customer", "theirs", "Questions are with the customer."),
    ("awaiting_supplier", "Waiting on a supplier", "theirs", "A price request is out."),
    ("sent", "Quote sent", "done", "With the customer to decide."),
    ("won", "Won", "done", ""),
    ("lost", "Lost", "done", ""),
]


@router.get("/dashboard")
def dashboard(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """Counts and money for the overview screen, grouped by what needs doing."""
    from collections import defaultdict

    from ..models import QuoteVersion
    from ..money import dec, money

    by_status: dict[str, int] = defaultdict(int)
    open_value: dict[str, Decimal] = defaultdict(Decimal)
    sent_value: dict[str, Decimal] = defaultdict(Decimal)
    won_value: dict[str, Decimal] = defaultdict(Decimal)
    lines_quoted = 0

    thirty_days_ago = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)

    for case in session.scalars(select(Case)):
        by_status[case.status] += 1
        versions = sorted(case.quote_versions, key=lambda v: v.version_number)
        if not versions:
            continue
        current = versions[-1]
        total = dec(current.grand_total)
        if total <= 0:
            continue
        lines_quoted += len(current.lines)
        if case.status in {"won"}:
            won_value[current.currency] += total
        elif case.status in {"sent", "revised"}:
            sent_value[current.currency] += total
        elif case.status not in {"lost", "cancelled"}:
            open_value[current.currency] += total

    def as_money(totals: dict[str, Decimal]) -> list[dict[str, str]]:
        return [
            {"currency": currency, "amount": str(money(amount))}
            for currency, amount in sorted(totals.items(), key=lambda kv: -kv[1])
            if amount > 0
        ]

    queues = [
        {
            "status": status,
            "label": label,
            "owner": owner,
            "hint": hint,
            "count": by_status.get(status, 0),
        }
        for status, label, owner, hint in QUEUES
    ]

    needs_you = sum(q["count"] for q in queues if q["owner"] == "yours")
    waiting = sum(q["count"] for q in queues if q["owner"] == "theirs")

    return {
        "queues": queues,
        "needs_you": needs_you,
        "waiting_on_others": waiting,
        "total_cases": sum(by_status.values()),
        "lines_quoted": lines_quoted,
        "open_value": as_money(open_value),
        "sent_value": as_money(sent_value),
        "won_value": as_money(won_value),
        "since": thirty_days_ago.date().isoformat(),
    }
