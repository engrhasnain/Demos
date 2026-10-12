"""The agent: the steps, in order, with everything written down.

Nothing here invents a number and nothing here sends anything on its own. The
agent reads, matches, asks, waits, prices and then stops in front of a person.
Each step records what it did, how long it took, which engine it used and what
that cost, so the case timeline is a true account rather than a summary.
"""

from __future__ import annotations

import datetime as dt
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..domain.partnumbers import merge_specifications, parse_specification
from ..money import dec, money
from ..models import (
    Case,
    CaseAttachment,
    CaseMessage,
    Customer,
    CustomerContact,
    QuoteLine,
    QuoteVersion,
    User,
)
from . import approvals, casestate, clarify, matching, pricing, rates, reasoning, supplier
from .audit import record_event
from .intake import AttachmentReading, ExtractedRow, addresses_in, read_attachment, split_thread
from ..text import count


class AgentError(Exception):
    pass


@dataclass(slots=True)
class StepResult:
    step: str
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------
def next_case_reference(session: Session) -> str:
    year = dt.date.today().year
    prefix = f"RQ-{year}-"
    highest = session.scalar(
        select(func.max(Case.reference)).where(Case.reference.like(f"{prefix}%"))
    )
    sequence = int(highest.rsplit("-", 1)[-1]) + 1 if highest else 1
    return f"{prefix}{sequence:05d}"


def move_to(session: Session, case: Case, status: str, *, note: str = "") -> None:
    casestate.assert_can_move(case.status, status)
    if case.status == status:
        return
    before = case.status
    case.status = status
    record_event(
        session,
        case_id=case.id,
        kind="status_changed",
        summary=(
            f"{casestate.STATUS_LABELS.get(before, before)} to "
            f"{casestate.STATUS_LABELS.get(status, status)}"
            + (f". {note}" if note else "")
        ),
        actor_type="system",
        actor_name="Case lifecycle",
        detail={"from": before, "to": status, "note": note},
    )


# ---------------------------------------------------------------------------
# 1. Intake
# ---------------------------------------------------------------------------
def receive_request(
    session: Session,
    *,
    sender: str,
    subject: str,
    body: str,
    external_message_id: str,
    attachments: list[tuple[str, bytes, str]] | None = None,
    received_at: dt.datetime | None = None,
    recipients: list[str] | None = None,
) -> tuple[Case, CaseMessage, bool]:
    """Take in an email. Delivering the same message twice changes nothing."""
    existing = session.scalar(
        select(CaseMessage).where(CaseMessage.external_message_id == external_message_id)
    )
    if existing is not None:
        case = session.get(Case, existing.case_id)
        assert case is not None
        record_event(
            session,
            case_id=case.id,
            kind="duplicate_delivery_ignored",
            summary=(
                f"The same email ({external_message_id}) arrived again and was ignored. "
                "Intake is repeat-safe."
            ),
            actor_type="system",
            actor_name="Intake",
        )
        return case, existing, False

    sender_address = (addresses_in(sender) or [sender.strip().lower()])[0]
    contact = session.scalar(
        select(CustomerContact).where(CustomerContact.email == sender_address)
    )
    customer: Customer | None = contact.customer if contact else None
    if customer is None:
        domain = sender_address.rsplit("@", 1)[-1]
        customer = session.scalar(
            select(Customer)
            .join(CustomerContact, CustomerContact.customer_id == Customer.id)
            .where(CustomerContact.email.like(f"%@{domain}"))
            .limit(1)
        )

    newest, _history = split_thread(body)
    language = "zh" if sum(1 for ch in newest if "一" <= ch <= "鿿") >= 4 else "en"

    case = Case(
        reference=next_case_reference(session),
        customer_id=customer.id if customer else None,
        contact_email=sender_address,
        contact_name=contact.full_name if contact else "",
        subject=subject[:255],
        language=contact.language if contact else language,
        status=casestate.RECEIVED,
        incoterm=customer.default_incoterm if customer else "FOB",
        named_place=customer.default_named_place if customer else "Taichung",
        destination_country=customer.country if customer else "TW",
        quote_currency=customer.currency if customer else settings.base_currency,
    )
    session.add(case)
    session.flush()

    message = CaseMessage(
        case_id=case.id,
        direction="inbound",
        external_message_id=external_message_id,
        sender=sender_address,
        recipients=recipients or ["sales@hengtai-industrial.example"],
        subject=subject[:255],
        body=body,
        language=case.language,
        occurred_at=received_at or dt.datetime.now(dt.timezone.utc),
        kind="customer",
    )
    session.add(message)
    session.flush()

    for filename, data, content_type in attachments or []:
        reading = read_attachment(data, filename, content_type)
        session.add(
            CaseAttachment(
                message_id=message.id,
                filename=filename,
                content_type=content_type or "application/octet-stream",
                size_bytes=len(data),
                parsed_with=reading.parsed_with,
                parse_note=(reading.note or "; ".join(reading.problems))[:255],
                extracted_rows=[row.to_dict() for row in reading.rows],
            )
        )

    session.flush()
    record_event(
        session,
        case_id=case.id,
        kind="request_received",
        summary=(
            f"Request received from {sender_address}"
            + (f" ({customer.name})" if customer else " (no customer record found)")
            + f" with {count(len(attachments or []), 'attachment')}."
        ),
        actor_type="customer",
        actor_name=sender_address,
        detail={
            "message_id": external_message_id,
            "subject": subject,
            "attachments": [name for name, _, _ in attachments or []],
            "customer_matched": bool(customer),
            "language": case.language,
        },
    )
    return case, message, True


