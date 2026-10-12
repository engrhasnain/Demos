"""Everything that happens to an invoice."""

from __future__ import annotations

import datetime as dt
from typing import Any, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import Approval, Exception_, Invoice, User
from ..security import get_current_user, require_role
from ..serializers import invoice_brief, invoice_detail
from ..services import approvals, audit, pipeline, posting, workflow

router = APIRouter(prefix="/api/invoices", tags=["invoices"])

MAX_UPLOAD_BYTES = 8 * 1024 * 1024


def _get(session: Session, invoice_id: int) -> Invoice:
    invoice = session.get(Invoice, invoice_id)
    if invoice is None:
        raise HTTPException(status_code=404, detail="There is no invoice with that number here.")
    return invoice


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
@router.get("")
def list_invoices(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    status_code: str | None = Query(None, alias="status"),
    needs_a_person: bool | None = None,
    vendor_id: int | None = None,
    kind: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    query = select(Invoice)
    if status_code:
        query = query.where(Invoice.status == status_code)
    if needs_a_person is True:
        query = query.where(Invoice.status.in_(sorted(workflow.NEEDS_A_PERSON)))
    elif needs_a_person is False:
        query = query.where(Invoice.status.notin_(sorted(workflow.NEEDS_A_PERSON)))
    if vendor_id:
        query = query.where(Invoice.vendor_id == vendor_id)
    if kind:
        query = query.where(Invoice.kind == kind)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            or_(
                Invoice.reference.ilike(pattern),
                Invoice.invoice_number_read.ilike(pattern),
                Invoice.vendor_name_read.ilike(pattern),
                Invoice.purchase_order_number_read.ilike(pattern),
            )
        )

    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(query.order_by(Invoice.id.desc()).limit(limit).offset(offset))
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [invoice_brief(row) for row in rows],
    }


@router.get("/queue")
def queue(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    """What is on somebody's desk, worst first.

    A blocked invoice is money that cannot move. It goes above an invoice that
    is merely waiting for a signature, however large the signature.
    """
    rank = {"block": 0, "hold": 1, "note": 2}
    rows = session.scalars(
        select(Invoice)
        .where(Invoice.status.in_(sorted(workflow.NEEDS_A_PERSON)))
        .order_by(Invoice.id.desc())
    )
    items: list[dict[str, Any]] = []
    for invoice in rows:
        open_rows = [e for e in invoice.exceptions if e.resolved_at is None]
        worst = min((rank.get(e.severity, 3) for e in open_rows), default=3)
        brief = invoice_brief(invoice)
        brief["severity_rank"] = worst
        items.append(brief)
    items.sort(key=lambda row: (row["severity_rank"], -float(row["amount_in_base"] or 0)))
    return {"total": len(items), "items": items}


@router.get("/{invoice_id}")
def read_invoice(
    invoice_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    return invoice_detail(session, _get(session, invoice_id))


@router.get("/{invoice_id}/document")
def read_document(
    invoice_id: int,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """The document as it arrived, so a person can check the screen against it."""
    invoice = _get(session, invoice_id)
    if invoice.document is None:
        raise HTTPException(status_code=404, detail="This invoice has no document attached.")
    return {
        "filename": invoice.document.filename,
        "content_type": invoice.document.content_type,
        "page_count": invoice.document.page_count,
        "received_from": invoice.document.received_from,
        "barcode_payload": invoice.document.barcode_payload,
        "text": invoice.document.text,
    }


# ---------------------------------------------------------------------------
# Taking documents in
# ---------------------------------------------------------------------------
@router.post("/upload", status_code=status.HTTP_201_CREATED)
async def upload(
    session: Session = Depends(get_session),
    user: User = Depends(require_role("clerk")),
    file: UploadFile = File(...),
    received_from: str = Form(""),
    kind: str = Form("bill"),
    barcode_payload: str = Form(""),
) -> dict[str, Any]:
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="That file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"That file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.",
        )

    text = content.decode("utf-8", errors="replace")
    invoice, _created = pipeline.receive(
        session,
        filename=file.filename or "upload.txt",
        content=content,
        content_type=file.content_type or "application/octet-stream",
        text=text,
        barcode_payload=barcode_payload,
        received_from=received_from,
        kind=kind if kind in {"bill", "credit_note"} else "bill",
    )
    audit.record_event(
        session,
        invoice_id=invoice.id,
        kind="uploaded",
        summary=f"{file.filename} added by {user.full_name}.",
        actor_type="person",
        actor_name=user.full_name,
    )
    try:
        pipeline.run(session, invoice)
    except pipeline.PipelineError as error:
        # The invoice still exists and still shows what went wrong. Losing the
        # document because the reading failed would be the worst outcome.
        audit.record_event(
            session,
            invoice_id=invoice.id,
            kind="failed",
            summary=str(error),
        )
    return invoice_detail(session, invoice)


# ---------------------------------------------------------------------------
# Working on one
# ---------------------------------------------------------------------------
@router.post("/{invoice_id}/recheck")
def recheck(
    invoice_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("clerk")),
) -> dict[str, Any]:
    """Read and check it again, after a person changed something it depends on."""
    invoice = _get(session, invoice_id)
    if invoice.status in workflow.TERMINAL:
        raise HTTPException(
            status_code=409,
            detail=f"This invoice is {workflow.LABELS[invoice.status].lower()} and cannot change.",
        )
    try:
        pipeline.read(session, invoice)
        pipeline.check(session, invoice)
    except pipeline.PipelineError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    audit.record_event(
        session,
        invoice_id=invoice.id,
        kind="rechecked",
        summary=f"Checked again by {user.full_name}.",
        actor_type="person",
        actor_name=user.full_name,
    )
    return invoice_detail(session, invoice)


class ResolveException(BaseModel):
    resolution: str = Field("", max_length=255)


@router.post("/{invoice_id}/exceptions/{exception_id}/resolve")
def resolve_exception(
    invoice_id: int,
    exception_id: int,
    body: ResolveException,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("accountant")),
) -> dict[str, Any]:
    invoice = _get(session, invoice_id)
    row = session.get(Exception_, exception_id)
    if row is None or row.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="There is no such exception on this invoice.")
    if row.resolved_at is not None:
        raise HTTPException(status_code=409, detail="That one has already been dealt with.")
    if row.kind == "bank_detail_change":
        raise HTTPException(
            status_code=409,
            detail=(
                "A change of bank details is cleared by making the telephone call, "
                "not by closing the exception."
            ),
        )

    row.resolved_at = dt.datetime.now(dt.timezone.utc)
    row.resolved_by_id = user.id
    row.resolution = body.resolution
    invoice.touched_by_a_person = True
    session.flush()

    audit.record_event(
        session,
        invoice_id=invoice.id,
        kind="exception_resolved",
        summary=f"{workflow.label_of(row.kind)} cleared by {user.full_name}.",
        actor_type="person",
        actor_name=user.full_name,
        detail={"resolution": body.resolution},
    )

    still_open = [e for e in invoice.exceptions if e.resolved_at is None]
    if not still_open and invoice.status == workflow.EXCEPTION:
        pipeline.move_to(session, invoice, workflow.CHECKED, note="Everything has been dealt with.")
        approvals.synchronise(session, invoice)
        if approvals.outstanding(session, invoice):
            pipeline.move_to(session, invoice, workflow.AWAITING_APPROVAL)
    return invoice_detail(session, invoice)


