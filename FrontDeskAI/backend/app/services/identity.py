"""Proving who somebody is, before showing them anything.

Two facts, not one. An order number on its own is guessable and gets
forwarded in emails; an email address on its own is public. Together they
are a reasonable bar for "where is my order", which is what this is for. It
is not a bar for changing a bank account, and this product never offers to.

Three things make the difference between a check and a formality:

**A wrong answer costs a try.** Three tries and the conversation is locked
out for half an hour. Without that, the front desk is an oracle: ask it
about ten thousand order numbers and watch which ones it recognises.

**A wrong answer is the same as an unknown one.** "That order does not
match" and "there is no such order" are one message. Telling them apart is
how somebody works out which order numbers are real.

**The attempt is recorded either way.**
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..clock import aware
from ..config import settings
from ..models import Contact, Conversation, Customer, Order
from . import isolation

#: One message for every failure, whatever the cause.
SAME_ANSWER = (
    "Those details do not match an order on our system. Please check the "
    "order number and the email address it was placed with."
)


@dataclass(slots=True)
class Verification:
    ok: bool
    message: str
    customer_id: int | None = None
    contact_id: int | None = None
    attempts_left: int = 0
    locked: bool = False


def _normalise_email(value: str) -> str:
    return unicodedata.normalize("NFKC", (value or "")).strip().casefold()


def _normalise_order(value: str) -> str:
    """``so-10422``, ``SO 10422`` and ``10422`` are one order number."""
    cleaned = re.sub(r"[^A-Za-z0-9]", "", (value or "").upper())
    cleaned = re.sub(r"^(SO|ORD|ORDER)", "", cleaned)
    return cleaned.lstrip("0") or cleaned


def is_locked(conversation: Conversation, now: dt.datetime | None = None) -> bool:
    now = now or dt.datetime.now(dt.timezone.utc)
    locked = aware(conversation.locked_until)
    return bool(locked and locked > now)


def is_verified(conversation: Conversation, now: dt.datetime | None = None) -> bool:
    if conversation.verified_at is None or conversation.customer_id is None:
        return False
    now = now or dt.datetime.now(dt.timezone.utc)
    expires = aware(conversation.verified_at) + dt.timedelta(
        minutes=settings.session_minutes
    )
    return now < expires


def verify(
    session: Session,
    conversation: Conversation,
    *,
    order_number: str,
    email: str,
    now: dt.datetime | None = None,
) -> Verification:
    """Check the pair, and spend a try if it is wrong."""
    now = now or dt.datetime.now(dt.timezone.utc)

    if is_locked(conversation, now):
        isolation.record(
            session,
            tool="verify",
            conversation=conversation,
            arguments={"order_number": order_number},
            allowed=False,
            refusal="locked out",
        )
        return Verification(
            ok=False,
            message=(
                "Too many attempts. Please wait a little, or ask for a person "
                "and we will sort it out."
            ),
            locked=True,
        )

    wanted_order = _normalise_order(order_number)
    wanted_email = _normalise_email(email)

    found = None
    if wanted_order and wanted_email:
        # Normalised on both sides, so punctuation does not decide whether
        # somebody gets through.
        for order in session.scalars(
            select(Order).where(
                func.replace(func.replace(func.upper(Order.number), "-", ""), " ", "").like(
                    f"%{wanted_order}"
                )
            ).limit(25)
        ):
            if _normalise_order(order.number) != wanted_order:
                continue
            for contact in order.customer.contacts:
                if _normalise_email(contact.email) == wanted_email:
                    found = (order, contact)
                    break
            if found:
                break

    if not found:
        conversation.verification_attempts += 1
        left = max(0, settings.verification_attempts - conversation.verification_attempts)
        if left == 0:
            conversation.locked_until = now + dt.timedelta(minutes=settings.lockout_minutes)
        session.flush()
        isolation.record(
            session,
            tool="verify",
            conversation=conversation,
            arguments={"order_number": order_number, "email": email},
            allowed=False,
            refusal=f"no match, {left} attempts left",
        )
        return Verification(
            ok=False,
            message=SAME_ANSWER,
            attempts_left=left,
            locked=left == 0,
        )

    order, contact = found
    conversation.customer_id = order.customer_id
    conversation.contact_id = contact.id
    conversation.verified_at = now
    conversation.verification_attempts = 0
    conversation.locked_until = None
    if not conversation.language or conversation.language == "en":
        conversation.language = order.customer.language
    session.flush()

    isolation.record(
        session,
        tool="verify",
        conversation=conversation,
        scope=isolation.scope_for(conversation),
        arguments={"order_number": order.number},
        allowed=True,
        rows=1,
    )
    return Verification(
        ok=True,
        message=f"Thank you, {contact.full_name.split()[0]}.",
        customer_id=order.customer_id,
        contact_id=contact.id,
    )


def remember_line_user(
    session: Session, conversation: Conversation, line_user_id: str
) -> None:
    """Tie a LINE account to the contact, so they verify once, not every time.

    Only after they have proved who they are. A LINE identifier arriving at
    the webhook proves the message came from that account and nothing more.
    """
    if not line_user_id or conversation.contact_id is None:
        return
    contact = session.get(Contact, conversation.contact_id)
    if contact is not None and not contact.line_user_id:
        contact.line_user_id = line_user_id
        session.flush()


def contact_for_line_user(session: Session, line_user_id: str) -> Contact | None:
    if not line_user_id:
        return None
    return session.scalar(select(Contact).where(Contact.line_user_id == line_user_id))
