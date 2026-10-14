"""The bot against the two systems."""

from __future__ import annotations

import datetime as dt

import pytest
from sqlalchemy import func, select

from app.domain import dangerous, drift
from app.models import Challenge, ScriptFlag, Shipment, Step
from app.seed.generator import Builder
from app.services import runner
from app.services.addresses import validate
from app.services.bot import EXCEPTION_WORDS, key_for
from app.systems.carrier import Behaviour, CarrierPortal, NeedsCode, PortalError
from app.systems.legacy import LegacySystem, Record, RecordLocked, StaleWrite


class TestTheKey:
    def test_the_same_shipment_computes_the_same_key(self, session):
        shipment = session.scalar(select(Shipment).limit(1))
        assert key_for(shipment) == key_for(shipment)

    def test_it_is_derived_not_generated(self, session):
        """A generated key is a new key every run, which books twice."""
        shipment = session.scalar(select(Shipment).limit(1))
        first = key_for(shipment)
        session.expire(shipment)
        reloaded = session.scalar(select(Shipment).where(Shipment.id == shipment.id))
        assert key_for(reloaded) == first

    def test_two_shipments_do_not_share_one(self, session):
        keys = {key_for(s) for s in session.scalars(select(Shipment).limit(50))}
        assert len(keys) == len(list(session.scalars(select(Shipment).limit(50))))

    def test_changing_what_matters_changes_the_key(self, session):
        shipment = session.scalar(select(Shipment).limit(1))
        before = key_for(shipment)
        shipment.packages += 1
        assert key_for(shipment) != before


class TestAddresses:
    def test_a_tidy_taiwan_postcode_passes(self):
        assert validate(
            name="A", line1="B", city="Taichung", postcode="407", country="TW"
        ).ok

    def test_a_four_digit_taiwan_postcode_is_refused_not_guessed(self):
        """Three or five. Four is ambiguous, and guessing ships it wrong."""
        checked = validate(
            name="A", line1="B", city="Taichung", postcode="4071", country="TW"
        )
        assert not checked.ok
        assert checked.kind == "bad_postcode"

    def test_a_messy_but_recoverable_postcode_is_tidied(self):
        checked = validate(
            name="A", line1="B", city="Cleveland", postcode="44113 ", country="US"
        )
        assert checked.ok

    def test_a_zip_with_a_letter_is_refused(self):
        assert not validate(
            name="A", line1="B", city="Cleveland", postcode="4411X", country="US"
        ).ok

    def test_a_country_with_no_rule_is_not_claimed_to_be_checked(self):
        checked = validate(
            name="A", line1="B", city="Lagos", postcode="100001", country="NG"
        )
        assert checked.ok
        assert "No postcode rule" in checked.summary


class TestDangerousGoods:
    def test_a_part_in_the_table_gets_its_un_number(self):
        found = dangerous.assess(
            [{"part_code": "HT-AER-PTFE-400", "description": "Dry film lubricant"}]
        )
        assert found.dangerous
        assert found.declarations[0].un_number == "UN1950"
        assert not found.needs_a_person

    def test_a_part_that_reads_dangerous_and_is_not_in_the_table_stops_the_run(self):
        """A UN number is a legal declaration. It is never guessed.

        The failure mode this prevents is not a data error: it is a false
        declaration, which can ground an aircraft and void the insurance.
        """
        found = dangerous.assess(
            [{"part_code": "HT-AER-NEW-999", "description": "New aerosol line"}]
        )
        assert found.needs_a_person
        assert found.unknown

    def test_ordinary_goods_are_not_dangerous(self):
        found = dangerous.assess(
            [{"part_code": "HT-SHC-M8X030-12.9-ZNB", "description": "Socket head screws"}]
        )
        assert not found.dangerous
        assert not found.needs_a_person

    def test_cells_in_equipment_are_a_different_entry_from_loose_cells(self):
        """UN3481 and UN3480 are not interchangeable."""
        inside = dangerous.TABLE["HT-SEN-PROX-LI"]
        loose = dangerous.TABLE["HT-BAT-CR2032-10"]
        assert inside.un_number == "UN3481"
        assert loose.un_number == "UN3480"

    def test_two_un_numbers_on_one_consignment_is_not_averaged(self):
        assert (
            dangerous.declaration_for(["HT-AER-PTFE-400", "HT-BAT-CR2032-10"]) is None
        )