# ---------------------------------------------------------------------------
# 2. Read the request into line items
# ---------------------------------------------------------------------------
def _rows_from_case(session: Session, case: Case) -> tuple[list[ExtractedRow], dict[str, Any]]:
    """Spreadsheet rows win; the email text fills in anything they did not cover."""
    message = next((m for m in case.messages if m.direction == "inbound"), None)
    if message is None:
        raise AgentError("This case has no incoming message to read.")

    spreadsheet_rows: list[ExtractedRow] = []
    attachment_notes: list[str] = []
    for attachment in message.attachments:
        for raw in attachment.extracted_rows or []:
            spreadsheet_rows.append(
                ExtractedRow(
                    line_number=int(raw["line_number"]),
                    description=raw["description"],
                    customer_reference=raw.get("customer_reference", ""),
                    quantity=dec(raw.get("quantity", 0)),
                    unit=raw.get("unit", "piece"),
                    requested_date=raw.get("requested_date", ""),
                    note=raw.get("note", ""),
                    source_reference=raw.get("source_reference", attachment.filename),
                )
            )
        if attachment.parse_note:
            attachment_notes.append(f"{attachment.filename}: {attachment.parse_note}")

    newest, _ = split_thread(message.body)
    reading = reasoning.read_request_lines(
        message.body,
        context=(
            f"The customer is {case.customer.name}. " if case.customer else ""
        )
        + "Hengtai Industrial Supply sells fasteners, bearings and pneumatic parts.",
    )
    text_rows = [
        ExtractedRow(
            line_number=int(item["line_number"]),
            description=item["description"],
            customer_reference=item.get("customer_reference", ""),
            quantity=dec(item.get("quantity", 0)),
            unit=item.get("unit", "piece"),
            requested_date=item.get("requested_date", ""),
            note="",
            source_reference="email body",
        )
        for item in reading.value.get("lines", [])
    ]

    # When a bill of materials is attached, the attachment is the bill of
    # materials. Prose in the covering email mentions part standards all the
    # time ("some are DIN numbers from the drawings") and reading those as
    # extra lines puts phantom items on the quote. Anything the email text
    # suggested that is not in the attachment is recorded on the timeline so
    # nothing is silently dropped, but it does not become a line.
    ignored_from_email: list[str] = []
    if spreadsheet_rows:
        known = {r.description.strip().lower() for r in spreadsheet_rows}
        ignored_from_email = [
            r.description for r in text_rows if r.description.strip().lower() not in known
        ]
        rows = spreadsheet_rows
    else:
        rows = text_rows

    for index, row in enumerate(rows, start=1):
        row.line_number = index

    detail = {
        "reading": reading.as_event_detail(),
        "rows_from_spreadsheet": len(spreadsheet_rows),
        "rows_from_email_text": len(text_rows),
        "lines_used": len(rows),
        "source_of_truth": "the attached spreadsheet" if spreadsheet_rows else "the email text",
        "ignored_from_email_text": ignored_from_email,
        "attachment_notes": attachment_notes,
        "incoterm_in_text": reading.value.get("incoterm", ""),
        "named_place_in_text": reading.value.get("named_place", ""),
        "currency_in_text": reading.value.get("currency", ""),
        "language": reading.value.get("language", case.language),
        "notes": reading.value.get("notes", []),
        "_result": reading,
    }
    return rows, detail


