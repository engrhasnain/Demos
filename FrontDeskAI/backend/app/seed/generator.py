"""The generated company, from the front desk's side of it.

Twelve hundred trade customers, their orders, and the carrier's version of
events — which is deliberately not always the same as ours, because the
cases where the two systems disagree are the ones a front desk has to be
honest about rather than confident about.

Technicians get skills, a base city and a van with particular parts in it,
so the scheduler has something real to refuse.
"""

from __future__ import annotations

import datetime as dt
import logging
import random
import time
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..clock import today as today_date
from ..models import (
    AccessLog,
    CarrierEvent,
    Contact,
    Conversation,
    Customer,
    EvaluationRun,
    Order,
    OrderLine,
    Quotation,
    ReturnRequest,
    Technician,
    Ticket,
    Turn,
    User,
    Visit,
)
from ..security import hash_password

DEMO_PASSWORD = "demo1234"

STAFF: list[dict[str, str]] = [
    {"email": "mei.lin@hengtai-industrial.example", "full_name": "Mei Lin", "role": "agent"},
    {"email": "david.okafor@hengtai-industrial.example", "full_name": "David Okafor", "role": "agent"},
    {"email": "yuki.sato@hengtai-industrial.example", "full_name": "Yuki Sato", "role": "supervisor"},
    {"email": "admin@hengtai-industrial.example", "full_name": "System administrator", "role": "administrator"},
]

COMPANY_WORDS = [
    "Precision", "Industrial", "Machinery", "Automation", "Engineering",
    "Tooling", "Hydraulics", "Pneumatics", "Fabrication", "Assembly",
    "Systems", "Components", "Works", "Technologies", "Manufacturing",
]
COMPANY_NAMES = [
    "Chen", "Lin", "Wang", "Huang", "Wu", "Hsu", "Yang", "Kuo",
    "Northwind", "Cascade", "Ironside", "Brightwater", "Granite", "Redstone",
    "Meridian", "Bluefin", "Crosshill", "Ardent", "Vantage", "Kestrel",
]
TW_CITIES = ["Taichung", "Tainan", "Kaohsiung", "Changhua", "Taoyuan", "Hsinchu", "New Taipei"]
US_CITIES = ["Cleveland", "Rockford", "Houston", "Ontario", "Greenville", "Toledo"]

PARTS: list[tuple[str, str]] = [
    ("HT-SHC-M8X030-12.9-ZNB", "Socket head cap screw ISO 4762 M8x30 class 12.9"),
    ("HT-HXB-M12X060-8.8-HDG", "Hexagon head bolt ISO 4017 M12x60 class 8.8"),
    ("HT-HXN-M12-10-ZNB", "Hexagon nut ISO 4032 M12 class 10"),
    ("HT-WSH-M12-200HV-ZNB", "Flat washer ISO 7089 M12 200 HV"),
    ("HT-BRG-6204-2RS-C3", "Deep groove ball bearing 6204-2RS C3"),
    ("HT-BRG-6206-2RS-CN", "Deep groove ball bearing 6206-2RS"),
    ("HT-CYL-032-0100-DA", "Pneumatic cylinder 32mm bore, 100mm stroke"),
    ("HT-VLV-5201-025", "Solenoid valve 5/2 single G1/4 24V"),
    ("HT-FIT-G14-8MM-PI", "Push-in fitting G1/4 to 8mm"),
    ("HT-ORG-0220-NBR70", "O-ring 22.0mm NBR70"),
]

SKILLS = ["pneumatics", "bearings", "hydraulics", "electrical", "fasteners"]
CARRIERS = ["Hsinchu Logistics", "T-Cat", "Kerry TJ", "FedEx", "DHL"]

ProgressCallback = Callable[[str, int, int], None]

log = logging.getLogger("frontdesk")


