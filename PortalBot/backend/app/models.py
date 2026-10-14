"""The tables.

The shape of ``Shipment`` is the design. Two systems have to be changed
and there is no transaction spanning them, so the state of each is
recorded separately and the row is the checkpoint. Killing the process at
any point leaves a row that says exactly how far it got, and the next run
reads that row before it does anything.

``idempotency_key`` is what makes a repeat free. It is derived from the
shipment, not generated, so the same shipment computes the same key on
every machine on every run.
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


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(40), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    #: Who gets the push when a one-time code is needed.
    on_duty: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


# ---------------------------------------------------------------------------
# What there is to ship
# ---------------------------------------------------------------------------
class Shipment(Base, TimestampMixin):
    """One consignment, and how far through the two systems it got."""

    __tablename__ = "shipments"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    order_number: Mapped[str] = mapped_column(String(32), index=True)
    customer_name: Mapped[str] = mapped_column(String(160))

    to_name: Mapped[str] = mapped_column(String(160), default="")
    to_line1: Mapped[str] = mapped_column(String(200), default="")
    to_city: Mapped[str] = mapped_column(String(80), default="")
    to_postcode: Mapped[str] = mapped_column(String(24), default="")
    to_country: Mapped[str] = mapped_column(String(2), default="TW", index=True)

    packages: Mapped[int] = mapped_column(Integer, default=1)
    weight_kg: Mapped[float] = mapped_column(Float, default=0.0)
    goods_description: Mapped[str] = mapped_column(String(255), default="")
    service: Mapped[str] = mapped_column(String(24), default="STD")
    lines: Mapped[list] = mapped_column(JSON, default=list)

    #: Worked out before the portal sees it, and never guessed.
    dangerous: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    dangerous_detail: Mapped[dict] = mapped_column(JSON, default=dict)

    #: The same shipment always computes the same key.
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)

    # --- how far it got -------------------------------------------------
    #: pending | booked | written_back | done | failed | needs_a_person
    state: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    consignment: Mapped[str] = mapped_column(String(32), default="", index=True)
    tracking_number: Mapped[str] = mapped_column(String(48), default="")
    carrier: Mapped[str] = mapped_column(String(40), default="")
    label_url: Mapped[str] = mapped_column(String(300), default="")
    booked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    written_back_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    exception_kind: Mapped[str] = mapped_column(String(40), default="", index=True)
    exception_detail: Mapped[str] = mapped_column(Text, default="")

    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True, index=True)
    steps: Mapped[list["Step"]] = relationship(
        back_populates="shipment", cascade="all, delete-orphan"
    )


class Run(Base):
    """One pass over the day's shipments."""

    __tablename__ = "runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: running | finished | stopped | halted
    status: Mapped[str] = mapped_column(String(16), default="running", index=True)
    considered: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    exceptions: Mapped[int] = mapped_column(Integer, default=0)
    skipped_already_done: Mapped[int] = mapped_column(Integer, default=0)
    seconds: Mapped[float] = mapped_column(Float, default=0.0)
    #: Set when the run stopped itself because the portal had changed.
    halted_reason: Mapped[str] = mapped_column(String(255), default="")
    drift: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")


class Step(Base):
    """Every action against either system, so a run can be replayed.

    This is the trace the acceptance criteria ask for. Not a log line: the
    request, the answer, how long it took and which attempt it was, so
    somebody can see exactly what the bot sent when it went wrong.
    """

    __tablename__ = "steps"

    id: Mapped[int] = mapped_column(primary_key=True)
    shipment_id: Mapped[int] = mapped_column(
        ForeignKey("shipments.id", ondelete="CASCADE"), index=True
    )
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True, index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    #: carrier | legacy | bot
    system: Mapped[str] = mapped_column(String(16), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    #: ok | refused | failed | skipped | waiting
    outcome: Mapped[str] = mapped_column(String(16), index=True)
    sent: Mapped[dict] = mapped_column(JSON, default=dict)
    received: Mapped[dict] = mapped_column(JSON, default=dict)
    note: Mapped[str] = mapped_column(String(400), default="")
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)

    shipment: Mapped[Shipment] = relationship(back_populates="steps")


class Challenge(Base):
    """A one-time code the bot cannot produce and will not try to.

    It pauses, pushes to whoever is on duty, and waits. An image challenge
    is never attempted at all: a system that bypasses a human check is a
    system that has been built to defeat a security control.
    """

    __tablename__ = "challenges"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    shipment_id: Mapped[int | None] = mapped_column(
        ForeignKey("shipments.id"), nullable=True, index=True
    )
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    kind: Mapped[str] = mapped_column(String(24), default="one_time_code")
    asked_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    asked_of_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    #: waiting | answered | expired | refused
    status: Mapped[str] = mapped_column(String(16), default="waiting", index=True)
    answered_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    #: The portal's own challenge identifier.
    external_id: Mapped[str] = mapped_column(String(48), default="")
    note: Mapped[str] = mapped_column(String(255), default="")

    shipment: Mapped[Shipment | None] = relationship()
    asked_of: Mapped[User | None] = relationship()


class ScriptFlag(Base):
    """The portal moved. A developer reads this; nothing rewrites itself."""

    __tablename__ = "script_flags"

    id: Mapped[int] = mapped_column(primary_key=True)
    raised_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    run_id: Mapped[int | None] = mapped_column(ForeignKey("runs.id"), nullable=True)
    script: Mapped[str] = mapped_column(String(48), index=True)
    expected_fingerprint: Mapped[str] = mapped_column(String(32), default="")
    found_fingerprint: Mapped[str] = mapped_column(String(32), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    #: open | acknowledged | fixed
    status: Mapped[str] = mapped_column(String(16), default="open", index=True)
    acknowledged_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"), nullable=True
    )
    note: Mapped[str] = mapped_column(Text, default="")

    acknowledged_by: Mapped[User | None] = relationship()


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    shipments: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    results: Mapped[list] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