def read_request(session: Session, case: Case) -> StepResult:
    started = time.perf_counter()
    rows, detail = _rows_from_case(session, case)
    result: reasoning.ReasoningResult = detail.pop("_result")

    version = current_version(session, case)
    if version is None:
        version = QuoteVersion(
            case=case,
            version_number=1,
            status="draft",
            currency=case.quote_currency,
            incoterm=case.incoterm,
            named_place=case.named_place,
            destination_country=case.destination_country,
        )
        session.add(version)
        session.flush()

    for line in list(version.lines):
        session.delete(line)
    version.lines.clear()
    session.flush()

    for row in rows:
        version.lines.append(
            QuoteLine(
                line_number=row.line_number,
                request_text=row.description,
                original_request_text=row.description,
                customer_reference=row.customer_reference,
                requested_quantity=row.quantity,
                requested_unit=row.unit,
                source_reference=row.source_reference,
                status="matched",
            )
        )

    if detail.get("incoterm_in_text"):
        case.incoterm = detail["incoterm_in_text"]
        version.incoterm = case.incoterm
        if detail.get("named_place_in_text"):
            case.named_place = detail["named_place_in_text"][:60]
            version.named_place = case.named_place
    if detail.get("currency_in_text"):
        case.quote_currency = detail["currency_in_text"]
        version.currency = case.quote_currency

    session.flush()
    duration = int((time.perf_counter() - started) * 1000)
    ignored = detail.get("ignored_from_email_text", [])
    move_to(session, case, casestate.PARSED)
    record_event(
        session,
        case_id=case.id,
        kind="request_read",
        summary=(
            f"{count(len(rows), 'line item')} read from {detail['source_of_truth']}."
            + (
                f" {count(len(ignored), 'phrase')} in the covering email looked like parts "
                "but are not on the attachment, so they were not added."
                if ignored
                else ""
            )
        ),
        detail=detail,
        duration_ms=duration,
        engine=result.engine,
        model=result.model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        cost_usd=result.cost_usd,
    )
    return StepResult("read_request", f"{count(len(rows), 'line item')} read", detail, duration)


