"""Database tables.

Money is stored as exact decimal text, never as a float, because an accounts
payable ledger that is a cent out is a ledger nobody trusts.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from .db import Base
from .money import dec


class DecimalText(TypeDecorator):
    """Exact decimal storage that behaves the same on SQLite and PostgreSQL."""

    impl = String(40)
    cache_ok = True

    def process_bind_param(self, value: Any, dialect: Any) -> str | None:
        return None if value is None else str(dec(value))

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        return None if value is None else dec(value)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    # clerk | accountant | controller | finance_director | administrator
    role: Mapped[str] = mapped_column(String(40), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(10), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------------------
# The two legal entities we pay from
# ---------------------------------------------------------------------------
class Entity(Base):
    __tablename__ = "entities"

    code: Mapped[str] = mapped_column(String(12), primary_key=True)
    name: Mapped[str] = mapped_column(String(160))
    country: Mapped[str] = mapped_column(String(2))
    currency: Mapped[str] = mapped_column(String(3))
    tax_identifier: Mapped[str] = mapped_column(String(32))
    tax_identifier_kind: Mapped[str] = mapped_column(String(40))
    ledger: Mapped[str] = mapped_column(String(40))


class AccountingPeriod(Base):
    """A month, and whether it is still open to postings."""

    __tablename__ = "accounting_periods"
    __table_args__ = (UniqueConstraint("entity_code", "year", "month"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_code: Mapped[str] = mapped_column(ForeignKey("entities.code"), index=True)
    year: Mapped[int] = mapped_column(Integer)
    month: Mapped[int] = mapped_column(Integer)
    is_open: Mapped[bool] = mapped_column(Boolean, default=True)
    closed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------
class Vendor(Base, TimestampMixin):
    __tablename__ = "vendors"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    #: The name as it is spelt on the invoice, which is rarely the same.
    name_on_invoices: Mapped[str] = mapped_column(String(160), default="")
    country: Mapped[str] = mapped_column(String(2), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    entity_code: Mapped[str] = mapped_column(ForeignKey("entities.code"), index=True)
    email: Mapped[str] = mapped_column(String(160))
    #: The number on file, the only one a call-back is ever made to.
    telephone: Mapped[str] = mapped_column(String(40), default="")
    tax_identifier: Mapped[str] = mapped_column(String(32), default="")
    tax_identifier_kind: Mapped[str] = mapped_column(String(40), default="")
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=45)

    # --- per-vendor tolerances -------------------------------------------
    tolerance_percent: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("2"))
    tolerance_absolute: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("500"))
    unordered_allowance: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("1000"))

    #: Set when a change of bank details is outstanding. Nothing is paid to a
    #: vendor in this state until somebody has telephoned the number on file.
    bank_change_pending: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    bank_accounts: Mapped[list["VendorBankAccount"]] = relationship(
        back_populates="vendor", cascade="all, delete-orphan"
    )


class VendorBankAccount(Base):
    """The account we pay into. It is never changed by software."""

    __tablename__ = "vendor_bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id", ondelete="CASCADE"), index=True)
    bank_name: Mapped[str] = mapped_column(String(120))
    account_number: Mapped[str] = mapped_column(String(40))
    account_name: Mapped[str] = mapped_column(String(160), default="")
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    verified_by: Mapped[str] = mapped_column(String(120), default="")
    verified_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    vendor: Mapped[Vendor] = relationship(back_populates="bank_accounts")


# ---------------------------------------------------------------------------
# What we ordered and what arrived
# ---------------------------------------------------------------------------
class PurchaseOrder(Base, TimestampMixin):
    __tablename__ = "purchase_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    entity_code: Mapped[str] = mapped_column(ForeignKey("entities.code"))
    currency: Mapped[str] = mapped_column(String(3))
    ordered_on: Mapped[dt.date] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)

    vendor: Mapped[Vendor] = relationship()
    lines: Mapped[list["PurchaseOrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class PurchaseOrderLine(Base):
    __tablename__ = "purchase_order_lines"
    __table_args__ = (UniqueConstraint("purchase_order_id", "line_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(255))
    part_code: Mapped[str] = mapped_column(String(48), default="", index=True)
    quantity_ordered: Mapped[Decimal] = mapped_column(DecimalText)
    unit: Mapped[str] = mapped_column(String(16), default="piece")
    unit_price: Mapped[Decimal] = mapped_column(DecimalText)

    order: Mapped[PurchaseOrder] = relationship(back_populates="lines")


class GoodsReceipt(Base):
    """One delivery. A purchase order usually has several."""

    __tablename__ = "goods_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    purchase_order_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_orders.id", ondelete="CASCADE"), index=True
    )
    received_on: Mapped[dt.date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(String(255), default="")

    lines: Mapped[list["GoodsReceiptLine"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan"
    )
    order: Mapped[PurchaseOrder] = relationship()


class GoodsReceiptLine(Base):
    __tablename__ = "goods_receipt_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    goods_receipt_id: Mapped[int] = mapped_column(
        ForeignKey("goods_receipts.id", ondelete="CASCADE"), index=True
    )
    purchase_order_line_id: Mapped[int] = mapped_column(
        ForeignKey("purchase_order_lines.id"), index=True
    )
    quantity_received: Mapped[Decimal] = mapped_column(DecimalText)

    receipt: Mapped[GoodsReceipt] = relationship(back_populates="lines")
    order_line: Mapped[PurchaseOrderLine] = relationship()


# ---------------------------------------------------------------------------
# What arrived in the mailbox
# ---------------------------------------------------------------------------
class Document(Base):
    """The original file, kept exactly as it arrived."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    #: The hash is one of the ways the same invoice twice is caught.
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    page_count: Mapped[int] = mapped_column(Integer, default=1)
    kind: Mapped[str] = mapped_column(String(32), default="")
    received_from: Mapped[str] = mapped_column(String(160), default="")
    received_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    stored_path: Mapped[str] = mapped_column(String(400), default="")
    text: Mapped[str] = mapped_column(Text, default="")
    #: Decoded from the square barcode on a Taiwan uniform invoice.
    barcode_payload: Mapped[str] = mapped_column(Text, default="")


