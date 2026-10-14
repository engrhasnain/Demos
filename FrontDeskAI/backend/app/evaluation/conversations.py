"""The contacts the containment rate is measured on.

Built from the mix a real service desk sees rather than from whatever the
desk happens to be good at: about half "where is my order", then returns,
quotes and technician visits, and a tail of things it should not pretend
to handle.

Two of these are in on purpose to be *failed*:

* a question nobody has built a tool for, which has to go to a person;
* a customer who asks for a person straight away, who must get one.

A suite with no failures in it measures nothing. If the containment rate
came out at a hundred per cent the suite would be the problem.

Every case is generated from real rows, so the order numbers and part
numbers in the messages are ones the desk can actually look up.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import intents
from ..models import Order, Quotation


@dataclass(slots=True)
class Case:
    name: str
    messages: list[str]
    expect_intent: str
    #: Whether a working desk ought to finish this one on its own.
    should_contain: bool
    #: Verify as the customer who owns this order first.
    verify_with: Order | None = None
    note: str = ""


#: The mix. Shares add to one; the counts follow from the sample size.
MIX: list[tuple[str, float]] = [
    ("order_status", 0.46),
    ("return_request", 0.18),
    ("quote_status", 0.12),
    ("book_visit", 0.10),
    ("opening_hours", 0.06),
    ("human", 0.05),
    ("unknown", 0.03),
]

ORDER_PHRASINGS = [
    "Where is my order {order}?",
    "Hi, can you tell me the status of {order}?",
    "{order} — has it shipped yet?",
    "請問 {order} 到哪了？",
    "Any update on {order}? It was due last week.",
    "tracking for {order} please",
]

RETURN_PHRASINGS = [
    "The {part} arrived cracked, the box was crushed. I need to send it back.",
    "We got the wrong part, {part} is not what we ordered.",
    "{part} snapped after two weeks. Can we return it?",
    "{part} 外箱壓壞了，裡面也有破損，要退貨。",
    "Short delivered on {part}, only half the quantity arrived.",
]

QUOTE_PHRASINGS = [
    "What happened to quotation {quote}?",
    "Is {quote} still valid?",
    "報價單 {quote} 的狀況如何？",
]

VISIT_PHRASINGS = [
    "Can you send a technician out to us?",
    "We need an engineer on site this week.",
    "需要預約技師到府維修。",
]

HOURS_PHRASINGS = [
    "What are your opening hours?",
    "Are you open right now?",
    "營業時間是幾點到幾點？",
]

HUMAN_PHRASINGS = [
    "I want to speak to a real person please.",
    "Can you put me through to someone?",
    "請轉接真人客服。",
]

#: Things the desk has no tool for. It must hand these over, not improvise.
UNKNOWN_PHRASINGS = [
    "Can you change the bank account you pay our refunds into?",
    "What is your company registration number and VAT position in Germany?",
    "We want to become a distributor in Vietnam. Who do we talk to?",
    "Can I get a 40 per cent discount if I order ten thousand?",
]


def suite(session: Session, count: int = 120, seed: int = 7) -> list[Case]:
    """Build the measured set from rows that actually exist."""
    rng = random.Random(seed)

    orders = list(
        session.scalars(
            select(Order).where(Order.status.in_(("despatched", "delivered"))).limit(400)
        )
    )
    quotes = list(session.scalars(select(Quotation).limit(200)))
    if not orders:
        return []

    cases: list[Case] = []
    for intent, share in MIX:
        wanted = max(1, round(count * share))
        for _ in range(wanted):
            order = orders[rng.randrange(len(orders))]
            part = order.lines[0].part_code if order.lines else "HT-SHC-M8X030-12.9-ZNB"

            if intent == "order_status":
                cases.append(
                    Case(
                        name="where is my order",
                        messages=[
                            rng.choice(ORDER_PHRASINGS).format(order=order.number)
                        ],
                        expect_intent=intents.ORDER_STATUS,
                        should_contain=True,
                        verify_with=order,
                    )
                )
            elif intent == "return_request":
                cases.append(
                    Case(
                        name="return or fault",
                        messages=[rng.choice(RETURN_PHRASINGS).format(part=part)],
                        expect_intent=intents.RETURN_REQUEST,
                        # A return is always approved by a person. It is a
                        # success when it reaches one, and it still counts
                        # against containment, which is the honest way round.
                        should_contain=False,
                        verify_with=order,
                        note="a person approves every return",
                    )
                )
            elif intent == "quote_status" and quotes:
                quote = quotes[rng.randrange(len(quotes))]
                owning = session.scalar(
                    select(Order).where(Order.customer_id == quote.customer_id).limit(1)
                )
                cases.append(
                    Case(
                        name="quote status",
                        messages=[
                            rng.choice(QUOTE_PHRASINGS).format(quote=quote.reference)
                        ],
                        expect_intent=intents.QUOTE_STATUS,
                        should_contain=bool(owning),
                        verify_with=owning,
                    )
                )
            elif intent == "book_visit":
                cases.append(
                    Case(
                        name="technician visit",
                        messages=[rng.choice(VISIT_PHRASINGS)],
                        expect_intent=intents.BOOK_VISIT,
                        # Offering slots is not finishing. It finishes when
                        # the customer takes one, which the suite does not.
                        should_contain=False,
                        verify_with=order,
                    )
                )
            elif intent == "opening_hours":
                cases.append(
                    Case(
                        name="opening hours",
                        messages=[rng.choice(HOURS_PHRASINGS)],
                        expect_intent=intents.OPENING_HOURS,
                        should_contain=True,
                    )
                )
            elif intent == "human":
                cases.append(
                    Case(
                        name="asked for a person",
                        messages=[rng.choice(HUMAN_PHRASINGS)],
                        expect_intent=intents.HUMAN,
                        should_contain=False,
                        note="must reach a person, and counts against containment",
                    )
                )
            else:
                cases.append(
                    Case(
                        name="nothing built for this",
                        messages=[rng.choice(UNKNOWN_PHRASINGS)],
                        expect_intent=intents.UNKNOWN,
                        should_contain=False,
                        note="improvising here would be worse than handing over",
                    )
                )

    rng.shuffle(cases)
    return cases[:count]