# ---------------------------------------------------------------------------
# 3. Match every line to a part
# ---------------------------------------------------------------------------
def match_lines(session: Session, case: Case) -> StepResult:
    started = time.perf_counter()
    version = require_version(session, case)
    index = matching.get_index(session)

    matched = ambiguous = non_catalogue = 0
    drafts: list[clarify.QuestionDraft] = []

    for line in version.lines:
        if line.status in {"awaiting_supplier", "withdrawn"}:
            continue
        # The customer's own part reference and the description are read as one
        # line, because a reference alone is a number and a description alone
        # often omits the number the cross-reference table is keyed on.
        text = f"{line.customer_reference} {line.request_text}".strip()
        specification = parse_specification(text)

        # Anything the customer has already settled by answering a question
        # overrides what the written line says, whatever language the answer
        # came in. Without this a clarified line would stay flagged for ever.
        for attribute, value in (line.resolved_attributes or {}).items():
            specification.attributes[attribute] = value
            if attribute in specification.missing:
                specification.missing.remove(attribute)
            if attribute in specification.assumed:
                specification.assumed.remove(attribute)
            specification.conflicts = [
                conflict
                for conflict in specification.conflicts
                if conflict.get("attribute") != attribute
            ]
            specification.notes.append(
                f"{attribute.replace('_', ' ')} settled by the customer's answer: {value}."
            )

        result = matching.match_line(
            session, text, specification=specification, index=index
        )

        line.product_id = result.product.id if result.product else None
        line.match_method = result.method
        line.match_confidence = result.confidence
        line.match_reasons = result.reasons
        line.attribute_check = {
            "family": result.specification.family,
            "requested": result.specification.attributes,
            "checks": [c.to_dict() for c in result.checks],
            "notes": result.specification.notes,
        }
        line.alternatives = result.alternatives
        line.requested_attributes = result.specification.attributes
        line.proposed_by = settings.reasoning_engine
        line.blocking_reason = result.blocking_reason

        if result.status == "matched":
            line.status = "matched"
            matched += 1
        elif result.status == "non_catalogue":
            line.status = "non_catalogue"
            non_catalogue += 1
        else:
            line.status = "needs_clarification"
            ambiguous += 1

        for question in result.questions:
            drafts.append(
                clarify.QuestionDraft(
                    line_number=line.line_number,
                    kind=question["kind"],
                    question_en=question["question"],
                    question_zh="",
                    options=[str(o) for o in question.get("options", [])],
                    quote_line_id=line.id,
                    attribute=question.get("attribute", ""),
                )
            )

    session.flush()
    round_number = clarify.next_round_number(session, case)
    created = clarify.record_questions(session, case, drafts, round_number=round_number)

    duration = int((time.perf_counter() - started) * 1000)
    move_to(session, case, casestate.MATCHED)
    detail = {
        "matched": matched,
        "needs_clarification": ambiguous,
        "not_in_catalogue": non_catalogue,
        "questions_raised": len(created),
        "question_round": round_number,
        "lines": [
            {
                "line_number": line.line_number,
                "request": line.request_text,
                "part": line.product.sku if line.product else "",
                "method": line.match_method,
                "confidence": str(line.match_confidence),
                "status": line.status,
                "reasons": line.match_reasons,
            }
            for line in version.lines
        ],
    }
    record_event(
        session,
        case_id=case.id,
        kind="lines_matched",
        summary=(
            f"{count(matched, 'line')} matched, {ambiguous} flagged for a question, "
            f"{non_catalogue} not in the catalogue."
        ),
        detail=detail,
        duration_ms=duration,
        engine=settings.reasoning_engine,
    )
    return StepResult("match_lines", detail_summary(detail), detail, duration)


def detail_summary(detail: dict[str, Any]) -> str:
    return (
        f"{detail['matched']} matched, {detail['needs_clarification']} to ask about, "
        f"{detail['not_in_catalogue']} not stocked"
    )


# ---------------------------------------------------------------------------
# 4. One consolidated question email
# ---------------------------------------------------------------------------
def draft_question_email(session: Session, case: Case, *, sender_name: str) -> CaseMessage | None:
    questions = clarify.open_questions(session, case)
    if not questions:
        return None

    subject, body = clarify.compose_email(case, questions, sender_name=sender_name)
    already_asked = sum(
        1 for m in case.messages if m.kind == "clarification" and m.direction == "outbound"
    )
    message = CaseMessage(
        case_id=case.id,
        direction="outbound",
        external_message_id=f"{case.reference}-questions-{already_asked + 1}",
        sender="sales@hengtai-industrial.example",
        recipients=[case.contact_email],
        subject=subject[:255],
        body=body,
        language=case.language,
        kind="clarification",
    )
    session.add(message)
    session.flush()
    for question in questions:
        question.asked_in_message_id = message.id

    record_event(
        session,
        case_id=case.id,
        kind="questions_drafted",
        summary=(
            f"One email drafted with {count(len(questions), 'question')}. It is not sent until "
            "a person approves it."
        ),
        detail={
            "question_count": len(questions),
            "subject": subject,
            "lines": sorted({q.line_number for q in questions}),
        },
    )
    return message


def send_message(session: Session, case: Case, message: CaseMessage, user: User) -> CaseMessage:
    """Nothing leaves the building without a named approver."""
    if message.sent_at is not None:
        raise AgentError("That email has already been sent.")
    message.approved_by_id = user.id
    message.sent_at = dt.datetime.now(dt.timezone.utc)
    session.flush()

    record_event(
        session,
        case_id=case.id,
        kind="email_sent",
        summary=f"{message.subject} sent to {', '.join(message.recipients)}, approved by {user.full_name}.",
        actor_type="person",
        actor_name=user.full_name,
        detail={"message_id": message.id, "kind": message.kind, "approved_by": user.email},
    )
    if message.kind == "clarification":
        move_to(session, case, casestate.AWAITING_CUSTOMER)
    return message