class Invoice(Base, TimestampMixin):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    document_id: Mapped[int | None] = mapped_column(ForeignKey("documents.id"), nullable=True)

    # bill | credit_note
    kind: Mapped[str] = mapped_column(String(16), default="bill", index=True)
    #: For a credit note, the bill it cancels part of.
    credits_invoice_id: Mapped[int | None] = mapped_column(
        ForeignKey("invoices.id"), nullable=True
    )

    # --- as read off the paper -------------------------------------------
    vendor_name_read: Mapped[str] = mapped_column(String(160), default="")
    invoice_number_read: Mapped[str] = mapped_column(String(64), default="")
    #: Punctuation and leading zeros removed, which is how "INV-0042" and "42"
    #: are recognised as the same document.
    invoice_number_normalised: Mapped[str] = mapped_column(String(64), default="", index=True)
    invoice_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="TWD")
    net_amount: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    tax_amount: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    total_amount: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    buyer_tax_identifier_read: Mapped[str] = mapped_column(String(32), default="")
    seller_tax_identifier_read: Mapped[str] = mapped_column(String(32), default="")
    purchase_order_number_read: Mapped[str] = mapped_column(String(32), default="")
    bank_account_read: Mapped[str] = mapped_column(String(40), default="")

    #: Per-field confidence from the reading step, so a weak field can be
    #: shown to a person instead of being trusted.
    field_confidence: Mapped[dict] = mapped_column(JSON, default=dict)
    read_with: Mapped[str] = mapped_column(String(20), default="")

    # --- as resolved against our own records ------------------------------
    vendor_id: Mapped[int | None] = mapped_column(ForeignKey("vendors.id"), nullable=True)
    entity_code: Mapped[str | None] = mapped_column(
        ForeignKey("entities.code"), nullable=True, index=True
    )
    purchase_order_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_orders.id"), nullable=True
    )
    exchange_rate: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    amount_in_base: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    # --- where it has got to ----------------------------------------------
    status: Mapped[str] = mapped_column(String(32), default="received", index=True)
    #: True only when it went from the mailbox to the ledger with nobody
    #: touching it. This is the number the whole product is judged on.
    posted_untouched: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    touched_by_a_person: Mapped[bool] = mapped_column(Boolean, default=False)

    #: The amount actually approved for payment, which is not the invoice
    #: total when only part of the delivery arrived.
    approved_amount: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    held_amount: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    hold_reason: Mapped[str] = mapped_column(String(255), default="")

    posting_period_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounting_periods.id"), nullable=True
    )
    calculation_trace: Mapped[dict] = mapped_column(JSON, default=dict)

    document: Mapped[Document | None] = relationship()
    vendor: Mapped[Vendor | None] = relationship()
    purchase_order: Mapped[PurchaseOrder | None] = relationship()
    lines: Mapped[list["InvoiceLine"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceLine.line_number"
    )
    exceptions: Mapped[list["Exception_"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan"
    )
    events: Mapped[list["InvoiceEvent"]] = relationship(
        back_populates="invoice", cascade="all, delete-orphan", order_by="InvoiceEvent.id"
    )


Index("ix_invoices_vendor_number", Invoice.vendor_id, Invoice.invoice_number_normalised)


class InvoiceLine(Base):
    __tablename__ = "invoice_lines"
    __table_args__ = (UniqueConstraint("invoice_id", "line_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int] = mapped_column(Integer)
    description: Mapped[str] = mapped_column(String(255))
    part_code: Mapped[str] = mapped_column(String(48), default="")
    quantity: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    unit: Mapped[str] = mapped_column(String(16), default="piece")
    unit_price: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    line_total: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    #: Which page of a long invoice this line came off.
    page: Mapped[int] = mapped_column(Integer, default=1)

    purchase_order_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("purchase_order_lines.id"), nullable=True
    )
    # matched | over_tolerance | not_ordered | not_received | partly_received
    match_result: Mapped[str] = mapped_column(String(32), default="")
    quantity_received_to_date: Mapped[Decimal] = mapped_column(
        DecimalText, default=Decimal("0")
    )
    quantity_billed_before: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    payable_quantity: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    payable_amount: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    held_amount: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    note: Mapped[str] = mapped_column(String(255), default="")
    calculation_trace: Mapped[dict] = mapped_column(JSON, default=dict)

    invoice: Mapped[Invoice] = relationship(back_populates="lines")
    order_line: Mapped[PurchaseOrderLine | None] = relationship()


class Exception_(Base):
    """Something a person has to look at, with the reason spelled out."""

    __tablename__ = "exceptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    #: duplicate | bank_detail_change | wrong_entity | wrong_buyer_tax_id |
    #: over_tolerance | no_purchase_order | partly_received | arithmetic |
    #: missing_field | closed_period | late_arrival | unreadable
    kind: Mapped[str] = mapped_column(String(40), index=True)
    #: block stops it dead; hold lets the rest of the invoice post; note is
    #: recorded and does not stop anything.
    severity: Mapped[str] = mapped_column(String(10), default="hold")
    summary: Mapped[str] = mapped_column(String(255))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    raised_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    resolution: Mapped[str] = mapped_column(String(255), default="")

    invoice: Mapped[Invoice] = relationship(back_populates="exceptions")
    resolved_by: Mapped[User | None] = relationship()


class CallBackTask(Base):
    """Telephone the number already on file. Never the one on the email."""

    __tablename__ = "call_back_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"), index=True)
    invoice_id: Mapped[int | None] = mapped_column(ForeignKey("invoices.id"), nullable=True)
    telephone_on_file: Mapped[str] = mapped_column(String(40))
    requested_change: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    outcome: Mapped[str] = mapped_column(String(32), default="")
    note: Mapped[str] = mapped_column(Text, default="")

    vendor: Mapped[Vendor] = relationship()
    completed_by: Mapped[User | None] = relationship()


class Approval(Base):
    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    rule_code: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(Text)
    required_role: Mapped[str] = mapped_column(String(40))
    step: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    comment: Mapped[str] = mapped_column(Text, default="")

    decided_by: Mapped[User | None] = relationship()


class Posting(Base):
    """One attempt to write a bill into a ledger."""

    __tablename__ = "postings"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    ledger: Mapped[str] = mapped_column(String(40))
    #: The same key twice is the same posting. This is what makes a retry
    #: after a crash safe.
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    external_reference: Mapped[str] = mapped_column(String(64), default="")
    amount: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="TWD")
    period_id: Mapped[int | None] = mapped_column(
        ForeignKey("accounting_periods.id"), nullable=True
    )
    last_error: Mapped[str] = mapped_column(String(255), default="")
    posted_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    invoice: Mapped[Invoice] = relationship()


