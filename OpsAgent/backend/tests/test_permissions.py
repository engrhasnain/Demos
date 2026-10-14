"""Who can see what, tested at the layer that decides it.

These tests go around the planner on purpose. The planner is the part
that can be talked into things, so a permission test that goes through
it is really a test of the planner's refusals. Everything here calls the
executor directly, with the worst parameters an attacker could want,
and asks only one question: did a row belonging to somebody else come
back.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.domain import capabilities
from app.models import Customer, Grant, Order, Part, Supplier, User
from app.security import role_satisfies
from app.services.executor import BadParameter, run
from app.services.permissions import NotAllowed, Reach, apply, may_use, reach_of


def _limited(session, role: str = "salesperson") -> tuple[User, Reach]:
    user = session.scalar(select(User).where(User.role == role))
    return user, reach_of(session, user)


def _outside(session, reach: Reach) -> Customer:
    return session.scalar(
        select(Customer)
        .where(Customer.id.notin_(reach.customers or {0}))
        .order_by(Customer.id)
        .limit(1)
    )


# ---------------------------------------------------------------------------
# Reach
# ---------------------------------------------------------------------------
def test_a_director_sees_everything(session):
    _, reach = _limited(session, "director")
    assert reach.everything is True


def test_a_salesperson_sees_only_their_grants(session):
    user, reach = _limited(session)
    assert reach.everything is False
    granted = {
        g.customer_id
        for g in session.scalars(select(Grant).where(Grant.user_id == user.id))
        if g.customer_id
    }
    assert reach.customers == granted
    assert 0 < len(reach.customers) < session.scalar(
        select(Customer.id).order_by(Customer.id.desc()).limit(1)
    )


def test_reach_is_read_from_the_database_not_from_the_request(session):
    """There is no way to construct a wider Reach than the grants allow."""
    user, reach = _limited(session)
    again = reach_of(session, user)
    assert again.customers == reach.customers
    assert again.everything is False


# ---------------------------------------------------------------------------
# The filter
# ---------------------------------------------------------------------------
def test_the_filter_is_added_to_every_scoped_query(session):
    _, reach = _limited(session)
    for capability in capabilities.CATALOGUE:
        if capability.scope_column is None:
            continue
        scoped = apply(capability, {}, reach)
        assert "AS scoped WHERE" in scoped.sql, capability.name


def test_no_grant_means_nothing_not_everything(session):
    """The failure mode that matters. An empty set is not 'no filter'."""
    empty = Reach(user_id=0, role="viewer", customers=set(), suppliers=set())
    capability = capabilities.BY_NAME["customers_with_late_orders"]
    scoped = apply(capability, {}, empty)
    assert "WHERE 1 = 0" in scoped.sql
    rows = session.execute(
        __import__("sqlalchemy").text(scoped.sql), scoped.parameters
    ).fetchall()
    assert rows == []


def test_a_director_gets_no_filter_at_all(session):
    _, reach = _limited(session, "director")
    capability = capabilities.BY_NAME["customers_with_late_orders"]
    scoped = apply(capability, {}, reach)
    assert "AS scoped" not in scoped.sql
    assert scoped.filter_applied == ""


# ---------------------------------------------------------------------------
# The whole point
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("role", ["salesperson", "account_manager", "manager"])
def test_no_capability_returns_a_row_outside_the_grants(session, role):
    """Every capability, every bad parameter, no planner involved."""
    user, reach = _limited(session, role)
    if reach.everything:
        pytest.skip(f"{role} sees everything by role")
    outside = _outside(session, reach)
    if outside is None:
        pytest.skip(f"{role} happens to be granted every account in this dataset")
    other_supplier = session.scalar(
        select(Supplier)
        .where(Supplier.id.notin_(reach.suppliers or {0}))
        .order_by(Supplier.id)
        .limit(1)
    )
    their_part = session.scalar(
        select(Part).where(Part.supplier_id == other_supplier.id).limit(1)
    )
    their_order = session.scalar(
        select(Order).where(Order.customer_id == outside.id).limit(1)
    )

    escaped: list[str] = []
    for capability in capabilities.CATALOGUE:
        given = {}
        for parameter in capability.parameters:
            if parameter.kind == "customer":
                given[parameter.name] = outside.id
            elif parameter.kind == "supplier":
                given[parameter.name] = other_supplier.id
            elif parameter.kind == "part":
                given[parameter.name] = their_part.code if their_part else "HT-X-1"
            elif parameter.kind in {"number", "days"}:
                given[parameter.name] = 999
            elif parameter.kind == "date":
                given[parameter.name] = "2020-01-01"
            else:
                given[parameter.name] = (
                    their_order.number
                    if their_order and parameter.name == "order"
                    else outside.name
                )
        try:
            result = run(session, capability, given, reach)
        except (NotAllowed, BadParameter):
            continue
        for row in result.raw_rows:
            customer = row.get("customer_id")
            supplier = row.get("supplier_id")
            if customer is not None and customer not in reach.customers:
                escaped.append(f"{capability.name}: customer {customer}")
            if supplier is not None and supplier not in reach.suppliers:
                escaped.append(f"{capability.name}: supplier {supplier}")

    assert escaped == []


def test_the_grouped_total_only_adds_up_rows_the_asker_may_see(session):
    """The regression test for the ungrouped-SUM hole.

    A manager with grants asks what is owed altogether. The figure has
    to be the sum over their accounts, not over the company.
    """
    from app.models import Invoice

    user, reach = _limited(session, "manager")
    if _outside(session, reach) is None:
        pytest.skip("the manager is granted every account in this dataset")
    capability = capabilities.BY_NAME["money_owed_in_total"]
    result = run(session, capability, {}, reach)

    theirs = sum(float(r["total_owed"]) for r in result.rows)
    everyone = float(
        session.scalar(
            select(__import__("sqlalchemy").func.sum(Invoice.total)).where(
                Invoice.paid_on.is_(None)
            )
        )
        or 0
    )
    by_hand = float(
        session.scalar(
            select(__import__("sqlalchemy").func.sum(Invoice.total)).where(
                Invoice.paid_on.is_(None),
                Invoice.customer_id.in_(reach.customers),
            )
        )
        or 0
    )
    assert abs(theirs - by_hand) < 1.0
    assert theirs < everyone


# ---------------------------------------------------------------------------
# Roles
# ---------------------------------------------------------------------------
def test_a_whole_company_query_is_closed_to_a_limited_account(session):
    _, reach = _limited(session, "manager")
    capability = capabilities.BY_NAME["headline_numbers"]
    with pytest.raises(NotAllowed):
        may_use(capability, reach)


def test_role_checks_fail_closed():
    """Both sides used to fall back to -1, so -1 >= -1 let anybody in."""
    assert role_satisfies("director", "manager") is True
    assert role_satisfies("salesperson", "manager") is False
    assert role_satisfies("not_a_role", "manager") is False
    assert role_satisfies("manager", "not_a_requirement") is False
    assert role_satisfies("not_a_role", "not_a_requirement") is False
    # The administrator is the deliberate exception, and is explicit.
    assert role_satisfies("administrator", "not_a_requirement") is True


# ---------------------------------------------------------------------------
# Parameters
# ---------------------------------------------------------------------------
def test_a_parameter_of_the_wrong_kind_is_refused(session):
    _, reach = _limited(session, "director")
    capability = capabilities.BY_NAME["late_orders_for_customer"]
    with pytest.raises(BadParameter):
        run(session, capability, {"customer": "1 OR 1=1"}, reach)


def test_sql_in_a_text_parameter_is_refused_or_bound(session):
    _, reach = _limited(session, "director")
    capability = capabilities.BY_NAME["find_customer"]
    with pytest.raises(BadParameter):
        run(session, capability, {"text": "Acme'; DROP TABLE orders; --"}, reach)
    # Still there.
    assert session.scalar(select(Order.id).limit(1)) is not None


def test_a_harmless_apostrophe_still_works(session):
    _, reach = _limited(session, "director")
    capability = capabilities.BY_NAME["find_customer"]
    result = run(session, capability, {"text": "O'Brien"}, reach)
    assert result.row_count == 0


def test_every_result_carries_its_query_and_the_time_it_was_read(session):
    _, reach = _limited(session, "director")
    capability = capabilities.BY_NAME["customers_with_late_orders"]
    result = run(session, capability, {}, reach)
    assert result.sql
    assert result.read_at is not None
    assert result.duration_ms >= 0
    assert "read_at" in result.to_dict()


def test_internal_identifiers_do_not_reach_the_client(session):
    _, reach = _limited(session, "director")
    capability = capabilities.BY_NAME["customers_with_late_orders"]
    result = run(session, capability, {}, reach)
    assert result.raw_rows and "customer_id" in result.raw_rows[0]
    for row in result.rows:
        assert "customer_id" not in row


def test_scope_parameters_are_not_echoed_back(session):
    _, reach = _limited(session)
    capability = capabilities.BY_NAME["customers_with_late_orders"]
    result = run(session, capability, {}, reach)
    assert any(k.startswith("scope_") for k in result.parameters)
    assert not any(k.startswith("scope_") for k in result.to_dict()["parameters"])
