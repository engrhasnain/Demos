"""Builds the accounts payable side of Hengtai Industrial Supply.

Two legal entities, 140 suppliers, the orders they are working against and the
deliveries that have actually arrived. Everything from a fixed seed, so two
people see the same ledger, including the same awkward records: a supplier
whose name is spelt differently on the invoice than in the master file, orders
only partly delivered, and a month that has already been closed.
"""

from __future__ import annotations

import datetime as dt
import logging
import random
import time
from decimal import Decimal
from typing import Any, Callable

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..clock import today
from ..domain.taxid import generate_unified_business_number
from ..models import (
    AccountingPeriod,
    Approval,
    AuditEntry,
    CallBackTask,
    Document,
    Entity,
    EvaluationRun,
    ExchangeRate,
    Exception_,
    GoodsReceipt,
    GoodsReceiptLine,
    Invoice,
    InvoiceEvent,
    InvoiceLine,
    LedgerBill,
    Posting,
    PurchaseOrder,
    PurchaseOrderLine,
    User,
    Vendor,
    VendorBankAccount,
)
from ..money import money
from ..security import hash_password

log = logging.getLogger("ledgerflow")

SEED = 20_261_006
DEMO_PASSWORD = "demo1234"
TODAY = today()

#: How long the heavier stages of a rebuild may run before this gives up on
#: them for this request. Entities, periods and the demo sign-in accounts
#: always finish first and are never subject to this budget, so a slow cold
#: start still leaves somebody able to sign in - it just means the suppliers,
#: orders and deliveries did not finish loading and a retry (or the next
#: call) picks up where this one gave up, rather than the request crashing
#: or running into the platform's own hard timeout.
DEFAULT_SEED_TIME_BUDGET_SECONDS = 22.0

DEMO_USERS: list[dict[str, str]] = [
    {"email": "mei.kuo@hengtai-industrial.example", "full_name": "Mei Kuo",
     "role": "clerk", "language": "zh"},
    {"email": "james.oliveira@hengtai-industrial.example", "full_name": "James Oliveira",
     "role": "clerk", "language": "en"},
    {"email": "sophie.tan@hengtai-industrial.example", "full_name": "Sophie Tan",
     "role": "accountant", "language": "en"},
    {"email": "ravi.menon@hengtai-industrial.example", "full_name": "Ravi Menon",
     "role": "controller", "language": "en"},
    {"email": "clare.whitfield@hengtai-industrial.example", "full_name": "Clare Whitfield",
     "role": "finance_director", "language": "en"},
    {"email": "admin@hengtai-industrial.example", "full_name": "System administrator",
     "role": "administrator", "language": "en"},
]

VENDOR_NAMES = [
    "Chang Hsing Fastener", "Yung Li Precision", "Ta Chen Metal", "Hong Ji Industrial",
    "Sheng Yu Screw", "Fu Shan Bearing", "Kai Hong Pneumatics", "Ming Tai Steel",
    "Jin Cheng Fastener", "Da Wei Industrial", "Shun Feng Components",
    "Tian Yuan Precision", "Bao Cheng Metal Works", "Hua An Fastener",
    "Zhong Xin Bearing", "Lian Fa Industrial", "Guang Ming Screw",
    "Pacific Rim Logistics", "Harbour Freight Forwarding", "Cascade Packaging",
]
SUFFIXES = ["Co., Ltd.", "Corporation", "Industrial Co.", "Enterprise Co., Ltd."]
CITIES = {
    "TW": ["Taichung", "Tainan", "Kaohsiung", "Changhua", "Taoyuan"],
    "US": ["Cleveland", "Rockford", "Houston", "Ontario"],
    "CN": ["Ningbo", "Dongguan", "Wenzhou"],
    "JP": ["Osaka", "Nagoya"],
    "DE": ["Solingen", "Hagen"],
}

