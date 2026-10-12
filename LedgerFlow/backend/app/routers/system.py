"""The front page, the ledger, and the settings the screens need to know."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import AuditEntry, Entity, LedgerBill, User
from ..security import ROLE_LABELS, get_current_user, require_role
from ..serializers import dashboard, entity_row, ledger_bill, when
from ..services import workflow

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Open on purpose: a load balancer cannot sign in."""
    try:
        session.execute(select(1))
        database = "ready"
    except Exception as error:  # pragma: no cover - only on a broken deployment
        database = f"unavailable: {type(error).__name__}"
    return {
        "service": settings.app_name,
        "environment": settings.environment,
        "database": database,
        "reading_engine": settings.reading_engine,
        "serverless": settings.is_serverless,
    }


@router.get("/settings")
def read_settings(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """The policy the screens have to explain, in the units the screens show."""
    return {
        "base_currency": settings.base_currency,
        "business_tax_percent": settings.business_tax_percent,
        "auto_post_ceiling": settings.auto_post_ceiling_twd,
        "two_step_approval": settings.two_step_approval_twd,
        "default_tolerance_percent": settings.default_tolerance_percent,
        "default_tolerance_absolute": settings.default_tolerance_absolute_twd,
        "default_unordered_allowance": settings.default_unordered_allowance_twd,
        "late_arrival_days": settings.late_arrival_days,
        "reading_engine": settings.reading_engine,
        "statuses": workflow.all_statuses(),
        "exception_kinds": [
            {
                "kind": kind,
                "label": label,
                "severity": workflow.severity_of(kind),
            }
            for kind, label in workflow.EXCEPTION_LABELS.items()
        ],
        "roles": [{"code": code, "label": label} for code, label in ROLE_LABELS.items()],
    }


@router.get("/dashboard")
def read_dashboard(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return dashboard(session)


@router.get("/entities")
def list_entities(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> list[dict[str, Any]]:
    return [entity_row(row) for row in session.scalars(select(Entity).order_by(Entity.code))]


@router.get("/ledger")
def read_ledger(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    """What the accounting system holds. The product's output, in other words."""
    total = session.scalar(select(func.count(LedgerBill.id))) or 0
    rows = session.scalars(
        select(LedgerBill).order_by(LedgerBill.id.desc()).limit(limit).offset(offset)
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [ledger_bill(row) for row in rows],
    }


@router.get("/audit")
def read_audit(
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("controller")),
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    rows = session.scalars(select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit))
    return {
        "items": [
            {
                "id": row.id,
                "occurred_at": when(row.occurred_at),
                "user_email": row.user_email,
                "action": row.action,
                "entity": row.entity,
                "entity_id": row.entity_id,
                "before": row.before,
                "after": row.after,
            }
            for row in rows
        ]
    }
