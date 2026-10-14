"""The conversation, over HTTP and over LINE.

The web endpoints here are deliberately open: a customer has not signed in
to anything, they have opened a chat window. What protects the data is the
verification inside the conversation, not a bearer token at the door.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..channels import line as line_channel
from ..config import settings
from ..db import get_session
from ..models import Conversation, Technician
from ..serializers import conversation_detail, reply_out
from ..services import desk, identity

router = APIRouter(prefix="/api/chat", tags=["chat"])


def _next_reference(session: Session, channel: str) -> str:
    today = dt.date.today()
    count = session.scalar(select(func.count(Conversation.id))) or 0
    return f"{'W' if channel == 'web' else 'L'}-{today:%y%m%d}-{count + 1:05d}"


def _get(session: Session, reference: str) -> Conversation:
    conversation = session.scalar(
        select(Conversation).where(Conversation.reference == reference)
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="That conversation has ended.")
    return conversation


class Start(BaseModel):
    channel: str = "web"


@router.post("/start", status_code=status.HTTP_201_CREATED)
def start(body: Start, session: Session = Depends(get_session)) -> dict[str, Any]:
    channel = body.channel if body.channel in {"web", "line"} else "web"
    conversation = Conversation(
        reference=_next_reference(session, channel), channel=channel, status="open"
    )
    session.add(conversation)
    session.flush()
    return conversation_detail(conversation)


class Say(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    attachment: str = Field("", max_length=160)


@router.post("/{reference}/say")
def say(
    reference: str, body: Say, session: Session = Depends(get_session)
) -> dict[str, Any]:
    conversation = _get(session, reference)
    reply = desk.handle(
        session, conversation, body.message, attachment=body.attachment
    )
    return {
        "reply": reply_out(reply),
        "conversation": conversation_detail(conversation),
    }


class Verify(BaseModel):
    order_number: str = Field(min_length=1, max_length=64)
    email: str = Field(min_length=3, max_length=160)


@router.post("/{reference}/verify")
def verify(
    reference: str, body: Verify, session: Session = Depends(get_session)
) -> dict[str, Any]:
    conversation = _get(session, reference)
    result = identity.verify(
        session, conversation, order_number=body.order_number, email=body.email
    )
    return {
        "ok": result.ok,
        "message": result.message,
        "attempts_left": result.attempts_left,
        "locked": result.locked,
        "conversation": conversation_detail(conversation),
    }


class Take(BaseModel):
    slot: str = Field(min_length=3, max_length=120)


@router.post("/{reference}/book")
def book(
    reference: str, body: Take, session: Session = Depends(get_session)
) -> dict[str, Any]:
    conversation = _get(session, reference)
    reply = desk.take_slot(session, conversation, body.slot)
    return {
        "reply": reply_out(reply),
        "conversation": conversation_detail(conversation),
    }


@router.get("/{reference}")
def read(reference: str, session: Session = Depends(get_session)) -> dict[str, Any]:
    return conversation_detail(_get(session, reference), with_turns=True)


# ---------------------------------------------------------------------------
# LINE
# ---------------------------------------------------------------------------
@router.post("/line/webhook")
async def line_webhook(
    request: Request, session: Session = Depends(get_session)
) -> dict[str, Any]:
    """LINE posts here. An unsigned request gets nothing.

    Without the signature check this is an endpoint anybody can post to,
    claiming to be any LINE user. The check is not optional and it is not
    conditional on the demonstration.
    """
    body = await request.body()
    header = request.headers.get("X-Line-Signature", "")

    if not settings.line_configured:
        raise HTTPException(
            status_code=503,
            detail="No LINE channel secret is set, so this endpoint is closed.",
        )
    if not line_channel.verify(body, header):
        raise HTTPException(status_code=400, detail="Bad signature.")

    import json

    try:
        payload = json.loads(body or b"{}")
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Not JSON.") from error

    send = line_channel.sender()
    handled: list[dict[str, Any]] = []

    for incoming in line_channel.unpack(payload):
        contact = identity.contact_for_line_user(session, incoming.line_user_id)
        conversation = session.scalar(
            select(Conversation)
            .where(
                Conversation.channel == "line",
                Conversation.external_id == incoming.line_user_id,
                Conversation.status == "open",
            )
            .order_by(Conversation.id.desc())
            .limit(1)
        )
        if conversation is None:
            conversation = Conversation(
                reference=_next_reference(session, "line"),
                channel="line",
                external_id=incoming.line_user_id,
                status="open",
            )
            # A LINE account we have seen before, already tied to a contact,
            # does not have to verify again inside the session window.
            if contact is not None:
                conversation.customer_id = contact.customer_id
                conversation.contact_id = contact.id
                conversation.verified_at = dt.datetime.now(dt.timezone.utc)
            session.add(conversation)
            session.flush()

        text = incoming.text or ("[photograph]" if incoming.is_photo else "")
        reply = desk.handle(
            session,
            conversation,
            text,
            attachment=incoming.attachment_id if incoming.is_photo else "",
        )
        identity.remember_line_user(session, conversation, incoming.line_user_id)

        outgoing = line_channel.compose(incoming.reply_token, reply.text, reply.actions)
        handled.append(
            {
                "conversation": conversation.reference,
                "reply": reply.text,
                "transport": send(outgoing),
            }
        )

    return {"handled": len(handled), "events": handled}