class LedgerBill(Base):
    """What the ledger holds. Standing in for the accounting system."""

    __tablename__ = "ledger_bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    ledger: Mapped[str] = mapped_column(String(40), index=True)
    external_reference: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    idempotency_key: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    vendor_name: Mapped[str] = mapped_column(String(160))
    invoice_number: Mapped[str] = mapped_column(String(64))
    amount: Mapped[Decimal] = mapped_column(DecimalText)
    currency: Mapped[str] = mapped_column(String(3))
    posted_on: Mapped[dt.date] = mapped_column(Date)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ExchangeRate(Base):
    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("base_currency", "quote_currency", "as_of_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), index=True)
    quote_currency: Mapped[str] = mapped_column(String(3), index=True)
    rate: Mapped[Decimal] = mapped_column(DecimalText)
    as_of_date: Mapped[dt.date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(120), default="Demo treasury feed")


class InvoiceEvent(Base):
    """The story of one invoice, step by step, with what each step cost."""

    __tablename__ = "invoice_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    invoice_id: Mapped[int] = mapped_column(
        ForeignKey("invoices.id", ondelete="CASCADE"), index=True
    )
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor_type: Mapped[str] = mapped_column(String(20))
    actor_name: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(48), index=True)
    summary: Mapped[str] = mapped_column(String(400))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    engine: Mapped[str] = mapped_column(String(20), default="")
    cost_usd: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    invoice: Mapped[Invoice] = relationship(back_populates="events")


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    user_email: Mapped[str] = mapped_column(String(160), default="")
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    before: Mapped[dict] = mapped_column(JSON, default=dict)
    after: Mapped[dict] = mapped_column(JSON, default=dict)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    engine: Mapped[str] = mapped_column(String(20), default="built-in")
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    results: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
