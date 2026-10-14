"""The tables.

Two halves. The operational data the questions are asked about, pulled
together from the five systems the other MVPs each look after, and the
record of what was asked, what ran, and what was proposed.

``Grant`` is the one that matters: it is where "which rows may this
person see" lives, in the database, as data, rather than in a prompt or
in a comment.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
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
    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: D102
        return None if value is None else str(Decimal(str(value)))

    def process_result_value(self, value, dialect):  # noqa: D102
        return None if value is None else Decimal(value)


# ---------------------------------------------------------------------------
# People, and what they may see
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Grant(Base):
    """One account this person may see. Data, not a prompt.

    A director has no rows here and sees everything; everybody else sees
    exactly what is listed. The absence of a grant is "nothing", never
    "everything", which is the way round that fails safe.
    """

    __tablename__ = "grants"
    __table_args__ = (
        UniqueConstraint("user_id", "customer_id", "supplier_id", name="one_grant_once"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True, index=True
    )
    note: Mapped[str] = mapped_column(String(160), default="")


# ---------------------------------------------------------------------------
# The operational picture
# ---------------------------------------------------------------------------
class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    region: Mapped[str] = mapped_column(String(40), default="", index=True)


class Supplier(Base):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    quoted_lead_time_days: Mapped[int] = mapped_column(Integer, default=28)
    shutdown_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    shutdown_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)


class Delivery(Base):
    """What a supplier's deliveries actually took."""

    __tablename__ = "deliveries"

    id: Mapped[int] = mapped_column(primary_key=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    arrived_on: Mapped[dt.date] = mapped_column(Date)
    actual_days: Mapped[int] = mapped_column(Integer)


class Part(Base):
    __tablename__ = "parts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255))
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    on_hand: Mapped[int] = mapped_column(Integer, default=0)
    on_order: Mapped[int] = mapped_column(Integer, default=0)
    weekly_demand: Mapped[float] = mapped_column(Float, default=0.0)
    unit_cost: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    placed_on: Mapped[dt.date] = mapped_column(Date, index=True)
    promised_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(24), default="open", index=True)
    total: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))


class OrderLine(Base):
    __tablename__ = "order_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    part_code: Mapped[str] = mapped_column(String(48), index=True)
    quantity: Mapped[int] = mapped_column(Integer, default=0)


class Shipment(Base):
    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    order_number: Mapped[str] = mapped_column(String(32), index=True)
    state: Mapped[str] = mapped_column(String(24), default="pending", index=True)
    exception_kind: Mapped[str] = mapped_column(String(48), default="", index=True)
    tracking_number: Mapped[str] = mapped_column(String(48), default="")


class Invoice(Base):
    __tablename__ = "invoices"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    issued_on: Mapped[dt.date] = mapped_column(Date)
    due_on: Mapped[dt.date] = mapped_column(Date, index=True)
    paid_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True, index=True)
    total: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    reason: Mapped[str] = mapped_column(String(80))
    raised_on: Mapped[dt.date] = mapped_column(Date, index=True)
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)


class Document(Base):
    """An email or a note. Content, never instructions.

    Here so the injection suite has somewhere real to put an attack: a
    supplier email that tries to give the operations system orders.
    """

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    kind: Mapped[str] = mapped_column(String(24), default="email")
    subject: Mapped[str] = mapped_column(String(200), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    received_on: Mapped[dt.date] = mapped_column(Date)
    customer_id: Mapped[int | None] = mapped_column(
        ForeignKey("customers.id"), nullable=True, index=True
    )
    supplier_id: Mapped[int | None] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True, index=True
    )


# ---------------------------------------------------------------------------
# What was asked, and what was proposed
# ---------------------------------------------------------------------------
class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    asked_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    asked_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    text: Mapped[str] = mapped_column(Text)
    reading: Mapped[str] = mapped_column(Text, default="")
    answer: Mapped[str] = mapped_column(Text, default="")
    refused: Mapped[str] = mapped_column(String(400), default="")
    plan: Mapped[list] = mapped_column(JSON, default=list)
    #: Every step's query, parameters, row count and the moment it ran.
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    seconds: Mapped[float] = mapped_column(Float, default=0.0)
    cost_usd: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    engine: Mapped[str] = mapped_column(String(16), default="built-in")
    #: Set when something in the content tried to give instructions.
    injection_seen: Mapped[bool] = mapped_column(Boolean, default=False, index=True)

    asked_by: Mapped[User | None] = relationship()


class Proposal(Base):
    """Something the system thinks ought to be done. Never done by it.

    Excessive agency is third on the OWASP list for a reason. Everything
    this system can suggest ends up here, with a named approver, and the
    approving is a person pressing a button.
    """

    __tablename__ = "proposals"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id"), nullable=True, index=True
    )
    raised_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    summary: Mapped[str] = mapped_column(String(400))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    #: The role that has to sign it off. Nothing happens without one.
    needs_role: Mapped[str] = mapped_column(String(40), default="manager")
    #: proposed | approved | refused
    status: Mapped[str] = mapped_column(String(16), default="proposed", index=True)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, default="")

    decided_by: Mapped[User | None] = relationship()


class AccessLog(Base):
    """Every capability anybody ran, allowed or refused."""

    __tablename__ = "access_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    question_id: Mapped[int | None] = mapped_column(
        ForeignKey("questions.id"), nullable=True
    )
    capability: Mapped[str] = mapped_column(String(48), index=True)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    allowed: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    refusal: Mapped[str] = mapped_column(String(255), default="")
    rows_returned: Mapped[int] = mapped_column(Integer, default=0)
    filter_applied: Mapped[str] = mapped_column(String(120), default="")


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    questions: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    results: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
