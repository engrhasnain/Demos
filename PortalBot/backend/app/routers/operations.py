"""Running the bot, and watching what it did."""

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
from ..models import Challenge, Run, ScriptFlag, Shipment, Step, User
from ..security import get_current_user, oauth2_scheme, require_role
from ..seed import generator
from ..seed.generator import Builder
from ..serializers import (
    challenge_out,
    dashboard,
    flag_out,
    run_out,
    shipment_brief,
    shipment_detail,
)
from ..services import runner
from ..systems.carrier import Behaviour, CarrierPortal

router = APIRouter(prefix="/api", tags=["operations"])

#: The portal and the business system live for the life of the process,
#: which is what makes "the carrier remembers what we booked" true across
#: runs. On serverless this resets with the function, and the state screen
#: says so rather than pretending otherwise.
_CARRIER: CarrierPortal | None = None
_BEHAVIOUR = Behaviour(tracking_delay_seconds=0.0)


def carrier() -> CarrierPortal:
    global _CARRIER
    if _CARRIER is None:
        _CARRIER = CarrierPortal(behaviour=_BEHAVIOUR)
    return _CARRIER


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
        "carrier": settings.carrier_name,
        "portal_version": _BEHAVIOUR.version,
        "serverless": settings.is_serverless,
    }


@router.get("/dashboard")
def read_dashboard(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    return dashboard(session)


# ---------------------------------------------------------------------------
# Running it
# ---------------------------------------------------------------------------
class RunRequest(BaseModel):
    limit: int | None = Field(None, ge=1, le=2000)
    #: The demonstration's kill switch: stop after this many, as though the
    #: process had gone away.
    stop_after: int | None = Field(None, ge=0, le=2000)


@router.post("/run")
def start_run(
    body: RunRequest,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("clerk")),
) -> dict[str, Any]:
    legacy = Builder.legacy_for(session)
    report = runner.run_once(
        session,
        carrier(),
        legacy,
        limit=body.limit,
        stop_after=body.stop_after,
    )
    return {
        "run": run_out(report.run),
        "halted": report.halted,
        "halt_reason": report.halt_reason,
        "drift": report.drift or None,
        "completed": report.completed,
        "exceptions": report.exceptions,
        "already_done": report.already_done,
    }