class TestTheCarrierPortal:
    def test_it_refuses_the_same_reference_twice(self, carrier):
        form = _form(carrier, "REF-1")
        carrier.book(form)
        with pytest.raises(PortalError) as error:
            carrier.book(_form(carrier, "REF-1"))
        assert error.value.code == "duplicate"

    def test_it_refuses_undeclared_dangerous_goods(self, carrier):
        form = _form(carrier, "REF-2")
        form[carrier.fields["goods_description"]] = "Aerosol lubricant"
        with pytest.raises(PortalError) as error:
            carrier.book(form)
        assert error.value.code == "undeclared_dangerous_goods"

    def test_it_refuses_a_made_up_un_number(self, carrier):
        form = _form(carrier, "REF-3")
        form[carrier.fields["dangerous"]] = "yes"
        form[carrier.fields["un_number"]] = "probably 1950"
        with pytest.raises(PortalError) as error:
            carrier.book(form)
        assert error.value.code == "bad_un_number"

    def test_it_refuses_an_overweight_package(self, carrier):
        form = _form(carrier, "REF-4")
        form[carrier.fields["packages"]] = 1
        form[carrier.fields["weight_kg"]] = 120
        with pytest.raises(PortalError) as error:
            carrier.book(form)
        assert error.value.code == "overweight_package"

    def test_the_tracking_number_is_not_in_the_booking_answer(self):
        """Which is why the bot polls rather than sleeping for a guess."""
        slow = CarrierPortal(behaviour=Behaviour(tracking_delay_seconds=60))
        booking = slow.book(_form(slow, "REF-5"))
        assert not booking.tracking_number
        assert not slow.collect(booking.consignment).tracking_number


class TestTheLegacySystem:
    def test_a_stale_write_is_refused(self):
        legacy = LegacySystem()
        legacy.add(Record(order="SO-1", customer="A"))
        # Snapshot the revision, the way a bot reading a screen would. The
        # record object itself is live and moves under you.
        read_at = legacy.read("SO-1").revision
        legacy.write_tracking("SO-1", tracking_number="HT1", carrier="C", revision=read_at)
        with pytest.raises(StaleWrite):
            legacy.write_tracking(
                "SO-1", tracking_number="HT2", carrier="C", revision=read_at
            )

    def test_it_is_case_sensitive_on_write_and_not_on_read(self):
        """A real inconsistency: it reads fine and then will not save."""
        legacy = LegacySystem()
        legacy.add(Record(order="SO-1", customer="A"))
        assert legacy.read("so-1") is not None
        with pytest.raises(Exception):
            legacy.write_tracking("so-1", tracking_number="HT1", carrier="C", revision=1)

    def test_it_truncates_silently(self):
        """The nastiest habit, because the write succeeds."""
        legacy = LegacySystem()
        legacy.add(Record(order="SO-1", customer="A"))
        long = "HT" + "9" * 40
        written = legacy.write_tracking(
            "SO-1", tracking_number=long, carrier="C", revision=1
        )
        assert written.tracking_number != long
        assert len(written.tracking_number) == 18


class TestARun:
    def test_clean_shipments_go_right_through(self, session, carrier, legacy):
        report = runner.run_once(session, carrier, legacy)
        clean = report.run.considered - report.exceptions
        assert report.completed == clean

    def test_every_exception_has_a_name_and_a_trace(self, session, carrier, legacy):
        report = runner.run_once(session, carrier, legacy)
        for outcome in report.outcomes:
            if not outcome.exception_kind:
                continue
            assert outcome.exception_kind in EXCEPTION_WORDS
            steps = session.scalar(
                select(func.count(Step.id)).where(
                    Step.shipment_id == outcome.shipment.id
                )
            )
            assert steps, f"{outcome.shipment.reference} has no trace"

    def test_running_again_books_nothing_more(self, session, carrier, legacy):
        runner.run_once(session, carrier, legacy)
        before = len(carrier.bookings)
        runner.run_once(session, carrier, legacy)
        assert len(carrier.bookings) == before

    def test_a_finished_shipment_is_not_picked_up_again(self, session, carrier, legacy):
        runner.run_once(session, carrier, legacy)
        done = session.scalar(
            select(func.count(Shipment.id)).where(Shipment.state == "done")
        )
        again = runner.run_once(session, carrier, legacy)
        assert again.run.considered == report_total(session) - done

    def test_one_bad_shipment_does_not_stop_the_others(self, session, carrier, legacy):
        report = runner.run_once(session, carrier, legacy)
        assert report.exceptions > 0
        assert report.completed > 0


