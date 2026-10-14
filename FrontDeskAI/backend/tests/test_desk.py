"""The conversation itself: understanding, answering, and handing over."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import select

from app.clock import aware
from app.config import settings
from app.domain import intents, language
from app.models import CarrierEvent, Order, ReturnRequest, Technician, Visit
from app.services import desk, escalation, identity, isolation, returns, scheduling


class TestUnderstanding:
    @pytest.mark.parametrize(
        "message,expected",
        [
            ("Where is my order SO-20004?", intents.ORDER_STATUS),
            ("has it shipped yet", intents.ORDER_STATUS),
            ("請問 SO-20004 到哪了？", intents.ORDER_STATUS),
            ("The part arrived cracked, I want to return it", intents.RETURN_REQUEST),
            ("退貨申請", intents.RETURN_REQUEST),
            ("Is quotation RQ-30001 still valid?", intents.QUOTE_STATUS),
            ("Can you send a technician?", intents.BOOK_VISIT),
            ("需要預約技師到府", intents.BOOK_VISIT),
            ("What are your opening hours?", intents.OPENING_HOURS),
            ("I want to speak to a human", intents.HUMAN),
            ("請轉接真人", intents.HUMAN),
        ],
    )
    def test_it_picks_the_right_one(self, message, expected):
        assert intents.read(message).intent == expected

    def test_asking_for_a_person_beats_everything_else(self):
        """A customer who says it twice does not want a third answer."""
        read = intents.read(
            "Where is my order SO-20004? Actually just give me a real person."
        )
        assert read.intent == intents.HUMAN

    def test_a_greeting_with_a_question_is_the_question(self):
        assert intents.read("Hi, where is my order?").intent == intents.ORDER_STATUS

    def test_an_intent_it_has_no_tool_for_is_not_invented(self):
        read = intents.read("Can you change our bank details for refunds?")
        assert read.intent == intents.UNKNOWN
        assert not read.can_resolve

    def test_only_intents_on_the_list_exist(self):
        assert intents.is_known(intents.ORDER_STATUS)
        assert not intents.is_known("transfer_money")


class TestLanguage:
    def test_any_chinese_means_a_chinese_reply(self):
        assert language.detect("請問 SO-20004 到哪了？") == language.CHINESE
        assert language.detect("where is SO-20004") == language.ENGLISH

    def test_part_numbers_survive_being_masked(self):
        text = "HT-SHC-M8X030-12.9-ZNB is cracked, from order SO-20004"
        protected = language.protect(text)
        assert "HT-SHC-M8X030-12.9-ZNB" not in protected.masked
        assert protected.restore(protected.masked) == text

    def test_a_dropped_part_number_is_detected(self):
        """Two part codes one character apart are two different parts."""
        said = "Please quote HT-SHC-M8X030-12.9-ZNB"
        assert language.survived(said, "We can quote that") == [
            "HT-SHC-M8X030-12.9-ZNB"
        ]
        assert language.survived(said, "HT-SHC-M8X030-12.9-ZNB is in stock") == []


class TestAnsweringOrders:
    def test_an_unverified_visitor_is_asked_to_verify(self, session, conversation):
        reply = desk.handle(session, conversation, "Where is my order?")
        assert reply.needs_verification
        assert not reply.tool_result.get("number")

    def test_a_verified_one_gets_the_answer(self, session, verified, orders):
        mine, _ = orders
        reply = desk.handle(session, verified, f"Where is my order {mine.number}?")
        assert reply.tool == "order_status"
        assert mine.number in reply.text

    def test_the_two_systems_disagreeing_is_said_out_loud(self, session, verified, orders):
        """A label printed is not a collection, and saying so is the point."""
        mine, _ = orders
        mine.status = "despatched"
        mine.tracking_number = mine.tracking_number or "TT1234567890"
        session.query(CarrierEvent).filter(
            CarrierEvent.tracking_number == mine.tracking_number
        ).delete()
        session.add(
            CarrierEvent(
                tracking_number=mine.tracking_number,
                occurred_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=4),
                code="label_created",
                place="Taichung",
            )
        )
        session.flush()

        reply = desk.handle(session, verified, f"Where is {mine.number}?")
        assert "label" in reply.text.lower()
        # Four days of silence is a person's problem, not a reassurance.
        assert reply.escalated
        assert not reply.resolved


class TestReturns:
    def test_the_desk_proposes_and_never_approves(self, session, verified, orders):
        mine, _ = orders
        reply = desk.handle(
            session,
            verified,
            f"The part from {mine.number} arrived cracked, the box was crushed.",
            attachment="IMG_1.jpg",
        )
        assert reply.tool == "propose_return"
        assert not reply.resolved
        request = session.scalar(
            select(ReturnRequest).order_by(ReturnRequest.id.desc())
        )
        assert request.status == "proposed"

    def test_the_consumer_right_is_not_quoted_to_a_trade_account(
        self, session, verified, orders
    ):
        """Taiwan's seven day rule is consumer law. These are businesses.

        Quoting it to a purchasing manager promises a refund nobody owes,
        in writing, in a channel they will screenshot.
        """
        mine, _ = orders
        assert mine.customer.is_trade_account
        reply = desk.handle(
            session, verified, f"I want to return the part from {mine.number}, it is cracked."
        )
        text = reply.text.lower()
        assert "seven day" in text
        assert "does not apply" in text

    def test_transit_damage_uses_the_contract_window(self):
        order = Order(
            number="SO-1",
            customer_id=1,
            placed_on=dt.date(2026, 1, 1),
            despatched_on=dt.date(2026, 1, 2),
            delivered_on=dt.date(2026, 1, 5),
        )
        inside = returns.check_cover(
            order, returns.SHIPPING_DAMAGE,
            is_trade_account=True, warranty_months=12, today=dt.date(2026, 1, 9),
        )
        outside = returns.check_cover(
            order, returns.SHIPPING_DAMAGE,
            is_trade_account=True, warranty_months=12, today=dt.date(2026, 2, 9),
        )
        assert inside.covered
        assert not outside.covered

    def test_the_wrong_part_comes_back_whatever_the_date(self):
        order = Order(
            number="SO-1", customer_id=1,
            placed_on=dt.date(2024, 1, 1), despatched_on=dt.date(2024, 1, 2),
        )
        cover = returns.check_cover(
            order, returns.WRONG_PART,
            is_trade_account=True, warranty_months=12, today=dt.date(2026, 6, 1),
        )
        assert cover.covered

    def test_triage_suggests_and_refuses_to_be_certain(self):
        shipping = returns.triage("The outer box was crushed in transit")
        assert shipping.kind == returns.SHIPPING_DAMAGE
        assert shipping.confidence < 1.0

    def test_a_description_pointing_two_ways_lowers_the_confidence(self):
        one = returns.triage("The box was crushed in transit")
        both = returns.triage(
            "The box was crushed in transit, though it is also quite rusted "
            "after two years"
        )
        assert both.confidence < one.confidence

    def test_nothing_in_the_description_means_no_guess(self):
        found = returns.triage("I want to send this back")
        assert found.kind == returns.UNCLEAR
        assert not found.confident_enough


class TestTheRouteToAPerson:
    def test_every_reply_offers_one(self, session, verified, orders):
        mine, _ = orders
        for message in (
            "hello",
            f"where is {mine.number}",
            "what are your hours",
            "can you change our bank details",
            "I want a human",
        ):
            reply = desk.handle(session, verified, message)
            assert any(a["code"] == "human" for a in reply.actions), message

    def test_asking_for_one_raises_a_ticket_with_a_real_time(
        self, session, verified
    ):
        reply = desk.handle(session, verified, "Please put me through to a person.")
        assert reply.escalated
        assert reply.ticket_reference
        assert verified.ticket is not None
        assert aware(verified.ticket.reply_by) > dt.datetime.now(dt.timezone.utc)

    def test_one_conversation_raises_one_ticket(self, session, verified):
        desk.handle(session, verified, "I want a human")
        first = verified.ticket.reference
        desk.handle(session, verified, "I still want a human")
        assert verified.ticket.reference == first


class TestPromisedTimes:
    def test_inside_hours_it_promises_minutes(self):
        # A Wednesday at 10am Taipei.
        now = dt.datetime(2026, 10, 7, 2, 0, tzinfo=dt.timezone.utc)
        made = escalation.promise(now)
        assert made.was_open
        assert "minutes" in made.wording

    def test_outside_hours_it_says_so_rather_than_promising_shortly(self):
        """Two in the morning Taipei is not 'somebody will be right with you'."""
        now = dt.datetime(2026, 10, 6, 18, 0, tzinfo=dt.timezone.utc)  # 2am Taipei
        made = escalation.promise(now)
        assert not made.was_open
        assert "closed" in made.wording
        assert made.reply_by > now

    def test_a_friday_night_rolls_to_monday(self):
        friday_night = dt.datetime(2026, 10, 9, 14, 0, tzinfo=dt.timezone.utc)  # 10pm Fri
        made = escalation.promise(friday_night)
        assert made.reply_by.astimezone(escalation.TAIPEI).weekday() == 0


class TestScheduling:
    def test_a_technician_without_the_skill_is_not_offered(self, session):
        search = scheduling.find_slots(
            session, city="Taichung", skill="underwater_welding", parts=[]
        )
        assert not search.slots
        assert search.ruled_out.get("not qualified")

    def test_a_technician_without_the_parts_is_not_offered(self, session):
        search = scheduling.find_slots(
            session, city="Taichung", skill="", parts=["HT-NOT-A-REAL-PART"]
        )
        assert not search.slots
        assert search.ruled_out.get("parts not in the van")

    def test_slots_are_inside_working_hours(self, session):
        search = scheduling.find_slots(session, city="Taichung", skill="", parts=[])
        for slot in search.slots:
            local = slot.starts_at.astimezone(scheduling.TAIPEI)
            assert local.weekday() in settings.working_days
            assert settings.office_opens_hour <= local.hour < settings.office_closes_hour

    def test_two_bookings_at_once_produce_one_visit(self, session, verified, orders):
        """The race. Checking then writing loses it; the database wins it."""
        from app.models import Customer

        technician = session.scalar(select(Technician).limit(1))
        starts_at = dt.datetime.now(dt.timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ) + dt.timedelta(days=5)
        slot = scheduling.Slot(
            technician_id=technician.id,
            technician_name=technician.full_name,
            starts_at=starts_at,
            minutes=90,
            city="Taichung",
            travel_minutes=0,
        )

        first = isolation.scope_for(verified)
        other = session.scalar(
            select(Customer).where(Customer.id != first.customer_id).limit(1)
        )
        second = isolation.Scope(
            customer_id=other.id, conversation_id=verified.id, customer_name=other.name
        )

        scheduling.book(session, first, slot)
        with pytest.raises(scheduling.SlotTaken):
            scheduling.book(session, second, slot)

        booked = list(
            session.scalars(
                select(Visit).where(
                    Visit.technician_id == technician.id, Visit.starts_at == starts_at
                )
            )
        )
        assert len(booked) == 1

    def test_travel_time_is_charged_against_the_diary(self, session, verified):
        """A technician in one city cannot be in another an hour later."""
        technician = session.scalar(select(Technician).limit(1))
        starts_at = dt.datetime.now(dt.timezone.utc).replace(
            minute=0, second=0, microsecond=0
        ) + dt.timedelta(days=6)
        scheduling.book(
            session,
            isolation.scope_for(verified),
            scheduling.Slot(
                technician_id=technician.id,
                technician_name=technician.full_name,
                starts_at=starts_at,
                minutes=90,
                city="Taichung",
                travel_minutes=0,
            ),
        )
        # An hour and a half later in a different city is not available,
        # because the drive is two hours.
        diary = [(starts_at, 90, "Taichung")]
        assert scheduling._clashes(
            starts_at + dt.timedelta(minutes=90),
            90,
            settings.travel_minutes_other_city,
            diary,
            "Kaohsiung",
        )