@router.get("/runs")
def list_runs(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    rows = list(session.scalars(select(Run).order_by(Run.id.desc()).limit(50)))
    return {"total": len(rows), "items": [run_out(row) for row in rows]}


# ---------------------------------------------------------------------------
# The shipments
# ---------------------------------------------------------------------------
@router.get("/shipments")
def list_shipments(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    state: str | None = None,
    exception_kind: str | None = None,
    search: str | None = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    query = select(Shipment)
    if state:
        query = query.where(Shipment.state == state)
    if exception_kind:
        query = query.where(Shipment.exception_kind == exception_kind)
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(
            Shipment.reference.ilike(pattern)
            | Shipment.order_number.ilike(pattern)
            | Shipment.customer_name.ilike(pattern)
        )
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(query.order_by(Shipment.id).limit(limit).offset(offset))
    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "items": [shipment_brief(row) for row in rows],
    }


@router.get("/shipments/{reference}")
def read_shipment(
    reference: str,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """One shipment with every step, which is the replayable trace."""
    shipment = session.scalar(
        select(Shipment).where(Shipment.reference == reference)
    )
    if shipment is None:
        raise HTTPException(status_code=404, detail="No such shipment.")
    return shipment_detail(shipment)


# ---------------------------------------------------------------------------
# One-time codes
# ---------------------------------------------------------------------------
@router.get("/challenges")
def list_challenges(
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
    waiting_only: bool = True,
) -> dict[str, Any]:
    query = select(Challenge).order_by(Challenge.id.desc())
    if waiting_only:
        query = query.where(Challenge.status == "waiting")
    rows = list(session.scalars(query.limit(100)))
    return {"total": len(rows), "items": [challenge_out(row) for row in rows]}


class Code(BaseModel):
    code: str = Field(min_length=4, max_length=12)


@router.post("/challenges/{reference}")
def answer_challenge(
    reference: str,
    body: Code,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("clerk")),
) -> dict[str, Any]:
    """A clerk supplies the code. The bot never produces one."""
    challenge = session.scalar(
        select(Challenge).where(Challenge.reference == reference)
    )
    if challenge is None:
        raise HTTPException(status_code=404, detail="No such challenge.")
    if challenge.status != "waiting":
        raise HTTPException(
            status_code=409, detail=f"That one was already {challenge.status}."
        )

    accepted = carrier().answer_challenge(challenge.external_id, body.code)
    challenge.status = "answered" if accepted else "refused"
    challenge.answered_at = dt.datetime.now(dt.timezone.utc)
    challenge.note = (
        f"Supplied by {user.full_name}."
        if accepted
        else "The portal did not accept that code."
    )
    if accepted and challenge.shipment is not None:
        challenge.shipment.state = "pending"
        challenge.shipment.exception_kind = ""
    session.flush()
    return challenge_out(challenge)


# ---------------------------------------------------------------------------
# The portal moving
# ---------------------------------------------------------------------------
@router.get("/flags")
def list_flags(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    rows = list(session.scalars(select(ScriptFlag).order_by(ScriptFlag.id.desc()).limit(50)))
    return {"total": len(rows), "items": [flag_out(row) for row in rows]}


class Acknowledge(BaseModel):
    note: str = Field("", max_length=2000)


@router.post("/flags/{flag_id}")
def acknowledge_flag(
    flag_id: int,
    body: Acknowledge,
    session: Session = Depends(get_session),
    user: User = Depends(require_role("developer")),
) -> dict[str, Any]:
    """A developer acknowledges it. Nothing here rewrites a script."""
    flag = session.get(ScriptFlag, flag_id)
    if flag is None:
        raise HTTPException(status_code=404, detail="No such flag.")
    flag.status = "acknowledged"
    flag.acknowledged_by_id = user.id
    flag.note = body.note
    session.flush()
    return flag_out(flag)


class PortalRelease(BaseModel):
    """The demonstration's lever: ship a new version of the portal."""

    version: str = Field("v2", pattern="^v[12]$")


@router.post("/portal/release")
def release_portal(
    body: PortalRelease, _user: User = Depends(require_role("developer"))
) -> dict[str, Any]:
    """Change the booking form under the script, as a real carrier would."""
    _BEHAVIOUR.version = body.version
    global _CARRIER
    if _CARRIER is not None:
        _CARRIER.behaviour = _BEHAVIOUR
    return {"version": _BEHAVIOUR.version, "fields": sorted(carrier().fields.values())}


# ---------------------------------------------------------------------------
# The demonstration data and the evidence
# ---------------------------------------------------------------------------
@router.get("/demo/state")
def demo_state(session: Session = Depends(get_session)) -> dict[str, Any]:
    shipments = session.scalar(select(func.count(Shipment.id))) or 0
    return {
        "loaded": shipments > 0,
        "shipments": shipments,
        "storage_is_temporary": settings.storage_is_temporary,
    }


def _database_is_empty(session: Session) -> bool:
    return not session.scalar(select(func.count(Shipment.id)))


def administrator_unless_first_run(
    token: str | None = Depends(oauth2_scheme),
    session: Session = Depends(get_session),
) -> User | None:
    """An administrator, except on a brand new database.

    The demonstration accounts are created by the load itself, so on an empty
    database nobody can sign in to start it and the first run could never be
    reached. In that one state the load is open to anyone. As soon as any
    shipment exists it needs an administrator again, so this cannot be used
    to wipe or replace data that is already there.
    """
    if _database_is_empty(session):
        return None
    return require_role("administrator")(get_current_user(token, session))


class LoadRequest(BaseModel):
    shipments: int = Field(180, ge=10, le=2000)


@router.post("/demo/load")
def load_demo(
    body: LoadRequest,
    session: Session = Depends(get_session),
    _user: User | None = Depends(administrator_unless_first_run),
) -> dict[str, Any]:
    global _CARRIER
    _CARRIER = None  # a new day, a fresh portal
    _BEHAVIOUR.version = "v1"
    started = time.perf_counter()
    counts = generator.build_demo_data(session, shipment_target=body.shipments)
    return {
        "seconds": round(time.perf_counter() - started, 2),
        "counts": counts,
        "state": demo_state(session),
    }


@router.get("/evidence/criteria")
def criteria(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return {"criteria": CRITERIA}


class EvidenceRequest(BaseModel):
    shipments: int = Field(180, ge=20, le=600)


@router.post("/evidence/run")
def run_evidence(
    body: EvidenceRequest,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("operations_lead")),
) -> dict[str, Any]:
    count = body.shipments
    if settings.is_serverless:
        count = min(count, 120)
    return run_evaluation(session, shipments=count)
