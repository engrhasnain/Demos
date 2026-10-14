"""The rule that no amount of clever wording can get around.

A front desk that can read any customer's orders is one sentence away from
reading them to the wrong person. Prompts do not prevent that. Prompts are
text, and the thing reading them is a text machine.

So the rule lives here instead, in two parts:

1. **Nothing is read without a customer.** Every function that touches
   customer data takes a ``Scope``, and a ``Scope`` cannot be built without
   a verified conversation. There is no argument you can pass to make it
   read somebody else's rows, because the customer is not an argument the
   caller chooses — it comes from the verification.

2. **Every attempt is recorded.** Allowed or refused, with what was asked
   for. The refused ones are the ones worth reading.

The engine above this layer can be as wrong as it likes. It can decide the
visitor is asking about order AB-1234 when AB-1234 belongs to somebody
else. It still will not get the row.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..models import AccessLog, Conversation, Customer

T = TypeVar("T")


class NotVerified(Exception):
    """Somebody asked for customer data before proving who they are."""


class Refused(Exception):
    """A request that was understood, and declined."""

    def __init__(self, message: str, *, tool: str = "") -> None:
        super().__init__(message)
        self.tool = tool


@dataclass(frozen=True, slots=True)
class Scope:
    """Permission to read one customer's data, and nobody else's.

    Deliberately frozen and deliberately awkward to build. If making one of
    these were convenient, somewhere in this codebase there would eventually
    be a line that built one with a customer id taken from user input.
    """

    customer_id: int
    conversation_id: int
    customer_name: str

    def __post_init__(self) -> None:
        if not self.customer_id:
            raise NotVerified("A scope without a customer is not a scope.")


def scope_for(conversation: Conversation) -> Scope:
    """The only way to get one.

    The customer comes from the conversation's verification and from
    nowhere else. Note what is *not* a parameter of this function.
    """
    if conversation.verified_at is None or conversation.customer_id is None:
        raise NotVerified(
            "This conversation has not been verified, so there is nothing it "
            "may read."
        )
    return Scope(
        customer_id=conversation.customer_id,
        conversation_id=conversation.id,
        customer_name=conversation.customer.name if conversation.customer else "",
    )


def owned_by(query: Select, column, scope: Scope) -> Select:
    """Narrow a query to the scope. Every customer query goes through this."""
    return query.where(column == scope.customer_id)


def record(
    session: Session,
    *,
    tool: str,
    scope: Scope | None = None,
    conversation: Conversation | None = None,
    arguments: dict[str, Any] | None = None,
    allowed: bool = True,
    refusal: str = "",
    rows: int = 0,
) -> AccessLog:
    """Write down that somebody reached for customer data."""
    entry = AccessLog(
        conversation_id=(
            scope.conversation_id if scope else (conversation.id if conversation else None)
        ),
        acting_customer_id=scope.customer_id if scope else None,
        tool=tool,
        arguments=_safe(arguments or {}),
        allowed=allowed,
        refusal=refusal[:160],
        rows_returned=rows,
    )
    session.add(entry)
    session.flush()
    return entry


def _safe(arguments: dict[str, Any]) -> dict[str, Any]:
    """Keep the log readable, and keep secrets out of it."""
    out: dict[str, Any] = {}
    for key, value in arguments.items():
        if key in {"password", "token", "secret"}:
            out[key] = "***"
        elif isinstance(value, (str, int, float, bool)) or value is None:
            out[key] = value
        else:
            out[key] = str(value)[:200]
    return out


def belongs_to(session: Session, scope: Scope, model, identifier: Any, column) -> Any:
    """Fetch one row and prove it is this customer's before returning it.

    The important case is the one where the row exists and belongs to
    somebody else. The answer there is the same as for a row that does not
    exist at all: *we have no record of that*. Saying "that order is not
    yours" confirms the order exists, which is a small leak, and small
    leaks are how account numbers get enumerated.
    """
    return session.scalar(
        owned_by(select(model).where(column == identifier), model.customer_id, scope)
    )


def count_of(rows: Iterable[T]) -> int:
    return sum(1 for _ in rows)
