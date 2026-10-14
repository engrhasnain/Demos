"""The tables.

One column does more work than any other: ``customer_id``. Every row a
visitor can ever be shown hangs off it, and the one place that reads those
rows refuses to run without it. Data isolation is not a prompt instruction
here, it is a function signature.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class DecimalText(TypeDecorator):
    """Exact money, stored as text."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: D102
        return None if value is None else str(Decimal(str(value)))

    def process_result_value(self, value, dialect):  # noqa: D102
        return None if value is None else Decimal(value)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ---------------------------------------------------------------------------
# Staff
# ---------------------------------------------------------------------------
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------------------
# Customers and the things that belong to them
# ---------------------------------------------------------------------------
class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    city: Mapped[str] = mapped_column(String(80), default="")
    language: Mapped[str] = mapped_column(String(10), default="en")
    #: Trade accounts are not consumers, which changes what they are owed.
    is_trade_account: Mapped[bool] = mapped_column(Boolean, default=True)
    warranty_months: Mapped[int] = mapped_column(Integer, default=12)

    contacts: Mapped[list["Contact"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class Contact(Base):
    """A person at a customer. Verification is against one of these."""

    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(160), index=True)
    telephone: Mapped[str] = mapped_column(String(40), default="")
    #: The LINE account this person messages from, once they have been seen.
    line_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)

    customer: Mapped[Customer] = relationship(back_populates="contacts")


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    placed_on: Mapped[dt.date] = mapped_column(Date, index=True)
    promised_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    #: What the business system believes.
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    despatched_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    delivered_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    carrier: Mapped[str] = mapped_column(String(40), default="")
    tracking_number: Mapped[str] = mapped_column(String(48), default="")
    total: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="TWD")

    customer: Mapped[Customer] = relationship()
    lines: Mapped[list["OrderLine"]] = relationship(
        back_populates="order", cascade="all, delete-orphan"
    )


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("orders.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int] = mapped_column(Integer)
    part_code: Mapped[str] = mapped_column(String(48), index=True)
    description: Mapped[str] = mapped_column(String(255))
    quantity: Mapped[int] = mapped_column(Integer)
    #: The batch, which decides whether a fault is a known one.
    lot_number: Mapped[str] = mapped_column(String(32), default="")
    unit_price: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    order: Mapped[Order] = relationship(back_populates="lines")


class CarrierEvent(Base):
    """What the carrier says, which is not always what the system says."""

    __tablename__ = "carrier_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    tracking_number: Mapped[str] = mapped_column(String(48), index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    #: label_created | collected | in_transit | customs | out_for_delivery
    #: | delivered | exception
    code: Mapped[str] = mapped_column(String(32))
    place: Mapped[str] = mapped_column(String(120), default="")
    note: Mapped[str] = mapped_column(String(255), default="")


class Quotation(Base):
    """Answered from the quoting system, read only."""

    __tablename__ = "quotations"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default="sent", index=True)
    sent_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    total: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    currency: Mapped[str] = mapped_column(String(3), default="TWD")
    lines: Mapped[int] = mapped_column(Integer, default=0)