class Decision(BaseModel):
    approved: bool
    comment: str = Field("", max_length=2000)


@router.post("/{invoice_id}/approvals/{approval_id}")
def decide_approval(
    invoice_id: int,
    approval_id: int,
    body: Decision,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("accountant")),
) -> dict[str, Any]:
    invoice = _get(session, invoice_id)
    approval = session.get(Approval, approval_id)
    if approval is None or approval.invoice_id != invoice.id:
        raise HTTPException(status_code=404, detail="There is no such approval on this invoice.")
    try:
        approvals.decide(session, approval, user, approved=body.approved, comment=body.comment)
    except PermissionError as error:
        raise HTTPException(status_code=403, detail=str(error)) from error

    invoice.touched_by_a_person = True
    audit.record_event(
        session,
        invoice_id=invoice.id,
        kind="approval_decided",
        summary=(
            f"{approval.title} {'approved' if body.approved else 'refused'} by {user.full_name}."
        ),
        actor_type="person",
        actor_name=user.full_name,
        detail={"comment": body.comment},
    )

    if not body.approved:
        pipeline.move_to(session, invoice, workflow.REJECTED, note=body.comment or "Refused.")
    elif not approvals.outstanding(session, invoice):
        pipeline.move_to(session, invoice, workflow.APPROVED, note="Every signature is in.")
    session.flush()
    return invoice_detail(session, invoice)


@router.post("/{invoice_id}/post")
def post_invoice(
    invoice_id: int,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("accountant")),
) -> dict[str, Any]:
    invoice = _get(session, invoice_id)
    try:
        pipeline.post_to_ledger(session, invoice, by=user)
    except posting.LedgerUnavailable as error:
        # 503, not 500. The caller may safely try again: the key makes the
        # second attempt land on the same bill.
        raise HTTPException(status_code=503, detail=str(error)) from error
    except pipeline.PipelineError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return invoice_detail(session, invoice)


class Reject(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


@router.post("/{invoice_id}/reject")
def reject_invoice(
    invoice_id: int,
    body: Reject,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("accountant")),
) -> dict[str, Any]:
    invoice = _get(session, invoice_id)
    try:
        pipeline.move_to(session, invoice, workflow.REJECTED, note=body.reason)
    except workflow.IllegalTransition as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    invoice.touched_by_a_person = True
    audit.record_event(
        session,
        invoice_id=invoice.id,
        kind="rejected",
        summary=f"Sent back by {user.full_name}: {body.reason}",
        actor_type="person",
        actor_name=user.full_name,
    )
    return invoice_detail(session, invoice)


class ForceFailure(BaseModel):
    """Only for the demonstration: drop the connection after the ledger writes."""

    mode: Literal["after_ledger_write"] = "after_ledger_write"


@router.post("/{invoice_id}/post-with-a-dropped-connection")
def post_with_a_dropped_connection(
    invoice_id: int,
    _body: ForceFailure,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("accountant")),
) -> dict[str, Any]:
    """Prove the retry is safe, on a real invoice, in front of the room.

    The ledger takes the bill and then the connection dies before we hear
    about it. Posting again afterwards must not produce a second bill.
    """
    invoice = _get(session, invoice_id)
    try:
        pipeline.post_to_ledger(session, invoice, by=user, fail_after_ledger_write=True)
    except posting.LedgerUnavailable as error:
        return {
            "dropped": True,
            "message": str(error),
            "bills_in_the_ledger": len(posting.bills_for(session, invoice)),
            "invoice": invoice_detail(session, invoice),
        }
    except pipeline.PipelineError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "dropped": False,
        "message": "It went through before the connection dropped.",
        "bills_in_the_ledger": len(posting.bills_for(session, invoice)),
        "invoice": invoice_detail(session, invoice),
    }
