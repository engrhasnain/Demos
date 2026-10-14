"""What the staff see: the queue, the returns to approve, the access log."""

from __future__ import annotations

import datetime as dt
import time
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..evaluation.runner import CRITERIA, run_evaluation
from ..models import (
    AccessLog,
    Conversation,
    Customer,
    ReturnRequest,
    Ticket,
    User,
    Visit,
)
from ..security import get_current_user, oauth2_scheme, require_role
from ..seed import generator
from ..serializers import (
    access_out,
    conversation_brief,
    conversation_detail,
    dashboard,
    return_out,
    ticket_out,
    visit_out,
)

router = APIRouter(prefix="/api", tags=["desk"])


@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, Any]:
    try:
        session.execute(select(1))
        database = "ready"
    except Exception as error:  # pragma: no cover
        database = f"unavailable: {type(error).__name__}"
    return {
        "service": settings.app_name,
        "environment": settings.environment,
        "database": database,
        "engine": settings.reply_engine,
        "line": "configured" if settings.line_configured else "not configured",
        "serverless": settings.is_serverless,
    }


@router.get("/dashboard")
def read_dashboard(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return dashboard(session, dt.datetime.now(dt.timezone.utc))


@router.get("/conversations")
def list_conversations(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    status_code: str | None = Query(None, alias="status"),
    channel: str | None = None,
    limit: int = Query(40, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    query = select(Conversation)
    if status_code:
        query = query.where(Conversation.status == status_code)
    if channel:
        query = query.where(Conversation.channel == channel)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(
        query.order_by(Conversation.id.desc()).limit(limit).offset(offset)
    )
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [conversation_brief(row) for row in rows],
    }


@router.get("/conversations/{reference}")
def read_conversation(
    reference: str,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    conversation = session.scalar(
        select(Conversation).where(Conversation.reference == reference)
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="No such conversation.")
    return conversation_detail(conversation, with_turns=True)


@router.get("/tickets")
def list_tickets(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    open_only: bool = True,
) -> dict[str, Any]:
    query = select(Ticket).order_by(Ticket.reply_by)
    if open_only:
        query = query.where(Ticket.status == "open")
    rows = list(session.scalars(query.limit(200)))
    return {"total": len(rows), "items": [ticket_out(row) for row in rows]}


# ---------------------------------------------------------------------------
# Returns, which only a person may approve
# ---------------------------------------------------------------------------
@router.get("/returns")
def list_returns(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    status_code: str | None = Query(None, alias="status"),
) -> dict[str, Any]:
    query = select(ReturnRequest).order_by(ReturnRequest.id.desc())
    if status_code:
        query = query.where(ReturnRequest.status == status_code)
    rows = list(session.scalars(query.limit(200)))
    return {"total": len(rows), "items": [return_out(row) for row in rows]}


class Decision(BaseModel):
    approved: bool
    note: str = Field("", max_length=2000)


@router.post("/returns/{reference}")
def decide_return(
    reference: str,
    body: Decision,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("agent")),
) -> dict[str, Any]:
    """A person decides every return. The desk only ever proposes one."""
    request = session.scalar(
        select(ReturnRequest).where(ReturnRequest.reference == reference)
    )
    if request is None:
        raise HTTPException(status_code=404, detail="No such return.")
    if request.status != "proposed":
        raise HTTPException(
            status_code=409, detail=f"That one was already {request.status}."
        )
    request.status = "approved" if body.approved else "refused"
    request.decided_by_id = user.id
    request.decided_at = dt.datetime.now(dt.timezone.utc)
    request.decision_note = body.note
    session.flush()
    return return_out(request)


@router.get("/visits")
def list_visits(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    rows = list(
        session.scalars(select(Visit).order_by(Visit.starts_at).limit(200))
    )
    return {"total": len(rows), "items": [visit_out(row) for row in rows]}


@router.get("/access-log")
def read_access_log(
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("supervisor")),
    refused_only: bool = False,
    limit: int = Query(100, ge=1, le=500),
) -> dict[str, Any]:
    """Every reach for customer data. The refused ones are the interesting ones."""
    query = select(AccessLog).order_by(AccessLog.id.desc())
    if refused_only:
        query = query.where(AccessLog.allowed.is_(False))
    rows = list(session.scalars(query.limit(limit)))
    return {"total": len(rows), "items": [access_out(row) for row in rows]}


# ---------------------------------------------------------------------------
# The demonstration data and the evidence
# ---------------------------------------------------------------------------
@router.get("/demo/state")
def demo_state(session: Session = Depends(get_session)) -> dict[str, Any]:
    customers = session.scalar(select(func.count(Customer.id))) or 0
    return {
        "loaded": customers > 0,
        "customers": customers,
        "engine": settings.reply_engine,
        "storage_is_temporary": settings.storage_is_temporary,
        "storage_warning": settings.storage_warning,
    }


class LoadRequest(BaseModel):
    size: str = "full"


SIZES: dict[str, tuple[int, int]] = {
    "full": (1200, 3600),
    "small": (300, 900),
}


def _database_is_empty(session: Session) -> bool:
    """No staff and no company yet: a brand new database."""
    return not session.scalar(select(func.count(User.id))) and not session.scalar(
        select(func.count(Customer.id))
    )


def load_straight_through(session: Session, customer_target: int, order_target: int) -> dict[str, int]:
    """The whole load inside one session, for serverless and for start-up."""
    counts = generator.build_demo_data(
        session, customer_target=customer_target, order_target=order_target
    )
    counts.update(generator.build_sample_conversations(session))
    return counts


def administrator_unless_first_run(
    token: str | None = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User | None:
    """An administrator, except on a brand new database.

    The demonstration accounts are created by the load itself, so on an empty
    database nobody can sign in to start it and the guided first run could
    never be reached. In that one state the load is open to anyone. As soon
    as an account or any of the company exists it needs an administrator
    again, so this cannot be used to wipe or replace data that is already
    there.
    """
    if _database_is_empty(session):
        return None
    return require_role("administrator")(get_current_user(token, session))


@router.post("/demo/load")
def load_demo(
    body: LoadRequest,
    session: Session = Depends(get_session),
    _user: User | None = Depends(administrator_unless_first_run),
) -> dict[str, Any]:
    customers, orders = SIZES.get(body.size, SIZES["full"])
    started = time.perf_counter()
    counts = load_straight_through(session, customers, orders)
    return {
        "seconds": round(time.perf_counter() - started, 2),
        "counts": counts,
        "state": demo_state(session),
    }


@router.get("/evidence/criteria")
def criteria(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"criteria": CRITERIA}


class EvidenceRequest(BaseModel):
    conversations: int = Field(120, ge=20, le=600)


@router.post("/evidence/run")
def run_evidence(
    body: EvidenceRequest,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("supervisor")),
) -> dict[str, Any]:
    count = body.conversations
    if settings.is_serverless:
        count = min(count, 120)
    return run_evaluation(session, conversations=count)
