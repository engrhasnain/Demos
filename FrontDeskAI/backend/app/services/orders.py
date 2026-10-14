"""Where is my order.

Half the contacts, and the one the desk should finish on its own. The
interesting part is not looking up a row, it is what to do when the two
systems disagree.

The business system says despatched on Tuesday. The carrier says a label
was created on Tuesday and nothing since. Those are not the same thing: a
label is a printed sticker, not a collection. A front desk that picks one
and states it confidently will tell a customer their goods are on the way
when they are sitting on a bench in the warehouse.

So both are shown, the difference is named, and when the gap is large
enough to matter the conversation goes to a person with the gap already
written down. Nobody has to be told twice.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..clock import aware
from ..models import CarrierEvent, Order
from .isolation import Scope, owned_by, record

#: How the carrier's codes read to a person.
CARRIER_WORDS: dict[str, str] = {
    "label_created": "label printed",
    "collected": "collected from us",
    "in_transit": "in transit",
    "customs": "in customs",
    "out_for_delivery": "out for delivery",
    "delivered": "delivered",
    "exception": "held up",
}

#: How far the carrier has actually got. Used to compare against what the
#: business system claims, in one direction only: the carrier can be behind
#: the system, and that is the case worth catching.
PROGRESS: dict[str, int] = {
    "label_created": 1,
    "collected": 2,
    "in_transit": 3,
    "customs": 3,
    "out_for_delivery": 4,
    "delivered": 5,
    "exception": 2,
}

SYSTEM_PROGRESS: dict[str, int] = {
    "open": 0,
    "picking": 1,
    "despatched": 3,
    "delivered": 5,
    "cancelled": 0,
}

#: A label printed and nothing since, for longer than this, is a problem
#: rather than a lag.
STALE_LABEL_HOURS = 36


@dataclass(slots=True)
class Disagreement:
    kind: str
    summary: str
    system_says: str
    carrier_says: str
    hours_apart: float = 0.0
    needs_a_person: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "summary": self.summary,
            "system_says": self.system_says,
            "carrier_says": self.carrier_says,
            "hours_apart": round(self.hours_apart, 1),
            "needs_a_person": self.needs_a_person,
        }


@dataclass(slots=True)
class OrderView:
    order: Order
    latest: CarrierEvent | None
    events: list[CarrierEvent] = field(default_factory=list)
    disagreement: Disagreement | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "number": self.order.number,
            "status": self.order.status,
            "placed_on": self.order.placed_on.isoformat(),
            "promised_on": (
                self.order.promised_on.isoformat() if self.order.promised_on else None
            ),
            "despatched_on": (
                self.order.despatched_on.isoformat() if self.order.despatched_on else None
            ),
            "delivered_on": (
                self.order.delivered_on.isoformat() if self.order.delivered_on else None
            ),
            "carrier": self.order.carrier,
            "tracking_number": self.order.tracking_number,
            "total": str(self.order.total),
            "currency": self.order.currency,
            "lines": [
                {
                    "line_number": line.line_number,
                    "part_code": line.part_code,
                    "description": line.description,
                    "quantity": line.quantity,
                    "lot_number": line.lot_number,
                }
                for line in self.order.lines
            ],
            "carrier_events": [
                {
                    "occurred_at": event.occurred_at.isoformat(),
                    "code": event.code,
                    "says": CARRIER_WORDS.get(event.code, event.code),
                    "place": event.place,
                    "note": event.note,
                }
                for event in self.events
            ],
            "latest": (
                CARRIER_WORDS.get(self.latest.code, self.latest.code)
                if self.latest
                else None
            ),
            "disagreement": self.disagreement.to_dict() if self.disagreement else None,
        }


def _compare(order: Order, latest: CarrierEvent | None, now: dt.datetime) -> Disagreement | None:
    """Do the two systems tell the same story?"""
    if not order.tracking_number:
        if order.status == "despatched":
            return Disagreement(
                kind="no_tracking",
                summary="Marked as despatched here, but there is no tracking number yet.",
                system_says="despatched",
                carrier_says="nothing on record",
                needs_a_person=True,
            )
        return None

    if latest is None:
        return Disagreement(
            kind="carrier_silent",
            summary="The carrier has nothing against this tracking number yet.",
            system_says=order.status,
            carrier_says="nothing on record",
            needs_a_person=order.status == "despatched",
        )

    system = SYSTEM_PROGRESS.get(order.status, 0)
    carrier = PROGRESS.get(latest.code, 0)
    hours = (now - aware(latest.occurred_at)).total_seconds() / 3600.0

    if latest.code == "exception":
        return Disagreement(
            kind="carrier_exception",
            summary=f"The carrier has it held up: {latest.note or 'no reason given'}.",
            system_says=order.status,
            carrier_says=CARRIER_WORDS["exception"],
            hours_apart=hours,
            needs_a_person=True,
        )

    if latest.code == "label_created" and system >= 3:
        # The case this whole module exists for.
        return Disagreement(
            kind="label_only",
            summary=(
                "Our system has it as despatched, but the carrier has only "
                "printed the label, which means they have not collected it yet."
            ),
            system_says="despatched",
            carrier_says=CARRIER_WORDS["label_created"],
            hours_apart=hours,
            needs_a_person=hours >= STALE_LABEL_HOURS,
        )

    if carrier < system - 1:
        return Disagreement(
            kind="carrier_behind",
            summary="The carrier's record is behind ours.",
            system_says=order.status,
            carrier_says=CARRIER_WORDS.get(latest.code, latest.code),
            hours_apart=hours,
            needs_a_person=hours >= STALE_LABEL_HOURS,
        )

    if carrier == 5 and system < 5:
        return Disagreement(
            kind="carrier_ahead",
            summary="The carrier says it was delivered; our system has not caught up.",
            system_says=order.status,
            carrier_says=CARRIER_WORDS["delivered"],
            hours_apart=hours,
            needs_a_person=False,
        )

    return None


def recent(session: Session, scope: Scope, limit: int = 5) -> list[Order]:
    """This customer's latest orders. Never anybody else's."""
    rows = list(
        session.scalars(
            owned_by(select(Order), Order.customer_id, scope)
            .order_by(Order.placed_on.desc())
            .limit(limit)
        )
    )
    record(session, tool="recent_orders", scope=scope, rows=len(rows))
    return rows


def look_up(
    session: Session,
    scope: Scope,
    *,
    number: str | None = None,
    now: dt.datetime | None = None,
) -> OrderView | None:
    """One order, if it is this customer's.

    An order that exists and belongs to somebody else returns the same
    nothing as an order that does not exist. Telling those apart is how
    somebody discovers which order numbers are real.
    """
    now = now or dt.datetime.now(dt.timezone.utc)

    query = owned_by(select(Order), Order.customer_id, scope)
    if number:
        wanted = number.strip().upper().replace(" ", "")
        query = query.where(Order.number.ilike(f"%{wanted}%"))
    order = session.scalar(query.order_by(Order.placed_on.desc()).limit(1))

    if order is None:
        record(
            session,
            tool="order_status",
            scope=scope,
            arguments={"number": number},
            allowed=True,
            rows=0,
            refusal="no order of this customer's matches",
        )
        return None

    events = list(
        session.scalars(
            select(CarrierEvent)
            .where(CarrierEvent.tracking_number == order.tracking_number)
            .order_by(CarrierEvent.occurred_at)
        )
        if order.tracking_number
        else []
    )
    latest = events[-1] if events else None

    record(
        session,
        tool="order_status",
        scope=scope,
        arguments={"number": order.number},
        rows=1,
    )
    return OrderView(
        order=order,
        latest=latest,
        events=events,
        disagreement=_compare(order, latest, now),
    )
