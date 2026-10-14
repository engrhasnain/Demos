"""One turn of a conversation.

The shape of this file is the whole design:

    understand  →  check permission  →  run a tool  →  compose words

The model, if one is configured, takes part in the first step and the last.
It picks an intent from a closed list, and it phrases a sentence. It does
not run the second or third step, it never receives a customer id, and it
never sees a row it was not handed. Rewriting the prompt cannot change any
of that, because none of it is in the prompt.

Everything that could show somebody else's data goes through ``isolation``,
and everything the desk cannot finish goes to a person with the context
already written down.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..domain import intents, language
from ..models import Conversation, Order, Quotation, Technician, Turn
from . import escalation, identity, isolation, orders, returns, scheduling

#: Offsets used only to say a reply time in the customer's own evening.
COUNTRY_OFFSETS: dict[str, int] = {
    "TW": 8, "CN": 8, "JP": 9, "US": -8, "DE": 1, "VN": 7, "GB": 0,
}


@dataclass(slots=True)
class Reply:
    """What the desk says, and everything behind it."""

    text: str
    intent: str = ""
    confidence: float = 0.0
    tool: str = ""
    tool_result: dict[str, Any] = field(default_factory=dict)
    refusal: str = ""
    #: Offered buttons, so a person is always one tap away.
    actions: list[dict[str, str]] = field(default_factory=list)
    needs_verification: bool = False
    resolved: bool = False
    escalated: bool = False
    ticket_reference: str = ""
    engine: str = "built-in"
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "intent": self.intent,
            "confidence": round(self.confidence, 2),
            "tool": self.tool,
            "tool_result": self.tool_result,
            "refusal": self.refusal,
            "actions": self.actions,
            "needs_verification": self.needs_verification,
            "resolved": self.resolved,
            "escalated": self.escalated,
            "ticket_reference": self.ticket_reference,
            "engine": self.engine,
            "duration_ms": self.duration_ms,
        }


def _person_action(code: str = "human") -> dict[str, str]:
    """The button that is on every single reply, without exception."""
    return {"code": code, "label": "Talk to a person"}


def _offset_for(conversation: Conversation) -> int:
    if conversation.customer is not None:
        return COUNTRY_OFFSETS.get(conversation.customer.country, 8)
    return 8


# ---------------------------------------------------------------------------
# The turn
# ---------------------------------------------------------------------------
def handle(
    session: Session,
    conversation: Conversation,
    message: str,
    *,
    attachment: str = "",
    now: dt.datetime | None = None,
) -> Reply:
    """Take one thing the customer said and answer it."""
    started = time.perf_counter()
    now = now or dt.datetime.now(dt.timezone.utc)

    conversation.language = language.detect(message) or conversation.language
    _remember(session, conversation, "customer", message, attachment=attachment)

    read = intents.read(message)
    reply = _route(session, conversation, message, read, attachment=attachment, now=now)

    reply.intent = read.intent
    reply.confidence = read.confidence
    reply.duration_ms = int((time.perf_counter() - started) * 1000)

    # A person is always one tap away. Not sometimes, not after three
    # failed answers, not hidden behind "is there anything else".
    if not any(action["code"] == "human" for action in reply.actions):
        reply.actions.append(_person_action())

    # Nothing leaves with a mangled part number. Only applied to replies
    # that actually answered something: appending "(SO-20001)" to "I have no
    # record of that" tells the reader nothing and reads like a fault.
    if reply.tool_result and not reply.refusal and not reply.needs_verification:
        missing = language.survived(message, reply.text)
        if missing:
            reply.text += " (" + ", ".join(missing) + ")"

    conversation.intent = read.intent
    _remember(
        session,
        conversation,
        "desk",
        reply.text,
        intent=read.intent,
        confidence=read.confidence,
        tool=reply.tool,
        tool_result=reply.tool_result,
        refusal=reply.refusal,
        engine=reply.engine,
        duration_ms=reply.duration_ms,
    )
    session.flush()
    return reply


def _route(
    session: Session,
    conversation: Conversation,
    message: str,
    read: intents.Read,
    *,
    attachment: str,
    now: dt.datetime,
) -> Reply:
    tongue = conversation.language

    # --- asked for a person: answered before anything else -------------
    if read.intent == intents.HUMAN:
        ticket = escalation.raise_ticket(
            session,
            conversation,
            reason="asked_for_a_person",
            summary=_summarise(conversation),
            now=now,
            customer_offset_hours=_offset_for(conversation),
        )
        return Reply(
            text=(
                f"{language.say('handing_over', tongue)} "
                f"Somebody will reply {ticket.reply_wording}. "
                f"Your reference is {ticket.reference}."
            ),
            tool="raise_ticket",
            tool_result={"reference": ticket.reference, "reply_by": ticket.reply_wording},
            escalated=True,
            ticket_reference=ticket.reference,
        )

    if read.intent == intents.GREETING:
        return Reply(
            text=language.say("greeting", tongue),
            resolved=False,
            actions=[
                {"code": "order_status", "label": "Where is my order"},
                {"code": "return_request", "label": "Return or fault"},
                {"code": "book_visit", "label": "Book a technician"},
            ],
        )

    if read.intent == intents.OPENING_HOURS:
        return _hours(now, tongue)

    if read.intent == intents.UNKNOWN:
        ticket = escalation.raise_ticket(
            session,
            conversation,
            reason="not_understood",
            summary=f"Could not understand: {message[:300]}",
            now=now,
            customer_offset_hours=_offset_for(conversation),
        )
        return Reply(
            text=(
                f"{language.say('not_understood', tongue)} "
                f"They will reply {ticket.reply_wording} ({ticket.reference})."
            ),
            tool="raise_ticket",
            tool_result={"reference": ticket.reference},
            escalated=True,
            ticket_reference=ticket.reference,
        )

    # --- everything below needs to know who it is talking to -----------
    if not identity.is_verified(conversation, now):
        if identity.is_locked(conversation, now):
            ticket = escalation.raise_ticket(
                session,
                conversation,
                reason="locked_out",
                summary="Too many failed verification attempts.",
                now=now,
                customer_offset_hours=_offset_for(conversation),
            )
            return Reply(
                text=(
                    "I cannot verify this account from here. A person will "
                    f"pick it up {ticket.reply_wording} ({ticket.reference})."
                ),
                refusal="locked out",
                escalated=True,
                ticket_reference=ticket.reference,
            )
        return Reply(
            text=language.say("ask_to_verify", tongue),
            needs_verification=True,
            tool="ask_to_verify",
        )

    scope = isolation.scope_for(conversation)

    if read.intent == intents.ORDER_STATUS:
        return _order_status(session, conversation, scope, message, now, tongue)
    if read.intent == intents.QUOTE_STATUS:
        return _quote_status(session, scope, message, tongue)
    if read.intent == intents.RETURN_REQUEST:
        return _return(session, conversation, scope, message, attachment, now, tongue)
    if read.intent == intents.BOOK_VISIT:
        return _visit(session, conversation, scope, message, now, tongue)

    ticket = escalation.raise_ticket(
        session,
        conversation,
        reason="not_understood",
        summary=message[:300],
        now=now,
        customer_offset_hours=_offset_for(conversation),
    )
    return Reply(
        text=f"{language.say('not_understood', tongue)} ({ticket.reference})",
        escalated=True,
        ticket_reference=ticket.reference,
    )


# ---------------------------------------------------------------------------
# The answers
# ---------------------------------------------------------------------------
def _hours(now: dt.datetime, tongue: str) -> Reply:
    open_now = escalation.is_open(now)
    opens = escalation.next_open(now).astimezone(escalation.TAIPEI)
    if tongue == language.CHINESE:
        text = (
            "我們的服務時間是台北時間週一至週五 "
            f"{settings.office_opens_hour}:00 至 {settings.office_closes_hour}:00。"
            + ("目前營業中。" if open_now else f"目前休息中，下次開門是 {opens:%m/%d %H:%M}。")
        )
    else:
        text = (
            f"We are open {settings.office_opens_hour}:00 to "
            f"{settings.office_closes_hour}:00, Monday to Friday, Taipei time. "
            + ("We are open now." if open_now else f"Next open {opens:%a %d %b, %H:%M}.")
        )
    return Reply(text=text, tool="opening_hours", resolved=True)


def _order_status(
    session: Session,
    conversation: Conversation,
    scope: isolation.Scope,
    message: str,
    now: dt.datetime,
    tongue: str,
) -> Reply:
    wanted = next(
        (i for i in language.identifiers_in(message) if i.upper().startswith("SO")), None
    )
    view = orders.look_up(session, scope, number=wanted, now=now)

    if view is None:
        # Same answer whether it does not exist or is somebody else's.
        return Reply(
            text=(
                "I have no record of that order on your account."
                if tongue == language.ENGLISH
                else "您的帳戶沒有這筆訂單的紀錄。"
            ),
            tool="order_status",
            tool_result={"found": False},
            refusal="no order of this customer's matches",
        )

    order = view.order
    parts = [f"Order {order.number}: {order.status}."]
    if order.promised_on:
        parts.append(f"Promised {order.promised_on:%d %b}.")
    if view.latest:
        where = f" at {view.latest.place}" if view.latest.place else ""
        parts.append(
            f"{order.carrier} last recorded it as "
            f"{orders.CARRIER_WORDS.get(view.latest.code, view.latest.code)}{where}."
        )

    reply = Reply(
        text=" ".join(parts),
        tool="order_status",
        tool_result=view.to_dict(),
        resolved=True,
        actions=[{"code": "return_request", "label": "Something is wrong with it"}],
    )

    if view.disagreement is not None:
        reply.text += " " + view.disagreement.summary
        if view.disagreement.needs_a_person:
            ticket = escalation.raise_ticket(
                session,
                conversation,
                reason="systems_disagree",
                summary=(
                    f"{order.number}: our system says {view.disagreement.system_says}, "
                    f"the carrier says {view.disagreement.carrier_says}, "
                    f"{view.disagreement.hours_apart:.0f} hours old."
                ),
                now=now,
                customer_offset_hours=_offset_for(conversation),
            )
            reply.text += (
                f" I am not going to guess which is right, so I have asked a "
                f"person to chase the carrier. They will reply "
                f"{ticket.reply_wording} ({ticket.reference})."
            )
            reply.resolved = False
            reply.escalated = True
            reply.ticket_reference = ticket.reference
    return reply


def _quote_status(
    session: Session, scope: isolation.Scope, message: str, tongue: str
) -> Reply:
    wanted = next(
        (i for i in language.identifiers_in(message) if i.upper().startswith("RQ")), None
    )
    query = isolation.owned_by(select(Quotation), Quotation.customer_id, scope)
    if wanted:
        # Match on the digits, so RQ-30000, RQ30000 and "rq 30000" all find
        # the same quotation. Stripping only one side finds nothing.
        digits = "".join(c for c in wanted if c.isdigit())
        if digits:
            query = query.where(Quotation.reference.ilike(f"%{digits}%"))
    quote = session.scalar(query.order_by(Quotation.sent_on.desc()).limit(1))
    isolation.record(
        session,
        tool="quote_status",
        scope=scope,
        arguments={"reference": wanted},
        rows=1 if quote else 0,
    )

    if quote is None:
        return Reply(
            text=(
                "I have no quotation on your account matching that."
                if tongue == language.ENGLISH
                else "您的帳戶沒有符合的報價單。"
            ),
            tool="quote_status",
            tool_result={"found": False},
        )

    text = (
        f"Quotation {quote.reference} is {quote.status}, "
        f"{quote.total} {quote.currency} over {quote.lines} lines."
    )
    if quote.valid_until:
        text += f" Valid until {quote.valid_until:%d %b}."
    return Reply(
        text=text,
        tool="quote_status",
        tool_result={
            "reference": quote.reference,
            "status": quote.status,
            "total": str(quote.total),
            "currency": quote.currency,
            "valid_until": quote.valid_until.isoformat() if quote.valid_until else None,
        },
        resolved=True,
    )


def _return(
    session: Session,
    conversation: Conversation,
    scope: isolation.Scope,
    message: str,
    attachment: str,
    now: dt.datetime,
    tongue: str,
) -> Reply:
    # Against the order they named if they named one, and otherwise the
    # most recent. Attaching a return to the wrong order is the sort of
    # small wrongness that makes a customer stop trusting the whole thing.
    named = next(
        (i for i in language.identifiers_in(message) if i.upper().startswith("SO")), None
    )
    view = orders.look_up(session, scope, number=named) if named else None
    order = view.order if view else None
    if order is None:
        recent = orders.recent(session, scope, limit=1)
        if not recent:
            return Reply(
                text="I cannot see an order on your account to return against.",
                tool="propose_return",
                tool_result={"found": False},
            )
        order = recent[0]
    part = next(
        (i for i in language.identifiers_in(message) if i.upper().startswith("HT-")),
        order.lines[0].part_code if order.lines else "",
    )
    customer = conversation.customer

    request = returns.propose(
        session,
        scope,
        order=order,
        part_code=part,
        quantity=1,
        reported=message,
        photo_name=attachment,
        is_trade_account=bool(customer and customer.is_trade_account),
        warranty_months=customer.warranty_months if customer else None,
        today=now.date(),
    )
    ticket = escalation.raise_ticket(
        session,
        conversation,
        reason="return_needs_approval",
        summary=f"{request.reference} on {order.number}: {request.triage}",
        now=now,
        customer_offset_hours=_offset_for(conversation),
    )

    found = request.triage_detail
    cover = request.warranty_detail
    text = (
        f"{language.say('return_proposed', tongue)} "
        f"Reference {request.reference}, against order {order.number}."
    )
    if found.get("confident_enough"):
        text += f" From what you describe this looks like {found.get('label', '').lower()}."
    else:
        text += " I am not confident enough from the description to say what caused it."
    text += f" {cover.get('note', '')}"
    text += f" A person will confirm {ticket.reply_wording} ({ticket.reference})."

    return Reply(
        text=text,
        tool="propose_return",
        tool_result={
            "reference": request.reference,
            "order": order.number,
            "part_code": part,
            "triage": found,
            "cover": cover,
        },
        # A return is never resolved by the desk. A person approves it.
        resolved=False,
        escalated=True,
        ticket_reference=ticket.reference,
    )


def _visit(
    session: Session,
    conversation: Conversation,
    scope: isolation.Scope,
    message: str,
    now: dt.datetime,
    tongue: str,
) -> Reply:
    customer = conversation.customer
    city = customer.city if customer else ""
    search = scheduling.find_slots(
        session, city=city, skill="", parts=[], from_day=now.astimezone(scheduling.TAIPEI).date()
    )
    isolation.record(
        session,
        tool="find_slots",
        scope=scope,
        arguments={"city": city},
        rows=len(search.slots),
    )

    if not search.slots:
        ticket = escalation.raise_ticket(
            session,
            conversation,
            reason="nothing_available",
            summary=f"No technician slot for {city} inside the horizon.",
            now=now,
            customer_offset_hours=_offset_for(conversation),
        )
        return Reply(
            text=(
                "I cannot find a technician slot in the next two weeks. A "
                f"person will arrange something {ticket.reply_wording} "
                f"({ticket.reference})."
            ),
            tool="find_slots",
            tool_result=search.to_dict(),
            escalated=True,
            ticket_reference=ticket.reference,
        )

    shown = [slot.to_dict() for slot in search.slots[:3]]
    text = (
        "Here are the next available visits in "
        + (city or "your area")
        + ": "
        + "; ".join(f"{s['shown_as']} with {s['technician']}" for s in shown)
        + "."
    )
    return Reply(
        text=text,
        tool="find_slots",
        tool_result=search.to_dict(),
        resolved=False,
        actions=[
            {"code": f"book:{slot['key']}", "label": slot["shown_as"]} for slot in shown
        ],
    )


def take_slot(
    session: Session,
    conversation: Conversation,
    slot_key: str,
    *,
    now: dt.datetime | None = None,
) -> Reply:
    """Accept one of the offered slots, and lose the race gracefully."""
    now = now or dt.datetime.now(dt.timezone.utc)
    tongue = conversation.language
    if not identity.is_verified(conversation, now):
        return Reply(text=language.say("ask_to_verify", tongue), needs_verification=True)

    scope = isolation.scope_for(conversation)
    customer = conversation.customer
    city = customer.city if customer else ""

    technician_id, _, when = slot_key.partition(":")
    try:
        starts_at = dt.datetime.fromisoformat(when)
    except ValueError:
        return Reply(text="That slot is no longer on offer.", refusal="bad slot key")

    technician = session.get(Technician, int(technician_id))
    if technician is None:
        return Reply(text="That slot is no longer on offer.", refusal="unknown technician")

    slot = scheduling.Slot(
        technician_id=technician.id,
        technician_name=technician.full_name,
        starts_at=starts_at,
        minutes=settings.visit_minutes,
        city=city,
        travel_minutes=0,
    )

    try:
        visit = scheduling.book(session, scope, slot)
    except scheduling.SlotTaken:
        # The race, lost. Offer the next one rather than an error.
        again = scheduling.find_slots(
            session, city=city, skill="", parts=[],
            from_day=now.astimezone(scheduling.TAIPEI).date(),
        )
        nexts = [s.to_dict() for s in again.slots[:3]]
        return Reply(
            text=language.say("slot_taken", tongue)
            + (
                " " + "; ".join(f"{s['shown_as']} with {s['technician']}" for s in nexts)
                if nexts
                else ""
            ),
            tool="book_visit",
            tool_result={"taken": True, "alternatives": nexts},
            actions=[
                {"code": f"book:{s['key']}", "label": s["shown_as"]} for s in nexts
            ],
        )

    isolation.record(
        session, tool="book_visit", scope=scope, arguments={"slot": slot_key}, rows=1
    )
    local = visit.starts_at.astimezone(scheduling.TAIPEI)
    reply = Reply(
        text=(
            f"{language.say('visit_booked', tongue)} {visit.technician.full_name} "
            f"will be with you {local:%A %d %b at %H:%M}. "
            f"Reference {visit.reference}."
        ),
        tool="book_visit",
        tool_result={
            "reference": visit.reference,
            "technician": visit.technician.full_name,
            "starts_at": visit.starts_at.isoformat(),
        },
        resolved=True,
    )
    _remember(
        session, conversation, "desk", reply.text, tool="book_visit",
        tool_result=reply.tool_result,
    )
    conversation.status = "resolved"
    conversation.resolved_at = now
    session.flush()
    return reply


# ---------------------------------------------------------------------------
def _summarise(conversation: Conversation) -> str:
    said = [t.text for t in conversation.turns if t.speaker == "customer"]
    return " / ".join(said[-4:])[:2000]


def _remember(
    session: Session,
    conversation: Conversation,
    speaker: str,
    text: str,
    **extra: Any,
) -> Turn:
    turn = Turn(
        conversation_id=conversation.id,
        speaker=speaker,
        text=text,
        intent=extra.get("intent", ""),
        intent_confidence=extra.get("confidence", 0.0),
        tool=extra.get("tool", ""),
        tool_arguments=extra.get("tool_arguments", {}) or {},
        tool_result=extra.get("tool_result", {}) or {},
        refusal=extra.get("refusal", ""),
        engine=extra.get("engine", "built-in"),
        duration_ms=extra.get("duration_ms", 0),
        attachment=extra.get("attachment", ""),
    )
    session.add(turn)
    session.flush()
    return turn
