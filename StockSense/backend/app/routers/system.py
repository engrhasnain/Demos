"""The front page, the settings, the demonstration data and the evidence."""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..clock import today as today_date
from ..config import settings
from ..db import get_session
from ..domain import classify, forecast as models
from ..evaluation.runner import CRITERIA, run_evaluation
from ..models import (
    AuditEntry,
    DemandHistory,
    HistoricOrder,
    Part,
    PlanLine,
    PlanRun,
    ReplayRun,
    Supplier,
    User,
)
from ..security import ROLE_LABELS, get_current_user, require_role
from ..seed import generator
from ..serializers import dashboard
from ..services.reorder import DECISION_LABELS, REASON_LABELS

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        session.execute(select(1))
        database = "ready"
    except Exception as error:  # pragma: no cover - only on a broken deployment
        database = f"unavailable: {type(error).__name__}"
    return {
        "service": settings.app_name,
        "environment": settings.environment,
        "database": database,
        "engine": settings.forecast_engine,
        "serverless": settings.is_serverless,
    }


@router.get("/settings")
def read_settings(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """The policy the screens have to explain, in the units they show."""
    return {
        "base_currency": settings.base_currency,
        "weekly_cash_cap": settings.weekly_cash_cap_twd,
        "carrying_cost_percent_low": settings.carrying_cost_percent_low,
        "carrying_cost_percent_high": settings.carrying_cost_percent_high,
        "review_period_days": settings.review_period_days,
        "service_levels": {
            "A": settings.service_level_a,
            "B": settings.service_level_b,
            "C": settings.service_level_c,
        },
        "project_spike_multiple": settings.project_spike_multiple,
        "shutdown_prebuild_weeks": settings.shutdown_prebuild_weeks,
        "history_weeks": settings.history_weeks,
        "patterns": [
            {
                "kind": kind,
                "label": label,
                "description": classify.DESCRIPTIONS[kind],
                "method": classify.METHOD_FOR[kind],
                "intermittent": classify.is_intermittent(kind),
            }
            for kind, label in classify.LABELS.items()
        ],
        "methods": [
            {"code": code, "label": label, "note": models.METHOD_NOTES.get(code, "")}
            for code, label in models.METHOD_LABELS.items()
        ],
        "decisions": [{"code": c, "label": l} for c, l in DECISION_LABELS.items()],
        "reasons": [{"code": c, "label": l} for c, l in REASON_LABELS.items()],
        "roles": [{"code": c, "label": l} for c, l in ROLE_LABELS.items()],
        "cutoffs": {
            "average_demand_interval": classify.ADI_CUTOFF,
            "coefficient_of_variation_squared": classify.CV_SQUARED_CUTOFF,
        },
    }


@router.get("/dashboard")
def read_dashboard(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return dashboard(session, today_date())


@router.get("/audit")
def read_audit(
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("purchasing_manager")),
    limit: int = 100,
) -> dict[str, Any]:
    rows = session.scalars(
        select(AuditEntry).order_by(AuditEntry.id.desc()).limit(min(limit, 500))
    )
    return {
        "items": [
            {
                "id": row.id,
                "occurred_at": row.occurred_at.isoformat() if row.occurred_at else None,
                "user_email": row.user_email,
                "action": row.action,
                "entity": row.entity,
                "entity_id": row.entity_id,
                "detail": row.detail,
            }
            for row in rows
        ]
    }


# ---------------------------------------------------------------------------
# The demonstration data
# ---------------------------------------------------------------------------
@router.get("/demo/state")
def demo_state(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Open, because the first screen asks before anybody has signed in."""
    parts = session.scalar(select(func.count(Part.id))) or 0
    plans = session.scalar(select(func.count(PlanRun.id))) or 0
    return {
        "loaded": parts > 0,
        "planned": plans > 0,
        "parts": parts,
        "engine": settings.forecast_engine,
        "storage_is_temporary": settings.storage_is_temporary,
    }


class LoadRequest(BaseModel):
    size: str = "full"


SIZES: dict[str, tuple[int, int]] = {
    "full": (18_000, 140),
    "medium": (6_000, 90),
    "small": (1_500, 40),
}


@router.post("/demo/load")
def load_demo(
    body: LoadRequest,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("administrator")),
) -> dict[str, Any]:
    parts, suppliers = SIZES.get(body.size, SIZES["full"])
    if settings.is_serverless and parts > 6_000:
        parts, suppliers = SIZES["medium"]
    # On serverless hosting the platform's own request timeout is the real
    # deadline. A soft budget well inside it means a slow cold start is
    # logged clearly rather than the function simply being killed mid-write.
    budget = 22.0 if settings.is_serverless else None
    started = time.perf_counter()
    counts = generator.build_demo_data(
        session, part_target=parts, supplier_target=suppliers, time_budget_seconds=budget
    )
    return {
        "seconds": round(time.perf_counter() - started, 2),
        "counts": counts,
        "state": demo_state(session),
    }


# ---------------------------------------------------------------------------
# The evidence
# ---------------------------------------------------------------------------
@router.get("/evidence/criteria")
def criteria(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"criteria": CRITERIA}


class EvidenceRequest(BaseModel):
    parts: int | None = Field(1200, ge=50, le=50_000)
    weeks: int = Field(52, ge=8, le=104)


@router.post("/evidence/run")
def run_evidence(
    body: EvidenceRequest,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("senior_buyer")),
) -> dict[str, Any]:
    parts = body.parts
    if settings.is_serverless:
        parts = min(parts or 500, 500)
    try:
        return run_evaluation(session, parts=parts, weeks=body.weeks)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
