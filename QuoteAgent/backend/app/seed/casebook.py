"""A working inbox.

One case is a demonstration. Two dozen cases, spread across every state a
request can be in, is a business. This module builds the second kind.

Nothing here is fabricated: each case is a real request put through the real
agent, so the lines were genuinely matched, the prices genuinely computed and
the traces behind every figure are real. Only the clock is moved, so the cases
look like six weeks of ordinary work rather than six weeks of nothing followed
by a busy afternoon.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Case, CaseEvent, CaseMessage, Customer, Product, QuoteVersion, User
from ..services import agent, approvals, casestate
from .samples import workbook_bytes

SEED = 5_120_026

#: How many cases end up in each state. The shape of a real inbox: most work
#: is finished or priced, a steady minority is waiting on somebody outside the
#: company, and a few have only just arrived.
SHAPE: list[tuple[str, int]] = [
    ("received", 3),
    ("awaiting_customer", 4),
    ("awaiting_supplier", 2),
    ("priced", 5),
    ("awaiting_approval", 3),
    ("sent", 4),
    ("won", 2),
    ("lost", 2),
]

SUBJECTS = [
    "RFQ {ref} - {count} items",
    "Quotation request {ref}",
    "Please quote - {ref}",
    "{ref} enquiry, {count} lines",
    "Price request {ref}",
    "RFQ {ref} - urgent",
]

OPENINGS = [
    "Hi,\n\nPlease quote the following.\n\n",
    "Good morning,\n\nCould you price these for us?\n\n",
    "Hello,\n\nWe need a quotation for the items below.\n\n",
    "Hi,\n\nQuote request, items listed below. Lead time please as well.\n\n",
]

CLOSINGS = [
    "\nThanks,\n{name}\n{company}\n",
    "\nBest regards,\n{name}\nPurchasing, {company}\n",
    "\nRegards,\n{name}\n{company}\n",
]

#: Lines Hengtai does not stock, used for the cases waiting on a supplier.
NON_CATALOGUE_LINES = [
    "Shoulder bolt ISO 7379 12x50 M10 class 12.9 plain",
    "Trapezoidal lead screw Tr20x4 right hand, 1000 mm, C7",
    "Linear guide rail 20 mm, 1200 mm long, with two carriages",
    "Shaft collar, one piece clamp, 25 mm bore, stainless",
]

#: Lines that do not say enough, used for the cases waiting on a customer.
UNCLEAR_LINES = [
    "M10 bolt, class 8.8, zinc",
    "Socket head cap screw M8x30, zinc plated",
    "Hexagon head bolt M12x60 class 10.9",
    "Deep groove ball bearing 6205",
    "M16 stud, stainless, 200 off",
]

LOST_REASONS = [
    "Competitor was 4% cheaper on the fasteners.",
    "Customer postponed the project to next quarter.",
    "Lead time on the bearings was too long.",
]

WON_REASONS = [
    "Order placed the same afternoon.",
    "Customer accepted the split shipment option.",
]


@dataclass(slots=True)
class BuiltCase:
    case_id: int
    reference: str
    status: str


def _render(product: Product, style: str) -> str:
    """Write a catalogue part the way a customer would write it."""
    attributes = product.attributes or {}
    if style == "sku":
        return product.sku
    if style == "standard" and product.family == "fastener":
        legacy = attributes.get("legacy_standard") or product.standard
        thread = attributes.get("thread", "")
        length = attributes.get("length_mm", "")
        size = f"{thread}x{length}" if length else thread
        finish = {
            "plain": "plain",
            "zinc_blue": "zinc",
            "zinc_yellow": "yellow zinc",
            "hot_dip_galvanised": "hot dip galvanised",
            "black_oxide": "black",
            "stainless_plain": "stainless",
        }.get(attributes.get("finish", ""), "")
        grade = attributes.get("property_class", "")
        return f"{legacy} {size} {grade} {finish}".strip()
    return product.description_en


def _quantity(generator: random.Random) -> int:
    return generator.choice([25, 40, 100, 200, 250, 500, 750, 1000, 1500, 2000, 2500, 5000])


def _body(
    generator: random.Random,
    products: list[Product],
    *,
    line_count: int,
    extra_lines: list[str],
    contact_name: str,
    company: str,
    reference: str,
) -> tuple[str, list[tuple[str, int]]]:
    rows: list[tuple[str, int]] = []
    for product in generator.sample(products, line_count):
        style = generator.choice(["sku", "standard", "description"])
        rows.append((_render(product, style), _quantity(generator)))
    for line in extra_lines:
        rows.append((line, generator.choice([12, 25, 50, 100, 250])))
    generator.shuffle(rows)

    text = generator.choice(OPENINGS)
    for index, (description, quantity) in enumerate(rows, start=1):
        text += f"{index}. {description} - {quantity} pcs\n"
    text += generator.choice(CLOSINGS).format(name=contact_name, company=company)
    return text, rows


def _backdate(session: Session, case: Case, days_ago: int, hours: int) -> None:
    """Move a finished case back in time so the inbox looks like real weeks."""
    when = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days_ago, hours=hours)
    case.created_at = when
    case.updated_at = when + dt.timedelta(hours=2)
    for offset, event in enumerate(sorted(case.events, key=lambda e: e.id)):
        event.occurred_at = when + dt.timedelta(minutes=3 * offset)
    for message in case.messages:
        message.occurred_at = when + dt.timedelta(minutes=5)
        if message.sent_at is not None:
            message.sent_at = when + dt.timedelta(hours=1)
    for version in case.quote_versions:
        version.created_at = when
        version.updated_at = when + dt.timedelta(hours=1)
        if version.sent_at is not None:
            version.sent_at = when + dt.timedelta(hours=2)
    session.flush()


def build_case_book(
    session: Session,
    *,
    progress: Callable[[str, int, int], None] | None = None,
) -> list[BuiltCase]:
    """Fill the inbox with real cases in every state a request can be in."""
    report = progress or (lambda *_: None)
    generator = random.Random(SEED)

    approver = session.scalar(select(User).where(User.role == "administrator"))
    if approver is None:
        raise RuntimeError("Load the demonstration data before building the case book.")

    products = list(
        session.scalars(
            select(Product).where(Product.is_stocked.is_(True)).order_by(Product.id).limit(4_000)
        )
    )
    if len(products) < 40:
        raise RuntimeError("The catalogue is too small to build a case book.")

    customers = list(
        session.scalars(
            select(Customer)
            .where(Customer.on_credit_hold.is_(False))
            .order_by(Customer.id)
            .limit(400)
        )
    )

    plan: list[str] = []
    for status, count in SHAPE:
        plan.extend([status] * count)

    built: list[BuiltCase] = []
    total = len(plan)

    for index, wanted in enumerate(plan):
        report("Filling the inbox with worked cases", index, total)
        customer = customers[(index * 7 + 3) % len(customers)]
        contact = customer.contacts[0] if customer.contacts else None
        if contact is None:
            continue

        reference = f"PO-{2026}{generator.randint(1000, 9999)}"
        extra: list[str] = []
        if wanted == "awaiting_customer":
            extra = generator.sample(UNCLEAR_LINES, 2)
        elif wanted == "awaiting_supplier":
            extra = [generator.choice(NON_CATALOGUE_LINES)]

        line_count = generator.choice([4, 6, 8, 10, 12, 16])
        body, rows = _body(
            generator,
            products,
            line_count=line_count,
            extra_lines=extra,
            contact_name=contact.full_name,
            company=customer.name,
            reference=reference,
        )
        subject = generator.choice(SUBJECTS).format(ref=reference, count=len(rows))

        attachments: list[tuple[str, bytes, str]] = []
        # Every third request comes as a spreadsheet, as it would in life.
        if index % 3 == 0:
            sheet_rows = [
                {
                    "item": position,
                    "part_number": "",
                    "description": description,
                    "quantity": quantity,
                    "unit": "pcs",
                    "note": "",
                }
                for position, (description, quantity) in enumerate(rows, start=1)
            ]
            attachments.append(
                (
                    f"{reference}.xlsx",
                    workbook_bytes(sheet_rows, title=f"Request for quotation {reference}"),
                    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                )
            )

        case, _message, created = agent.receive_request(
            session,
            sender=f"{contact.full_name} <{contact.email}>",
            subject=subject,
            body=body,
            external_message_id=f"<casebook-{index}-{reference}@{contact.email.split('@')[-1]}>",
            attachments=attachments,
        )
        if not created:
            continue
        case.owner_id = approver.id

        if wanted != "received":
            try:
                agent.run_to_first_stop(session, case, sender_name=approver.full_name)
            except Exception:  # pragma: no cover - a case that cannot run is skipped
                session.rollback()
                continue

            _advance(session, case, wanted, approver, generator)

        _backdate(session, case, days_ago=generator.randint(0, 38), hours=generator.randint(0, 9))
        built.append(BuiltCase(case.id, case.reference, case.status))

    session.flush()
    report("Filling the inbox with worked cases", total, total)
    return built


def _advance(
    session: Session, case: Case, wanted: str, approver: User, generator: random.Random
) -> None:
    """Take a freshly run case to the state the inbox needs it in."""
    version = agent.current_version(session, case)
    if version is None:
        return

    # A question email is drafted but not sent by the agent. Sending it is what
    # moves a case to "waiting for the customer". It is read back from the
    # database rather than off the relationship, which may not have seen it yet.
    draft = session.scalar(
        select(CaseMessage)
        .where(
            CaseMessage.case_id == case.id,
            CaseMessage.kind == "clarification",
            CaseMessage.sent_at.is_(None),
        )
        .order_by(CaseMessage.id.desc())
        .limit(1)
    )

    if wanted == "awaiting_customer":
        if draft is not None:
            agent.send_message(session, case, draft, approver)
        return

    if wanted == "awaiting_supplier":
        if case.status != casestate.AWAITING_SUPPLIER and casestate.can_move(
            case.status, casestate.AWAITING_SUPPLIER
        ):
            agent.move_to(session, case, casestate.AWAITING_SUPPLIER)
        return

    # Everything from here needs a clean, fully priced quote.
    if any(line.status == "needs_clarification" for line in version.lines):
        if draft is not None:
            agent.send_message(session, case, draft, approver)
        return

    if wanted == "awaiting_approval":
        version.requested_discount_percent = Decimal(str(generator.choice([8, 10, 12, 15])))
        agent.price_case(session, case)
        return

    if wanted in {"sent", "won", "lost"}:
        for approval in approvals.outstanding(session, case):
            approvals.decide(
                session, approval, approver, approved=True, comment="Approved by the sales desk."
            )
        if case.status == casestate.AWAITING_APPROVAL:
            case.status = casestate.PRICED
            version.status = "approved"
        if approvals.blocking_reasons(session, version):
            return
        try:
            agent.send_quote(session, case, approver)
        except Exception:  # pragma: no cover - leave it priced rather than fail the load
            session.rollback()
            return

        if wanted == "won":
            case.status = casestate.WON
            case.outcome = "won"
            case.outcome_reason = generator.choice(WON_REASONS)
            case.closed_at = dt.datetime.now(dt.timezone.utc)
        elif wanted == "lost":
            case.status = casestate.LOST
            case.outcome = "lost"
            case.outcome_reason = generator.choice(LOST_REASONS)
            case.closed_at = dt.datetime.now(dt.timezone.utc)
        session.flush()


def summarise(session: Session) -> dict[str, Any]:
    """What the inbox looks like now, for the loader to report."""
    counts: dict[str, int] = {}
    for case in session.scalars(select(Case)):
        counts[case.status] = counts.get(case.status, 0) + 1
    return {"cases": sum(counts.values()), "by_status": counts}
