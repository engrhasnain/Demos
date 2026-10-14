"""Rows into the shapes the screens draw."""

from __future__ import annotations

import datetime as dt
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .config import settings
from .domain import intents
from .models import (
    AccessLog,
    Conversation,
    Customer,
    ReturnRequest,
    Technician,
    Ticket,
    Turn,
    User,
    Visit,
)
from .security import ROLE_LABELS
from .services import escalation
from .services.returns import TRIAGE_WORDS, WHO_PAYS


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
    }


def user_detail(user: User) -> dict[str, Any]:
    out = user_brief(user) or {}
    out["is_active"] = user.is_active
    return out


def reply_out(reply) -> dict[str, Any]:
    return reply.to_dict()


def turn_out(turn: Turn) -> dict[str, Any]:
    return {
        "id": turn.id,
        "at": when(turn.occurred_at),
        "speaker": turn.speaker,
        "text": turn.text,
        "intent": turn.intent,
        "intent_label": intents.LABELS.get(turn.intent, turn.intent),
        "confidence": round(turn.intent_confidence, 2),
        "tool": turn.tool,
        "tool_result": turn.tool_result or None,
        "refusal": turn.refusal,
        "engine": turn.engine,
        "duration_ms": turn.duration_ms,
        "attachment": turn.attachment,
    }


def conversation_detail(
    conversation: Conversation, *, with_turns: bool = True
) -> dict[str, Any]:
    ticket = conversation.ticket
    return {
        "reference": conversation.reference,
        "channel": conversation.channel,
        "status": conversation.status,
        "language": conversation.language,
        "intent": conversation.intent,
        "intent_label": intents.LABELS.get(conversation.intent, ""),
        "verified": conversation.verified_at is not None,
        "verified_at": when(conversation.verified_at),
        "locked": bool(conversation.locked_until),
        "attempts": conversation.verification_attempts,
        "customer": (
            {
                "name": conversation.customer.name,
                "code": conversation.customer.code,
                "country": conversation.customer.country,
                "city": conversation.customer.city,
            }
            if conversation.customer
            else None
        ),
        "contact": (
            {"name": conversation.contact.full_name, "email": conversation.contact.email}
            if conversation.contact
            else None
        ),
        "ticket": (
            {
                "reference": ticket.reference,
                "reason": ticket.reason,
                "reason_label": escalation.REASON_WORDS.get(ticket.reason, ticket.reason),
                "reply_by": when(ticket.reply_by),
                "reply_wording": ticket.reply_wording,
                "status": ticket.status,
            }
            if ticket
            else None
        ),
        "turns": [turn_out(t) for t in conversation.turns] if with_turns else [],
    }


def conversation_brief(conversation: Conversation) -> dict[str, Any]:
    last = conversation.turns[-1] if conversation.turns else None
    return {
        "reference": conversation.reference,
        "channel": conversation.channel,
        "status": conversation.status,
        "intent": conversation.intent,
        "intent_label": intents.LABELS.get(conversation.intent, ""),
        "customer": conversation.customer.name if conversation.customer else None,
        "verified": conversation.verified_at is not None,
        "turns": len(conversation.turns),
        "last_said": (last.text[:120] if last else ""),
        "at": when(conversation.created_at),
        "ticket": conversation.ticket.reference if conversation.ticket else None,
    }


def ticket_out(ticket: Ticket) -> dict[str, Any]:
    return {
        "reference": ticket.reference,
        "conversation": ticket.conversation.reference if ticket.conversation else "",
        "customer": (
            ticket.conversation.customer.name
            if ticket.conversation and ticket.conversation.customer
            else None
        ),
        "reason": ticket.reason,
        "reason_label": escalation.REASON_WORDS.get(ticket.reason, ticket.reason),
        "summary": ticket.summary,
        "reply_by": when(ticket.reply_by),
        "reply_wording": ticket.reply_wording,
        "status": ticket.status,
        "assigned_to": user_brief(ticket.assigned_to),
        "at": when(ticket.created_at),
    }


