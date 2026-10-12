"""The acceptance criteria, over HTTP."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_session
from ..evaluation.runner import CRITERIA, last_run, run_evaluation
from ..models import User
from ..security import get_current_user, require_role

router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.get("/criteria")
def criteria(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    """What is measured and what the bar is, without running anything."""
    return {"criteria": CRITERIA}


@router.get("/last")
def read_last(
    session: Session = Depends(get_session), _user: User = Depends(get_current_user)
) -> dict[str, Any] | None:
    return last_run(session)


class RunRequest(BaseModel):
    clean_count: int = Field(120, ge=10, le=400)
    duplicate_count: int = Field(40, ge=0, le=200)
    bank_change_count: int = Field(20, ge=0, le=100)
    retry_count: int = Field(50, ge=0, le=200)


@router.post("/run")
def run(
    body: RunRequest,
    session: Session = Depends(get_session),
    _user: User = Depends(require_role("controller")),
) -> dict[str, Any]:
    """Measure the product, now, on this data.

    On serverless hosting the function has a short life, so the sample is
    trimmed to what fits rather than being cut off halfway.
    """
    clean = body.clean_count
    retries = body.retry_count
    if settings.is_serverless:
        clean = min(clean, 60)
        retries = min(retries, 20)
    try:
        return run_evaluation(
            session,
            clean_count=clean,
            duplicate_count=body.duplicate_count,
            bank_change_count=body.bank_change_count,
            retry_count=retries,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
