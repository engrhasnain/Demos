"""The guards.

Typing an invoice costs six minutes. Paying the same one twice, or paying a
stranger because an email said the bank had changed, costs rather more. These
three checks exist for that, and none of them is a confidence score.

* **Duplicates** are caught five different ways, because the same invoice
  comes back as a photograph, as "0042" instead of "INV-0042", or through the
  post after it already came by email.
* **A change of bank details is a hard block.** The supplier record is never
  altered by software. A task goes out to telephone the number already on
  file, and nothing is paid until somebody has done it and said so.
* **An invoice billed to the wrong company** of the two is stopped rather than
  posted into whichever ledger happened to be nearest.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import dec, money
from ..models import (
    AccountingPeriod,
    CallBackTask,
    Entity,
    Invoice,
    Vendor,
    VendorBankAccount,
)

#: Two invoices this close in value are treated as the same amount.
AMOUNT_TOLERANCE = Decimal("1")
#: ... and this close in time are treated as the same date.
DATE_WINDOW_DAYS = 5


@dataclass(slots=True)
class GuardFinding:
    kind: str
    summary: str
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind, "summary": self.summary, "detail": self.detail}


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------
@dataclass(slots=True)
class DuplicateMatch:
    invoice: Invoice
    signals: list[str]
    confidence: str  # certain | likely

    def to_dict(self) -> dict[str, Any]:
        return {
            "invoice_id": self.invoice.id,
            "reference": self.invoice.reference,
            "invoice_number": self.invoice.invoice_number_read,
            "status": self.invoice.status,
            "total": str(self.invoice.total_amount),
            "currency": self.invoice.currency,
            "signals": self.signals,
            "confidence": self.confidence,
        }


def find_duplicates(session: Session, invoice: Invoice) -> list[DuplicateMatch]:
    """Five signals, any two of which make a duplicate.

    The file being byte for byte identical, or the same supplier and the same
    normalised number, is enough on its own.
    """
    candidates: dict[int, list[str]] = {}

    def flag(other: Invoice, signal: str) -> None:
        if other.id == invoice.id or other.status in {"rejected", "cancelled"}:
            return
        candidates.setdefault(other.id, [])
        if signal not in candidates[other.id]:
            candidates[other.id].append(signal)

    # 1. the identical file
    if invoice.document is not None and invoice.document.content_hash:
        for other in session.scalars(
            select(Invoice).join(Invoice.document).where(
                Invoice.document_id.isnot(None),
                Invoice.id != invoice.id,
            )
        ):
            if (
                other.document is not None
                and other.document.content_hash == invoice.document.content_hash
            ):
                flag(other, "same file")

    # 2. the same supplier and the same number, however it is punctuated
    if invoice.vendor_id and invoice.invoice_number_normalised:
        for other in session.scalars(
            select(Invoice).where(
                Invoice.vendor_id == invoice.vendor_id,
                Invoice.invoice_number_normalised == invoice.invoice_number_normalised,
                Invoice.id != invoice.id,
            )
        ):
            flag(other, "same supplier and number")

    # 3. the same supplier, amount and date, under a different number
    if invoice.vendor_id and dec(invoice.total_amount) > 0 and invoice.invoice_date:
        window_start = invoice.invoice_date - dt.timedelta(days=DATE_WINDOW_DAYS)
        window_end = invoice.invoice_date + dt.timedelta(days=DATE_WINDOW_DAYS)
        for other in session.scalars(
            select(Invoice).where(
                Invoice.vendor_id == invoice.vendor_id,
                Invoice.id != invoice.id,
                Invoice.invoice_date.isnot(None),
            )
        ):
            if other.invoice_date is None:
                continue
            same_amount = (
                abs(dec(other.total_amount) - dec(invoice.total_amount)) <= AMOUNT_TOLERANCE
            )
            near_date = window_start <= other.invoice_date <= window_end
            if same_amount and near_date:
                flag(other, "same supplier, amount and date")

    # 4. the same number across the whole ledger, even if the supplier was
    #    read differently on the two copies
    if invoice.invoice_number_normalised:
        for other in session.scalars(
            select(Invoice).where(
                Invoice.invoice_number_normalised == invoice.invoice_number_normalised,
                Invoice.id != invoice.id,
            )
        ):
            flag(other, "same number")

    # 5. the same purchase order, amount and supplier
    if invoice.purchase_order_id and dec(invoice.total_amount) > 0:
        for other in session.scalars(
            select(Invoice).where(
                Invoice.purchase_order_id == invoice.purchase_order_id,
                Invoice.id != invoice.id,
            )
        ):
            if abs(dec(other.total_amount) - dec(invoice.total_amount)) <= AMOUNT_TOLERANCE:
                flag(other, "same order and amount")

    matches: list[DuplicateMatch] = []
    for other_id, signals in candidates.items():
        other = session.get(Invoice, other_id)
        if other is None:
            continue
        certain = (
            "the same file, byte for byte" in signals
            or "same supplier and number" in signals
            or len(signals) >= 2
        )
        matches.append(
            DuplicateMatch(
                invoice=other,
                signals=signals,
                confidence="certain" if certain else "likely",
            )
        )
    matches.sort(key=lambda m: (m.confidence != "certain", -len(m.signals)))
    return matches


def check_duplicates(session: Session, invoice: Invoice) -> GuardFinding | None:
    matches = [m for m in find_duplicates(session, invoice) if m.confidence == "certain"]
    if not matches:
        return None
    first = matches[0]
    return GuardFinding(
        kind="duplicate",
        summary=(
            f"Same as {first.invoice.reference}"
            f" - {first.signals[0]}"
        ),
        detail={"matches": [m.to_dict() for m in matches]},
    )


# ---------------------------------------------------------------------------
# Bank details
# ---------------------------------------------------------------------------
def _digits(value: str) -> str:
    return "".join(ch for ch in (value or "") if ch.isdigit())


def check_bank_details(
    session: Session, invoice: Invoice, vendor: Vendor | None
) -> GuardFinding | None:
    """Any account that is not the one on file stops the invoice dead."""
    stated = _digits(invoice.bank_account_read)
    if not stated or vendor is None:
        return None

    on_file = [
        account
        for account in vendor.bank_accounts
        if account.is_current and _digits(account.account_number)
    ]
    if not on_file:
        return GuardFinding(
            kind="bank_detail_change",
            summary=f"No account on file; invoice gives {invoice.bank_account_read}",
            detail={"account_on_invoice": invoice.bank_account_read, "accounts_on_file": []},
        )

    if any(stated == _digits(account.account_number) for account in on_file):
        return None

    return GuardFinding(
        kind="bank_detail_change",
        # The label already says what happened and the panel shows both
        # accounts side by side. The summary carries the one fact neither of
        # them does: which account was asked for.
        summary=f"Asked for {invoice.bank_account_read}, not on file",
        detail={
            "account_on_invoice": invoice.bank_account_read,
            "accounts_on_file": [
                {"bank": a.bank_name, "number": a.account_number} for a in on_file
            ],
            "telephone_on_file": vendor.telephone,
        },
    )


def raise_call_back(
    session: Session, invoice: Invoice, vendor: Vendor, finding: GuardFinding
) -> CallBackTask:
    """Create the task, leave the supplier record exactly as it was."""
    existing = session.scalar(
        select(CallBackTask).where(
            CallBackTask.vendor_id == vendor.id,
            CallBackTask.invoice_id == invoice.id,
            CallBackTask.status == "open",
        )
    )
    if existing is not None:
        return existing

    task = CallBackTask(
        vendor_id=vendor.id,
        invoice_id=invoice.id,
        telephone_on_file=vendor.telephone,
        requested_change={
            "account_on_invoice": invoice.bank_account_read,
            "accounts_on_file": finding.detail.get("accounts_on_file", []),
            "invoice_reference": invoice.reference,
        },
        status="open",
    )
    session.add(task)
    vendor.bank_change_pending = True
    session.flush()
    return task


def complete_call_back(
    session: Session,
    task: CallBackTask,
    *,
    user_id: int,
    confirmed: bool,
    note: str,
) -> CallBackTask:
    """Record the telephone call. Only a confirmed call can change anything."""
    task.status = "completed"
    task.completed_at = dt.datetime.now(dt.timezone.utc)
    task.completed_by_id = user_id
    task.outcome = "confirmed" if confirmed else "refused"
    task.note = note

    vendor = task.vendor
    if confirmed:
        number = str(task.requested_change.get("account_on_invoice") or "")
        for account in vendor.bank_accounts:
            account.is_current = False
        # Appended through the relationship, not added to the session, so the
        # supplier's list of accounts is right straight away. Adding it to the
        # session alone leaves the caller holding a stale collection and
        # showing a supplier with no current account at all.
        vendor.bank_accounts.append(
            VendorBankAccount(
                bank_name="Confirmed by telephone",
                account_number=number,
                account_name=vendor.name,
                is_current=True,
                verified_by=str(user_id),
                verified_at=dt.datetime.now(dt.timezone.utc),
            )
        )
    vendor.bank_change_pending = False
    session.flush()
    return task


# ---------------------------------------------------------------------------
# The right company, and an open month
# ---------------------------------------------------------------------------
def check_entity(
    invoice: Invoice, vendor: Vendor | None, entity: Entity | None
) -> GuardFinding | None:
    if vendor is None or entity is None:
        return None
    if vendor.entity_code == entity.code:
        return None
    return GuardFinding(
        kind="wrong_entity",
        summary=f"They bill {vendor.entity_code}, this says {entity.code}",
        detail={"vendor_entity": vendor.entity_code, "invoice_entity": entity.code},
    )


def period_for(
    session: Session, entity_code: str, when: dt.date
) -> tuple[AccountingPeriod | None, GuardFinding | None]:
    """The month an invoice posts into, which is not always its own month."""
    wanted = session.scalar(
        select(AccountingPeriod).where(
            AccountingPeriod.entity_code == entity_code,
            AccountingPeriod.year == when.year,
            AccountingPeriod.month == when.month,
        )
    )
    if wanted is not None and wanted.is_open:
        return wanted, None

    first_open = session.scalar(
        select(AccountingPeriod)
        .where(AccountingPeriod.entity_code == entity_code, AccountingPeriod.is_open.is_(True))
        .order_by(AccountingPeriod.year, AccountingPeriod.month)
        .limit(1)
    )
    if wanted is None:
        return first_open, None

    finding = GuardFinding(
        kind="closed_period",
        summary=(
            f"{when.strftime('%b %Y')} closed, posts into "
            + (
                dt.date(first_open.year, first_open.month, 1).strftime("%b %Y")
                if first_open
                else "the first open month"
            )
        ),
        detail={
            "invoice_month": when.strftime("%Y-%m"),
            "posting_month": (
                f"{first_open.year}-{first_open.month:02d}" if first_open else ""
            ),
        },
    )
    return first_open, finding
