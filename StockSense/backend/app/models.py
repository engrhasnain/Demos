"""The tables.

One decision shapes the rest of this file: a demand history is stored as a
series on the part, not as a row per part per week. Eighteen thousand parts
over a hundred and four weeks is nearly two million rows that are only ever
read all at once, for one part at a time. As a list on the part it loads in
one go, seeds in seconds, and still holds exactly the same figures.

Money is text, via the decimal column type, so nothing is ever a float.
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
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base
from .numbers import dec


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class DecimalText(TypeDecorator):
    """Exact money. Stored as text so no database rounds it for us."""

    impl = String(32)
    cache_ok = True

    def process_bind_param(self, value, dialect):  # noqa: D102
        return None if value is None else str(dec(value))

    def process_result_value(self, value, dialect):  # noqa: D102
        return None if value is None else dec(value)


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
    role: Mapped[str] = mapped_column(String(40), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------------------
# Suppliers
# ---------------------------------------------------------------------------
class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    country: Mapped[str] = mapped_column(String(2), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="TWD")

    #: What they say the lead time is.
    quoted_lead_time_days: Mapped[int] = mapped_column(Integer, default=28)
    #: What it actually was, one entry per delivery on record.
    lead_time_samples: Mapped[list] = mapped_column(JSON, default=list)

    #: Ordering constraints that make a recommendation a real order.
    minimum_order_value: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    #: Orders are consolidated to fill a container when one is specified.
    container_cubic_metres: Mapped[Decimal] = mapped_column(
        DecimalText, default=Decimal("0")
    )

    parts: Mapped[list["Part"]] = relationship(back_populates="supplier")


# ---------------------------------------------------------------------------
# Parts
# ---------------------------------------------------------------------------
class Part(Base, TimestampMixin):
    """One stock-keeping unit, with its history alongside it."""

    __tablename__ = "parts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    description: Mapped[str] = mapped_column(String(255))
    #: Parts in a family are close enough to borrow a forecast from.
    family: Mapped[str] = mapped_column(String(48), index=True)

    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    unit_cost: Mapped[Decimal] = mapped_column(DecimalText)
    unit: Mapped[str] = mapped_column(String(16), default="piece")

    pack_size: Mapped[int] = mapped_column(Integer, default=1)
    minimum_order_quantity: Mapped[int] = mapped_column(Integer, default=0)
    cubic_metres_each: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    #: A, B or C by value sold, which sets the service level.
    abc_class: Mapped[str] = mapped_column(String(1), default="C", index=True)

    on_hand: Mapped[int] = mapped_column(Integer, default=0)
    on_order: Mapped[int] = mapped_column(Integer, default=0)
    #: When what is already on order is expected.
    on_order_due: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    first_sold_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    #: Set when this part replaces another, so its history can be carried.
    replaces_part_id: Mapped[int | None] = mapped_column(
        ForeignKey("parts.id"), nullable=True, index=True
    )
    #: Set when this part has been replaced and should not be reordered.
    replaced_by_part_id: Mapped[int | None] = mapped_column(
        ForeignKey("parts.id"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    supplier: Mapped[Supplier] = relationship(back_populates="parts")
    history: Mapped["DemandHistory | None"] = relationship(
        back_populates="part", uselist=False, cascade="all, delete-orphan"
    )


class DemandHistory(Base):
    """Weekly demand for one part, as three series of the same length.

    ``sold`` is what left the warehouse. ``stocked_out`` says whether the
    shelf was empty that week, which is the difference between "nobody
    wanted it" and "we could not have sold it anyway". ``was_project`` marks
    the weeks that were a one-off build rather than the usual trade.
    """

    __tablename__ = "demand_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(
        ForeignKey("parts.id", ondelete="CASCADE"), unique=True, index=True
    )
    #: The Monday of the first week in the series.
    starts_on: Mapped[dt.date] = mapped_column(Date)
    weeks: Mapped[int] = mapped_column(Integer, default=0)

    sold: Mapped[list] = mapped_column(JSON, default=list)
    stocked_out: Mapped[list] = mapped_column(JSON, default=list)
    was_project: Mapped[list] = mapped_column(JSON, default=list)

    part: Mapped[Part] = relationship(back_populates="history")


# ---------------------------------------------------------------------------
# What the buyers did, so the replay has something to beat
# ---------------------------------------------------------------------------
class HistoricOrder(Base):
    """An order the buyers actually placed, from the spreadsheet era."""

    __tablename__ = "historic_orders"

    id: Mapped[int] = mapped_column(primary_key=True)
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), index=True)
    ordered_on: Mapped[dt.date] = mapped_column(Date, index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    arrived_on: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    unit_cost: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    part: Mapped[Part] = relationship()


# ---------------------------------------------------------------------------
# What StockSense recommends
# ---------------------------------------------------------------------------
class PlanRun(Base):
    """One weekly ordering round."""

    __tablename__ = "plan_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    as_of: Mapped[dt.date] = mapped_column(Date, index=True)

    cash_cap: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    cash_committed: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    parts_considered: Mapped[int] = mapped_column(Integer, default=0)
    lines_recommended: Mapped[int] = mapped_column(Integer, default=0)
    lines_deferred: Mapped[int] = mapped_column(Integer, default=0)
    seconds: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    notes: Mapped[str] = mapped_column(Text, default="")

    lines: Mapped[list["PlanLine"]] = relationship(
        back_populates="run", cascade="all, delete-orphan"
    )
    created_by: Mapped[User | None] = relationship()


class PlanLine(Base):
    """One recommendation: buy this many of this, or deliberately not yet."""

    __tablename__ = "plan_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("plan_runs.id", ondelete="CASCADE"), index=True
    )
    part_id: Mapped[int] = mapped_column(ForeignKey("parts.id"), index=True)

    #: order | prebuild | deferred | watch
    decision: Mapped[str] = mapped_column(String(16), index=True)
    #: Why, in a word the screen can group by.
    reason: Mapped[str] = mapped_column(String(48), index=True)

    quantity: Mapped[int] = mapped_column(Integer, default=0)
    #: Before pack sizes and minimums were applied.
    raw_quantity: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    value: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    demand_method: Mapped[str] = mapped_column(String(16), default="")
    demand_pattern: Mapped[str] = mapped_column(String(16), default="")
    weekly_rate: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    reorder_point: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    order_up_to: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    safety_stock: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    position: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    lead_time_days: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    service_level: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    #: How badly this is needed, which is how the cash cap decides.
    urgency: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    #: Days of cover left if nothing is ordered.
    days_of_cover: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    shutdown_note: Mapped[str] = mapped_column(String(160), default="")
    flags: Mapped[list] = mapped_column(JSON, default=list)
    trace: Mapped[dict] = mapped_column(JSON, default=dict)

    run: Mapped[PlanRun] = relationship(back_populates="lines")
    part: Mapped[Part] = relationship()


# ---------------------------------------------------------------------------
# The replay, which is how the product is actually graded
# ---------------------------------------------------------------------------
class ReplayRun(Base):
    """A twelve month re-run of the year against what the buyers did."""

    __tablename__ = "replay_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    weeks: Mapped[int] = mapped_column(Integer, default=52)
    parts: Mapped[int] = mapped_column(Integer, default=0)
    seconds: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    #: Side by side: what happened, and what would have happened.
    buyers: Mapped[dict] = mapped_column(JSON, default=dict)
    stocksense: Mapped[dict] = mapped_column(JSON, default=dict)
    by_pattern: Mapped[list] = mapped_column(JSON, default=list)
    weekly: Mapped[list] = mapped_column(JSON, default=list)
    accuracy: Mapped[dict] = mapped_column(JSON, default=dict)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[str] = mapped_column(Text, default="")


class AuditEntry(Base):
    __tablename__ = "audit_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, index=True
    )
    user_email: Mapped[str] = mapped_column(String(160), default="")
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[str] = mapped_column(String(60), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