# ---------------------------------------------------------------------------
# 5. Supplier sub-requests, which never block the other lines
# ---------------------------------------------------------------------------
def request_supplier_prices(session: Session, case: Case) -> StepResult:
    version = require_version(session, case)
    waiting = [line for line in version.lines if line.status == "non_catalogue"]
    if not waiting:
        return StepResult("request_supplier_prices", "No lines need a supplier price.")

    chosen = supplier.choose_supplier(session, waiting[0])
    if chosen is None:
        raise AgentError("No supplier is on file to ask.")

    request = supplier.create_request(session, case, waiting, chosen)
    subject, body = supplier.compose_request_email(case, waiting, request.reference)
    message = CaseMessage(
        case_id=case.id,
        direction="outbound",
        external_message_id=f"{request.reference}-out",
        sender="purchasing@hengtai-industrial.example",
        recipients=[chosen.email],
        subject=subject[:255],
        body=body,
        language="en",
        kind="supplier_request",
    )
    session.add(message)
    session.flush()

    detail = {
        "supplier": chosen.name,
        "reference": request.reference,
        "lines": request.line_numbers,
        "other_lines_continue": len(version.lines) - len(waiting),
    }
    record_event(
        session,
        case_id=case.id,
        kind="supplier_request_drafted",
        summary=(
            f"Price request {request.reference} drafted to {chosen.name} for "
            f"{count(len(waiting), 'line')}. The other {count(detail['other_lines_continue'], 'line')} "
            "carry on."
        ),
        detail=detail,
    )
    if case.status != casestate.AWAITING_CUSTOMER:
        move_to(session, case, casestate.AWAITING_SUPPLIER)
    return StepResult("request_supplier_prices", f"Asked {chosen.name}", detail)


# ---------------------------------------------------------------------------
# 6. Price
# ---------------------------------------------------------------------------
def price_case(session: Session, case: Case, *, on_date: dt.date | None = None) -> StepResult:
    started = time.perf_counter()
    version = require_version(session, case)
    version.incoterm = case.incoterm
    version.named_place = case.named_place
    version.destination_country = case.destination_country
    version.currency = case.quote_currency

    report = pricing.price_quote_version(session, version, on_date=on_date)
    created = approvals.synchronise(session, version)
    session.flush()

    duration = int((time.perf_counter() - started) * 1000)
    if version.lines and report.priced_lines:
        move_to(session, case, casestate.PRICED)
    if created:
        move_to(session, case, casestate.AWAITING_APPROVAL)
        version.status = "awaiting_approval"

    detail = {
        "priced_lines": report.priced_lines,
        "lines_not_priced": report.skipped_lines,
        "currency": report.currency,
        "goods_total": str(report.goods_total),
        "freight_total": str(report.freight_total),
        "insurance_total": str(report.insurance_total),
        "duty_total": str(report.duty_total),
        "grand_total": str(report.grand_total),
        "margin_percent": str(report.margin_percent),
        "approvals_created": [a.title for a in created],
        "warnings": report.warnings,
        "tariff_table": rates.tariff_table_summary(version.tariff_table),
    }
    record_event(
        session,
        case_id=case.id,
        kind="quote_priced",
        summary=(
            f"{count(report.priced_lines, 'line')} priced. Total {report.grand_total} "
            f"{report.currency} at {version.incoterm} {version.named_place}."
        ),
        detail=detail,
        duration_ms=duration,
    )
    return StepResult("price_case", f"{report.grand_total} {report.currency}", detail, duration)


