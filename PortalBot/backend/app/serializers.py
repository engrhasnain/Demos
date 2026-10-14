"""Rows into the shapes the screens draw."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .models import Challenge, Run, ScriptFlag, Shipment, Step, User
from .security import ROLE_LABELS
from .services.bot import EXCEPTION_WORDS

STATE_WORDS: dict[str, str] = {
    "pending": "Not started",
    "booked": "Booked, not written back",
    "written_back": "Written back",
    "done": "Done",
    "failed": "Failed",
    "needs_a_person": "Needs a person",
}


def when(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def user_brief(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
        "on_duty": user.on_duty,
    }


def user_detail(user: User) -> dict[str, Any]:
    out = user_brief(user) or {}
    out["is_active"] = user.is_active
    return out


def step_out(step: Step) -> dict[str, Any]:
    return {
        "id": step.id,
        "at": when(step.occurred_at),
        "system": step.system,
        "action": step.action,
        "attempt": step.attempt,
        "outcome": step.outcome,
        "sent": step.sent,
        "received": step.received,
        "note": step.note,
        "duration_ms": step.duration_ms,
    }


def shipment_brief(shipment: Shipment) -> dict[str, Any]:
    return {
        "reference": shipment.reference,
        "order_number": shipment.order_number,
        "customer": shipment.customer_name,
        "country": shipment.to_country,
        "city": shipment.to_city,
        "packages": shipment.packages,
        "weight_kg": shipment.weight_kg,
        "dangerous": shipment.dangerous,
        "state": shipment.state,
        "state_label": STATE_WORDS.get(shipment.state, shipment.state),
        "consignment": shipment.consignment,
        "tracking_number": shipment.tracking_number,
        "attempts": shipment.attempts,
        "exception_kind": shipment.exception_kind,
        "exception_label": EXCEPTION_WORDS.get(shipment.exception_kind, ""),
        "exception_detail": shipment.exception_detail,
    }


def shipment_detail(shipment: Shipment) -> dict[str, Any]:
    out = shipment_brief(shipment)
    out.update(
        {
            "to_name": shipment.to_name,
            "to_line1": shipment.to_line1,
            "to_postcode": shipment.to_postcode,
            "goods_description": shipment.goods_description,
            "service": shipment.service,
            "lines": shipment.lines,
            "dangerous_detail": shipment.dangerous_detail,
            "idempotency_key": shipment.idempotency_key,
            "booked_at": when(shipment.booked_at),
            "written_back_at": when(shipment.written_back_at),
            "label_url": shipment.label_url,
            "steps": [step_out(s) for s in shipment.steps],
        }
    )
    return out


def run_out(run: Run) -> dict[str, Any]:
    return {
        "id": run.id,
        "started_at": when(run.started_at),
        "finished_at": when(run.finished_at),
        "status": run.status,
        "considered": run.considered,
        "completed": run.completed,
        "exceptions": run.exceptions,
        "skipped_already_done": run.skipped_already_done,
        "seconds": round(run.seconds, 2),
        "halted_reason": run.halted_reason,
        "drift": run.drift or None,
        "notes": run.notes,
    }


def challenge_out(challenge: Challenge) -> dict[str, Any]:
    return {
        "reference": challenge.reference,
        "kind": challenge.kind,
        "status": challenge.status,
        "asked_at": when(challenge.asked_at),
        "asked_of": user_brief(challenge.asked_of),
        "shipment": challenge.shipment.reference if challenge.shipment else None,
        "note": challenge.note,
    }


def flag_out(flag: ScriptFlag) -> dict[str, Any]:
    return {
        "id": flag.id,
        "raised_at": when(flag.raised_at),
        "script": flag.script,
        "expected_fingerprint": flag.expected_fingerprint,
        "found_fingerprint": flag.found_fingerprint,
        "detail": flag.detail,
        "status": flag.status,
        "acknowledged_by": user_brief(flag.acknowledged_by),
        "note": flag.note,
    }


def dashboard(session: Session) -> dict[str, Any]:
    total = session.scalar(select(func.count(Shipment.id))) or 0
    by_state: dict[str, int] = {}
    for state, number in session.execute(
        select(Shipment.state, func.count(Shipment.id)).group_by(Shipment.state)
    ):
        by_state[state] = number

    done = by_state.get("done", 0)
    finished = sum(
        by_state.get(state, 0)
        for state in ("done", "failed", "needs_a_person")
    )

    by_exception = [
        {
            "kind": kind,
            "label": EXCEPTION_WORDS.get(kind, kind),
            "count": number,
        }
        for kind, number in session.execute(
            select(Shipment.exception_kind, func.count(Shipment.id))
            .where(Shipment.exception_kind != "")
            .group_by(Shipment.exception_kind)
            .order_by(func.count(Shipment.id).desc())
        )
    ]

    latest = session.scalar(select(Run).order_by(Run.id.desc()).limit(1))
    waiting = (
        session.scalar(
            select(func.count(Challenge.id)).where(Challenge.status == "waiting")
        )
        or 0
    )
    flags = (
        session.scalar(
            select(func.count(ScriptFlag.id)).where(ScriptFlag.status == "open")
        )
        or 0
    )

    #: What a clerk would have spent on this, at four minutes each.
    minutes_saved = done * 4

    return {
        "shipments": total,
        "done": done,
        "automated_share": round(100.0 * done / finished, 1) if finished else 0.0,
        "by_state": [
            {"state": state, "label": STATE_WORDS.get(state, state), "count": number}
            for state, number in sorted(by_state.items(), key=lambda kv: -kv[1])
        ],
        "by_exception": by_exception,
        "waiting_for_a_code": waiting,
        "open_flags": flags,
        "latest_run": run_out(latest) if latest else None,
        "minutes_saved": minutes_saved,
        "hours_saved": round(minutes_saved / 60.0, 1),
        "carrier": settings.carrier_name,
    }
