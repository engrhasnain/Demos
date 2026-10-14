"""Who may see what, decided in code and applied in SQL.

Two layers, and both of them are below the model.

**The role** decides which capabilities exist for this person at all. A
salesperson asking what the company is owed does not get a refusal from a
query that ran; the query never runs.

**The grant** decides which rows. A salesperson sees their own accounts.
An account manager sees their region. A director sees everything. That is
expressed as a set of customer and supplier identifiers, and it is
attached to every query as a mandatory ``AND`` before execution — not by
the person who wrote the query, who might forget, but by this module,
which cannot.

The filter is added to the SQL text by wrapping, so there is no way for a
capability author to write a query that escapes it and no way for a
parameter to turn it off. A capability with no scope column and no
whole-company flag will not load at all, which is checked when the
catalogue is imported.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain.capabilities import Capability
from ..models import Grant, User
from ..security import role_satisfies


class NotAllowed(Exception):
    """Refused before anything ran."""

    def __init__(self, message: str, *, capability: str = "") -> None:
        super().__init__(message)
        self.capability = capability


@dataclass(slots=True)
class Reach:
    """Exactly what one person may see."""

    user_id: int
    role: str
    #: Empty means every customer. A set means only these.
    customers: set[int] = field(default_factory=set)
    suppliers: set[int] = field(default_factory=set)
    everything: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "everything": self.everything,
            "customers": len(self.customers) if not self.everything else None,
            "suppliers": len(self.suppliers) if not self.everything else None,
        }


def reach_of(session: Session, user: User) -> Reach:
    """Read the person's grants. Never taken from the question."""
    if role_satisfies(user.role, "director"):
        return Reach(user_id=user.id, role=user.role, everything=True)

    customers: set[int] = set()
    suppliers: set[int] = set()
    for grant in session.scalars(select(Grant).where(Grant.user_id == user.id)):
        if grant.customer_id:
            customers.add(grant.customer_id)
        if grant.supplier_id:
            suppliers.add(grant.supplier_id)

    return Reach(
        user_id=user.id, role=user.role, customers=customers, suppliers=suppliers
    )


def may_use(capability: Capability, reach: Reach) -> None:
    """Does this person's role reach this capability at all?"""
    if not role_satisfies(reach.role, capability.needs_role):
        raise NotAllowed(
            f"{capability.asks} needs the {capability.needs_role} role.",
            capability=capability.name,
        )
    if capability.whole_company and not reach.everything:
        # The role check above usually catches this; both are kept because
        # a grant-limited manager is a real case.
        raise NotAllowed(
            "That is a whole-company figure, and this account is limited to "
            "particular accounts.",
            capability=capability.name,
        )


@dataclass(slots=True)
class Scoped:
    sql: str
    parameters: dict[str, Any]
    #: What was added, so the answer can show it.
    filter_applied: str = ""


def apply(capability: Capability, parameters: dict[str, Any], reach: Reach) -> Scoped:
    """Wrap the query so it can only return rows this person may see.

    Wrapped rather than edited. Editing a query means parsing it, and a
    parser that is wrong once is a permission hole. Wrapping is a select
    over the capability's own result, with the filter on the scope column
    it already declared and already selects.
    """
    sql = capability.sql.strip().rstrip(";")

    if reach.everything or capability.scope_column is None:
        return Scoped(sql=sql, parameters=dict(parameters), filter_applied="")

    # The name the query outputs, which the catalogue check has already
    # confirmed is one of these two and is actually selected under it.
    column = capability.scope_column
    allowed: set[int] = set()
    if column == "customer_id":
        allowed = reach.customers
    elif column == "supplier_id":
        allowed = reach.suppliers
    else:  # pragma: no cover - the catalogue will not load in this state
        raise NotAllowed(
            f"{capability.name} is scoped on {column}, which nobody has a "
            "grant for. Refusing rather than guessing."
        )

    if not allowed:
        # No grant is not the same as no filter. It means nothing.
        return Scoped(
            sql=f"SELECT * FROM ({sql}) AS scoped WHERE 1 = 0",
            parameters=dict(parameters),
            filter_applied=f"{column} in () — this account has no grants",
        )

    names = {f"scope_{index}": value for index, value in enumerate(sorted(allowed))}
    placeholders = ", ".join(f":{name}" for name in names)
    wrapped = (
        f"SELECT * FROM ({sql}) AS scoped WHERE scoped.{column} IN ({placeholders})"
    )
    merged = dict(parameters)
    merged.update(names)
    return Scoped(
        sql=wrapped,
        parameters=merged,
        filter_applied=f"{column} in ({len(allowed)} allowed)",
    )