PARTS = [
    ("HT-SHC-M8X030-12.9-ZNB", "Socket head cap screw ISO 4762 M8x30 class 12.9, zinc plated", 4),
    ("HT-SHC-M10X040-8.8-PLN", "Socket head cap screw ISO 4762 M10x40 class 8.8, plain", 6),
    ("HT-HXB-M12X060-8.8-HDG", "Hexagon head bolt ISO 4017 M12x60 class 8.8, galvanised", 9),
    ("HT-HXN-M12-10-ZNB", "Hexagon nut ISO 4032 M12 class 10, zinc plated", 2),
    ("HT-WSH-M12-200HV-ZNB", "Flat washer ISO 7089 M12 200 HV, zinc plated", 1),
    ("HT-BRG-6204-2RS-C3", "Deep groove ball bearing 6204-2RS C3", 95),
    ("HT-BRG-6206-2RS-CN", "Deep groove ball bearing 6206-2RS", 140),
    ("HT-CYL-032-0100-DA", "Pneumatic cylinder ISO 15552 bore 32 stroke 100", 1850),
    ("HT-VLV-5201-025", "Solenoid valve 5/2 single G1/4 24V", 1420),
    ("HT-SHC-M6X020-12.9-PLN", "Socket head cap screw ISO 4762 M6x20 class 12.9, plain", 3),
    ("HT-HXB-M16X080-10.9-ZNY", "Hexagon head bolt ISO 4017 M16x80 class 10.9, yellow zinc", 18),
    ("HT-STD-M10X1000-8.8-ZNB", "Threaded stud DIN 976 M10 x 1000, zinc plated", 46),
]

STAGES: list[tuple[str, str]] = [
    ("entities", "Opening the two companies and their ledgers"),
    ("periods", "Opening the accounting months"),
    ("users", "Creating the accounts payable team"),
    ("vendors", "Loading 140 suppliers and their bank details"),
    ("orders", "Loading purchase orders"),
    ("receipts", "Recording what has actually been delivered"),
    ("rates", "Loading exchange rates"),
]

ProgressCallback = Callable[[str, int, int], None]