# ---------------------------------------------------------------------------
# 7. Send the quote
# ---------------------------------------------------------------------------
def send_quote(session: Session, case: Case, user: User) -> StepResult:
    version = require_version(session, case)

    # Sending the same version twice was caught only by the unique key on the
    # message, which surfaced as a database error and a 500. The customer
    # never got two quotes, but only because the schema happened to stop it.
    if version.status == "sent":
        raise AgentError(
            f"Version {version.version_number} has already been sent"
            + (f" on {version.sent_at:%Y-%m-%d}" if version.sent_at else "")
            + ". Revise it to send a new one."
        )

    blocking = approvals.blocking_reasons(session, version)
    if blocking:
        raise AgentError("This quote cannot be sent yet: " + " ".join(blocking))

    integrity = pricing.verify_pricing_integrity(session, version)
    if not integrity.ok:
        raise PricingRefused(integrity)

    version = require_version(session, case)
    version.status = "sent"
    version.sent_at = dt.datetime.now(dt.timezone.utc)

    message = CaseMessage(
        case_id=case.id,
        direction="outbound",
        external_message_id=f"{case.reference}-quote-v{version.version_number}",
        sender="sales@hengtai-industrial.example",
        recipients=[case.contact_email],
        subject=f"Quotation {case.reference} version {version.version_number}",
        body=(
            f"Dear {case.contact_name or 'Sir or Madam'},\n\n"
            f"Please find our quotation {case.reference} version {version.version_number}, "
            f"valid until {version.valid_until}.\n\n"
            f"Total {version.grand_total} {version.currency}, "
            f"{version.incoterm} {version.named_place}.\n\n"
            "Kind regards,\nHengtai Industrial Supply"
        ),
        language=case.language,
        kind="quote",
        approved_by_id=user.id,
        sent_at=dt.datetime.now(dt.timezone.utc),
    )
    session.add(message)
    session.flush()

    move_to(session, case, casestate.SENT)
    detail = {
        "version": version.version_number,
        "total": str(version.grand_total),
        "currency": version.currency,
        "valid_until": version.valid_until.isoformat() if version.valid_until else "",
        "pricing_integrity": integrity.to_dict(),
        "approved_by": user.email,
    }
    record_event(
        session,
        case_id=case.id,
        kind="quote_sent",
        summary=(
            f"Quote version {version.version_number} sent, {version.grand_total} "
            f"{version.currency}, approved by {user.full_name}."
        ),
        actor_type="person",
        actor_name=user.full_name,
        detail=detail,
    )
    return StepResult("send_quote", "Quote sent", detail)


class PricingRefused(Exception):
    def __init__(self, report: pricing.IntegrityReport) -> None:
        super().__init__(report.to_dict()["statement"])
        self.report = report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def current_version(session: Session, case: Case) -> QuoteVersion | None:
    """Always asked of the database, never of a relationship that may be stale."""
    return session.scalar(
        select(QuoteVersion)
        .where(QuoteVersion.case_id == case.id)
        .order_by(QuoteVersion.version_number.desc())
        .limit(1)
    )


def require_version(session: Session, case: Case) -> QuoteVersion:
    version = current_version(session, case)
    if version is None:
        raise AgentError("This case has no quote version yet. Read the request first.")
    return version


def elapsed_summary(case: Case) -> dict[str, Any]:
    """How long the case has taken, and what the reading has cost so far."""
    events = sorted(case.events, key=lambda e: e.id)
    if not events:
        return {"elapsed_minutes": 0, "model_cost_usd": "0", "steps": 0}
    first, last = events[0].occurred_at, events[-1].occurred_at
    cost = sum((dec(e.cost_usd) for e in events), Decimal("0"))
    working_ms = sum(e.duration_ms for e in events)
    return {
        "started_at": first.isoformat(),
        "latest_at": last.isoformat(),
        "elapsed_minutes": round((last - first).total_seconds() / 60, 1),
        "agent_working_seconds": round(working_ms / 1000, 2),
        "model_cost_usd": str(money(cost).normalize()) if cost else "0",
        "steps": len(events),
        "tokens_in": sum(e.input_tokens for e in events),
        "tokens_out": sum(e.output_tokens for e in events),
    }


def run_to_first_stop(session: Session, case: Case, *, sender_name: str = "Sales") -> list[StepResult]:
    """Read, match, ask, request supplier prices and price what can be priced.

    Stops at the first thing that needs a person. That is the whole point.
    """
    steps: list[StepResult] = [read_request(session, case), match_lines(session, case)]

    version = require_version(session, case)
    if any(line.status == "non_catalogue" for line in version.lines):
        steps.append(request_supplier_prices(session, case))

    if clarify.open_questions(session, case):
        draft_question_email(session, case, sender_name=sender_name)
        steps.append(
            StepResult(
                "draft_question_email",
                "One email drafted with every open question, waiting for approval.",
            )
        )

    priceable = [line for line in version.lines if line.status in {"matched", "priced"}]
    if priceable:
        steps.append(price_case(session, case))

    return steps
