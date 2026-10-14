"""Everything the screen talks to.

Two things are worth noticing about the shape of this file.

There is **no endpoint that takes SQL**, a capability's query text, a
customer identifier, or a role. The only thing a client sends is a
question in words and, optionally, a document to read. Everything that
decides what runs and over which rows is read from the catalogue and the
database on this side.

And there is **no endpoint that changes operational data**. The only
writes anywhere in this router are the question log, the access log and
a proposal's decision — a record of what was asked, what was read and
what a person decided. Orders, invoices, shipments and stock are read
only to this product, which is checked when the catalogue loads.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..domain import capabilities
from ..evaluation.runner import CRITERIA, run_evaluation
from ..models import (
    AccessLog,
    Customer,
    Document,
    EvaluationRun,
    Order,
    Proposal,
    Question,
    Supplier,
    User,
)
from ..security import get_current_user, require_role
from ..serializers import (
    access_row,
    answer_detail,
    capability_row,
    document_row,
    proposal_row,
    question_detail,
    question_row,
    reach_detail,
)
from ..services import answering, proposals as proposal_service
from ..services.permissions import reach_of

router = APIRouter(prefix="/api", tags=["operations"])


# ---------------------------------------------------------------------------
# Health and shape
# ---------------------------------------------------------------------------
@router.get("/health")
def health(session: Session = Depends(get_session)) -> dict[str, Any]:
    return {
        "status": "ok",
        "service": settings.app_name,
        "engine": settings.answer_engine,
        "capabilities": len(capabilities.CATALOGUE),
        "questions_asked": session.scalar(select(func.count(Question.id))) or 0,
        "storage_is_temporary": settings.storage_is_temporary,
        "warnings": settings.insecure_defaults,
    }


@router.get("/capabilities")
def catalogue(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """The whole list, query text included.

    Published deliberately. "It can only run queries a person wrote and
    reviewed" is the central claim of this product, and a claim nobody
    can inspect is a slogan.
    """
    return {
        "count": len(capabilities.CATALOGUE),
        "capabilities": [capability_row(c) for c in capabilities.CATALOGUE],
    }


# ---------------------------------------------------------------------------
# Asking
# ---------------------------------------------------------------------------
class Ask(BaseModel):
    question: str = Field(min_length=1, max_length=400)
    #: A document, email or message the question is about. Treated as
    #: data from an untrusted source wherever it goes.
    content: str = Field(default="", max_length=20_000)
    #: Or the reference of a document already held, which is read from
    #: the database rather than taken from the request.
    document_reference: str = Field(default="", max_length=40)


@router.post("/ask")
def ask(
    body: Ask,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    content = body.content
    if body.document_reference:
        document = session.scalar(
            select(Document).where(Document.reference == body.document_reference.strip())
        )
        if document is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"There is no document {body.document_reference}.",
            )
        content = f"{document.subject}\n\n{document.body}"

    reach = reach_of(session, user)
    answer = answering.ask(session, user, body.question, content=content)

    raised: list[Proposal] = []
    if answer.ok and answer.proposals and answer.question_id:
        question = session.get(Question, answer.question_id)
        raised = proposal_service.raise_from_answer(
            session, question, answer.proposals
        )

    body_out = answer_detail(answer, reach=reach)
    body_out["proposals"] = [proposal_row(p) for p in raised]
    return body_out


@router.get("/questions")
def history(
    limit: int = Query(default=30, ge=1, le=200),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """What this person asked. Not what anybody else asked."""
    rows = session.scalars(
        select(Question)
        .where(Question.asked_by_id == user.id)
        .order_by(Question.id.desc())
        .limit(limit)
    ).all()
    return {"questions": [question_row(q) for q in rows]}


@router.get("/questions/{question_id}")
def one_question(
    question_id: int,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    question = session.get(Question, question_id)
    if question is None or question.asked_by_id != user.id:
        # The same answer either way, so the identifier cannot be used to
        # find out what somebody else asked.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="There is no question here under this account.",
        )
    return question_detail(question)


# ---------------------------------------------------------------------------
# Proposals: suggested, decided by a person, never carried out
# ---------------------------------------------------------------------------
class Decision(BaseModel):
    approve: bool
    note: str = Field(default="", max_length=2000)


@router.get("/proposals")
def list_proposals(
    status_filter: str = Query(default="", alias="status"),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    query = select(Proposal).order_by(Proposal.id.desc()).limit(100)
    if status_filter:
        query = query.where(Proposal.status == status_filter)
    rows = session.scalars(query).all()
    return {
        "proposals": [proposal_row(p) for p in rows],
        "note": (
            "Approving one records a decision. Nothing in this system acts "
            "on it."
        ),
    }


@router.post("/proposals/{proposal_id}/decide")
def decide_proposal(
    proposal_id: int,
    body: Decision,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    proposal = session.get(Proposal, proposal_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No such proposal."
        )
    try:
        proposal_service.decide(
            session, proposal, user, approve=body.approve, note=body.note
        )
    except proposal_service.CannotDecide as refusal:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail=str(refusal)
        ) from refusal
    return proposal_row(proposal)


# ---------------------------------------------------------------------------
# Documents, including the one with instructions in it
# ---------------------------------------------------------------------------
@router.get("/documents")
def documents(
    _user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, Any]:
    rows = session.scalars(
        select(Document).order_by(Document.received_on.desc()).limit(limit)
    ).all()
    return {"documents": [document_row(d) for d in rows]}


# ---------------------------------------------------------------------------
# The access log: who read what, and what the filter did
# ---------------------------------------------------------------------------
@router.get("/access-log")
def access_log(
    limit: int = Query(default=50, ge=1, le=500),
    _user: User = Depends(require_role("manager")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    rows = session.execute(
        select(AccessLog, User.full_name)
        .join(User, User.id == AccessLog.user_id, isouter=True)
        .order_by(AccessLog.id.desc())
        .limit(limit)
    ).all()
    return {
        "entries": [access_row(log, who=who or "") for log, who in rows],
        "refused": sum(1 for log, _ in rows if not log.allowed),
    }


# ---------------------------------------------------------------------------
# The evaluation
# ---------------------------------------------------------------------------
@router.get("/evaluation/criteria")
def criteria(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"criteria": CRITERIA}


@router.post("/evaluation/run")
def run_the_evaluation(
    _user: User = Depends(require_role("manager")),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    results = run_evaluation(session)
    session.add(
        EvaluationRun(
            finished_at=dt.datetime.now(dt.timezone.utc),
            questions=results["answers"]["asked"],
            passed=results["passed"],
            results=results["criteria"],
            notes=results["statement"],
        )
    )
    session.flush()
    return results


@router.get("/evaluation/latest")
def latest_evaluation(
    _user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    run = session.scalar(select(EvaluationRun).order_by(EvaluationRun.id.desc()).limit(1))
    if run is None:
        return {"run": None, "criteria": CRITERIA}
    return {
        "run": {
            "id": run.id,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "questions": run.questions,
            "passed": run.passed,
            "criteria": run.results,
            "notes": run.notes,
        },
        "criteria": CRITERIA,
    }


# ---------------------------------------------------------------------------
# The demonstration data
# ---------------------------------------------------------------------------
@router.get("/demo/state")
def demo_state(session: Session = Depends(get_session)) -> dict[str, Any]:
    customers = session.scalar(select(func.count(Customer.id))) or 0
    return {
        "loaded": customers > 0,
        "customers": customers,
        "suppliers": session.scalar(select(func.count(Supplier.id))) or 0,
        "orders": session.scalar(select(func.count(Order.id))) or 0,
        "people": session.scalar(select(func.count(User.id))) or 0,
        "storage_is_temporary": settings.storage_is_temporary,
    }


@router.post("/demo/load")
def demo_load(
    customers: int = Body(default=200, embed=True, ge=20, le=400),
    orders: int = Body(default=1200, embed=True, ge=100, le=4000),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    """Build the business. Open, because there is nobody to sign in as yet."""
    from ..seed.generator import build_demo_data

    if session.scalar(select(func.count(Customer.id))):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="There is already data here. Clear it first if you want it rebuilt.",
        )
    counts = build_demo_data(session, customer_target=customers, order_target=orders)
    return {"loaded": True, "counts": counts}


@router.get("/demo/people")
def demo_people(session: Session = Depends(get_session)) -> dict[str, Any]:
    """Who you can sign in as, and what each of them can see.

    Shown on the sign-in screen, because the point of the demonstration
    is the difference between these accounts.
    """
    from ..seed.generator import DEMO_PASSWORD

    rows = session.scalars(select(User).order_by(User.id)).all()
    people = []
    for user in rows:
        reach = reach_of(session, user)
        people.append(
            {
                **{"email": user.email, "name": user.full_name, "role": user.role},
                "reach": reach_detail(reach),
            }
        )
    return {"people": people, "password": DEMO_PASSWORD}
