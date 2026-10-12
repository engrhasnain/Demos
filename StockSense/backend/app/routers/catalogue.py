"""Parts and suppliers."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from ..clock import today as today_date
from ..db import get_session
from ..models import DemandHistory, Part, Supplier, User
from ..security import get_current_user
from ..serializers import part_brief, supplier_brief, supplier_detail
from ..services import demand as demand_service, reorder

router = APIRouter(prefix="/api", tags=["catalogue"])


@router.get("/parts")
def list_parts(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    search: str | None = None,
    abc_class: str | None = None,
    supplier_id: int | None = None,
    family: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    query = select(Part).options(selectinload(Part.supplier))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(Part.code.ilike(pattern), Part.description.ilike(pattern))
        )
    if abc_class:
        query = query.where(Part.abc_class == abc_class.upper())
    if supplier_id:
        query = query.where(Part.supplier_id == supplier_id)
    if family:
        query = query.where(Part.family == family)

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(query.order_by(Part.code).limit(limit).offset(offset))
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [part_brief(row) for row in rows],
    }


@router.get("/parts/{part_id}")
def read_part(
    part_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """One part, with the whole route from its history to a recommendation."""
    part = session.get(Part, part_id)
    if part is None:
        raise HTTPException(status_code=404, detail="There is no part with that number.")

    view = demand_service.for_part(session, part)
    recommendation = reorder.build(session, part, view, as_of=today_date())
    record = session.scalar(
        select(DemandHistory).where(DemandHistory.part_id == part.id)
    )

    successor = (
        session.get(Part, part.replaced_by_part_id) if part.replaced_by_part_id else None
    )
    predecessor = (
        session.get(Part, part.replaces_part_id) if part.replaces_part_id else None
    )

    return {
        **part_brief(part),
        "supplier": supplier_detail(session, part.supplier, today_date()),
        "history_starts_on": record.starts_on.isoformat() if record else None,
        "demand": view.to_dict(),
        "recommendation": recommendation.to_dict(),
        "successor": part_brief(successor) if successor else None,
        "predecessor": part_brief(predecessor) if predecessor else None,
    }


@router.get("/suppliers")
def list_suppliers(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    search: str | None = None,
    limit: int = Query(60, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    query = select(Supplier)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(Supplier.name.ilike(pattern), Supplier.code.ilike(pattern))
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(query.order_by(Supplier.name).limit(limit).offset(offset))
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [supplier_brief(row) for row in rows],
    }


@router.get("/suppliers/{supplier_id}")
def read_supplier(
    supplier_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    supplier = session.get(Supplier, supplier_id)
    if supplier is None:
        raise HTTPException(status_code=404, detail="There is no supplier with that number.")
    out = supplier_detail(session, supplier, today_date())
    parts = session.scalars(
        select(Part)
        .options(selectinload(Part.supplier))
        .where(Part.supplier_id == supplier.id)
        .order_by(Part.code)
        .limit(50)
    )
    out["part_list"] = [part_brief(row) for row in parts]
    return out