# ---------------------------------------------------------------------------
# Returns
# ---------------------------------------------------------------------------
class ReturnRequest(Base, TimestampMixin):
    __tablename__ = "return_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    order_id: Mapped[int | None] = mapped_column(ForeignKey("orders.id"), nullable=True)
    part_code: Mapped[str] = mapped_column(String(48), default="")
    quantity: Mapped[int] = mapped_column(Integer, default=0)

    #: What the customer said.
    reported: Mapped[str] = mapped_column(Text, default="")
    #: What the photograph suggested, and how sure.
    triage: Mapped[str] = mapped_column(String(32), default="")
    triage_confidence: Mapped[float] = mapped_column(default=0.0)
    triage_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    photo_name: Mapped[str] = mapped_column(String(160), default="")

    #: Whether the contract actually covers it, worked out in code.
    within_warranty: Mapped[bool] = mapped_column(Boolean, default=False)
    warranty_detail: Mapped[dict] = mapped_column(JSON, default=dict)

    #: proposed | approved | refused | withdrawn. A person decides.
    status: Mapped[str] = mapped_column(String(16), default="proposed", index=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_note: Mapped[str] = mapped_column(Text, default="")

    customer: Mapped[Customer] = relationship()
    order: Mapped[Order | None] = relationship()
    decided_by: Mapped[User | None] = relationship()


# ---------------------------------------------------------------------------
# Technician visits
# ---------------------------------------------------------------------------
class Technician(Base):
    __tablename__ = "technicians"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    base_city: Mapped[str] = mapped_column(String(80), index=True)
    #: What they are qualified to work on.
    skills: Mapped[list] = mapped_column(JSON, default=list)
    #: What is in the van today, so a visit is not wasted.
    van_stock: Mapped[list] = mapped_column(JSON, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Visit(Base, TimestampMixin):
    """A booked technician visit.

    The unique constraint is the point. Two customers pressing the same slot
    at the same instant is not a rare case, it is what happens on the first
    morning. The database decides, not the application.
    """

    __tablename__ = "visits"
    __table_args__ = (
        UniqueConstraint("technician_id", "starts_at", name="one_visit_per_slot"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    technician_id: Mapped[int] = mapped_column(ForeignKey("technicians.id"), index=True)

    starts_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), index=True)
    minutes: Mapped[int] = mapped_column(Integer, default=90)
    city: Mapped[str] = mapped_column(String(80), default="")
    skill_needed: Mapped[str] = mapped_column(String(48), default="")
    parts_needed: Mapped[list] = mapped_column(JSON, default=list)
    note: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(16), default="booked", index=True)

    customer: Mapped[Customer] = relationship()
    technician: Mapped[Technician] = relationship()


# ---------------------------------------------------------------------------
# Conversations
# ---------------------------------------------------------------------------
class Conversation(Base, TimestampMixin):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    #: web | line
    channel: Mapped[str] = mapped_column(String(16), default="web", index=True)
    #: Who the visitor turned out to be, once they proved it. Null until then.
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id"), nullable=True)
    external_id: Mapped[str] = mapped_column(String(64), default="", index=True)

    language: Mapped[str] = mapped_column(String(10), default="en")
    verified_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    verification_attempts: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    #: open | resolved | escalated | abandoned
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    #: What the visitor came for, as last understood.
    intent: Mapped[str] = mapped_column(String(32), default="", index=True)
    resolved_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: Set when the customer said the answer was no good, which is the only
    #: honest way to know a resolution was not one.
    reopened: Mapped[bool] = mapped_column(Boolean, default=False)

    customer: Mapped[Customer | None] = relationship()
    contact: Mapped[Contact | None] = relationship()
    turns: Mapped[list["Turn"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan"
    )
    ticket: Mapped["Ticket | None"] = relationship(
        back_populates="conversation", uselist=False
    )


class Turn(Base):
    __tablename__ = "turns"

    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"), index=True
    )
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    #: customer | desk | staff
    speaker: Mapped[str] = mapped_column(String(12))
    text: Mapped[str] = mapped_column(Text)

    intent: Mapped[str] = mapped_column(String(32), default="")
    intent_confidence: Mapped[float] = mapped_column(default=0.0)
    #: Which tool ran, if any, and what it was given.
    tool: Mapped[str] = mapped_column(String(40), default="")
    tool_arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    tool_result: Mapped[dict] = mapped_column(JSON, default=dict)
    #: Anything the engine refused, and why.
    refusal: Mapped[str] = mapped_column(String(160), default="")
    engine: Mapped[str] = mapped_column(String(16), default="built-in")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    attachment: Mapped[str] = mapped_column(String(160), default="")

    conversation: Mapped[Conversation] = relationship(back_populates="turns")


class Ticket(Base, TimestampMixin):
    """A handover to a person, with a reply time somebody can keep."""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id"), unique=True, index=True
    )
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    reason: Mapped[str] = mapped_column(String(48), index=True)
    summary: Mapped[str] = mapped_column(Text, default="")
    #: Worked out from office hours, not promised blindly.
    reply_by: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True))
    reply_wording: Mapped[str] = mapped_column(String(160), default="")
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    assigned_to_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    conversation: Mapped[Conversation] = relationship(back_populates="ticket")
    assigned_to: Mapped[User | None] = relationship()


class AccessLog(Base):
    """Every attempt to reach customer data, allowed or not.

    The refused ones are the interesting ones. Somebody asking the front
    desk about an order that is not theirs is either confused or probing,
    and both are worth a record.
    """

    __tablename__ = "access_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id"), nullable=True, index=True
    )
    #: Who the conversation had proved itself to be, if anybody.
    acting_customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True
    )
    tool: Mapped[str] = mapped_column(String(40), index=True)
    arguments: Mapped[dict] = mapped_column(JSON, default=dict)
    allowed: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    refusal: Mapped[str] = mapped_column(String(160), default="")
    rows_returned: Mapped[int] = mapped_column(Integer, default=0)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    engine: Mapped[str] = mapped_column(String(16), default="built-in")
    conversations: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    results: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
