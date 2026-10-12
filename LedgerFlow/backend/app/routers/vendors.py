"""Suppliers, their bank details, and the telephone calls that change them."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import CallBackTask, Invoice, User, Vendor
from ..security import get_current_user, require_role
from ..serializers import call_back, invoice_brief, vendor_brief, vendor_detail
from ..services import approvals, audit, guards, pipeline, workflow

router = APIRouter(prefix="/api/vendors", tags=["suppliers"])


@router.get("")
def list_vendors(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    search: str | None = None,
    bank_change_pending: bool | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    query = select(Vendor)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(Vendor.name.ilike(pattern), Vendor.code.ilike(pattern), Vendor.email.ilike(pattern))
        )
    if bank_change_pending is not None:
        query = query.where(Vendor.bank_change_pending.is_(bank_change_pending))

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(query.order_by(Vendor.name).limit(limit).offset(offset))
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [vendor_brief(row) for row in rows],
    }


@router.get("/call-backs")
def list_call_backs(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    open_only: bool = True,
) -> dict[str, Any]:
    query = select(CallBackTask).order_by(CallBackTask.id.desc())
    if open_only:
        query = query.where(CallBackTask.status == "open")
    rows = list(session.scalars(query))
    return {"total": len(rows), "items": [call_back(row) for row in rows]}


@router.get("/{vendor_id}")
def read_vendor(
    vendor_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    vendor = session.get(Vendor, vendor_id)
    if vendor is None:
        raise HTTPException(status_code=404, detail="There is no supplier with that number here.")
    out = vendor_detail(session, vendor)
    recent = session.scalars(
        select(Invoice).where(Invoice.vendor_id == vendor.id).order_by(Invoice.id.desc()).limit(25)
    )
    out["invoices"] = [invoice_brief(row) for row in recent]
    return out


class CallBackOutcome(BaseModel):
    confirmed: bool
    note: str = Field("", max_length=2000)


@router.post("/call-backs/{task_id}")
def complete_call_back(
    task_id: int,
    body: CallBackOutcome,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("controller")),
) -> dict[str, Any]:
    """Record the call. This is the only way a bank account ever changes.

    The controller role is required because this is the one action in the
    product that can move money to an account nobody has paid before.
    """
    task = session.get(CallBackTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="There is no such call-back.")
    if task.status != "open":
        raise HTTPException(status_code=409, detail="That call has already been recorded.")
    if body.confirmed and len(body.note.strip()) < 10:
        raise HTTPException(
            status_code=422,
            detail="Say who you spoke to and on what number before confirming a new account.",
        )

    before = [
        {"account_number": a.account_number, "is_current": a.is_current}
        for a in task.vendor.bank_accounts
    ]
    guards.complete_call_back(
        session, task, user_id=user.id, confirmed=body.confirmed, note=body.note
    )
    audit.record_change(
        session,
        user=user,
        action="call_back_completed",
        entity="vendor",
        entity_id=str(task.vendor_id),
        before={"bank_accounts": before},
        after={
            "bank_accounts": [
                {"account_number": a.account_number, "is_current": a.is_current}
                for a in task.vendor.bank_accounts
            ],
            "outcome": task.outcome,
        },
    )

    # The invoices this supplier had stuck behind the block can move again.
    freed: list[dict[str, Any]] = []
    stuck = session.scalars(
        select(Invoice).where(
            Invoice.vendor_id == task.vendor_id,
            Invoice.status.notin_(sorted(workflow.TERMINAL)),
        )
    )
    for invoice in list(stuck):
        for row in invoice.exceptions:
            if row.kind == "bank_detail_change" and row.resolved_at is None:
                row.resolved_at = task.completed_at
                row.resolved_by_id = user.id
                row.resolution = (
                    "Confirmed on the telephone." if body.confirmed else "Refused on the telephone."
                )
        if not body.confirmed:
            continue
        # The approvals were raised because the invoice was blocked. With the
        # block gone they are stale, and a stale signature is as good as a
        # block: the invoice sits there waiting for something nobody owes it.
        approvals.synchronise(session, invoice)
        if any(e.resolved_at is None for e in invoice.exceptions):
            continue
        if invoice.status == workflow.EXCEPTION:
            target = (
                workflow.AWAITING_APPROVAL
                if approvals.outstanding(session, invoice)
                else workflow.CHECKED
            )
            pipeline.move_to(session, invoice, target, note="The call-back was made.")
            freed.append(invoice_brief(invoice))
    session.flush()

    return {
        "call_back": call_back(task),
        "vendor": vendor_detail(session, task.vendor),
        "invoices_freed": freed,
    }