class Builder:
    def __init__(
        self,
        session: Session,
        *,
        customer_target: int = 1200,
        order_target: int = 3600,
        seed: int = 20261005,
        progress: ProgressCallback | None = None,
        deadline: float | None = None,
    ) -> None:
        self.session = session
        self.customer_target = customer_target
        self.order_target = order_target
        self.random = random.Random(seed)
        self._progress = progress
        self.counts: dict[str, int] = {}
        self.today = today_date()
        # A `time.monotonic()` instant past which the heavier, optional
        # stages below are skipped rather than run. The demo accounts (from
        # `_staff`, which always runs first) are what sign-in depends on, so
        # tripping the budget loses sample business data, never the ability
        # to log in. `None` means no budget - the manual "load demo data"
        # endpoint for staff still gets the full, uncapped load.
        self.deadline = deadline
        self.timed_out = False

    def progress(self, stage: str, done: int, total: int) -> None:
        if self._progress:
            self._progress(stage, done, total)

    def _over_budget(self, stage: str) -> bool:
        if self.deadline is None or time.monotonic() <= self.deadline:
            return False
        self.timed_out = True
        log.warning(
            "Demo data load exceeded its time budget after '%s'; stopping "
            "here so the request can proceed with what was loaded so far "
            "(the demo accounts from 'staff' are already in place).",
            stage,
        )
        return True

    def build(self) -> dict[str, int]:
        self._clear()
        # Accounts first: as soon as this stage commits, sign-in works, even
        # if every stage after it is cut short by the time budget.
        self._staff()
        if self._over_budget("staff"):
            return self.counts
        customers = self._customers()
        if self._over_budget("customers"):
            return self.counts
        self._orders(customers)
        if self._over_budget("orders"):
            return self.counts
        self._quotations(customers)
        if self._over_budget("quotations"):
            return self.counts
        self._technicians()
        self.session.flush()
        return self.counts

    def _clear(self) -> None:
        for model in (
            Turn, AccessLog, Ticket, Conversation, Visit, Technician,
            ReturnRequest, CarrierEvent, OrderLine, Order, Quotation,
            Contact, Customer, EvaluationRun, User,
        ):
            self.session.execute(delete(model))
        self.session.flush()

    def _staff(self) -> None:
        password = hash_password(DEMO_PASSWORD)
        for person in STAFF:
            self.session.add(User(password_hash=password, **person))
        self.session.flush()
        self.counts["staff"] = len(STAFF)

    def _customers(self) -> list[Customer]:
        rows: list[Customer] = []
        # About a third in the United States, which is where the overnight
        # contacts come from and why the reply times have to be honest.
        countries = (["TW"] * 6 + ["US"] * 3 + ["JP"]) * 200
        for index in range(self.customer_target):
            country = countries[index]
            name = (
                f"{self.random.choice(COMPANY_NAMES)} "
                f"{self.random.choice(COMPANY_WORDS)} "
                + ("Co., Ltd." if country == "TW" else "Inc.")
            )
            city = self.random.choice(TW_CITIES if country == "TW" else US_CITIES)
            customer = Customer(
                code=f"C-{10000 + index}",
                name=name,
                country=country,
                city=city,
                language="zh" if country == "TW" and self.random.random() < 0.65 else "en",
                is_trade_account=True,
                warranty_months=self.random.choice([12, 12, 12, 18, 24]),
            )
            self.session.add(customer)
            rows.append(customer)
        self.session.flush()

        contacts: list[dict[str, Any]] = []
        given = ["Wei", "Mei", "Jun", "Ling", "Hao", "Ana", "Tom", "Sara", "Raj", "Yu"]
        family = ["Chen", "Lin", "Wang", "Huang", "Smith", "Jones", "Patel", "Garcia"]
        for customer in rows:
            for which in range(self.random.randint(1, 2)):
                first = self.random.choice(given)
                last = self.random.choice(family)
                contacts.append(
                    {
                        "customer_id": customer.id,
                        "full_name": f"{first} {last}",
                        "email": (
                            f"{first.lower()}.{last.lower()}{customer.id}"
                            f"@{customer.code.lower()}.example"
                        ),
                        "telephone": (
                            f"+886 4 {self.random.randint(2000, 2999)} "
                            f"{self.random.randint(1000, 9999)}"
                            if customer.country == "TW"
                            else f"+1 {self.random.randint(200, 989)} "
                            f"{self.random.randint(100, 999)} {self.random.randint(1000, 9999)}"
                        ),
                    }
                )
        self.session.bulk_insert_mappings(Contact, contacts)
        self.session.flush()

        self.counts["customers"] = len(rows)
        self.counts["contacts"] = len(contacts)
        return rows

    def _orders(self, customers: list[Customer]) -> None:
        orders: list[Order] = []
        lines: list[dict[str, Any]] = []
        events: list[dict[str, Any]] = []

        for index in range(self.order_target):
            customer = customers[self.random.randrange(len(customers))]
            placed = self.today - dt.timedelta(days=self.random.randint(1, 120))
            carrier = self.random.choice(CARRIERS)
            tracking = f"{carrier[:2].upper()}{self.random.randint(10**9, 10**10 - 1)}"

            # The shape of the book: most delivered, some moving, a few
            # that have only just been placed.
            age = (self.today - placed).days
            roll = self.random.random()
            if age > 30 and roll < 0.82:
                status, despatched = "delivered", placed + dt.timedelta(days=self.random.randint(2, 7))
                delivered = despatched + dt.timedelta(days=self.random.randint(2, 12))
            elif age > 5 and roll < 0.94:
                status = "despatched"
                despatched = placed + dt.timedelta(days=self.random.randint(2, 7))
                delivered = None
            else:
                status, despatched, delivered = "open", None, None

            order = Order(
                number=f"SO-{20000 + index}",
                customer_id=customer.id,
                placed_on=placed,
                promised_on=placed + dt.timedelta(days=self.random.randint(7, 28)),
                status=status,
                despatched_on=despatched,
                delivered_on=delivered,
                carrier=carrier if despatched else "",
                tracking_number=tracking if despatched else "",
                currency="TWD" if customer.country == "TW" else "USD",
            )
            orders.append(order)
        self.session.add_all(orders)
        self.session.flush()

        for order in orders:
            total = Decimal("0")
            for line_number in range(1, self.random.randint(2, 5)):
                part_code, description = PARTS[self.random.randrange(len(PARTS))]
                quantity = self.random.choice([50, 100, 200, 500, 1000, 2000])
                price = Decimal(str(round(self.random.uniform(1.0, 1500.0), 2)))
                total += price * quantity
                lines.append(
                    {
                        "order_id": order.id,
                        "line_number": line_number,
                        "part_code": part_code,
                        "description": description,
                        "quantity": quantity,
                        "lot_number": f"L{self.random.randint(10000, 99999)}",
                        "unit_price": price,
                    }
                )
            order.total = total

            if not order.tracking_number:
                continue

            # --- the carrier's version ---------------------------------
            moment = dt.datetime.combine(
                order.despatched_on, dt.time(self.random.randint(9, 17)),
                tzinfo=dt.timezone.utc,
            )
            story: list[tuple[str, str]] = [("label_created", "Taichung")]
            roll = self.random.random()

            if roll < 0.08:
                # The case the whole product is built around: our system
                # says despatched, the carrier printed a label and stopped.
                pass
            elif roll < 0.12:
                story += [("collected", "Taichung"), ("exception", "Taoyuan")]
            elif order.delivered_on:
                story += [
                    ("collected", "Taichung"),
                    ("in_transit", "Taoyuan"),
                    ("out_for_delivery", order.customer.city),
                    ("delivered", order.customer.city),
                ]
            else:
                story += [("collected", "Taichung"), ("in_transit", "Taoyuan")]
                if order.customer.country != "TW":
                    story.append(("customs", "Taoyuan"))

            for code, place in story:
                events.append(
                    {
                        "tracking_number": order.tracking_number,
                        "occurred_at": moment,
                        "code": code,
                        "place": place,
                        "note": (
                            "Address could not be found"
                            if code == "exception"
                            else ""
                        ),
                    }
                )
                moment += dt.timedelta(hours=self.random.randint(6, 40))

        self.session.bulk_insert_mappings(OrderLine, lines)
        self.session.bulk_insert_mappings(CarrierEvent, events)
        self.session.flush()
        self.counts["orders"] = len(orders)
        self.counts["order_lines"] = len(lines)
        self.counts["carrier_events"] = len(events)

    def _quotations(self, customers: list[Customer]) -> None:
        rows: list[dict[str, Any]] = []
        for index in range(self.order_target // 4):
            customer = customers[self.random.randrange(len(customers))]
            sent = self.today - dt.timedelta(days=self.random.randint(1, 60))
            rows.append(
                {
                    "reference": f"RQ-{30000 + index}",
                    "customer_id": customer.id,
                    "status": self.random.choice(
                        ["sent", "sent", "sent", "won", "lost", "expired"]
                    ),
                    "sent_on": sent,
                    "valid_until": sent + dt.timedelta(days=14),
                    "total": Decimal(str(round(self.random.uniform(5_000, 900_000), 2))),
                    "currency": "TWD" if customer.country == "TW" else "USD",
                    "lines": self.random.randint(3, 40),
                }
            )
        self.session.bulk_insert_mappings(Quotation, rows)
        self.session.flush()
        self.counts["quotations"] = len(rows)

    def _technicians(self) -> None:
        names = [
            "Kai Wu", "Ping Hsu", "Jian Lo", "Mei Chang", "Hao Tseng", "Ting Yeh",
        ]
        rows: list[Technician] = []
        for index, name in enumerate(names):
            skills = self.random.sample(SKILLS, self.random.randint(2, 3))
            stock = [
                PARTS[i][0]
                for i in self.random.sample(range(len(PARTS)), self.random.randint(3, 6))
            ]
            rows.append(
                Technician(
                    code=f"T-{index + 1:02d}",
                    full_name=name,
                    base_city=TW_CITIES[index % len(TW_CITIES)],
                    skills=skills,
                    van_stock=stock,
                    is_active=True,
                )
            )
        self.session.add_all(rows)
        self.session.flush()
        self.counts["technicians"] = len(rows)


def build_demo_data(
    session: Session,
    *,
    customer_target: int = 1200,
    order_target: int = 3600,
    progress: ProgressCallback | None = None,
    deadline: float | None = None,
) -> dict[str, int]:
    return Builder(
        session,
        customer_target=customer_target,
        order_target=order_target,
        progress=progress,
        deadline=deadline,
    ).build()


def build_sample_conversations(session: Session) -> dict[str, int]:
    """A handful of conversations, so the desk does not open on an empty room.

    Just enough to show every screen: a visitor who never proved who they
    are, a verified customer who gets a real answer, a return that a person
    has to approve (the one handover example), and a technician visit that
    is actually booked. Uses the real conversation engine throughout, so
    this is not sample data pretending to be one - it is what the engine
    actually produces, the same way a live contact would.
    """
    from ..services import desk, identity

    orders = list(
        session.scalars(
            select(Order)
            .where(Order.status.in_(("delivered", "despatched")))
            .order_by(Order.id)
            .limit(5)
        )
    )
    eligible = [order for order in orders if order.customer.contacts]
    if not eligible:
        return {"conversations": 0}
    mine = eligible[0]
    contact = mine.customer.contacts[0]
    counts = {"conversations": 0, "bookings": 0}

    def opened(reference: str, channel: str = "web") -> Conversation:
        conversation = Conversation(reference=reference, channel=channel, status="open")
        session.add(conversation)
        session.flush()
        counts["conversations"] += 1
        return conversation

    # 1. A visitor who asks, and never proves who they are.
    unverified = opened("DEMO-0001")
    desk.handle(session, unverified, f"Where is my order {mine.number}?")

    # 2. A verified customer, answered from their own live records.
    verified = opened("DEMO-0002")
    desk.handle(session, verified, f"Where is my order {mine.number}?")
    identity.verify(session, verified, order_number=mine.number, email=contact.email)
    desk.handle(session, verified, f"Where is my order {mine.number}?")

    # 3. A return with a photograph: triaged in code, then handed to a
    #    person to approve. The one handover example.
    returning = opened("DEMO-0003")
    identity.verify(session, returning, order_number=mine.number, email=contact.email)
    desk.handle(
        session,
        returning,
        "The part arrived cracked, I need to return it.",
        attachment="IMG_demo.jpg",
    )

    # 4 and 5. Two technician visits, actually booked - the couple of
    #    bookings. A second customer where one exists, so the diary does
    #    not show the same name twice.
    second = eligible[1] if len(eligible) > 1 else mine
    second_contact = second.customer.contacts[0]
    for index, (order, order_contact, channel) in enumerate(
        ((mine, contact, "line"), (second, second_contact, "web")), start=4
    ):
        visiting = opened(f"DEMO-{index:04d}", channel=channel)
        identity.verify(session, visiting, order_number=order.number, email=order_contact.email)
        reply = desk.handle(session, visiting, "Can someone come and look at it?")
        slots = (reply.tool_result or {}).get("slots") or []
        if slots:
            booked = desk.take_slot(session, visiting, slots[0]["key"])
            if booked.tool_result.get("reference"):
                counts["bookings"] += 1

    session.flush()
    return counts
