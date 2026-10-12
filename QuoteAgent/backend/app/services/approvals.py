"""Approval rules.

Four things always need a named person to say yes:

* a line priced below the customer's margin floor;
* a quote worth more than the director's threshold;
* a line for something that is not in the catalogue;
* any email that leaves the building.

The rules are evaluated on the server every time a quote is priced. Changing a
price re-opens the approvals it affects, so an approval cannot be collected on
one set of numbers and then used to send a different set.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..money import dec, money
from ..models import Approval, Case, QuoteVersion, User
from ..security import ROLE_LABELS, role_satisfies
from ..text import count


@dataclass(slots=True)
class RuleOutcome:
    rule_code: str
    title: str
    reason: str
    required_role: str
    detail: dict[str, Any]


def evaluate(session: Session, version: QuoteVersion) -> list[RuleOutcome]:
    """Work out which approvals this version of the quote needs."""
    case = version.case
    customer = case.customer
    outcomes: list[RuleOutcome] = []

    floor = (
        dec(customer.margin_floor_percent)
        if customer is not None
        else dec(settings.default_margin_floor_percent)
    )
    below = [line for line in version.lines if line.below_margin_floor and line.product is not None]
    if below:
        outcomes.append(
            RuleOutcome(
                rule_code="margin_floor",
                title=f"{count(len(below), 'line')} below the {floor}% margin floor",
                reason=f"Floor agreed for {customer.name if customer else 'this customer'}",
                required_role="sales_manager",
                detail={
                    "margin_floor_percent": str(floor),
                    "lines": [
                        {
                            "line_number": line.line_number,
                            "part": line.product.sku if line.product else "",
                            "description": line.product.description_en if line.product else "",
                            "quantity": str(line.quantity_billed),
                            "unit_price": str(line.unit_price),
                            "unit_cost": str(line.unit_cost),
                            "margin_percent": str(line.margin_percent),
                            "shortfall_percent": str(floor - dec(line.margin_percent)),
                            "price_build_up": line.calculation_trace,
                        }
                        for line in below
                    ],
                },
            )
        )

    threshold = dec(settings.director_approval_threshold_twd)
    total_in_base = _total_in_base_currency(version)
    if total_in_base > threshold:
        outcomes.append(
            RuleOutcome(
                rule_code="quote_value",
                title=f"Above {money(threshold)} TWD",
                reason=f"{money(total_in_base)} TWD",
                required_role="director",
                detail={
                    "threshold_twd": str(money(threshold)),
                    "quote_total_twd": str(money(total_in_base)),
                    "quote_total": str(version.grand_total),
                    "currency": version.currency,
                },
            )
        )

    non_catalogue = [line for line in version.lines if line.status == "non_catalogue"]
    if non_catalogue:
        outcomes.append(
            RuleOutcome(
                rule_code="non_catalogue_item",
                title=f"{count(len(non_catalogue), 'line')} for parts Hengtai does not list",
                reason="Supplier price and lead time to accept",
                required_role="sales_manager",
                detail={
                    "lines": [
                        {
                            "line_number": line.line_number,
                            "request_text": line.request_text,
                            "blocking_reason": line.blocking_reason,
                        }
                        for line in non_catalogue
                    ]
                },
            )
        )

    if version.tariff_table is not None and not version.tariff_table.is_signed_off:
        if dec(version.duty_total) > 0:
            outcomes.append(
                RuleOutcome(
                    rule_code="unsigned_duty_table",
                    title="Duty priced on a table a broker has not signed off",
                    reason=f"Table {version.tariff_table.version}, no broker sign-off",
                    required_role="pricing_owner",
                    detail={
                        "tariff_table_version": version.tariff_table.version,
                        "duty_total": str(version.duty_total),
                        "currency": version.currency,
                    },
                )
            )

    return outcomes


def _total_in_base_currency(version: QuoteVersion) -> Decimal:
    total = dec(version.grand_total)
    if version.currency == settings.base_currency or version.exchange_rate is None:
        return total
    rate = dec(version.exchange_rate.rate)
    return money(total / rate) if rate > 0 else total


def synchronise(session: Session, version: QuoteVersion) -> list[Approval]:
    """Create, keep or withdraw approvals so they always match the current numbers."""
    wanted = {outcome.rule_code: outcome for outcome in evaluate(session, version)}
    existing = list(
        session.scalars(
            select(Approval).where(Approval.quote_version_id == version.id)
        )
    )

    for approval in existing:
        outcome = wanted.get(approval.rule_code)
        if outcome is None:
            if approval.status == "pending":
                approval.status = "withdrawn"
                approval.decision_comment = "No longer needed after the quote was re-priced."
            continue
        changed = approval.detail != outcome.detail
        if changed and approval.status != "pending":
            # The numbers moved after someone approved them, so ask again.
            approval.status = "superseded"
            approval.decision_comment = "The quote was re-priced after this decision."
        elif changed:
            approval.reason = outcome.reason
            approval.title = outcome.title
            approval.detail = outcome.detail

    live_codes = {
        approval.rule_code
        for approval in existing
        if approval.status in {"pending", "approved"}
    }
    created: list[Approval] = []
    for code, outcome in wanted.items():
        if code in live_codes:
            continue
        approval = Approval(
            case_id=version.case_id,
            quote_version_id=version.id,
            rule_code=outcome.rule_code,
            title=outcome.title,
            reason=outcome.reason,
            required_role=outcome.required_role,
            detail=outcome.detail,
            status="pending",
        )
        session.add(approval)
        created.append(approval)

    session.flush()
    return created


def outstanding(session: Session, case: Case) -> list[Approval]:
    return list(
        session.scalars(
            select(Approval).where(Approval.case_id == case.id, Approval.status == "pending")
        )
    )


def can_decide(user: User, approval: Approval) -> tuple[bool, str]:
    if approval.status != "pending":
        return False, f"This approval has already been {approval.status}."
    if not role_satisfies(user.role, approval.required_role):
        return False, (
            f"This approval needs the {ROLE_LABELS.get(approval.required_role, approval.required_role)} "
            f"role. You are signed in as {ROLE_LABELS.get(user.role, user.role)}."
        )
    return True, ""


def decide(
    session: Session, approval: Approval, user: User, *, approved: bool, comment: str = ""
) -> Approval:
    import datetime as dt

    allowed, why_not = can_decide(user, approval)
    if not allowed:
        raise PermissionError(why_not)
    approval.status = "approved" if approved else "rejected"
    approval.decided_by_id = user.id
    approval.decided_at = dt.datetime.now(dt.timezone.utc)
    approval.decision_comment = comment
    session.flush()
    return approval


def blocking_reasons(session: Session, version: QuoteVersion) -> list[str]:
    """Everything that stops this quote being sent right now."""
    reasons: list[str] = []

    pending = [
        approval
        for approval in session.scalars(
            select(Approval).where(Approval.quote_version_id == version.id)
        )
        if approval.status == "pending"
    ]
    for approval in pending:
        reasons.append(
            f"{approval.title} - waiting for "
            f"{ROLE_LABELS.get(approval.required_role, approval.required_role).lower()} approval."
        )

    open_questions = [
        line for line in version.lines if line.status == "needs_clarification"
    ]
    if open_questions:
        numbers = ", ".join(str(line.line_number) for line in open_questions[:8])
        reasons.append(
            f"{count(len(open_questions), 'line')} still have an open question (lines {numbers})."
        )

    waiting_supplier = [line for line in version.lines if line.status == "awaiting_supplier"]
    if waiting_supplier:
        reasons.append(
            f"{count(len(waiting_supplier), 'line')} are waiting for a supplier price."
        )

    if not version.lines:
        reasons.append("The quote has no lines.")

    if dec(version.grand_total) <= 0 and version.lines:
        reasons.append("The quote has no value, so nothing has been priced yet.")

    if version.needs_repricing:
        reasons.append(
            version.repricing_reason or "The quote has to be re-priced before it is sent."
        )

    return reasons
