"""The weekly ordering round, and the replay that grades it."""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from ..clock import today as today_date
from ..config import settings
from ..db import get_session
from ..models import Part, PlanLine, PlanRun, ReplayRun, User
from ..numbers import money
from ..security import get_current_user, require_role
from ..serializers import plan_line, plan_run, plan_summary
from ..services import plan as planning, replay as replaying

router = APIRouter(prefix="/api", tags=["planning"])


class PlanRequest(BaseModel):
    cash_cap: float | None = Field(None, ge=0)
    parts: int | None = Field(None, ge=1, le=50_000)
    as_of: dt.date | None = None


@router.post("/plan")
def build_plan(
    body: PlanRequest,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("buyer")),
) -> dict[str, Any]:
    """Look at every part and decide what to buy this week."""
    limit = body.parts
    if settings.is_serverless:
        # A serverless function has a short life. Trimming the sample is
        # better than being cut off halfway through.
        limit = min(limit or 4_000, 4_000)
    summary = planning.run_plan(
        session,
        as_of=body.as_of or today_date(),
        cash_cap=body.cash_cap,
        limit=limit,
        by=user,
    )
    out = plan_summary(session, summary.run)
    out["allocation"] = summary.allocation.to_dict()
    return out


@router.get("/plan")
def latest_plan(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any] | None:
    run = session.scalar(select(PlanRun).order_by(PlanRun.id.desc()).limit(1))
    return plan_summary(session, run) if run else None


@router.get("/plan/{run_id}/lines")
def plan_lines(
    run_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    decision: str | None = None,
    reason: str | None = None,
    pattern: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    run = session.get(PlanRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="There is no plan with that number.")

    query = (
        select(PlanLine)
        .options(selectinload(PlanLine.part).selectinload(Part.supplier))
        .where(PlanLine.run_id == run_id)
    )
    if decision:
        query = query.where(PlanLine.decision == decision)
    if reason:
        query = query.where(PlanLine.reason == reason)
    if pattern:
        query = query.where(PlanLine.demand_pattern == pattern)
    if search:
        query = query.join(Part, PlanLine.part_id == Part.id).where(
            Part.code.ilike(f"%{search.strip()}%")
        )

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(PlanLine.urgency.desc(), PlanLine.id).limit(limit).offset(offset)
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [plan_line(row) for row in rows],
    }


@router.get("/plan/{run_id}/lines/{line_id}")
def one_plan_line(
    run_id: int,
    line_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    line = session.get(PlanLine, line_id)
    if line is None or line.run_id != run_id:
        raise HTTPException(status_code=404, detail="There is no such line on this plan.")
    return plan_line(line, with_trace=True)


# ---------------------------------------------------------------------------
# The replay
# ---------------------------------------------------------------------------
class ReplayRequest(BaseModel):
    parts: int | None = Field(1200, ge=10, le=50_000)
    weeks: int = Field(52, ge=8, le=104)


@router.post("/replay")
def run_replay(
    body: ReplayRequest,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("senior_buyer")),
) -> dict[str, Any]:
    """Run the last year again, both ways, and report the difference."""
    parts = body.parts
    if settings.is_serverless:
        parts = min(parts or 500, 500)
    report = replaying.run_replay(session, weeks=body.weeks, limit=parts)

    run = ReplayRun(
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
    session.add(run)
    session.flush()
    report["id"] = run.id
    return report


@router.get("/replay")
def latest_replay(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any] | None:
    run = session.scalar(select(ReplayRun).order_by(ReplayRun.id.desc()).limit(1))
    if run is None:
        return None
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "weeks": run.weeks,
        "parts": run.parts,
        "seconds": float(run.seconds),
        "buyers": run.buyers,
        "stocksense": run.stocksense,
        "by_pattern": run.by_pattern,
        "weekly": run.weekly,
        "accuracy": run.accuracy,
        "passed": run.passed,
        "notes": run.notes,
    }
