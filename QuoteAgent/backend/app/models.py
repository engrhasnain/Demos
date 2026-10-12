"""Database tables.

Money columns use DecimalText, which stores the exact decimal string.
SQLite has no decimal type and would otherwise round money through a float.
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
        if value is None:
            return None
        return str(dec(value))

    def process_result_value(self, value: Any, dialect: Any) -> Decimal | None:
        if value is None:
            return None
        return dec(value)


def utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


class TimestampMixin:
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


# ---------------------------------------------------------------------------
# People and permissions
# ---------------------------------------------------------------------------
class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(160), unique=True, index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    # sales_engineer | sales_manager | director | pricing_owner | administrator
    role: Mapped[str] = mapped_column(String(40), index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    language: Mapped[str] = mapped_column(String(10), default="en")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


# ---------------------------------------------------------------------------
# Company master data
# ---------------------------------------------------------------------------
class Warehouse(Base):
    __tablename__ = "warehouses"

    code: Mapped[str] = mapped_column(String(20), primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    country: Mapped[str] = mapped_column(String(2))
    legal_entity: Mapped[str] = mapped_column(String(40))
    city: Mapped[str] = mapped_column(String(60))


class Supplier(Base, TimestampMixin):
    __tablename__ = "suppliers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    country: Mapped[str] = mapped_column(String(2), index=True)
    email: Mapped[str] = mapped_column(String(160))
    currency: Mapped[str] = mapped_column(String(3))
    lead_time_days: Mapped[int] = mapped_column(Integer)
    lead_time_variance_days: Mapped[int] = mapped_column(Integer, default=5)
    minimum_order_quantity: Mapped[int] = mapped_column(Integer, default=1)
    reliability_percent: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("95"))
    # Lunar New Year and national shutdowns, held per supplier and per country.
    annual_shutdown: Mapped[dict] = mapped_column(JSON, default=dict)


class Customer(Base, TimestampMixin):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(160))
    country: Mapped[str] = mapped_column(String(2), index=True)
    currency: Mapped[str] = mapped_column(String(3))
    language: Mapped[str] = mapped_column(String(10), default="en")
    default_incoterm: Mapped[str] = mapped_column(String(8), default="FOB")
    default_named_place: Mapped[str] = mapped_column(String(60), default="Taichung")
    price_tier: Mapped[str] = mapped_column(String(20), default="standard")
    margin_floor_percent: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("18"))
    # Taiwan unified business number (8 digits) or a US employer identification number.
    tax_identifier: Mapped[str] = mapped_column(String(32), default="")
    tax_identifier_kind: Mapped[str] = mapped_column(String(24), default="")
    payment_terms_days: Mapped[int] = mapped_column(Integer, default=45)
    credit_limit: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    on_credit_hold: Mapped[bool] = mapped_column(Boolean, default=False)

    contacts: Mapped[list["CustomerContact"]] = relationship(
        back_populates="customer", cascade="all, delete-orphan"
    )


class CustomerContact(Base):
    __tablename__ = "customer_contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id", ondelete="CASCADE"))
    email: Mapped[str] = mapped_column(String(160), index=True)
    full_name: Mapped[str] = mapped_column(String(120))
    language: Mapped[str] = mapped_column(String(10), default="en")

    customer: Mapped[Customer] = relationship(back_populates="contacts")


class Product(Base, TimestampMixin):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(48), unique=True, index=True)
    family: Mapped[str] = mapped_column(String(40), index=True)
    description_en: Mapped[str] = mapped_column(String(255))
    description_zh: Mapped[str] = mapped_column(String(255), default="")
    # The published standard the part is made to, for example "ISO 4762" or "ISO 15".
    standard: Mapped[str] = mapped_column(String(40), default="", index=True)
    # Checked attribute by attribute during matching; a mismatch flags the line.
    attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    search_text: Mapped[str] = mapped_column(Text, default="")

    selling_unit: Mapped[str] = mapped_column(String(12), default="piece")
    pack_size: Mapped[int] = mapped_column(Integer, default=1)
    weight_grams: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    harmonised_tariff_code: Mapped[str] = mapped_column(String(16), index=True)
    country_of_origin: Mapped[str] = mapped_column(String(2), default="TW")

    list_price: Mapped[Decimal] = mapped_column(DecimalText)      # always in TWD
    standard_cost: Mapped[Decimal] = mapped_column(DecimalText)   # always in TWD

    supplier_id: Mapped[int | None] = mapped_column(ForeignKey("suppliers.id"), nullable=True)
    replenishment_lead_time_days: Mapped[int] = mapped_column(Integer, default=30)
    is_stocked: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)

    supplier: Mapped[Supplier | None] = relationship()
    stock: Mapped[list["StockLevel"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    price_breaks: Mapped[list["PriceBreak"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )


Index("ix_products_family_standard", Product.family, Product.standard)


class StockLevel(Base):
    __tablename__ = "stock_levels"
    __table_args__ = (UniqueConstraint("product_id", "warehouse_code"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    warehouse_code: Mapped[str] = mapped_column(ForeignKey("warehouses.code"))
    quantity_on_hand: Mapped[int] = mapped_column(Integer, default=0)
    quantity_allocated: Mapped[int] = mapped_column(Integer, default=0)

    product: Mapped[Product] = relationship(back_populates="stock")

    @property
    def available(self) -> int:
        return max(self.quantity_on_hand - self.quantity_allocated, 0)


class PriceBreak(Base):
    """Volume pricing used when a customer has no contract for the part."""

    __tablename__ = "price_breaks"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    price_tier: Mapped[str] = mapped_column(String(20), default="standard")
    minimum_quantity: Mapped[int] = mapped_column(Integer)
    unit_price: Mapped[Decimal] = mapped_column(DecimalText)

    product: Mapped[Product] = relationship(back_populates="price_breaks")


class Contract(Base, TimestampMixin):
    __tablename__ = "contracts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    customer_id: Mapped[int] = mapped_column(
        ForeignKey("customers.id", ondelete="CASCADE"), index=True
    )
    valid_from: Mapped[dt.date] = mapped_column(Date)
    valid_to: Mapped[dt.date] = mapped_column(Date)
    note: Mapped[str] = mapped_column(String(255), default="")

    lines: Mapped[list["ContractLine"]] = relationship(
        back_populates="contract", cascade="all, delete-orphan"
    )


class ContractLine(Base):
    __tablename__ = "contract_lines"
    __table_args__ = (UniqueConstraint("contract_id", "product_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    contract_id: Mapped[int] = mapped_column(ForeignKey("contracts.id", ondelete="CASCADE"))
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    unit_price: Mapped[Decimal] = mapped_column(DecimalText)
    minimum_quantity: Mapped[int] = mapped_column(Integer, default=1)

    contract: Mapped[Contract] = relationship(back_populates="lines")


class CrossReference(Base):
    """Competitor and standard part numbers that map onto a Hengtai part."""

    __tablename__ = "cross_references"
    __table_args__ = (UniqueConstraint("normalised_number", "brand"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), index=True
    )
    external_number: Mapped[str] = mapped_column(String(80))
    normalised_number: Mapped[str] = mapped_column(String(80), index=True)
    brand: Mapped[str] = mapped_column(String(40), index=True)
    # exact | interchange | approximate - "approximate" always forces a human check
    equivalence: Mapped[str] = mapped_column(String(20), default="interchange")
    note: Mapped[str] = mapped_column(String(160), default="")
    verified_by: Mapped[str] = mapped_column(String(80), default="")


# ---------------------------------------------------------------------------
# Pricing reference data that a named person owns
# ---------------------------------------------------------------------------
class TariffTable(Base, TimestampMixin):
    """A dated, versioned duty table.

    Duty is never worked out by the reasoning engine and never written into the
    code. It is read from the one table that was active on the quote date, and
    the quote records which version priced it. Loading a newer version flags
    every open quote priced on an older one.
    """

    __tablename__ = "tariff_tables"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(160))
    effective_from: Mapped[dt.date] = mapped_column(Date, index=True)
    effective_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    # draft | active | superseded
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    owned_by: Mapped[str] = mapped_column(String(80))
    customs_broker: Mapped[str] = mapped_column(String(120), default="")
    broker_signed_off_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source_note: Mapped[str] = mapped_column(Text, default="")

    lines: Mapped[list["TariffLine"]] = relationship(
        back_populates="table", cascade="all, delete-orphan"
    )

    @property
    def is_signed_off(self) -> bool:
        return self.broker_signed_off_at is not None


class TariffLine(Base):
    """One duty component for one commodity code on one trade lane."""

    __tablename__ = "tariff_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    tariff_table_id: Mapped[int] = mapped_column(
        ForeignKey("tariff_tables.id", ondelete="CASCADE"), index=True
    )
    harmonised_tariff_code: Mapped[str] = mapped_column(String(16), index=True)
    origin_country: Mapped[str] = mapped_column(String(2), index=True)
    destination_country: Mapped[str] = mapped_column(String(2), index=True)
    # most_favoured_nation | section_232 | section_301 | section_122 | reciprocal
    component: Mapped[str] = mapped_column(String(40))
    rate_percent: Mapped[Decimal] = mapped_column(DecimalText)
    # customs_value | metal_content_value
    basis: Mapped[str] = mapped_column(String(32), default="customs_value")
    # Stacking: if another component with this code is present, this one is dropped.
    excluded_by: Mapped[str] = mapped_column(String(80), default="")
    # When set, the combined rate of all components is capped at this figure.
    combined_cap_percent: Mapped[Decimal | None] = mapped_column(DecimalText, nullable=True)
    authority: Mapped[str] = mapped_column(String(160), default="")
    note: Mapped[str] = mapped_column(String(255), default="")

    table: Mapped[TariffTable] = relationship(back_populates="lines")


class ExchangeRate(Base):
    """A dated currency rate. A quote locks one and stores its identifier."""

    __tablename__ = "exchange_rates"
    __table_args__ = (UniqueConstraint("base_currency", "quote_currency", "as_of_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    base_currency: Mapped[str] = mapped_column(String(3), index=True)
    quote_currency: Mapped[str] = mapped_column(String(3), index=True)
    rate: Mapped[Decimal] = mapped_column(DecimalText)
    as_of_date: Mapped[dt.date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(120), default="Demo treasury feed")


class FreightRate(Base):
    """Freight cost table, owned by the logistics team, not guessed."""

    __tablename__ = "freight_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    origin_country: Mapped[str] = mapped_column(String(2), index=True)
    destination_country: Mapped[str] = mapped_column(String(2), index=True)
    mode: Mapped[str] = mapped_column(String(20))  # air | sea | courier
    minimum_charge: Mapped[Decimal] = mapped_column(DecimalText)
    price_per_kilogram: Mapped[Decimal] = mapped_column(DecimalText)
    handling_per_shipment: Mapped[Decimal] = mapped_column(DecimalText)
    insurance_percent: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0.35"))
    transit_days: Mapped[int] = mapped_column(Integer, default=7)
    currency: Mapped[str] = mapped_column(String(3), default="TWD")


# ---------------------------------------------------------------------------
# The request-for-quote case
# ---------------------------------------------------------------------------
class Case(Base, TimestampMixin):
    __tablename__ = "cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    reference: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(160), index=True)
    contact_name: Mapped[str] = mapped_column(String(120), default="")
    subject: Mapped[str] = mapped_column(String(255))
    # The language the customer wrote in; replies go back in the same one.
    language: Mapped[str] = mapped_column(String(10), default="en")
    status: Mapped[str] = mapped_column(String(32), default="received", index=True)
    owner_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    incoterm: Mapped[str] = mapped_column(String(8), default="FOB")
    named_place: Mapped[str] = mapped_column(String(60), default="Taichung")
    destination_country: Mapped[str] = mapped_column(String(2), default="TW")
    quote_currency: Mapped[str] = mapped_column(String(3), default="TWD")
    requested_delivery_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    closed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(20), default="")  # won | lost | ""
    outcome_reason: Mapped[str] = mapped_column(String(255), default="")

    customer: Mapped[Customer | None] = relationship()
    owner: Mapped[User | None] = relationship()
    messages: Mapped[list["CaseMessage"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseMessage.id"
    )
    quote_versions: Mapped[list["QuoteVersion"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="QuoteVersion.version_number"
    )
    events: Mapped[list["CaseEvent"]] = relationship(
        back_populates="case", cascade="all, delete-orphan", order_by="CaseEvent.id"
    )


class CaseMessage(Base):
    """An email in or out. The external identifier makes intake repeat-safe."""

    __tablename__ = "case_messages"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(10))  # inbound | outbound
    channel: Mapped[str] = mapped_column(String(20), default="email")
    external_message_id: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    sender: Mapped[str] = mapped_column(String(160))
    recipients: Mapped[list] = mapped_column(JSON, default=list)
    subject: Mapped[str] = mapped_column(String(255), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    language: Mapped[str] = mapped_column(String(10), default="en")
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    # Outbound email is never sent without a named approver.
    kind: Mapped[str] = mapped_column(String(40), default="customer")
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    case: Mapped[Case] = relationship(back_populates="messages")
    attachments: Mapped[list["CaseAttachment"]] = relationship(
        back_populates="message", cascade="all, delete-orphan"
    )


class CaseAttachment(Base):
    __tablename__ = "case_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    message_id: Mapped[int] = mapped_column(
        ForeignKey("case_messages.id", ondelete="CASCADE"), index=True
    )
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer, default=0)
    # How the file was read: spreadsheet_reader | pdf_text_reader | plain_text
    parsed_with: Mapped[str] = mapped_column(String(40), default="")
    parse_note: Mapped[str] = mapped_column(String(255), default="")
    extracted_rows: Mapped[list] = mapped_column(JSON, default=list)
    stored_path: Mapped[str] = mapped_column(String(400), default="")

    message: Mapped[CaseMessage] = relationship(back_populates="attachments")


class QuoteVersion(Base, TimestampMixin):
    __tablename__ = "quote_versions"
    __table_args__ = (UniqueConstraint("case_id", "version_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    # draft | awaiting_approval | approved | sent | superseded
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)

    currency: Mapped[str] = mapped_column(String(3), default="TWD")
    incoterm: Mapped[str] = mapped_column(String(8), default="FOB")
    named_place: Mapped[str] = mapped_column(String(60), default="Taichung")
    destination_country: Mapped[str] = mapped_column(String(2), default="TW")

    exchange_rate_id: Mapped[int | None] = mapped_column(
        ForeignKey("exchange_rates.id"), nullable=True
    )
    exchange_rate_locked_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    tariff_table_id: Mapped[int | None] = mapped_column(
        ForeignKey("tariff_tables.id"), nullable=True
    )
    valid_until: Mapped[dt.date | None] = mapped_column(Date, nullable=True)

    goods_total: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    freight_total: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    insurance_total: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    duty_total: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    grand_total: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    total_cost: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    margin_percent: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    requested_discount_percent: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    needs_repricing: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    repricing_reason: Mapped[str] = mapped_column(String(255), default="")
    change_log: Mapped[list] = mapped_column(JSON, default=list)
    totals_trace: Mapped[dict] = mapped_column(JSON, default=dict)
    # Set by the integrity check: every price on the quote came from the engine.
    pricing_checksum: Mapped[str] = mapped_column(String(64), default="")

    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_path: Mapped[str] = mapped_column(String(400), default="")
    document_format: Mapped[str] = mapped_column(String(10), default="")

    case: Mapped[Case] = relationship(back_populates="quote_versions")
    lines: Mapped[list["QuoteLine"]] = relationship(
        back_populates="quote_version", cascade="all, delete-orphan", order_by="QuoteLine.line_number"
    )
    exchange_rate: Mapped[ExchangeRate | None] = relationship()
    tariff_table: Mapped[TariffTable | None] = relationship()


class QuoteLine(Base):
    __tablename__ = "quote_lines"
    __table_args__ = (UniqueConstraint("quote_version_id", "line_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    quote_version_id: Mapped[int] = mapped_column(
        ForeignKey("quote_versions.id", ondelete="CASCADE"), index=True
    )
    line_number: Mapped[int] = mapped_column(Integer)

    # --- what the customer wrote -----------------------------------------
    #: The working text. Answers to questions are folded into it, so it grows.
    request_text: Mapped[str] = mapped_column(Text)
    #: Exactly what arrived, never edited. Comparing two versions of a request
    #: has to use this, or a line the customer clarified looks like a line the
    #: customer rewrote.
    original_request_text: Mapped[str] = mapped_column(Text, default="")
    customer_reference: Mapped[str] = mapped_column(String(80), default="")
    requested_quantity: Mapped[Decimal] = mapped_column(DecimalText)
    requested_unit: Mapped[str] = mapped_column(String(16), default="piece")
    requested_attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    #: Attributes settled by an answer from the customer. They override what
    #: the written line says, in whatever language the answer arrived in.
    resolved_attributes: Mapped[dict] = mapped_column(JSON, default=dict)
    source_reference: Mapped[str] = mapped_column(String(80), default="")  # e.g. "Sheet1!A14"

    # --- what the matcher decided ----------------------------------------
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True)
    # catalogue_number | cross_reference | attribute_match | text_similarity | manual | none
    match_method: Mapped[str] = mapped_column(String(32), default="none")
    match_confidence: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    match_reasons: Mapped[list] = mapped_column(JSON, default=list)
    attribute_check: Mapped[dict] = mapped_column(JSON, default=dict)
    alternatives: Mapped[list] = mapped_column(JSON, default=list)
    proposed_by: Mapped[str] = mapped_column(String(20), default="built-in")

    # matched | needs_clarification | awaiting_supplier | non_catalogue | priced | withdrawn
    status: Mapped[str] = mapped_column(String(32), default="matched", index=True)
    blocking_reason: Mapped[str] = mapped_column(String(255), default="")

    # --- what the pricing engine produced ---------------------------------
    quantity_billed: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    unit_of_sale: Mapped[str] = mapped_column(String(16), default="piece")
    rounding_note: Mapped[str] = mapped_column(String(255), default="")
    unit_price: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    # contract | volume_break | list | supplier_quote
    price_source: Mapped[str] = mapped_column(String(32), default="")
    price_source_reference: Mapped[str] = mapped_column(String(80), default="")
    discount_percent: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    extended_price: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    unit_cost: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    margin_percent: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    below_margin_floor: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    freight_share: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    insurance_share: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    duty_amount: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))
    duty_breakdown: Mapped[list] = mapped_column(JSON, default=list)
    landed_total: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    # --- how it will be supplied ------------------------------------------
    lead_time_days: Mapped[int] = mapped_column(Integer, default=0)
    fulfilment_options: Mapped[list] = mapped_column(JSON, default=list)
    chosen_fulfilment: Mapped[str] = mapped_column(String(40), default="")

    calculation_trace: Mapped[dict] = mapped_column(JSON, default=dict)

    quote_version: Mapped[QuoteVersion] = relationship(back_populates="lines")
    product: Mapped[Product | None] = relationship()


class Clarification(Base):
    """One open question. All open questions go out in one email, not one each."""

    __tablename__ = "clarifications"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    quote_line_id: Mapped[int | None] = mapped_column(
        ForeignKey("quote_lines.id", ondelete="SET NULL"), nullable=True
    )
    line_number: Mapped[int] = mapped_column(Integer, default=0)
    round_number: Mapped[int] = mapped_column(Integer, default=1, index=True)
    # missing_attribute | conflicting_specification | ambiguous_match | quantity_unit
    question_kind: Mapped[str] = mapped_column(String(40))
    #: Which attribute the question settles, so the answer can be applied.
    attribute: Mapped[str] = mapped_column(String(40), default="")
    question_en: Mapped[str] = mapped_column(Text)
    question_zh: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)  # open | answered
    asked_in_message_id: Mapped[int | None] = mapped_column(
        ForeignKey("case_messages.id", ondelete="SET NULL"), nullable=True
    )
    answer_text: Mapped[str] = mapped_column(Text, default="")
    answer_value: Mapped[dict] = mapped_column(JSON, default=dict)
    answered_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class SupplierRequest(Base):
    """A sub-request sent to a supplier for a part Hengtai does not stock."""

    __tablename__ = "supplier_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    supplier_id: Mapped[int] = mapped_column(ForeignKey("suppliers.id"), index=True)
    reference: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    line_numbers: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(20), default="sent", index=True)
    sent_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    responded_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    response: Mapped[dict] = mapped_column(JSON, default=dict)

    supplier: Mapped[Supplier] = relationship()


class Approval(Base):
    """A decision a named person has to make before anything leaves the building."""

    __tablename__ = "approvals"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    quote_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("quote_versions.id", ondelete="CASCADE"), nullable=True
    )
    rule_code: Mapped[str] = mapped_column(String(48), index=True)
    title: Mapped[str] = mapped_column(String(160))
    reason: Mapped[str] = mapped_column(Text)
    required_role: Mapped[str] = mapped_column(String(40))
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    requested_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    decided_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    decided_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_comment: Mapped[str] = mapped_column(Text, default="")

    decided_by: Mapped[User | None] = relationship()


class CaseEvent(Base):
    """The timeline. Every step, every tool call, every approval, with its cost."""

    __tablename__ = "case_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    case_id: Mapped[int] = mapped_column(ForeignKey("cases.id", ondelete="CASCADE"), index=True)
    occurred_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    actor_type: Mapped[str] = mapped_column(String(20))  # agent | person | system | customer | supplier
    actor_name: Mapped[str] = mapped_column(String(120), default="")
    kind: Mapped[str] = mapped_column(String(48), index=True)
    summary: Mapped[str] = mapped_column(String(400))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0)
    engine: Mapped[str] = mapped_column(String(20), default="")
    model: Mapped[str] = mapped_column(String(60), default="")
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd: Mapped[Decimal] = mapped_column(DecimalText, default=Decimal("0"))

    case: Mapped[Case] = relationship(back_populates="events")


class AuditEntry(Base):
    """Who changed what. Separate from the timeline, which is the story."""

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
    """A recorded run of the acceptance criteria."""

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
