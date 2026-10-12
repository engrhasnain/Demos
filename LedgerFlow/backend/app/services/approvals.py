"""Who has to sign, and when.

An invoice posts on its own only when every check passed and it is small
enough. Above that somebody signs; above that again, two people sign. Each
rule is re-evaluated whenever the figures change, so an approval given on one
amount can never be used to pay a different one.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..money import dec, money
from ..models import Invoice, Approval, User
from ..security import ROLE_LABELS, role_satisfies
from . import workflow


@dataclass(slots=True)
class RuleOutcome:
    rule_code: str
    title: str
    reason: str
    required_role: str
    step: int
    detail: dict[str, Any]


def amount_in_base(invoice: Invoice) -> Decimal:
    """Everything is compared in one currency, or the limits mean nothing.

    Compared as a size, not a direction: a credit note for a large sum needs
    the same signature a bill for it would.
    """
    if invoice.amount_in_base and dec(invoice.amount_in_base) > 0:
        return abs(dec(invoice.amount_in_base))
    return abs(dec(invoice.approved_amount))


def evaluate(session: Session, invoice: Invoice) -> list[RuleOutcome]:
    outcomes: list[RuleOutcome] = []
    value = amount_in_base(invoice)
    ceiling = dec(settings.auto_post_ceiling_twd)
    two_step = dec(settings.two_step_approval_twd)

    # --- an exception anybody has to look at ------------------------------
    open_exceptions = [e for e in invoice.exceptions if e.resolved_at is None]
    blocking = [e for e in open_exceptions if e.severity == "block"]
    holding = [e for e in open_exceptions if e.severity == "hold"]

    if blocking:
        outcomes.append(
            RuleOutcome(
                rule_code="blocked",
                title=workflow.label_of(blocking[0].kind),
                reason=blocking[0].summary,
                required_role="accountant",
                step=1,
                detail={
                    "exceptions": [
                        {"kind": e.kind, "summary": e.summary} for e in blocking
                    ]
                },
            )
        )
        return outcomes

    if holding:
        outcomes.append(
            RuleOutcome(
                rule_code="held_amount",
                title=f"{money(invoice.held_amount)} held back",
                reason=(
                    f"{money(invoice.approved_amount)} of {money(invoice.total_amount)} payable"
                    + (f" - {invoice.hold_reason}" if invoice.hold_reason else "")
                ),
                required_role="accountant",
                step=1,
                detail={
                    "payable": str(invoice.approved_amount),
                    "held": str(invoice.held_amount),
                    "reasons": [
                        {"kind": e.kind, "summary": e.summary} for e in holding
                    ],
                },
            )
        )

    # --- the value ---------------------------------------------------------
    if value > two_step:
        outcomes.append(
            RuleOutcome(
                rule_code="value_two_step",
                title=f"Above {money(two_step)}",
                reason=f"{money(value)} against a {money(two_step)} limit",
                required_role="controller",
                step=1,
                detail={"amount": str(value), "limit": str(two_step)},
            )
        )
        outcomes.append(
            RuleOutcome(
                rule_code="value_two_step_second",
                title="Second signature",
                reason=f"{money(value)} needs two signatures",
                required_role="finance_director",
                step=2,
                detail={"amount": str(value), "limit": str(two_step)},
            )
        )
    elif value > ceiling:
        outcomes.append(
            RuleOutcome(
                rule_code="value_single",
                title=f"Above {money(ceiling)}",
                reason=f"{money(value)} against a {money(ceiling)} limit",
                required_role="accountant",
                step=1,
                detail={"amount": str(value), "limit": str(ceiling)},
            )
        )

    # --- a credit note always gets a pair of eyes -------------------------
    if invoice.kind == "credit_note":
        outcomes.append(
            RuleOutcome(
                rule_code="credit_note",
                title="Credit note",
                reason="Applied against an earlier bill",
                required_role="accountant",
                step=1,
                detail={"credits_invoice_id": invoice.credits_invoice_id},
            )
        )

    return outcomes


def synchronise(session: Session, invoice: Invoice) -> list[Approval]:
    """Keep the approvals in step with the current figures."""
    wanted = {outcome.rule_code: outcome for outcome in evaluate(session, invoice)}
    existing = list(
        session.scalars(select(Approval).where(Approval.invoice_id == invoice.id))
    )

    for approval in existing:
        outcome = wanted.get(approval.rule_code)
        if outcome is None:
            if approval.status == "pending":
                approval.status = "withdrawn"
                approval.comment = "No longer needed after the invoice was checked again."
            continue
        if approval.detail != outcome.detail:
            if approval.status == "approved":
                approval.status = "superseded"
                approval.comment = "The figures changed after this was signed."
            else:
                approval.title = outcome.title
                approval.reason = outcome.reason
                approval.detail = outcome.detail

    live = {a.rule_code for a in existing if a.status in {"pending", "approved"}}
    created: list[Approval] = []
    for code, outcome in wanted.items():
        if code in live:
            continue
        approval = Approval(
            invoice_id=invoice.id,
            rule_code=outcome.rule_code,
            title=outcome.title,
            reason=outcome.reason,
            required_role=outcome.required_role,
            step=outcome.step,
            detail=outcome.detail,
            status="pending",
        )
        session.add(approval)
        created.append(approval)

    session.flush()
    return created


def outstanding(session: Session, invoice: Invoice) -> list[Approval]:
    return list(
        session.scalars(
            select(Approval).where(
                Approval.invoice_id == invoice.id, Approval.status == "pending"
            ).order_by(Approval.step)
        )
    )


def can_decide(user: User, approval: Approval, session: Session) -> tuple[bool, str]:
    if approval.status != "pending":
        return False, f"This has already been {approval.status}."
    if not role_satisfies(user.role, approval.required_role):
        return False, (
            f"This needs the {ROLE_LABELS.get(approval.required_role, approval.required_role)} "
            f"role. You are signed in as {ROLE_LABELS.get(user.role, user.role)}."
        )
    # The second signature only opens once the first is given.
    if approval.step > 1:
        earlier = [
            a
            for a in session.scalars(
                select(Approval).where(
                    Approval.invoice_id == approval.invoice_id,
                    Approval.step < approval.step,
                )
            )
            if a.status == "pending"
        ]
        if earlier:
            return False, "The first signature has not been given yet."
    # Nobody signs their own second signature.
    if approval.step > 1:
        first = session.scalar(
            select(Approval).where(
                Approval.invoice_id == approval.invoice_id,
                Approval.step == approval.step - 1,
                Approval.status == "approved",
            )
        )
        if first is not None and first.decided_by_id == user.id:
            return False, "The second signature has to come from somebody else."
    return True, ""


def decide(
    session: Session, approval: Approval, user: User, *, approved: bool, comment: str = ""
) -> Approval:
    allowed, why_not = can_decide(user, approval, session)
    if not allowed:
        raise PermissionError(why_not)
    approval.status = "approved" if approved else "rejected"
    approval.decided_by_id = user.id
    approval.decided_at = dt.datetime.now(dt.timezone.utc)
    approval.comment = comment
    session.flush()
    return approval


def blocking_reasons(session: Session, invoice: Invoice) -> list[str]:
    """Everything stopping this invoice from reaching the ledger."""
    reasons: list[str] = []

    # Short on purpose. The screen already shows a card for every exception
    # and every signature; repeating their wording here as a sentence meant
    # the same thing was on the page three times over.
    for exception in invoice.exceptions:
        if exception.resolved_at is None and exception.severity == "block":
            reasons.append(workflow.label_of(exception.kind))

    for approval in outstanding(session, invoice):
        # The "blocked" rule is raised from a blocking exception and takes its
        # title, so listing both says the same thing twice.
        if approval.rule_code == "blocked":
            continue
        reasons.append(
            f"{approval.title}: "
            f"{ROLE_LABELS.get(approval.required_role, approval.required_role).lower()}"
        )

    if invoice.kind == "bill" and dec(invoice.approved_amount) <= 0:
        reasons.append("Nothing payable yet")

    if invoice.vendor is not None and invoice.vendor.bank_change_pending:
        # Only worth saying when it is the supplier that is blocked rather
        # than this invoice; otherwise the exception above already said it.
        if not any(
            e.kind == "bank_detail_change" and e.resolved_at is None
            for e in invoice.exceptions
        ):
            reasons.append("Bank details unconfirmed")

    # A supplier-level bank block and an invoice-level one are one problem.
    seen: set[str] = set()
    return [r for r in reasons if not (r in seen or seen.add(r))]


def may_post_untouched(session: Session, invoice: Invoice) -> tuple[bool, str]:
    """Can this go straight to the ledger with nobody looking at it?"""
    if invoice.touched_by_a_person:
        return False, "Already worked on"
    open_exceptions = [e for e in invoice.exceptions if e.resolved_at is None]
    if any(e.severity in {"block", "hold"} for e in open_exceptions):
        kinds = ", ".join(
            workflow.label_of(e.kind).lower()
            for e in open_exceptions
            if e.severity in {"block", "hold"}
        )
        return False, kinds
    if outstanding(session, invoice):
        return False, "Needs a signature"
    value = amount_in_base(invoice)
    if value > dec(settings.auto_post_ceiling_twd):
        return False, f"{money(value)} is above the limit"
    return True, "Ready"
