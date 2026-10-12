"""Loading the data and running the batch, from the screen.

This is the one place the product talks about itself as a demonstration. It
exists because a product owner opening the link should not have to run a
command to see anything.
"""

from __future__ import annotations

import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..models import (
    AccountingPeriod,
    Approval,
    AuditEntry,
    CallBackTask,
    Document,
    Entity,
    EvaluationRun,
    Exception_,
    ExchangeRate,
    GoodsReceipt,
    GoodsReceiptLine,
    Invoice,
    InvoiceEvent,
    InvoiceLine,
    LedgerBill,
    Posting,
    PurchaseOrder,
    PurchaseOrderLine,
    User,
    Vendor,
    VendorBankAccount,
)
from ..security import require_role
from ..seed import generator
from ..seed.invoices import build_batch
from ..serializers import dashboard, invoice_brief
from ..services import pipeline

router = APIRouter(prefix="/api/demo", tags=["demonstration"])

#: Child rows first, so nothing is orphaned on the way out.
_IN_ORDER = [
    InvoiceEvent,
    InvoiceLine,
    Exception_,
    Approval,
    Posting,
    LedgerBill,
    CallBackTask,
    Invoice,
    Document,
    GoodsReceiptLine,
    GoodsReceipt,
    PurchaseOrderLine,
    PurchaseOrder,
    VendorBankAccount,
    Vendor,
    ExchangeRate,
    AccountingPeriod,
    AuditEntry,
    EvaluationRun,
    User,
    Entity,
]


@router.get("/state")
def state(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Is there anything to look at yet? Open, because the first screen asks
    this before anybody has signed in."""
    vendors = session.scalar(select(func.count(Vendor.id))) or 0
    invoices = session.scalar(select(func.count(Invoice.id))) or 0
    return {
        "loaded": vendors > 0,
        "batch_run": invoices > 0,
        "vendors": vendors,
        "invoices": invoices,
        "reading_engine": settings.reading_engine,
        # On serverless hosting the database lives in the function's own
        # scratch space, so it goes away when the function does. Saying so is
        # better than letting somebody think they lost their work.
        "storage_is_temporary": settings.storage_is_temporary,
    }


class LoadRequest(BaseModel):
    size: str = "full"


@router.post("/load")
def load(
    body: LoadRequest,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("administrator")),
) -> dict[str, Any]:
    small = body.size == "small"
    started = time.perf_counter()
    for model in _IN_ORDER:
        session.execute(delete(model))
    session.flush()
    counts = generator.build_demo_data(
        session,
        vendor_target=40 if small else 140,
        order_target=60 if small else 220,
    )
    return {
        "seconds": round(time.perf_counter() - started, 2),
        "counts": counts,
        "state": state(session),
    }


@router.get("/batch")
def describe_batch(
    session: Session = Depends(get_session), _user: User = Depends(require_role("clerk"))
) -> dict[str, Any]:
    """What is in the batch and what each document is there to prove."""
    try:
        documents = build_batch(session)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return {
        "total": len(documents),
        "items": [
            {
                "key": d.key,
                "title": d.title,
                "what_it_tests": d.what_it_tests,
                "filename": d.filename,
                "expect": d.expect,
                "pages": max(d.text.lower().count("page ") or 1, 1),
            }
            for d in documents
        ],
    }


@router.post("/run-batch")
def run_batch(
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("clerk")),
    only: str | None = Query(None, description="One document's key, instead of all of them"),
) -> dict[str, Any]:
    """Put the batch through the same pipeline the upload screen uses."""
    try:
        documents = build_batch(session)
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    if only:
        documents = [d for d in documents if d.key == only]
        if not documents:
            raise HTTPException(status_code=404, detail="There is no such document in the batch.")

    started = time.perf_counter()
    processed: list[dict[str, Any]] = []
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
        row: dict[str, Any] = {"key": document.key, "title": document.title}
        try:
            pipeline.run(session, invoice)
        except pipeline.PipelineError as error:
            row["error"] = str(error)
        row["invoice"] = invoice_brief(invoice)
        row["what_it_tests"] = document.what_it_tests
        row["expect"] = document.expect
        processed.append(row)

    return {
        "seconds": round(time.perf_counter() - started, 2),
        "processed": len(processed),
        "untouched": sum(1 for r in processed if r["invoice"]["posted_untouched"]),
        "items": processed,
        "dashboard": dashboard(session),
    }
