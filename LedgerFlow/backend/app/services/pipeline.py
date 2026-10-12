"""The steps, in order, with everything written down.

    receive -> read -> check -> match -> guard -> approve -> post

Each step records what it did on the invoice's own timeline. An invoice that
passes every step and is small enough reaches the ledger without anybody
touching it, and that is counted. Everything else stops in front of a person
with the reason spelled out.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import re
import time
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..domain.uniforminvoice import normalise_invoice_number
from ..money import Trace, dec, money
from ..models import (
    AccountingPeriod,
    Document,
    Entity,
    Exception_,
    ExchangeRate,
    Invoice,
    InvoiceLine,
    User,
    Vendor,
)
from . import approvals, extraction, guards, matching, posting, validation, workflow
from .audit import record_event


class PipelineError(Exception):
    pass


@dataclass(slots=True)
class StepResult:
    step: str
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)
    duration_ms: int = 0


# ---------------------------------------------------------------------------
# References and small helpers
# ---------------------------------------------------------------------------
def _count(many: int, noun: str) -> str:
    """``1 line`` rather than ``1 line(s)``."""
    return f"{many} {noun}" if many == 1 else f"{many} {noun}s"


def next_reference(session: Session) -> str:
    year = dt.date.today().year
    prefix = f"AP-{year}-"
    highest = session.scalar(
        select(func.max(Invoice.reference)).where(Invoice.reference.like(f"{prefix}%"))
    )
    sequence = int(highest.rsplit("-", 1)[-1]) + 1 if highest else 1
    return f"{prefix}{sequence:05d}"


def move_to(session: Session, invoice: Invoice, status: str, *, note: str = "") -> None:
    workflow.assert_can_move(invoice.status, status)
    if invoice.status == status:
        return
    before = invoice.status
    invoice.status = status
    record_event(
        session,
        invoice_id=invoice.id,
        kind="status_changed",
        summary=(
            f"{workflow.LABELS.get(before, before)} to {workflow.LABELS.get(status, status)}"
            + (f". {note}" if note else "")
        ),
        actor_type="system",
        actor_name="Workflow",
        detail={"from": before, "to": status},
    )


def _raise_exception(
    session: Session, invoice: Invoice, kind: str, summary: str, detail: dict[str, Any]
) -> Exception_:
    """Record something a person has to look at, once."""
    for existing in invoice.exceptions:
        if existing.kind == kind and existing.resolved_at is None:
            existing.summary = summary[:255]
            existing.detail = detail
            return existing
    exception = Exception_(
        invoice_id=invoice.id,
        kind=kind,
        severity=workflow.severity_of(kind),
        summary=summary[:255],
        detail=detail,
    )
    session.add(exception)
    invoice.exceptions.append(exception)
    session.flush()
    return exception


# ---------------------------------------------------------------------------
# 1. Receive
# ---------------------------------------------------------------------------
def receive(
    session: Session,
    *,
    filename: str,
    content: bytes,
    content_type: str = "text/plain",
    text: str = "",
    barcode_payload: str = "",
    received_from: str = "",
    kind: str = "bill",
) -> tuple[Invoice, bool]:
    """Take a document in. The same file twice is still recorded, and caught
    later by the duplicate guard, because the arrival itself is a fact."""
    digest = hashlib.sha256(content).hexdigest()
    document = Document(
        filename=filename,
        content_type=content_type,
        size_bytes=len(content),
        content_hash=digest,
        page_count=max(text.lower().count("page ") or 1, 1),
        kind=_document_kind(filename, content_type),
        received_from=received_from,
        text=text or content.decode("utf-8", errors="replace"),
        barcode_payload=barcode_payload,
    )
    session.add(document)
    session.flush()

    invoice = Invoice(
        reference=next_reference(session),
        document_id=document.id,
        kind=kind,
        status=workflow.RECEIVED,
    )
    session.add(invoice)
    session.flush()

    record_event(
        session,
        invoice_id=invoice.id,
        kind="received",
        summary=f"{filename} from {received_from or 'the mailbox'}",
        actor_type="supplier",
        actor_name=received_from,
        detail={
            "filename": filename,
            "bytes": len(content),
            "hash": digest[:16],
            "document_kind": document.kind,
            "barcode": bool(barcode_payload),
        },
    )
    return invoice, True


def _document_kind(filename: str, content_type: str) -> str:
    low = filename.lower()
    if low.endswith(".pdf"):
        return "pdf"
    if low.endswith((".jpg", ".jpeg", ".png")):
        return "photograph"
    if low.endswith((".xml", ".json")):
        return "electronic invoice"
    return "text"


# ---------------------------------------------------------------------------
# 2. Read
# ---------------------------------------------------------------------------
def read(session: Session, invoice: Invoice) -> StepResult:
    started = time.perf_counter()
    document = invoice.document
    if document is None:
        raise PipelineError("There is no document to read.")

    reading = extraction.read_invoice(document.text, document.barcode_payload)

    header = reading.header
    invoice.vendor_name_read = str(header.get("vendor_name") or "")[:160]
    invoice.invoice_number_read = str(header.get("invoice_number") or "")[:64]
    invoice.invoice_number_normalised = normalise_invoice_number(invoice.invoice_number_read)
    invoice.invoice_date = _as_date(header.get("invoice_date"))
    invoice.due_date = _as_date(header.get("due_date"))
    invoice.currency = str(header.get("currency") or settings.base_currency)[:3]
    invoice.net_amount = dec(header.get("net_amount") or 0)
    invoice.tax_amount = dec(header.get("tax_amount") or 0)
    invoice.total_amount = dec(header.get("total_amount") or 0)
    invoice.buyer_tax_identifier_read = str(header.get("buyer_tax_identifier") or "")[:32]
    invoice.seller_tax_identifier_read = str(header.get("seller_tax_identifier") or "")[:32]
    invoice.purchase_order_number_read = str(header.get("purchase_order_number") or "")[:32]
    invoice.bank_account_read = str(header.get("bank_account") or "")[:40]
    invoice.field_confidence = reading.confidence
    invoice.read_with = reading.engine

    for line in list(invoice.lines):
        session.delete(line)
    invoice.lines.clear()
    session.flush()

    for read_line in reading.lines:
        invoice.lines.append(
            InvoiceLine(
                line_number=read_line.line_number,
                description=read_line.description[:255],
                part_code=read_line.part_code[:48],
                quantity=read_line.quantity,
                unit=read_line.unit,
                unit_price=read_line.unit_price,
                line_total=read_line.line_total,
                page=read_line.page,
            )
        )

    _resolve_vendor_and_entity(session, invoice)
    session.flush()

    duration = int((time.perf_counter() - started) * 1000)
    move_to(session, invoice, workflow.READ)
    detail = reading.as_event_detail()
    detail["page_subtotals"] = {str(k): str(v) for k, v in reading.page_subtotals.items()}
    record_event(
        session,
        invoice_id=invoice.id,
        kind="read",
        summary=(
            f"Read {detail['fields_read']}/{detail['fields_possible']} fields, "
            f"{_count(len(reading.lines), 'line')}"
            + (", barcode used" if reading.barcode else "")
        ),
        detail=detail,
        duration_ms=duration,
        engine=reading.engine,
        cost_usd=reading.cost_usd,
    )

    # Page subtotals have to add up to the total on a long invoice.
    if len(reading.page_subtotals) > 1:
        summed = sum(reading.page_subtotals.values(), Decimal("0"))
        if abs(money(summed) - money(invoice.net_amount)) > Decimal("1"):
            _raise_exception(
                session,
                invoice,
                "arithmetic",
                f"The page subtotals add to {money(summed)} but the invoice says "
                f"{money(invoice.net_amount)} before tax.",
                {
                    "page_subtotals": {str(k): str(v) for k, v in reading.page_subtotals.items()},
                    "net_amount": str(invoice.net_amount),
                },
            )

    return StepResult("read", f"{_count(len(reading.lines), 'line')} read", detail, duration)


def _as_date(value: Any) -> dt.date | None:
    if isinstance(value, dt.date):
        return value
    if not value:
        return None
    try:
        return dt.date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _resolve_vendor_and_entity(session: Session, invoice: Invoice) -> None:
    """Work out which supplier this is and which of our companies it bills."""
    vendor: Vendor | None = None

    seller = (invoice.seller_tax_identifier_read or "").replace("-", "").strip()
    if seller:
        vendor = session.scalar(
            select(Vendor).where(func.replace(Vendor.tax_identifier, "-", "") == seller)
        )

    if vendor is None and invoice.vendor_name_read:
        name = invoice.vendor_name_read.strip().lower()
        for candidate in session.scalars(select(Vendor)):
            known = {candidate.name.lower(), (candidate.name_on_invoices or "").lower()}
            if name in known or any(k and k in name for k in known):
                vendor = candidate
                break

    invoice.vendor_id = vendor.id if vendor else None

    # The company being billed comes from the buyer's business number first.
    buyer = (invoice.buyer_tax_identifier_read or "").replace("-", "").strip()
    entity: Entity | None = None
    if buyer:
        entity = session.scalar(
            select(Entity).where(func.replace(Entity.tax_identifier, "-", "") == buyer)
        )
    if entity is None and vendor is not None:
        entity = session.get(Entity, vendor.entity_code)
    invoice.entity_code = entity.code if entity else None


# ---------------------------------------------------------------------------
# 3. Check, match and guard
# ---------------------------------------------------------------------------
def check(session: Session, invoice: Invoice) -> StepResult:
    started = time.perf_counter()
    vendor = invoice.vendor
    entity = session.get(Entity, invoice.entity_code) if invoice.entity_code else None

    if vendor is None:
        _raise_exception(
            session,
            invoice,
            "unknown_vendor",
            f"No match for '{invoice.vendor_name_read}'",
            {"name_read": invoice.vendor_name_read,
             "tax_identifier_read": invoice.seller_tax_identifier_read},
        )

    # --- the checks that need no order ------------------------------------
    result = validation.validate(_reading_from(invoice), vendor=vendor, entity=entity)
    for finding in result.findings:
        _raise_exception(session, invoice, finding.kind, finding.summary, finding.detail)

    # --- currency ----------------------------------------------------------
    _convert_to_base(session, invoice)

    # --- a credit note is not matched against a delivery ------------------
    if invoice.kind == "credit_note":
        _link_credit_note(session, invoice)
        order = None
    else:
        # --- the three-way match ------------------------------------------
        order = matching.find_purchase_order(session, invoice, vendor)
        match_result = matching.match(session, invoice, vendor=vendor, order=order)
        matching.apply(match_result, invoice)
        for finding in match_result.findings:
            _raise_exception(
                session, invoice, finding["kind"], finding["summary"], finding["detail"]
            )

    # --- the guards --------------------------------------------------------
    duplicate = guards.check_duplicates(session, invoice)
    if duplicate:
        _raise_exception(session, invoice, duplicate.kind, duplicate.summary, duplicate.detail)

    bank = guards.check_bank_details(session, invoice, vendor)
    if bank:
        _raise_exception(session, invoice, bank.kind, bank.summary, bank.detail)
        if vendor is not None:
            guards.raise_call_back(session, invoice, vendor, bank)

    wrong_entity = guards.check_entity(invoice, vendor, entity)
    if wrong_entity:
        _raise_exception(
            session, invoice, wrong_entity.kind, wrong_entity.summary, wrong_entity.detail
        )

    if invoice.entity_code and invoice.invoice_date:
        period, closed = guards.period_for(session, invoice.entity_code, invoice.invoice_date)
        invoice.posting_period_id = period.id if period else None
        if closed:
            _raise_exception(session, invoice, closed.kind, closed.summary, closed.detail)

    session.flush()

    open_exceptions = [e for e in invoice.exceptions if e.resolved_at is None]
    blocking = [e for e in open_exceptions if e.severity == "block"]
    holding = [e for e in open_exceptions if e.severity == "hold"]

    if blocking:
        move_to(session, invoice, workflow.EXCEPTION)
    elif holding:
        move_to(session, invoice, workflow.EXCEPTION)
    else:
        move_to(session, invoice, workflow.CHECKED)

    approvals.synchronise(session, invoice)
    duration = int((time.perf_counter() - started) * 1000)

    detail = {
        "checks": result.checks_run,
        "purchase_order": order.number if order else "",
        "payable": str(invoice.approved_amount),
        "held": str(invoice.held_amount),
        "exceptions": [
            {"kind": e.kind, "severity": e.severity, "summary": e.summary}
            for e in open_exceptions
        ],
        "validation_trace": result.trace.to_dict() if result.trace else {},
    }
    summary = (
        f"{money(invoice.approved_amount)} {invoice.currency} payable"
        + (f", {money(invoice.held_amount)} held" if dec(invoice.held_amount) else "")
        + (f". {len(open_exceptions)} thing(s) to look at." if open_exceptions else ". Clean.")
    )
    record_event(
        session,
        invoice_id=invoice.id,
        kind="checked",
        summary=summary,
        detail=detail,
        duration_ms=duration,
    )
    return StepResult("check", summary, detail, duration)


def _link_credit_note(session: Session, invoice: Invoice) -> None:
    """A credit note reduces an earlier bill, so it has to find that bill.

    Nothing is matched against a delivery: goods going back out are not goods
    coming in. The amount is recorded as a negative payable so the supplier's
    balance moves the right way.
    """
    text = invoice.document.text if invoice.document else ""
    original: Invoice | None = None

    # The note usually says which invoice it credits.
    for candidate in re.findall(r"[A-Z]{1,4}[-\s]?\d{3,}", text or ""):
        normalised = normalise_invoice_number(candidate)
        if not normalised or normalised == invoice.invoice_number_normalised:
            continue
        found = session.scalar(
            select(Invoice).where(
                Invoice.invoice_number_normalised == normalised,
                Invoice.kind == "bill",
                Invoice.id != invoice.id,
            )
        )
        if found is not None:
            original = found
            break

    # Otherwise the most recent bill from the same supplier.
    if original is None and invoice.vendor_id:
        original = session.scalar(
            select(Invoice)
            .where(
                Invoice.vendor_id == invoice.vendor_id,
                Invoice.kind == "bill",
                Invoice.id != invoice.id,
            )
            .order_by(Invoice.id.desc())
            .limit(1)
        )

    invoice.credits_invoice_id = original.id if original else None
    credit = money(dec(invoice.total_amount))
    invoice.approved_amount = -credit
    invoice.held_amount = Decimal("0")
    invoice.hold_reason = ""
    for line in invoice.lines:
        line.match_result = "credit"
        line.payable_quantity = dec(line.quantity)
        line.payable_amount = -money(line.line_total)
        line.held_amount = Decimal("0")

    if original is None:
        _raise_exception(
            session,
            invoice,
            "missing_field",
            "This is a credit note but no earlier bill from this supplier was found "
            "to apply it against.",
            {"credit_amount": str(credit)},
        )
    else:
        trace = Trace("Credit applied")
        trace.add(
            "Credit note",
            f"{credit} {invoice.currency} credited against {original.reference}",
            f"-{credit}",
            unit=invoice.currency,
            note=f"Original invoice {original.invoice_number_read}.",
        )
        invoice.calculation_trace = trace.to_dict()


def _reading_from(invoice: Invoice) -> extraction.Reading:
    """Rebuild a reading from what was stored, so validation has one shape."""
    reading = extraction.Reading(engine=invoice.read_with or "built-in")
    reading.header = {
        "vendor_name": invoice.vendor_name_read,
        "invoice_number": invoice.invoice_number_read,
        "invoice_date": invoice.invoice_date.isoformat() if invoice.invoice_date else "",
        "due_date": invoice.due_date.isoformat() if invoice.due_date else "",
        "currency": invoice.currency,
        "net_amount": str(invoice.net_amount),
        "tax_amount": str(invoice.tax_amount),
        "total_amount": str(invoice.total_amount),
        "buyer_tax_identifier": invoice.buyer_tax_identifier_read,
        "seller_tax_identifier": invoice.seller_tax_identifier_read,
        "purchase_order_number": invoice.purchase_order_number_read,
        "bank_account": invoice.bank_account_read,
    }
    reading.confidence = invoice.field_confidence or {}
    reading.lines = [
        extraction.ReadLine(
            line_number=line.line_number,
            description=line.description,
            part_code=line.part_code,
            quantity=dec(line.quantity),
            unit=line.unit,
            unit_price=dec(line.unit_price),
            line_total=dec(line.line_total),
            page=line.page,
        )
        for line in invoice.lines
    ]
    if invoice.document is not None and invoice.document.barcode_payload:
        from ..domain.uniforminvoice import read_barcode

        decoded = read_barcode(invoice.document.barcode_payload)
        reading.barcode = decoded.to_dict() if decoded else None
    return reading


def _convert_to_base(session: Session, invoice: Invoice) -> None:
    """An invoice in another currency is also recorded in ours."""
    if invoice.currency == settings.base_currency:
        invoice.exchange_rate = None
        invoice.amount_in_base = money(invoice.total_amount)
        return
    on_date = invoice.invoice_date or dt.date.today()
    rate = session.scalar(
        select(ExchangeRate)
        .where(
            ExchangeRate.base_currency == invoice.currency,
            ExchangeRate.quote_currency == settings.base_currency,
            ExchangeRate.as_of_date <= on_date,
        )
        .order_by(ExchangeRate.as_of_date.desc())
        .limit(1)
    )
    if rate is None:
        invoice.amount_in_base = money(invoice.total_amount)
        return
    invoice.exchange_rate = dec(rate.rate)
    invoice.amount_in_base = money(dec(invoice.total_amount) * dec(rate.rate))


# ---------------------------------------------------------------------------
# 4. Post
# ---------------------------------------------------------------------------
def post_to_ledger(
    session: Session,
    invoice: Invoice,
    *,
    by: User | None = None,
    untouched: bool = False,
    fail_after_ledger_write: bool = False,
) -> StepResult:
    reasons = approvals.blocking_reasons(session, invoice)
    if reasons:
        raise PipelineError("This cannot be posted: " + " ".join(reasons))

    period = (
        session.get(AccountingPeriod, invoice.posting_period_id)
        if invoice.posting_period_id
        else None
    )

    try:
        result = posting.post(
            session, invoice, period=period, fail_after_ledger_write=fail_after_ledger_write
        )
    except posting.AlreadyPosted as error:
        raise PipelineError(str(error)) from error

    if invoice.status != workflow.POSTED:
        if invoice.status not in {workflow.CHECKED, workflow.APPROVED}:
            move_to(session, invoice, workflow.CHECKED)
        move_to(session, invoice, workflow.POSTED)
    invoice.posted_untouched = untouched and not invoice.touched_by_a_person

    record_event(
        session,
        invoice_id=invoice.id,
        kind="posted",
        summary=(
            f"{money(invoice.approved_amount)} {invoice.currency} posted to the "
            f"{result.posting.ledger.replace('_', ' ')} as {result.posting.external_reference}"
            + (" with nobody touching it." if invoice.posted_untouched else ".")
            + (" The ledger already had it from an earlier attempt."
               if result.already_there else "")
        ),
        actor_type="agent" if untouched else "person",
        actor_name="LedgerFlow" if untouched else (by.full_name if by else "a person"),
        detail=result.to_dict(),
    )
    return StepResult("post", "Posted", result.to_dict())


# ---------------------------------------------------------------------------
# The whole run
# ---------------------------------------------------------------------------
def run(session: Session, invoice: Invoice) -> list[StepResult]:
    """Read, check, and post if nothing needs a person."""
    steps = [read(session, invoice), check(session, invoice)]

    allowed, why = approvals.may_post_untouched(session, invoice)
    if allowed:
        steps.append(post_to_ledger(session, invoice, untouched=True))
    else:
        if invoice.status == workflow.CHECKED and approvals.outstanding(session, invoice):
            move_to(session, invoice, workflow.AWAITING_APPROVAL)
        record_event(
            session,
            invoice_id=invoice.id,
            kind="stopped_for_a_person",
            summary=why,
            detail={"reasons": approvals.blocking_reasons(session, invoice)},
        )
        steps.append(StepResult("stop", why))
    return steps


def elapsed(invoice: Invoice) -> dict[str, Any]:
    events = sorted(invoice.events, key=lambda e: e.id)
    if not events:
        return {"steps": 0, "working_seconds": 0, "cost_usd": "0"}
    working = sum(e.duration_ms for e in events)
    cost = sum((dec(e.cost_usd) for e in events), Decimal("0"))
    return {
        "steps": len(events),
        "working_seconds": round(working / 1000, 3),
        "cost_usd": str(cost),
        "first_at": events[0].occurred_at.isoformat(),
        "last_at": events[-1].occurred_at.isoformat(),
    }
