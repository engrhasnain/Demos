"""The checks that run when the catalogue loads, tested as rules.

Each of these is a hole somebody could open by adding a plausible-looking
query, and each one is a hole this product has actually had. They are
tested by constructing the bad capability and asserting that the check
refuses it, rather than by trusting that the current catalogue happens
to be clean.
"""

from __future__ import annotations

import re

import pytest

from app.domain import capabilities
from app.domain.capabilities import Capability, Parameter, _check_the_catalogue


def _only(capability: Capability):
    """Run the catalogue check over one made-up capability."""
    original = capabilities.CATALOGUE
    capabilities.CATALOGUE = [capability]
    try:
        _check_the_catalogue()
    finally:
        capabilities.CATALOGUE = original


def test_the_real_catalogue_passes_its_own_checks():
    _check_the_catalogue()
    assert len(capabilities.CATALOGUE) >= 19


def test_a_capability_that_writes_is_refused():
    with pytest.raises(RuntimeError, match="not read only"):
        _only(
            Capability(
                name="naughty",
                asks="?",
                sql="UPDATE orders SET status = 'delivered'",
                scope_column="customer_id",
            )
        )


def test_two_statements_are_refused():
    with pytest.raises(RuntimeError, match="more than one statement"):
        _only(
            Capability(
                name="stacked",
                asks="?",
                sql="SELECT 1 AS customer_id; SELECT 2",
                scope_column="customer_id",
            )
        )


def test_touching_somebody_s_data_without_a_scope_column_is_refused():
    with pytest.raises(RuntimeError, match="declares no scope column"):
        _only(
            Capability(
                name="unscoped",
                asks="?",
                sql="SELECT name FROM customers",
            )
        )


def test_a_scope_column_nobody_grants_is_refused():
    with pytest.raises(RuntimeError, match="only\n?\\s*columns a grant"):
        _only(
            Capability(
                name="odd_scope",
                asks="?",
                sql="SELECT c.region AS region FROM customers c",
                scope_column="region",
            )
        )


def test_a_scope_column_that_is_not_selected_under_that_name_is_refused():
    """The bug that refused every limited account its own accounts.

    ``c.id`` is a real column and reads like a correct declaration, but
    the filter wraps the query and can only bind to what the query
    *outputs*. Declaring the source expression instead of the alias
    produced a filter that matched nothing, so a salesperson could not
    see the four accounts they were granted.
    """
    with pytest.raises(RuntimeError, match="does not select it under that name"):
        _only(
            Capability(
                name="wrong_name",
                asks="?",
                sql="SELECT c.id AS something_else FROM customers c",
                scope_column="customer_id",
            )
        )


def test_an_ungrouped_total_over_scoped_rows_is_refused():
    """The permission hole this product shipped with for a day.

    The filter wraps the query, so it runs after the total has been
    computed. An ungrouped SUM over every invoice, with a bare
    customer_id beside it, hands one row to the filter — and if that
    row's arbitrary customer happens to be inside the asker's grants,
    the asker is shown the whole company's money.
    """
    with pytest.raises(RuntimeError, match="has to GROUP BY"):
        _only(
            Capability(
                name="leaky_total",
                asks="?",
                sql=(
                    "SELECT SUM(i.total) AS owed, i.customer_id AS customer_id "
                    "FROM invoices i"
                ),
                scope_column="customer_id",
                needs_role="manager",
            )
        )


def test_the_grouped_version_is_accepted():
    _only(
        Capability(
            name="honest_total",
            asks="?",
            sql=(
                "SELECT SUM(i.total) AS owed, i.customer_id AS customer_id "
                "FROM invoices i GROUP BY customer_id"
            ),
            scope_column="customer_id",
            needs_role="manager",
        )
    )


def test_a_whole_company_query_cannot_be_open_to_everybody():
    with pytest.raises(RuntimeError, match="allowed to see the whole company"):
        _only(
            Capability(
                name="everyones_numbers",
                asks="?",
                sql="SELECT COUNT(*) AS n FROM orders",
                scope_column=None,
                whole_company=True,
                needs_role="viewer",
            )
        )


def test_a_whole_company_query_cannot_also_be_scoped():
    with pytest.raises(RuntimeError, match="cannot be both"):
        _only(
            Capability(
                name="confused",
                asks="?",
                sql="SELECT COUNT(*) AS n, o.customer_id AS customer_id FROM orders o",
                scope_column="customer_id",
                whole_company=True,
                needs_role="director",
            )
        )


def test_every_catalogue_query_selects_what_it_claims_to_be_scoped_on():
    for capability in capabilities.CATALOGUE:
        if capability.scope_column:
            assert f"AS {capability.scope_column}" in capability.sql, capability.name


def test_nothing_in_the_catalogue_writes():
    forbidden = re.compile(
        r"\b(insert|update|delete|drop|alter|create|truncate)\b", re.IGNORECASE
    )
    for capability in capabilities.CATALOGUE:
        assert not forbidden.search(capability.sql), capability.name


def test_capability_names_are_unique():
    names = [c.name for c in capabilities.CATALOGUE]
    assert len(names) == len(set(names))


def test_a_parameter_declares_what_kind_of_thing_it_is():
    allowed = {"customer", "supplier", "part", "days", "date", "number", "text"}
    for capability in capabilities.CATALOGUE:
        for parameter in capability.parameters:
            assert parameter.kind in allowed, (capability.name, parameter.name)
            assert isinstance(parameter, Parameter)
