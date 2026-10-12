"""Writing a bill into the ledger, exactly once.

The dangerous moment is not the failure. It is the failure *after* the ledger
has accepted the bill but before our own record of it was saved. A retry then
looks like a fresh posting and the supplier gets paid twice.

So the ledger is keyed. The key is derived from the company, the supplier, the
invoice number and the amount, and the ledger refuses a second bill under the
same key. A retry finds the bill that is already there and finishes the job
rather than starting it again.
"""

from __future__ import annotations

import datetime as dt
import hashlib
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..money import dec, money
from ..models import AccountingPeriod, Invoice, LedgerBill, Posting


class LedgerUnavailable(Exception):
    """The ledger did not answer. The posting stays open and is retried."""


@dataclass(slots=True)
class PostingResult:
    posting: Posting
    bill: LedgerBill | None
    created: bool
    already_there: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.posting.status,
            "attempts": self.posting.attempts,
            "idempotency_key": self.posting.idempotency_key,
            "external_reference": self.posting.external_reference,
            "amount": str(self.posting.amount),
            "currency": self.posting.currency,
            "created_a_bill": self.created,
            "found_an_existing_bill": self.already_there,
        }


def idempotency_key(invoice: Invoice) -> str:
    """The same invoice always produces the same key."""
    parts = [
        invoice.entity_code or "",
        str(invoice.vendor_id or ""),
        invoice.invoice_number_normalised or invoice.reference,
        str(money(invoice.approved_amount)),
        invoice.currency,
    ]
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:24]
    return f"{invoice.entity_code or 'NA'}-{digest}"


class AlreadyPosted(Exception):
    """This invoice is in the ledger, and the figures have moved since."""


def prepare(session: Session, invoice: Invoice, period: AccountingPeriod | None) -> Posting:
    """Get the posting record for this invoice, creating it once.

    The key is a hash of the figures, which is what makes a retry safe. It
    also means that if the figures move after the invoice has been posted -
    a late goods receipt, a cleared exception, anything that changes what is
    payable - the key changes with them, and a second attempt would look like
    a brand new posting and write a second bill. That is the supplier being
    paid twice, which is the one thing this module exists to stop.

    So the posted bill is looked for by invoice first, and only then by key.
    An invoice gets one bill. A different amount after the fact is a credit
    note or an amendment, never another bill.
    """
    key = idempotency_key(invoice)

    posted = session.scalar(
        select(Posting).where(Posting.invoice_id == invoice.id, Posting.status == "posted")
    )
    if posted is not None:
        if posted.idempotency_key == key:
            return posted
        raise AlreadyPosted(
            f"{invoice.reference} is already in the ledger as "
            f"{posted.external_reference} for {posted.amount} {posted.currency}. "
            f"It is now {money(invoice.approved_amount)} {invoice.currency}. "
            "Raise a credit note or an amendment; a second bill would pay twice."
        )

    existing = session.scalar(select(Posting).where(Posting.idempotency_key == key))
    if existing is not None:
        return existing

    posting = Posting(
        invoice_id=invoice.id,
        ledger=_ledger_for(invoice),
        idempotency_key=key,
        status="pending",
        amount=money(invoice.approved_amount),
        currency=invoice.currency,
        period_id=period.id if period else None,
    )
    session.add(posting)
    session.flush()
    return posting


def _ledger_for(invoice: Invoice) -> str:
    return "united_states_ledger" if invoice.entity_code == "US" else "taiwan_ledger"


def post(
    session: Session,
    invoice: Invoice,
    *,
    period: AccountingPeriod | None = None,
    fail_after_ledger_write: bool = False,
) -> PostingResult:
    """Write the bill, or recognise that it is already written.

    ``fail_after_ledger_write`` reproduces the one failure that matters: the
    ledger took the bill and then the connection died. It is used by the
    walkthrough and by the tests, and it is the reason the key exists.
    """
    posting = prepare(session, invoice, period)
    posting.attempts += 1

    if posting.status == "posted":
        bill = session.scalar(
            select(LedgerBill).where(LedgerBill.idempotency_key == posting.idempotency_key)
        )
        return PostingResult(posting=posting, bill=bill, created=False, already_there=True)

    # Has the ledger already got it from an attempt that died halfway?
    bill = session.scalar(
        select(LedgerBill).where(LedgerBill.idempotency_key == posting.idempotency_key)
    )
    already_there = bill is not None

    if bill is None:
        reference = f"BILL-{posting.idempotency_key[-10:].upper()}"
        bill = LedgerBill(
            ledger=posting.ledger,
            external_reference=reference,
            idempotency_key=posting.idempotency_key,
            vendor_name=invoice.vendor.name if invoice.vendor else invoice.vendor_name_read,
            invoice_number=invoice.invoice_number_read,
            amount=money(invoice.approved_amount),
            currency=invoice.currency,
            posted_on=dt.date.today(),
        )
        session.add(bill)
        session.flush()

        if fail_after_ledger_write:
            # The ledger has it. We do not know that yet. This is the window
            # in which a careless retry pays the supplier twice.
            posting.status = "failed"
            posting.last_error = "The connection dropped after the ledger took the bill."
            session.flush()
            raise LedgerUnavailable(posting.last_error)

    posting.status = "posted"
    posting.external_reference = bill.external_reference
    posting.posted_at = dt.datetime.now(dt.timezone.utc)
    posting.last_error = ""
    session.flush()

    return PostingResult(
        posting=posting,
        bill=bill,
        created=not already_there,
        already_there=already_there,
    )


def bills_for(session: Session, invoice: Invoice) -> list[LedgerBill]:
    """Every bill in the ledger for this invoice. Should always be one."""
    return list(
        session.scalars(
            select(LedgerBill).where(LedgerBill.idempotency_key == idempotency_key(invoice))
        )
    )


def ledger_total(session: Session, ledger: str) -> Decimal:
    rows = session.scalars(select(LedgerBill).where(LedgerBill.ledger == ledger))
    return money(sum((dec(row.amount) for row in rows), Decimal("0")))
