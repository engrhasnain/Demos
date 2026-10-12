"""Turning database rows into the shapes the screens draw.

One rule throughout: money leaves here as a string, never as a float. A float
that has been through JSON is no longer the number the ledger holds, and the
whole point of this product is that the number does not drift.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .money import dec, money
from .models import (
    Approval,
    CallBackTask,
    Document,
    Entity,
    Exception_,
    Invoice,
    InvoiceEvent,
    InvoiceLine,
    LedgerBill,
    Posting,
    PurchaseOrder,
    User,
    Vendor,
    VendorBankAccount,
)
from .security import ROLE_LABELS
from .services import approvals, workflow


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def when(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


def day(value: dt.date | None) -> str | None:
    return value.isoformat() if value else None


def amount(value: Decimal | str | int | float | None) -> str:
    return money(dec(value or 0))


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------
def user_brief(user: User | None) -> dict[str, Any] | None:
    if user is None:
        return None
    return {
        "id": user.id,
        "name": user.full_name,
        "email": user.email,
        "role": user.role,
        "role_label": ROLE_LABELS.get(user.role, user.role),
    }


def user_detail(user: User) -> dict[str, Any]:
    out = user_brief(user) or {}
    out["language"] = user.language
    out["is_active"] = user.is_active
    return out


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------
def bank_account(account: VendorBankAccount) -> dict[str, Any]:
    number = account.account_number
    return {
        "id": account.id,
        "bank": account.bank_name,
        "account_number": number,
        # Only the last four digits reach the screen. Nobody needs the rest to
        # recognise an account, and a screenshot of this page should not be
        # enough to pay somebody.
        "shown_as": ("•" * max(0, len(number) - 4)) + number[-4:] if number else "",
        "account_name": account.account_name,
        "is_current": account.is_current,
        "verified_by": account.verified_by,
        "verified_at": when(account.verified_at),
    }


def vendor_brief(vendor: Vendor | None) -> dict[str, Any] | None:
    if vendor is None:
        return None
    return {
        "id": vendor.id,
        "code": vendor.code,
        "name": vendor.name,
        "country": vendor.country,
        "currency": vendor.currency,
        "bank_change_pending": vendor.bank_change_pending,
    }


def vendor_detail(session: Session, vendor: Vendor) -> dict[str, Any]:
    out = vendor_brief(vendor) or {}
    open_call_backs = session.scalars(
        select(CallBackTask).where(
            CallBackTask.vendor_id == vendor.id, CallBackTask.status == "open"
        )
    )
    out.update(
        {
            "name_on_invoices": vendor.name_on_invoices,
            "entity_code": vendor.entity_code,
            "email": vendor.email,
            "telephone": vendor.telephone,
            "tax_identifier": vendor.tax_identifier,
            "tax_identifier_kind": vendor.tax_identifier_kind,
            "payment_terms_days": vendor.payment_terms_days,
            "tolerance_percent": amount(vendor.tolerance_percent),
            "tolerance_absolute": amount(vendor.tolerance_absolute),
            "unordered_allowance": amount(vendor.unordered_allowance),
            "bank_accounts": [bank_account(a) for a in vendor.bank_accounts],
            "call_backs": [call_back(t) for t in open_call_backs],
        }
    )
    return out


def call_back(task: CallBackTask) -> dict[str, Any]:
    return {
        "id": task.id,
        "vendor_id": task.vendor_id,
        "vendor_name": task.vendor.name if task.vendor else "",
        "invoice_id": task.invoice_id,
        "telephone_on_file": task.telephone_on_file,
        "requested_change": task.requested_change,
        "status": task.status,
        "created_at": when(task.created_at),
        "completed_at": when(task.completed_at),
        "completed_by": user_brief(task.completed_by),
        "outcome": task.outcome,
        "note": task.note,
    }


# ---------------------------------------------------------------------------
# Orders
# ---------------------------------------------------------------------------
def purchase_order(order: PurchaseOrder | None) -> dict[str, Any] | None:
    if order is None:
        return None
    return {
        "id": order.id,
        "number": order.number,
        "vendor": vendor_brief(order.vendor),
        "entity_code": order.entity_code,
        "currency": order.currency,
        "ordered_on": day(order.ordered_on),
        "status": order.status,
        "lines": [
            {
                "id": line.id,
                "line_number": line.line_number,
                "part_code": line.part_code,
                "description": line.description,
                "quantity_ordered": amount(line.quantity_ordered),
                "unit": line.unit,
                "unit_price": amount(line.unit_price),
                "line_total": amount(dec(line.quantity_ordered) * dec(line.unit_price)),
            }
            for line in order.lines
        ],
    }


# ---------------------------------------------------------------------------
# Invoices
# ---------------------------------------------------------------------------
def invoice_line(line: InvoiceLine) -> dict[str, Any]:
    return {
        "id": line.id,
        "line_number": line.line_number,
        "page": line.page,
        "part_code": line.part_code,
        "description": line.description,
        "quantity": amount(line.quantity),
        "unit": line.unit,
        "unit_price": amount(line.unit_price),
        "line_total": amount(line.line_total),
        "match_result": line.match_result,
        "match_label": _LINE_LABELS.get(line.match_result, line.match_result or "—"),
        "order_line_id": line.purchase_order_line_id,
        "received_to_date": amount(line.quantity_received_to_date),
        "billed_before": amount(line.quantity_billed_before),
        "payable_quantity": amount(line.payable_quantity),
        "payable_amount": amount(line.payable_amount),
        "held_amount": amount(line.held_amount),
        "note": line.note,
        "trace": line.calculation_trace or None,
    }


_LINE_LABELS: dict[str, str] = {
    "matched": "Agrees",
    "partly_received": "Only part arrived",
    "not_received": "Nothing arrived",
    "over_tolerance": "Priced above the order",
    "already_billed": "Billed before",
    "not_ordered": "Not on the order",
    "no_order": "No order to check",
}


def exception_row(row: Exception_) -> dict[str, Any]:
    return {
        "id": row.id,
        "kind": row.kind,
        "label": workflow.label_of(row.kind),
        "severity": row.severity,
        "summary": row.summary,
        "detail": row.detail,
        "raised_at": when(row.raised_at),
        "resolved_at": when(row.resolved_at),
        "resolved_by": user_brief(row.resolved_by),
        "resolution": row.resolution,
    }


def approval_row(row: Approval) -> dict[str, Any]:
    return {
        "id": row.id,
        "rule_code": row.rule_code,
        "title": row.title,
        "reason": row.reason,
        "required_role": row.required_role,
        "required_role_label": ROLE_LABELS.get(row.required_role, row.required_role),
        "step": row.step,
        "status": row.status,
        "detail": row.detail,
        "requested_at": when(row.requested_at),
        "decided_by": user_brief(row.decided_by),
        "decided_at": when(row.decided_at),
        "comment": row.comment,
    }


def event_row(row: InvoiceEvent) -> dict[str, Any]:
    return {
        "id": row.id,
        "occurred_at": when(row.occurred_at),
        "actor_type": row.actor_type,
        "actor_name": row.actor_name,
        "kind": row.kind,
        "summary": row.summary,
        "detail": row.detail,
        "duration_ms": row.duration_ms,
        "engine": row.engine,
    }


def posting_row(row: Posting) -> dict[str, Any]:
    return {
        "id": row.id,
        "ledger": row.ledger,
        "status": row.status,
        "attempts": row.attempts,
        "external_reference": row.external_reference,
        "amount": amount(row.amount),
        "currency": row.currency,
        "last_error": row.last_error,
        "posted_at": when(row.posted_at),
        # The key is shown because it is the answer to "how do you know you did
        # not pay it twice?". It is a hash, not a secret.
        "idempotency_key": row.idempotency_key,
    }


def ledger_bill(row: LedgerBill) -> dict[str, Any]:
    return {
        "id": row.id,
        "ledger": row.ledger,
        "external_reference": row.external_reference,
        "vendor_name": row.vendor_name,
        "invoice_number": row.invoice_number,
        "amount": amount(row.amount),
        "currency": row.currency,
        "posted_on": day(row.posted_on),
    }


def document_row(row: Document | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {
        "id": row.id,
        "filename": row.filename,
        "content_type": row.content_type,
        "size_bytes": row.size_bytes,
        "page_count": row.page_count,
        "kind": row.kind,
        "received_from": row.received_from,
        "received_at": when(row.received_at),
        "has_barcode": bool(row.barcode_payload),
    }


def invoice_brief(invoice: Invoice) -> dict[str, Any]:
    """What a row in the list needs, and nothing else."""
    open_exceptions = [e for e in invoice.exceptions if e.resolved_at is None]
    worst = _worst(open_exceptions)
    # An invoice waiting for a signature has no exception, but a blank reason
    # in the queue tells a clerk nothing about why it is sitting there.
    headline = worst["label"] if worst else ""
    severity = worst["severity"] if worst else ""
    if not headline and invoice.status == workflow.AWAITING_APPROVAL:
        headline = "Waiting for a signature"
        severity = "hold"
    return {
        "id": invoice.id,
        "reference": invoice.reference,
        "kind": invoice.kind,
        "vendor": vendor_brief(invoice.vendor),
        "vendor_name": invoice.vendor.name if invoice.vendor else invoice.vendor_name_read,
        "invoice_number": invoice.invoice_number_read,
        "invoice_date": day(invoice.invoice_date),
        "due_date": day(invoice.due_date),
        "currency": invoice.currency,
        "total_amount": amount(invoice.total_amount),
        "amount_in_base": amount(invoice.amount_in_base),
        "approved_amount": amount(invoice.approved_amount),
        "held_amount": amount(invoice.held_amount),
        "status": invoice.status,
        "status_label": workflow.LABELS.get(invoice.status, invoice.status),
        "posted_untouched": invoice.posted_untouched,
        "touched_by_a_person": invoice.touched_by_a_person,
        "needs_a_person": invoice.status in workflow.NEEDS_A_PERSON,
        "exception_count": len(open_exceptions),
        "headline": headline,
        "headline_severity": severity,
        "received_at": when(invoice.document.received_at if invoice.document else None),
        "read_with": invoice.read_with,
    }


def _worst(rows: list[Exception_]) -> dict[str, str] | None:
    order = {"block": 0, "hold": 1, "note": 2}
    if not rows:
        return None
    first = sorted(rows, key=lambda r: order.get(r.severity, 3))[0]
    return {"label": workflow.label_of(first.kind), "severity": first.severity}


def invoice_detail(session: Session, invoice: Invoice) -> dict[str, Any]:
    out = invoice_brief(invoice)
    allowed, why = approvals.may_post_untouched(session, invoice)
    postings = session.scalars(
        select(Posting).where(Posting.invoice_id == invoice.id).order_by(Posting.id)
    )
    pending = session.scalars(
        select(Approval).where(Approval.invoice_id == invoice.id).order_by(Approval.step, Approval.id)
    )
    out.update(
        {
            "as_read": {
                "vendor_name": invoice.vendor_name_read,
                "invoice_number": invoice.invoice_number_read,
                "buyer_tax_identifier": invoice.buyer_tax_identifier_read,
                "seller_tax_identifier": invoice.seller_tax_identifier_read,
                "purchase_order_number": invoice.purchase_order_number_read,
                "bank_account": invoice.bank_account_read,
                "confidence": invoice.field_confidence or {},
            },
            "net_amount": amount(invoice.net_amount),
            "tax_amount": amount(invoice.tax_amount),
            "exchange_rate": amount(invoice.exchange_rate) if invoice.exchange_rate else None,
            "entity_code": invoice.entity_code,
            "purchase_order": purchase_order(invoice.purchase_order),
            "document": document_row(invoice.document),
            "lines": [invoice_line(line) for line in invoice.lines],
            "exceptions": [exception_row(e) for e in invoice.exceptions],
            "approvals": [approval_row(a) for a in pending],
            "events": [event_row(e) for e in invoice.events],
            "postings": [posting_row(p) for p in postings],
            "blocking_reasons": approvals.blocking_reasons(session, invoice),
            "may_post_untouched": allowed,
            "may_post_untouched_reason": why,
            "hold_reason": invoice.hold_reason,
            "trace": invoice.calculation_trace or None,
            "credits_invoice_id": invoice.credits_invoice_id,
        }
    )
    return out


# ---------------------------------------------------------------------------
# Entities
# ---------------------------------------------------------------------------
def entity_row(entity: Entity) -> dict[str, Any]:
    return {
        "code": entity.code,
        "name": entity.name,
        "country": entity.country,
        "currency": entity.currency,
        "tax_identifier": entity.tax_identifier,
        "tax_identifier_kind": entity.tax_identifier_kind,
        "ledger": entity.ledger,
    }


# ---------------------------------------------------------------------------
# The numbers on the front page
# ---------------------------------------------------------------------------
def dashboard(session: Session) -> dict[str, Any]:
    """Every figure here is one query, so the page cannot disagree with itself."""
    total = session.scalar(select(func.count(Invoice.id))) or 0
    by_status: dict[str, int] = {}
    for status_code, count in session.execute(
        select(Invoice.status, func.count(Invoice.id)).group_by(Invoice.status)
    ):
        by_status[status_code] = count

    posted = by_status.get(workflow.POSTED, 0)
    untouched = (
        session.scalar(
            select(func.count(Invoice.id)).where(Invoice.posted_untouched.is_(True))
        )
        or 0
    )
    waiting = sum(by_status.get(code, 0) for code in workflow.NEEDS_A_PERSON)

    held = sum(
        (dec(row) for row in session.scalars(select(Invoice.held_amount))), Decimal("0")
    )
    approved = sum(
        (
            dec(row)
            for row in session.scalars(
                select(Invoice.approved_amount).where(Invoice.status == workflow.POSTED)
            )
        ),
        Decimal("0"),
    )

    kinds: list[dict[str, Any]] = []
    for kind, count in session.execute(
        select(Exception_.kind, func.count(Exception_.id))
        .where(Exception_.resolved_at.is_(None))
        .group_by(Exception_.kind)
        .order_by(func.count(Exception_.id).desc())
    ):
        kinds.append(
            {
                "kind": kind,
                "label": workflow.label_of(kind),
                "severity": workflow.severity_of(kind),
                "count": count,
            }
        )

    open_call_backs = (
        session.scalar(
            select(func.count(CallBackTask.id)).where(CallBackTask.status == "open")
        )
        or 0
    )
    duplicates_stopped = (
        session.scalar(
            select(func.count(Exception_.id)).where(Exception_.kind == "duplicate")
        )
        or 0
    )

    return {
        "invoices": total,
        "posted": posted,
        "untouched": untouched,
        "untouched_share": _share(untouched, posted),
        "waiting_for_a_person": waiting,
        "held_amount": amount(held),
        "posted_amount": amount(approved),
        "open_call_backs": open_call_backs,
        "duplicates_stopped": duplicates_stopped,
        "by_status": [
            {
                "code": code,
                "label": workflow.LABELS.get(code, code),
                "count": by_status.get(code, 0),
            }
            for code in workflow.LABELS
            if by_status.get(code)
        ],
        "exception_kinds": kinds,
    }


def _share(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 1) if whole else 0.0
