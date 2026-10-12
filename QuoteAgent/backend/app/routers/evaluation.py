"""Running the acceptance criteria and reading the results."""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db import get_session, session_scope
from ..evaluation.runner import run_evaluation
from ..models import EvaluationRun, User
from ..security import get_current_user

router = APIRouter(prefix="/api/evaluation", tags=["Acceptance criteria"])


class RunState:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.running = False
        self.stage = ""
        self.done = 0
        self.total = 1
        self.error = ""
        self.result: dict[str, Any] | None = None

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {
                "running": self.running,
                "stage": self.stage,
                "done": self.done,
                "total": self.total,
                "percent": round(self.done / self.total * 100, 1) if self.total else 0.0,
                "error": self.error,
                "result": self.result,
            }


STATE = RunState()


def _progress(stage: str, done: int, total: int) -> None:
    with STATE.lock:
        STATE.stage = stage
        STATE.done = done
        STATE.total = max(total, 1)


def _run(request_count: int, lines_per_request: int, revision_pairs: int) -> None:
    try:
        with session_scope() as session:
            result = run_evaluation(
                session,
                request_count=request_count,
                lines_per_request=lines_per_request,
                revision_pairs=revision_pairs,
                progress=_progress,
            )
        with STATE.lock:
            STATE.result = result
    except Exception as exc:  # pragma: no cover - surfaced on the screen
        with STATE.lock:
            STATE.error = f"{type(exc).__name__}: {exc}"
    finally:
        with STATE.lock:
            STATE.running = False


class RunRequest(BaseModel):
    request_count: int = Field(default=60, ge=5, le=400)
    lines_per_request: int = Field(default=25, ge=5, le=60)
    revision_pairs: int = Field(default=30, ge=1, le=100)


@router.post("/run")
def start_run(
    payload: RunRequest | None = None, _user: User = Depends(get_current_user)
) -> dict[str, Any]:
    payload = payload or RunRequest()
    with STATE.lock:
        if STATE.running:
            raise HTTPException(status_code=409, detail="An evaluation is already running.")
        STATE.running = True
        STATE.error = ""
        STATE.result = None
        STATE.stage = "Starting"
        STATE.done = 0
        STATE.total = 1

    threading.Thread(
        target=_run,
        args=(payload.request_count, payload.lines_per_request, payload.revision_pairs),
        daemon=True,
    ).start()
    return {
        "started": True,
        "sample": (
            f"{payload.request_count} requests of {payload.lines_per_request} lines "
            f"({payload.request_count * payload.lines_per_request} lines) and "
            f"{payload.revision_pairs} revision pairs"
        ),
    }


@router.get("/progress")
def progress(_user: User = Depends(get_current_user)) -> dict[str, Any]:
    return STATE.snapshot()


@router.post("/run-now")
def run_now(
    payload: RunRequest | None = None,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Run straight through and return the report. Used by tests and scripts."""
    payload = payload or RunRequest()
    return run_evaluation(
        session,
        request_count=payload.request_count,
        lines_per_request=payload.lines_per_request,
        revision_pairs=payload.revision_pairs,
    )


@router.get("/runs")
def list_runs(
    limit: int = 10,
    session: Session = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict[str, Any]:
    runs = list(
        session.scalars(
            select(EvaluationRun).order_by(EvaluationRun.id.desc()).limit(min(limit, 50))
        )
    )
    return {
        "runs": [
            {
                "id": run.id,
                "started_at": run.started_at.isoformat(),
                "finished_at": run.finished_at.isoformat() if run.finished_at else None,
                "engine": run.engine,
                "sample_size": run.sample_size,
                "passed": run.passed,
                "criteria": run.results,
                "notes": run.notes,
            }
            for run in runs
        ],
        "pass_bars": [
            {
                "key": "line_matching",
                "name": "Line matching",
                "bar": "92 per cent or more correct at the first attempt",
                "how": "A labelled test set graded against the expected part for each line.",
            },
            {
                "key": "ambiguity_handling",
                "name": "Ambiguity handling",
                "bar": (
                    "95 per cent or more of genuinely unclear lines flagged, and no "
                    "more than 3 per cent of clear lines wrongly flagged"
                ),
                "how": "Lines built with an attribute deliberately removed or contradicted.",
            },
            {
                "key": "pricing_integrity",
                "name": "Pricing integrity",
                "bar": "every price on a quote equals the pricing engine's own output",
                "how": "A fingerprint of every figure, re-checked by re-running the engine.",
            },
            {
                "key": "revisions",
                "name": "Revisions",
                "bar": "every change between two versions detected",
                "how": "Pairs of requests with a known number of changes.",
            },
            {
                "key": "speed",
                "name": "Speed",
                "bar": "a draft ready within 15 minutes at the ninetieth percentile",
                "how": "Timed on the agent's own working time, excluding waiting on people.",
            },
            {
                "key": "edits",
                "name": "Edits by the salesperson",
                "bar": "a median of two lines or fewer changed between draft and sent",
                "how": "Needs a pilot with real salespeople. Reported as not measured.",
            },
        ],
    }
