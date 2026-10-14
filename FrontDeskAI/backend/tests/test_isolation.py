"""The rule the whole product rests on: one customer's data, and no other's."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import AccessLog, Order
from app.services import desk, identity, isolation, orders


class TestTheScope:
    def test_a_scope_cannot_be_built_without_verification(self, conversation):
        """There is no argument you can pass to get somebody else's rows."""
        with pytest.raises(isolation.NotVerified):
            isolation.scope_for(conversation)

    def test_the_customer_is_not_a_parameter(self):
        """The signature is the control.

        ``scope_for`` takes a conversation and reads the customer off its
        verification. If the customer were an argument, somewhere in this
        codebase there would eventually be a line passing one from the
        message.
        """
        import inspect

        parameters = list(inspect.signature(isolation.scope_for).parameters)
        assert parameters == ["conversation"]

    def test_a_scope_with_no_customer_refuses_to_exist(self):
        with pytest.raises(isolation.NotVerified):
            isolation.Scope(customer_id=0, conversation_id=1, customer_name="x")


class TestReadingOrders:
    def test_a_verified_customer_sees_their_own(self, session, verified, orders):
        mine, _ = orders
        view = orders_look_up(session, verified, mine.number)
        assert view is not None
        assert view.order.number == mine.number

    def test_they_do_not_see_anybody_else_s(self, session, verified, orders):
        _, theirs = orders
        assert orders_look_up(session, verified, theirs.number) is None

    def test_an_order_that_exists_elsewhere_reads_as_one_that_does_not(
        self, session, verified, orders
    ):
        """The small leak that lets somebody enumerate real order numbers."""
        _, theirs = orders
        real_but_not_mine = desk.handle(
            session, verified, f"Where is order {theirs.number}?"
        )
        invented = desk.handle(session, verified, "Where is order SO-99999999?")
        assert real_but_not_mine.text == invented.text

    def test_recent_orders_are_only_this_customer_s(self, session, verified):
        scope = isolation.scope_for(verified)
        for order in orders.recent(session, scope, limit=20):
            assert order.customer_id == scope.customer_id


class TestTheAccessLog:
    def test_a_successful_read_is_recorded(self, session, verified, orders):
        mine, _ = orders
        before = session.scalar(select(AccessLog.id).order_by(AccessLog.id.desc())) or 0
        orders_look_up(session, verified, mine.number)
        rows = list(
            session.scalars(select(AccessLog).where(AccessLog.id > before))
        )
        assert any(row.tool == "order_status" and row.allowed for row in rows)

    def test_a_refused_read_is_recorded_too(self, session, conversation, orders):
        """The refused ones are the interesting ones."""
        mine, _ = orders
        before = session.scalar(select(AccessLog.id).order_by(AccessLog.id.desc())) or 0
        identity.verify(
            session, conversation, order_number=mine.number, email="nobody@nowhere.example"
        )
        rows = list(session.scalars(select(AccessLog).where(AccessLog.id > before)))
        assert any(row.tool == "verify" and not row.allowed for row in rows)

    def test_the_log_does_not_keep_secrets(self, session, conversation):
        isolation.record(
            session,
            tool="test",
            conversation=conversation,
            arguments={"password": "hunter2", "order": "SO-1"},
        )
        row = session.scalar(select(AccessLog).order_by(AccessLog.id.desc()))
        assert row.arguments["password"] == "***"
        assert row.arguments["order"] == "SO-1"


class TestVerification:
    def test_the_right_pair_gets_through(self, session, conversation, orders):
        mine, _ = orders
        contact = mine.customer.contacts[0]
        result = identity.verify(
            session, conversation, order_number=mine.number, email=contact.email
        )
        assert result.ok
        assert conversation.customer_id == mine.customer_id

    def test_punctuation_does_not_decide(self, session, conversation, orders):
        """`so 20004` and `SO-20004` are the same order number."""
        mine, _ = orders
        contact = mine.customer.contacts[0]
        messy = mine.number.lower().replace("-", " ")
        result = identity.verify(
            session, conversation, order_number=messy, email=f"  {contact.email.upper()} "
        )
        assert result.ok

    def test_the_right_order_with_the_wrong_email_fails(
        self, session, conversation, orders
    ):
        mine, _ = orders
        result = identity.verify(
            session, conversation, order_number=mine.number, email="wrong@nowhere.example"
        )
        assert not result.ok

    def test_somebody_else_s_order_with_your_own_email_fails(
        self, session, conversation, orders
    ):
        mine, theirs = orders
        contact = mine.customer.contacts[0]
        result = identity.verify(
            session, conversation, order_number=theirs.number, email=contact.email
        )
        assert not result.ok

    def test_every_failure_reads_the_same(self, session, conversation, orders):
        """Otherwise the real order numbers are distinguishable from the rest."""
        mine, theirs = orders
        a = identity.verify(
            session, conversation, order_number=theirs.number, email="x@y.example"
        )
        b = identity.verify(
            session, conversation, order_number="SO-99999999", email="x@y.example"
        )
        assert a.message == b.message == identity.SAME_ANSWER

    def test_it_locks_out_rather_than_letting_somebody_guess(
        self, session, conversation, orders
    ):
        _, theirs = orders
        for attempt in range(5):
            identity.verify(
                session,
                conversation,
                order_number=theirs.number,
                email=f"guess{attempt}@nowhere.example",
            )
        assert identity.is_locked(conversation)
        # And a correct answer after the lock still does not get through.
        mine, _ = orders
        contact = mine.customer.contacts[0]
        result = identity.verify(
            session, conversation, order_number=mine.number, email=contact.email
        )
        assert not result.ok
        assert result.locked


def orders_look_up(session, conversation, number):
    return orders.look_up(session, isolation.scope_for(conversation), number=number)


class TestRoles:
    """The hole that let an unrecognised role satisfy any requirement."""

    def test_a_lower_role_does_not_satisfy_a_higher_one(self):
        from app.security import role_satisfies

        assert not role_satisfies("agent", "supervisor")
        assert role_satisfies("supervisor", "agent")

    def test_an_unknown_role_satisfies_nothing(self):
        """It used to satisfy everything, because -1 >= -1."""
        from app.security import role_satisfies

        assert not role_satisfies("contractor", "agent")
        assert not role_satisfies("contractor", "made_up_requirement")

    def test_an_unknown_requirement_is_met_by_nobody_but_the_administrator(self):
        from app.security import role_satisfies

        assert not role_satisfies("supervisor", "mistyped_role")
        assert role_satisfies("administrator", "mistyped_role")