def return_out(request: ReturnRequest) -> dict[str, Any]:
    return {
        "reference": request.reference,
        "customer": request.customer.name if request.customer else None,
        "order": request.order.number if request.order else None,
        "part_code": request.part_code,
        "quantity": request.quantity,
        "reported": request.reported,
        "triage": request.triage,
        "triage_label": TRIAGE_WORDS.get(request.triage, request.triage),
        "triage_confidence": round(request.triage_confidence, 2),
        "who_usually_pays": WHO_PAYS.get(request.triage, ""),
        "triage_detail": request.triage_detail,
        "within_warranty": request.within_warranty,
        "warranty_detail": request.warranty_detail,
        "photo_name": request.photo_name,
        "status": request.status,
        "decided_by": user_brief(request.decided_by),
        "decision_note": request.decision_note,
        "at": when(request.created_at),
    }


def visit_out(visit: Visit) -> dict[str, Any]:
    local = visit.starts_at
    return {
        "reference": visit.reference,
        "customer": visit.customer.name if visit.customer else None,
        "technician": visit.technician.full_name if visit.technician else None,
        "starts_at": when(visit.starts_at),
        "minutes": visit.minutes,
        "city": visit.city,
        "status": visit.status,
    }


def access_out(row: AccessLog) -> dict[str, Any]:
    return {
        "id": row.id,
        "at": when(row.occurred_at),
        "tool": row.tool,
        "arguments": row.arguments,
        "allowed": row.allowed,
        "refusal": row.refusal,
        "rows_returned": row.rows_returned,
        "conversation_id": row.conversation_id,
    }


def dashboard(session: Session, now: dt.datetime) -> dict[str, Any]:
    """Every figure one query, so the page cannot disagree with itself."""
    total = session.scalar(select(func.count(Conversation.id))) or 0
    by_status: dict[str, int] = {}
    for status_code, number in session.execute(
        select(Conversation.status, func.count(Conversation.id)).group_by(
            Conversation.status
        )
    ):
        by_status[status_code] = number

    resolved = by_status.get("resolved", 0)
    escalated = by_status.get("escalated", 0)
    finished = resolved + escalated

    open_tickets = (
        session.scalar(select(func.count(Ticket.id)).where(Ticket.status == "open")) or 0
    )
    waiting_returns = (
        session.scalar(
            select(func.count(ReturnRequest.id)).where(ReturnRequest.status == "proposed")
        )
        or 0
    )
    refused = (
        session.scalar(
            select(func.count(AccessLog.id)).where(AccessLog.allowed.is_(False))
        )
        or 0
    )
    booked = (
        session.scalar(select(func.count(Visit.id)).where(Visit.status == "booked")) or 0
    )

    by_intent = [
        {
            "intent": intent,
            "label": intents.LABELS.get(intent, intent),
            "count": number,
        }
        for intent, number in session.execute(
            select(Conversation.intent, func.count(Conversation.id))
            .where(Conversation.intent != "")
            .group_by(Conversation.intent)
            .order_by(func.count(Conversation.id).desc())
        )
    ]

    return {
        "conversations": total,
        "resolved": resolved,
        "escalated": escalated,
        "handled_share": round(100.0 * resolved / finished, 1) if finished else 0.0,
        "open_tickets": open_tickets,
        "returns_waiting": waiting_returns,
        "visits_booked": booked,
        "refused_attempts": refused,
        "by_status": [
            {"status": code, "count": number} for code, number in by_status.items()
        ],
        "by_intent": by_intent,
        "desk_open": escalation.is_open(now),
        "next_open": when(escalation.next_open(now)),
        "customers": session.scalar(select(func.count(Customer.id))) or 0,
        "technicians": session.scalar(select(func.count(Technician.id))) or 0,
        "engine": settings.reply_engine,
        "line_configured": settings.line_configured,
    }