class DemoDataBuilder:
    def __init__(
        self,
        session: Session,
        *,
        vendor_target: int = 140,
        order_target: int = 220,
        progress: ProgressCallback | None = None,
        time_budget_seconds: float | None = DEFAULT_SEED_TIME_BUDGET_SECONDS,
    ) -> None:
        self.session = session
        self.random = random.Random(SEED)
        self.vendor_target = vendor_target
        self.order_target = order_target
        self.progress = progress or (lambda *_: None)
        self.counts: dict[str, int] = {}
        #: None disables the budget outright (tests build a known-small
        #: dataset and want it to run to completion every time).
        self.time_budget_seconds = time_budget_seconds
        self._deadline: float | None = None

    # -- helpers ----------------------------------------------------------
    def _bulk(self, model: type, rows: list[dict[str, Any]], chunk: int = 2_000) -> None:
        for start in range(0, len(rows), chunk):
            self.session.bulk_insert_mappings(model, rows[start : start + chunk])
        self.session.flush()

    def _within_budget(self, about_to: str) -> bool:
        """Is there still time for the next stage?

        Checked only between stages, never inside one: a stage either runs to
        completion or does not start, so nothing is left half-written.
        """
        if self._deadline is None:
            return True
        remaining = self._deadline - time.monotonic()
        if remaining <= 0:
            log.warning(
                "Demo data seed ran past its %.0fs time budget before %s. "
                "Stopping here - the demo accounts and whatever loaded already "
                "stand, and the request returns instead of risking the "
                "platform's own hard timeout.",
                self.time_budget_seconds,
                about_to,
            )
            return False
        return True

    def build(self) -> dict[str, int]:
        self._deadline = (
            time.monotonic() + self.time_budget_seconds
            if self.time_budget_seconds is not None
            else None
        )
        self.wipe()
        self.build_entities()
        self.build_periods()
        # Sign-in accounts first, always: everything after this point is
        # business data a person can look at once signed in, not data a
        # person needs in order to sign in at all.
        self.build_users()
        if not self._within_budget("loading the suppliers"):
            self.session.flush()
            return self.counts
        vendors = self.build_vendors()
        if not self._within_budget("loading purchase orders and deliveries"):
            self.session.flush()
            return self.counts
        self.build_orders_and_receipts(vendors)
        if not self._within_budget("loading exchange rates"):
            self.session.flush()
            return self.counts
        self.build_rates()
        self.session.flush()
        return self.counts

    def wipe(self) -> None:
        for model in (
            EvaluationRun, AuditEntry, Approval, Exception_, CallBackTask, Posting,
            LedgerBill, InvoiceEvent, InvoiceLine, Invoice, Document,
            GoodsReceiptLine, GoodsReceipt, PurchaseOrderLine, PurchaseOrder,
            VendorBankAccount, Vendor, ExchangeRate, AccountingPeriod, Entity, User,
        ):
            self.session.execute(delete(model))
        self.session.flush()

    # -- the two companies --------------------------------------------------
    def build_entities(self) -> None:
        self.progress("entities", 0, 2)
        self.session.add_all(
            [
                Entity(
                    code="TW",
                    name="Hengtai Industrial Supply Co., Ltd.",
                    country="TW",
                    currency="TWD",
                    tax_identifier=generate_unified_business_number(8_812_440, on_date=TODAY),
                    tax_identifier_kind="taiwan_unified_business_number",
                    ledger="taiwan_ledger",
                ),
                Entity(
                    code="US",
                    name="Hengtai Industrial Supply USA, Inc.",
                    country="US",
                    currency="USD",
                    tax_identifier="88-2104773",
                    tax_identifier_kind="united_states_employer_identification_number",
                    ledger="united_states_ledger",
                ),
            ]
        )
        self.session.flush()
        self.counts["entities"] = 2
        self.progress("entities", 2, 2)

    def build_periods(self) -> None:
        """Eighteen months, with everything before August 2026 already closed."""
        rows: list[dict[str, Any]] = []
        for entity in ("TW", "US"):
            year, month = 2025, 7
            for _ in range(18):
                closed = (year, month) < (2026, 8)
                rows.append(
                    {
                        "entity_code": entity,
                        "year": year,
                        "month": month,
                        "is_open": not closed,
                        "closed_at": (
                            dt.datetime(year, month, 28, tzinfo=dt.timezone.utc)
                            if closed
                            else None
                        ),
                    }
                )
                month += 1
                if month > 12:
                    month, year = 1, year + 1
        self._bulk(AccountingPeriod, rows)
        self.counts["accounting_periods"] = len(rows)
        self.progress("periods", len(rows), len(rows))

    def build_users(self) -> None:
        password = hash_password(DEMO_PASSWORD)
        for person in DEMO_USERS:
            self.session.add(User(password_hash=password, **person))
        self.session.flush()
        self.counts["users"] = len(DEMO_USERS)
        self.progress("users", len(DEMO_USERS), len(DEMO_USERS))

    # -- suppliers ----------------------------------------------------------
    def build_vendors(self) -> list[Vendor]:
        # Interleaved rather than blocked, so a smaller demonstration set
        # still has suppliers in every country and currency.
        countries = (["TW"] * 13 + ["CN"] * 4 + ["US"] + ["JP"] + ["DE"])
        vendors: list[Vendor] = []
        accounts: list[VendorBankAccount] = []

        for index in range(self.vendor_target):
            country = countries[index % len(countries)]
            stem = VENDOR_NAMES[index % len(VENDOR_NAMES)]
            city = CITIES[country][index % len(CITIES[country])]
            name = (
                f"{stem} {SUFFIXES[index % len(SUFFIXES)]}"
                if index < len(VENDOR_NAMES)
                else f"{stem} ({city}) {SUFFIXES[index % len(SUFFIXES)]}"
            )
            entity = "US" if country == "US" else "TW"
            currency = {"TW": "TWD", "CN": "USD", "US": "USD", "JP": "JPY", "DE": "EUR"}[country]

            vendor = Vendor(
                code=f"SUP-{index + 1:04d}",
                name=name,
                # The name on the paperwork is rarely the name in the master file.
                name_on_invoices=(
                    name.replace(" Co., Ltd.", " CO LTD").replace(" Corporation", " CORP")
                    if index % 3 == 0
                    else name
                ),
                country=country,
                currency=currency,
                entity_code=entity,
                email=f"ar{index + 1}@supplier-{country.lower()}.example",
                telephone=(
                    f"+886 4 {self.random.randint(2000, 2999)} {self.random.randint(1000, 9999)}"
                    if country == "TW"
                    else f"+1 {self.random.randint(200, 989)} {self.random.randint(100, 999)} "
                    f"{self.random.randint(1000, 9999)}"
                ),
                tax_identifier=(
                    generate_unified_business_number(2_000_000 + index * 53, on_date=TODAY)
                    if country == "TW"
                    else f"{self.random.randint(10, 99)}-{self.random.randint(1000000, 9999999)}"
                ),
                tax_identifier_kind=(
                    "taiwan_unified_business_number"
                    if country == "TW"
                    else "united_states_employer_identification_number"
                ),
                payment_terms_days=self.random.choice([30, 45, 60]),
                tolerance_percent=Decimal(str(self.random.choice([1, 2, 2, 3, 5]))),
                tolerance_absolute=Decimal(str(self.random.choice([200, 500, 500, 1000]))),
                unordered_allowance=Decimal(
                    str(self.random.choice([0, 500, 1000, 1000, 2000]))
                ),
            )
            self.session.add(vendor)
            vendors.append(vendor)

            if index % 250 == 0:
                self.progress("vendors", index, self.vendor_target)

        self.session.flush()

        for vendor in vendors:
            accounts.append(
                VendorBankAccount(
                    vendor_id=vendor.id,
                    bank_name=(
                        "Mega International Commercial Bank"
                        if vendor.country == "TW"
                        else "First National Bank"
                    ),
                    account_number=f"{self.random.randint(10**11, 10**12 - 1)}",
                    account_name=vendor.name,
                    is_current=True,
                    verified_by="Sophie Tan, accountant",
                    verified_at=dt.datetime(2026, 1, 15, tzinfo=dt.timezone.utc),
                )
            )
        self.session.add_all(accounts)
        self.session.flush()

        self.counts["vendors"] = len(vendors)
        self.counts["bank_accounts"] = len(accounts)
        self.progress("vendors", self.vendor_target, self.vendor_target)
        return vendors

    # -- orders and deliveries ---------------------------------------------
    #: What a line on a purchase order is usually worth, in New Taiwan dollars.
    #: Buyers do not order a fixed count of everything: they order a few
    #: thousand screws or a dozen valves, and the two lines come out roughly
    #: the same size. Ordering by value rather than by count is what makes the
    #: generated ledger look like a real one, with many small invoices and a
    #: thin tail of large ones.
    LINE_VALUES: tuple[int, ...] = (
        2_500, 2_500, 3_200, 4_000, 4_000, 4_000, 5_000, 6_000, 6_000,
        8_000, 9_000, 9_000, 12_000, 12_000, 15_000, 18_000, 18_000,
        25_000, 25_000, 32_000, 40_000, 55_000, 75_000, 110_000, 240_000,
    )

    def _order_quantity(self, unit_price: float) -> Decimal:
        """A count that buys roughly one line's worth of this part."""
        target = self.random.choice(self.LINE_VALUES)
        count = max(1, round(target / max(unit_price, 0.01)))
        if count >= 1000:
            count = round(count / 500) * 500
        elif count >= 100:
            count = round(count / 50) * 50
        elif count >= 10:
            count = round(count / 5) * 5
        return Decimal(str(max(1, count)))

    def build_orders_and_receipts(self, vendors: list[Vendor]) -> None:
        order_rows: list[PurchaseOrder] = []
        line_rows: list[dict[str, Any]] = []

        for index in range(self.order_target):
            vendor = vendors[(index * 7 + 3) % len(vendors)]
            order = PurchaseOrder(
                number=f"PO-{26000 + index}",
                vendor_id=vendor.id,
                entity_code=vendor.entity_code,
                currency=vendor.currency,
                ordered_on=TODAY - dt.timedelta(days=self.random.randint(20, 120)),
                status="open",
            )
            self.session.add(order)
            order_rows.append(order)
            if index % 50 == 0:
                self.progress("orders", index, self.order_target)

        self.session.flush()

        for order in order_rows:
            line_count = self.random.choice([1, 1, 1, 2, 2, 2, 2, 3, 3, 4, 5])
            for line_number in range(1, line_count + 1):
                part_code, description, price = PARTS[
                    self.random.randrange(len(PARTS))
                ]
                line_rows.append(
                    {
                        "purchase_order_id": order.id,
                        "line_number": line_number,
                        "description": description,
                        "part_code": part_code,
                        "quantity_ordered": self._order_quantity(price),
                        "unit": "piece",
                        "unit_price": money(
                            Decimal(str(price))
                            * Decimal(str(self.random.choice([0.95, 1.0, 1.0, 1.05])))
                        ),
                    }
                )
        self._bulk(PurchaseOrderLine, line_rows)
        self.counts["purchase_orders"] = len(order_rows)
        self.counts["purchase_order_lines"] = len(line_rows)
        self.progress("orders", self.order_target, self.order_target)

        # --- the deliveries, which are often incomplete -------------------
        from sqlalchemy import select

        receipts = 0
        receipt_lines: list[dict[str, Any]] = []
        for order in order_rows:
            lines = list(
                self.session.scalars(
                    select(PurchaseOrderLine).where(
                        PurchaseOrderLine.purchase_order_id == order.id
                    )
                )
            )
            if not lines:
                continue
            # Most orders arrive in one or two deliveries; a few not at all.
            deliveries = self.random.choice([0, 1, 1, 1, 2, 2, 3])
            if deliveries == 0:
                continue
            for delivery in range(deliveries):
                receipt = GoodsReceipt(
                    number=f"GR-{order.number[3:]}-{delivery + 1}",
                    purchase_order_id=order.id,
                    received_on=order.ordered_on
                    + dt.timedelta(days=self.random.randint(7, 45)),
                    note="",
                )
                self.session.add(receipt)
                self.session.flush()
                receipts += 1
                for line in lines:
                    share = Decimal(
                        str(self.random.choice([0.3, 0.4, 0.5, 0.7, 1.0, 1.0]))
                    ) / Decimal(deliveries)
                    quantity = (line.quantity_ordered * share).quantize(Decimal("1"))
                    if quantity <= 0:
                        continue
                    receipt_lines.append(
                        {
                            "goods_receipt_id": receipt.id,
                            "purchase_order_line_id": line.id,
                            "quantity_received": quantity,
                        }
                    )
        self._bulk(GoodsReceiptLine, receipt_lines)
        self.counts["goods_receipts"] = receipts
        self.counts["goods_receipt_lines"] = len(receipt_lines)
        self.progress("receipts", receipts, receipts)

    # -- currency -----------------------------------------------------------
    def build_rates(self) -> None:
        rows: list[dict[str, Any]] = []
        usd_to_twd = Decimal("31.50")
        for week in range(60):
            as_of = TODAY - dt.timedelta(days=7 * week)
            drift = Decimal(str(round(self.random.uniform(-0.35, 0.35), 4)))
            rate = usd_to_twd + drift
            rows.append(
                {
                    "base_currency": "USD",
                    "quote_currency": "TWD",
                    "rate": rate.quantize(Decimal("0.0001")),
                    "as_of_date": as_of,
                    "source": "Demo treasury feed",
                }
            )
            rows.append(
                {
                    "base_currency": "TWD",
                    "quote_currency": "USD",
                    "rate": (Decimal("1") / rate).quantize(Decimal("0.000001")),
                    "as_of_date": as_of,
                    "source": "Demo treasury feed",
                }
            )
            rows.append(
                {
                    "base_currency": "EUR",
                    "quote_currency": "TWD",
                    "rate": (rate * Decimal("1.08")).quantize(Decimal("0.0001")),
                    "as_of_date": as_of,
                    "source": "Demo treasury feed",
                }
            )
            rows.append(
                {
                    "base_currency": "JPY",
                    "quote_currency": "TWD",
                    "rate": (rate / Decimal("150")).quantize(Decimal("0.000001")),
                    "as_of_date": as_of,
                    "source": "Demo treasury feed",
                }
            )
        self._bulk(ExchangeRate, rows)
        self.counts["exchange_rates"] = len(rows)
        self.progress("rates", len(rows), len(rows))


def build_demo_data(
    session: Session,
    *,
    vendor_target: int = 140,
    order_target: int = 220,
    progress: ProgressCallback | None = None,
    time_budget_seconds: float | None = DEFAULT_SEED_TIME_BUDGET_SECONDS,
) -> dict[str, int]:
    return DemoDataBuilder(
        session,
        vendor_target=vendor_target,
        order_target=order_target,
        progress=progress,
        time_budget_seconds=time_budget_seconds,
    ).build()