class TestKilledPartWay:
    def test_a_kill_between_the_two_systems_does_not_book_twice(
        self, session, carrier, legacy
    ):
        """The moment that costs money.

        Booked at the carrier, not yet written back, and the process goes
        away. The row says 'booked', and the next run reads that before it
        does anything.
        """
        for stop_after in (2, 5, 9, 14, 20, 40, 80):
            runner.run_once(session, carrier, legacy, stop_after=stop_after)
        runner.run_once(session, carrier, legacy)

        references = [b.reference for b in carrier.bookings.values()]
        assert len(references) == len(set(references)), "something was booked twice"

    def test_the_carrier_is_asked_before_assuming(self, session, legacy):
        """Local state can be lost. The carrier's cannot."""
        carrier = CarrierPortal(behaviour=Behaviour(tracking_delay_seconds=0))
        shipment = session.scalar(
            select(Shipment).where(Shipment.state == "pending").limit(1)
        )
        # The carrier already has it, from a run whose state we lost.
        carrier.book(_form(carrier, shipment.reference, country=shipment.to_country))
        before = len(carrier.bookings)

        runner.run_once(session, carrier, legacy, limit=1)
        assert len(carrier.bookings) == before, "it booked over an existing consignment"


class TestTheFormMoving:
    def test_a_changed_form_stops_the_run_before_anything_is_sent(
        self, session, legacy
    ):
        """Stopping is cheap. Carrying on against a changed page is not."""
        moved = CarrierPortal(behaviour=Behaviour(version="v2", tracking_delay_seconds=0))
        report = runner.run_once(session, moved, legacy)
        assert report.halted
        assert len(moved.bookings) == 0

    def test_it_raises_a_flag_for_a_developer(self, session, legacy):
        before = session.scalar(select(func.count(ScriptFlag.id))) or 0
        moved = CarrierPortal(behaviour=Behaviour(version="v2", tracking_delay_seconds=0))
        runner.run_once(session, moved, legacy)
        after = session.scalar(select(func.count(ScriptFlag.id))) or 0
        assert after > before

    def test_the_flag_says_what_moved(self, session, legacy):
        moved = CarrierPortal(behaviour=Behaviour(version="v2", tracking_delay_seconds=0))
        runner.run_once(session, moved, legacy)
        flag = session.scalar(select(ScriptFlag).order_by(ScriptFlag.id.desc()))
        assert flag.detail["missing"]
        assert flag.detail["added"]
        assert flag.detail["looks_renamed"]

    def test_renames_are_suggested_and_not_applied(self, session, legacy):
        """Nothing here rewrites a script. A person reads the diff."""
        from app.services import bot

        before = list(bot.EXPECTED.fields)
        moved = CarrierPortal(behaviour=Behaviour(version="v2", tracking_delay_seconds=0))
        runner.run_once(session, moved, legacy)
        assert bot.EXPECTED.fields == before


class TestOneTimeCodes:
    def test_it_asks_a_person_rather_than_guessing(self, session, legacy):
        asking = CarrierPortal(
            behaviour=Behaviour(challenge_rate=1.0, tracking_delay_seconds=0)
        )
        runner.run_once(session, asking, legacy, limit=3)
        waiting = list(
            session.scalars(select(Challenge).where(Challenge.status == "waiting"))
        )
        assert waiting
        assert len(asking.bookings) == 0

    def test_the_portal_will_not_take_an_invented_code(self):
        portal = CarrierPortal()
        portal.challenges["CH-1"] = False
        assert not portal.answer_challenge("CH-1", "guess")
        assert portal.answer_challenge("CH-1", "481920")


def report_total(session) -> int:
    from sqlalchemy import func, select

    return session.scalar(select(func.count(Shipment.id))) or 0


def _form(portal, reference: str, country: str = "TW") -> dict:
    names = portal.fields
    return {
        names["reference"]: reference,
        names["service"]: "STD",
        names["collection_date"]: dt.date.today().isoformat(),
        names["to_name"]: "A Customer",
        names["to_line1"]: "1 Industrial Road",
        names["to_city"]: "Taichung",
        names["to_postcode"]: "407" if country == "TW" else "44113",
        names["to_country"]: country,
        names["packages"]: 2,
        names["weight_kg"]: 20.0,
        names["goods_description"]: "Socket head cap screws",
        names["dangerous"]: "no",
    }
