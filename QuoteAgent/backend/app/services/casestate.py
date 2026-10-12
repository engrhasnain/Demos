"""The case lifecycle.

    received -> parsed -> matched -> awaiting customer / awaiting supplier
             -> priced -> awaiting approval -> sent -> revised -> won or lost

Every move is written down, so a case picked up four days later carries on from
exactly where it stopped. Moves that are not on this map are refused, which is
what stops a quote being sent while a question is still open.
"""

from __future__ import annotations

from dataclasses import dataclass

RECEIVED = "received"
PARSED = "parsed"
MATCHED = "matched"
AWAITING_CUSTOMER = "awaiting_customer"
AWAITING_SUPPLIER = "awaiting_supplier"
PRICED = "priced"
AWAITING_APPROVAL = "awaiting_approval"
SENT = "sent"
REVISED = "revised"
WON = "won"
LOST = "lost"
CANCELLED = "cancelled"

#: Plain wording for the interface.
STATUS_LABELS: dict[str, str] = {
    RECEIVED: "Received",
    PARSED: "Read",
    MATCHED: "Parts identified",
    AWAITING_CUSTOMER: "Waiting for the customer",
    AWAITING_SUPPLIER: "Waiting for a supplier",
    PRICED: "Priced",
    AWAITING_APPROVAL: "Waiting for approval",
    SENT: "Quote sent",
    REVISED: "Revised request received",
    WON: "Won",
    LOST: "Lost",
    CANCELLED: "Cancelled",
}

STATUS_DESCRIPTIONS: dict[str, str] = {
    RECEIVED: "The request has arrived and has not been read yet.",
    PARSED: "The request and its attachments have been turned into line items.",
    MATCHED: "Each line has been matched to a part, or flagged for a question.",
    AWAITING_CUSTOMER: "One consolidated email of questions is with the customer.",
    AWAITING_SUPPLIER: "A price request is with a supplier for parts we do not stock.",
    PRICED: "Every line has a price from the pricing engine.",
    AWAITING_APPROVAL: "One or more approvals are outstanding.",
    SENT: "The quote has gone to the customer.",
    REVISED: "The customer sent a changed request after a quote was sent.",
    WON: "The customer placed the order.",
    LOST: "The customer did not place the order.",
    CANCELLED: "The request was withdrawn.",
}

#: Allowed moves. Anything absent is refused.
#:
#: A revised request can arrive at almost any moment, including while the
#: quote is sitting with a manager for approval, so every live state can move
#: to "revised". What cannot happen is a quote being sent while a question is
#: open or an approval is outstanding, and that is enforced separately by the
#: approval rules rather than by this map.
TRANSITIONS: dict[str, set[str]] = {
    RECEIVED: {PARSED, CANCELLED},
    PARSED: {MATCHED, AWAITING_CUSTOMER, REVISED, CANCELLED},
    MATCHED: {AWAITING_CUSTOMER, AWAITING_SUPPLIER, PRICED, REVISED, CANCELLED},
    AWAITING_CUSTOMER: {MATCHED, AWAITING_SUPPLIER, PRICED, REVISED, CANCELLED},
    AWAITING_SUPPLIER: {MATCHED, AWAITING_CUSTOMER, PRICED, REVISED, CANCELLED},
    # A customer can answer a question while the quote is already priced or
    # sitting with a manager. That answer sends the line back to be matched
    # and priced again, so both states can step backwards to "matched".
    PRICED: {MATCHED, AWAITING_APPROVAL, AWAITING_CUSTOMER, AWAITING_SUPPLIER, SENT, REVISED, CANCELLED},
    AWAITING_APPROVAL: {MATCHED, PRICED, SENT, AWAITING_CUSTOMER, REVISED, CANCELLED},
    SENT: {REVISED, WON, LOST, AWAITING_CUSTOMER, CANCELLED},
    REVISED: {MATCHED, AWAITING_CUSTOMER, AWAITING_SUPPLIER, PRICED, CANCELLED},
    WON: set(),
    LOST: {REVISED},
    CANCELLED: set(),
}

#: Statuses where the case is finished and nothing further should happen.
TERMINAL = {WON, CANCELLED}

#: Statuses where the agent is waiting on somebody outside the company.
WAITING = {AWAITING_CUSTOMER, AWAITING_SUPPLIER}


class IllegalTransition(Exception):
    """Raised when a move is not on the map."""

    def __init__(self, current: str, requested: str) -> None:
        allowed = ", ".join(sorted(STATUS_LABELS.get(s, s) for s in TRANSITIONS.get(current, set())))
        super().__init__(
            f"A case that is {STATUS_LABELS.get(current, current).lower()} cannot move to "
            f"{STATUS_LABELS.get(requested, requested).lower()}. "
            f"Allowed from here: {allowed or 'nothing, the case is finished'}."
        )
        self.current = current
        self.requested = requested


def can_move(current: str, requested: str) -> bool:
    return requested in TRANSITIONS.get(current, set())


def assert_can_move(current: str, requested: str) -> None:
    if current == requested:
        return
    if not can_move(current, requested):
        raise IllegalTransition(current, requested)


@dataclass(frozen=True, slots=True)
class StatusView:
    code: str
    label: str
    description: str
    is_waiting: bool
    is_terminal: bool
    next_options: list[str]


def describe(status: str) -> StatusView:
    return StatusView(
        code=status,
        label=STATUS_LABELS.get(status, status),
        description=STATUS_DESCRIPTIONS.get(status, ""),
        is_waiting=status in WAITING,
        is_terminal=status in TERMINAL,
        next_options=sorted(TRANSITIONS.get(status, set())),
    )


def all_statuses() -> list[dict[str, object]]:
    return [
        {
            "code": code,
            "label": STATUS_LABELS[code],
            "description": STATUS_DESCRIPTIONS[code],
            "next_options": sorted(TRANSITIONS.get(code, set())),
        }
        for code in STATUS_LABELS
    ]
