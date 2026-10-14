"""Turning objects into what the screen needs, and nothing more.

Two rules run through this file.

**Money leaves as a string.** A float is a different number by the time
it has been through JSON and a browser, and the whole point of this
product is that the figure on the screen is the figure in the database.

**An internal identifier is not an answer.** Rows keep their customer and
supplier identifiers all the way through the query layer, because the
permission filter binds to them. They stop here. A screen that shows
``customer_id: 47`` is a screen that teaches somebody to type 47 into
the next question, and the only reason that does not work today is a
check they should never have been invited to test.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from .config import settings
from .models import AccessLog, Document, Proposal, Question, User
from .security import ROLE_LABELS


def _money(value: Any) -> str:
    if value is None:
        return "0.00"
    return str(Decimal(str(value)).quantize(Decimal("0.01")))


def user_detail(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "email": user.email,
        "name": user.full_name,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
    }


def reach_detail(reach) -> dict[str, Any]:
    """What this person can see, in words, for the top of the screen."""
    if reach.everything:
        return {
            "everything": True,
            "summary": "Every account.",
            "customers": None,
            "suppliers": None,
        }
    return {
        "everything": False,
        "summary": (
            f"{len(reach.customers)} accounts"
            + (f" and {len(reach.suppliers)} suppliers" if reach.suppliers else "")
            + "."
        ),
        "customers": len(reach.customers),
        "suppliers": len(reach.suppliers),
    }


def evidence_detail(result, *, now: dt.datetime | None = None) -> dict[str, Any]:
    """One step of the working, with the receipt attached.

    ``age_seconds`` and ``stale`` are here because a figure read eleven
    minutes ago is a figure somebody will quote in a meeting this
    afternoon. The screen says how old it is.
    """
    now = now or dt.datetime.now(dt.timezone.utc)
    read_at = result.read_at
    if read_at.tzinfo is None:
        read_at = read_at.replace(tzinfo=dt.timezone.utc)
    age = (now - read_at).total_seconds()
    body = result.to_dict()
    body["age_seconds"] = round(age, 1)
    body["stale"] = age > settings.stale_after_seconds
    return body


def answer_detail(answer, *, reach=None) -> dict[str, Any]:
    body = answer.to_dict()
    body["evidence"] = [evidence_detail(step) for step in answer.evidence]
    body["rows_read"] = sum(step.row_count for step in answer.evidence)
    body["queries"] = len(answer.evidence)
    if reach is not None:
        body["reach"] = reach_detail(reach)
    return body


def question_row(question: Question) -> dict[str, Any]:
    return {
        "id": question.id,
        "asked_at": question.asked_at.isoformat() if question.asked_at else None,
        "asked_by": question.asked_by.full_name if question.asked_by else None,
        "text": question.text,
        "reading": question.reading,
        "answer": question.answer,
        "refused": question.refused,
        "seconds": round(question.seconds, 2),
        "engine": question.engine,
        "injection_seen": question.injection_seen,
        "queries": len(question.evidence or []),
    }


def question_detail(question: Question) -> dict[str, Any]:
    body = question_row(question)
    body["plan"] = question.plan or []
    body["evidence"] = question.evidence or []
    return body


def proposal_row(proposal: Proposal) -> dict[str, Any]:
    return {
        "id": proposal.id,
        "reference": proposal.reference,
        "raised_at": proposal.raised_at.isoformat() if proposal.raised_at else None,
        "kind": proposal.kind,
        "summary": proposal.summary,
        "detail": proposal.detail or {},
        "needs_role": proposal.needs_role,
        "needs_role_label": ROLE_LABELS.get(proposal.needs_role, proposal.needs_role),
        "status": proposal.status,
        "decided_by": proposal.decided_by.full_name if proposal.decided_by else None,
        "decided_at": proposal.decided_at.isoformat() if proposal.decided_at else None,
        "note": proposal.note,
        "question_id": proposal.question_id,
    }


def document_row(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "reference": document.reference,
        "kind": document.kind,
        "subject": document.subject,
        "received_on": document.received_on.isoformat() if document.received_on else None,
        "body": document.body,
    }


def access_row(log: AccessLog, *, who: str = "") -> dict[str, Any]:
    return {
        "id": log.id,
        "occurred_at": log.occurred_at.isoformat() if log.occurred_at else None,
        "who": who,
        "capability": log.capability,
        "parameters": log.parameters or {},
        "allowed": log.allowed,
        "refusal": log.refusal,
        "rows_returned": log.rows_returned,
        "filter_applied": log.filter_applied,
    }


def capability_row(capability) -> dict[str, Any]:
    """The catalogue, shown to anybody who asks.

    Published on purpose. The list of things this system can do is the
    product's main safety claim, and a safety claim nobody can read is a
    marketing line.
    """
    body = capability.to_dict()
    body["needs_role_label"] = ROLE_LABELS.get(
        capability.needs_role, capability.needs_role
    )
    return body
