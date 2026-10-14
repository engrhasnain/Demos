"""Handing over to a person, with a time somebody can keep.

A promised reply time is the easiest thing in this product to get wrong and
the most damaging. "Someone will be with you shortly" sent at two in the
morning Taipei time to a customer in California is a lie that is found out
in eight hours, and the customer remembers it longer than they remember
whatever the question was.

So the time is worked out: if the desk is open, add the in-hours minutes.
If it is shut, find the next moment it opens and add the out-of-hours
minutes to that. Then say the actual time, in the customer's own evening
if that is where they are, rather than a number of minutes that quietly
spans a night and a weekend.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..models import Conversation, Ticket

TAIPEI = dt.timezone(dt.timedelta(hours=settings.office_timezone_offset_hours))

REASON_WORDS: dict[str, str] = {
    "asked_for_a_person": "Asked for a person",
    "not_understood": "Not understood",
    "systems_disagree": "The systems disagree",
    "return_needs_approval": "A return needs approving",
    "nothing_available": "Nothing could be offered",
    "locked_out": "Could not be verified",
    "refused": "Refused by the rules",
}


def is_open(moment: dt.datetime) -> bool:
    local = moment.astimezone(TAIPEI)
    if local.weekday() not in settings.working_days:
        return False
    return settings.office_opens_hour <= local.hour < settings.office_closes_hour


def next_open(moment: dt.datetime) -> dt.datetime:
    """The next instant the desk is staffed, at or after this one."""
    local = moment.astimezone(TAIPEI)
    for _ in range(14):  # a fortnight is plenty, even over a holiday
        if local.weekday() in settings.working_days:
            opens = local.replace(
                hour=settings.office_opens_hour, minute=0, second=0, microsecond=0
            )
            closes = local.replace(
                hour=settings.office_closes_hour, minute=0, second=0, microsecond=0
            )
            if local < opens:
                return opens.astimezone(dt.timezone.utc)
            if local < closes:
                return local.astimezone(dt.timezone.utc)
        # Roll to the start of the next day and try again.
        local = (local + dt.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    return moment


@dataclass(slots=True)
class Promise:
    reply_by: dt.datetime
    wording: str
    was_open: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "reply_by": self.reply_by.isoformat(),
            "wording": self.wording,
            "was_open": self.was_open,
        }


def promise(
    now: dt.datetime | None = None, *, customer_offset_hours: int | None = None
) -> Promise:
    """When a person will actually get to this, said in plain words."""
    now = now or dt.datetime.now(dt.timezone.utc)
    open_now = is_open(now)

    if open_now:
        reply_by = now + dt.timedelta(minutes=settings.reply_minutes_in_hours)
    else:
        reply_by = next_open(now) + dt.timedelta(
            minutes=settings.reply_minutes_out_of_hours
        )

    minutes = (reply_by - now).total_seconds() / 60.0
    where = dt.timezone(dt.timedelta(hours=customer_offset_hours or settings.office_timezone_offset_hours))
    local = reply_by.astimezone(where)

    if open_now and minutes <= 120:
        wording = f"within about {int(round(minutes / 15.0) * 15)} minutes"
    elif minutes < 60 * 20:
        wording = f"by about {local:%H:%M} your time"
    else:
        wording = f"by about {local:%H:%M} on {local:%A}, your time"

    if not open_now:
        wording += " — the desk in Taipei is closed at the moment"

    return Promise(reply_by=reply_by, wording=wording, was_open=open_now)


def raise_ticket(
    session: Session,
    conversation: Conversation,
    *,
    reason: str,
    summary: str,
    now: dt.datetime | None = None,
    customer_offset_hours: int | None = None,
) -> Ticket:
    """Hand the conversation over. Idempotent: one ticket per conversation."""
    existing = session.scalar(
        select(Ticket).where(Ticket.conversation_id == conversation.id)
    )
    if existing is not None:
        return existing

    made = promise(now, customer_offset_hours=customer_offset_hours)
    ticket = Ticket(
        reference=_next_reference(session),
        conversation_id=conversation.id,
        customer_id=conversation.customer_id,
        reason=reason,
        summary=summary[:2000],
        reply_by=made.reply_by,
        reply_wording=made.wording[:160],
        status="open",
    )
    session.add(ticket)
    conversation.status = "escalated"
    session.flush()
    return ticket


def _next_reference(session: Session) -> str:
    year = dt.datetime.now(TAIPEI).year
    highest = session.scalar(
        select(Ticket.reference)
        .where(Ticket.reference.like(f"T-{year}-%"))
        .order_by(Ticket.reference.desc())
        .limit(1)
    )
    number = int(highest.rsplit("-", 1)[1]) + 1 if highest else 1
    return f"T-{year}-{number:05d}"
