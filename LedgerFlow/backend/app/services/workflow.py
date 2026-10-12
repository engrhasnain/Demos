"""The life of an invoice.

    received -> read -> checked -> posted
                  |        |
                  |        +-> awaiting approval -> approved -> posted
                  |
                  +-> exception -> (resolved) -> checked
                                -> rejected

Moves that are not on this map are refused. That is what stops a blocked
invoice being posted because somebody clicked the wrong button.
"""

from __future__ import annotations

from dataclasses import dataclass

RECEIVED = "received"
READ = "read"
CHECKED = "checked"
EXCEPTION = "exception"
AWAITING_APPROVAL = "awaiting_approval"
APPROVED = "approved"
POSTED = "posted"
REJECTED = "rejected"
CANCELLED = "cancelled"

LABELS: dict[str, str] = {
    RECEIVED: "Received",
    READ: "Read",
    CHECKED: "Checked",
    EXCEPTION: "Needs a person",
    AWAITING_APPROVAL: "Waiting for approval",
    APPROVED: "Approved",
    POSTED: "Posted",
    REJECTED: "Rejected",
    CANCELLED: "Cancelled",
}

DESCRIPTIONS: dict[str, str] = {
    RECEIVED: "Arrived in the mailbox and not read yet.",
    READ: "Read into fields and lines.",
    CHECKED: "Arithmetic, identifiers, order and delivery all agree.",
    EXCEPTION: "Something is wrong or missing and somebody has to look.",
    AWAITING_APPROVAL: "Above the limit that posts on its own.",
    APPROVED: "Signed off and ready for the ledger.",
    POSTED: "In the ledger.",
    REJECTED: "Sent back to the supplier.",
    CANCELLED: "Withdrawn.",
}

TRANSITIONS: dict[str, set[str]] = {
    RECEIVED: {READ, EXCEPTION, CANCELLED},
    READ: {CHECKED, EXCEPTION, CANCELLED},
    CHECKED: {AWAITING_APPROVAL, POSTED, EXCEPTION, CANCELLED},
    EXCEPTION: {CHECKED, READ, AWAITING_APPROVAL, REJECTED, CANCELLED},
    AWAITING_APPROVAL: {APPROVED, EXCEPTION, REJECTED, CANCELLED},
    APPROVED: {POSTED, EXCEPTION, CANCELLED},
    POSTED: set(),
    REJECTED: set(),
    CANCELLED: set(),
}

#: Nothing more happens to an invoice in one of these.
TERMINAL = {POSTED, REJECTED, CANCELLED}

#: An invoice here is on somebody's desk.
NEEDS_A_PERSON = {EXCEPTION, AWAITING_APPROVAL}


class IllegalTransition(Exception):
    def __init__(self, current: str, requested: str) -> None:
        allowed = ", ".join(
            sorted(LABELS.get(s, s) for s in TRANSITIONS.get(current, set()))
        )
        super().__init__(
            f"An invoice that is {LABELS.get(current, current).lower()} cannot move to "
            f"{LABELS.get(requested, requested).lower()}. "
            f"Allowed from here: {allowed or 'nothing, it is finished'}."
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
    needs_a_person: bool
    is_terminal: bool


def describe(status: str) -> StatusView:
    return StatusView(
        code=status,
        label=LABELS.get(status, status),
        description=DESCRIPTIONS.get(status, ""),
        needs_a_person=status in NEEDS_A_PERSON,
        is_terminal=status in TERMINAL,
    )


def all_statuses() -> list[dict[str, object]]:
    return [
        {"code": code, "label": LABELS[code], "description": DESCRIPTIONS[code]}
        for code in LABELS
    ]


# ---------------------------------------------------------------------------
# Exception kinds, in the order a clerk would want to see them
# ---------------------------------------------------------------------------
EXCEPTION_LABELS: dict[str, str] = {
    "bank_detail_change": "Bank details changed",
    "duplicate": "Already received",
    "wrong_entity": "Billed to the wrong company",
    "wrong_buyer_tax_id": "Wrong buyer business number",
    "arithmetic": "The numbers do not add up",
    "future_date": "Dated in the future",
    "barcode_mismatch": "Barcode disagrees with the page",
    "over_tolerance": "Priced above the order",
    "no_purchase_order": "No purchase order",
    "partly_received": "Only part of it has arrived",
    "not_received": "Nothing has arrived yet",
    "missing_field": "Something could not be read",
    "closed_period": "The month is closed",
    "late_arrival": "Arrived very late",
    "unreadable": "The file could not be read",
    "unknown_vendor": "Supplier not recognised",
}

#: block  - nothing is posted and nothing is paid
#: hold   - the clean part posts, the rest is held back
#: note   - recorded, does not stop anything
SEVERITY: dict[str, str] = {
    "bank_detail_change": "block",
    "duplicate": "block",
    "wrong_entity": "block",
    "wrong_buyer_tax_id": "block",
    "unknown_vendor": "block",
    "unreadable": "block",
    "arithmetic": "block",
    "future_date": "block",
    "barcode_mismatch": "block",
    "over_tolerance": "hold",
    "no_purchase_order": "hold",
    "not_received": "hold",
    "missing_field": "hold",
    "partly_received": "hold",
    "closed_period": "note",
    "late_arrival": "note",
}


def severity_of(kind: str) -> str:
    return SEVERITY.get(kind, "hold")


def label_of(kind: str) -> str:
    return EXCEPTION_LABELS.get(kind, kind.replace("_", " "))
