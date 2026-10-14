"""Builds Hengtai Industrial Supply out of nothing.

Everything is generated from a fixed seed, so two people loading the demo see
the same catalogue, the same prices and the same awkward records. The data is
deliberately imperfect: duplicate supplier records, parts with no stock,
contracts that have run out, a part whose cost leaves no margin. A generator
that only produces tidy data produces a demonstration that only works on tidy
data.

Real reference points used here:

* ISO 15:2017 fixes deep groove ball bearing dimensions, so 6204 is
  20 x 47 x 14 mm from every maker and only the seal suffix differs
  (SKF ``2RS1``, FAG ``2RSR``, NSK ``DDU``, NTN ``LLU``, Timken ``2RS``).
* ISO 4762 / DIN 912 socket head cap screws, ISO 4017 / DIN 933 hexagon bolts,
  property classes 8.8 / 10.9 / 12.9 and stainless A2-70 / A4-80.
* United States commodity codes 7318.15.80 (threads 6 mm and over),
  7318.15.60 (under 6 mm), 7318.16.00 nuts, 7318.22.00 washers,
  8482.10.50 ball bearings, 8412.31.00 pneumatic cylinders, 8481.20.00 valves.
* The 2026 duty sequence for Taiwan goods entering the United States: the
  February reciprocal trade agreement, the April rebuild of the Section 232
  metals duty onto full customs value, and the Section 301 final action of
  24 July 2026 that caps the combined rate for Taiwan at 10 per cent.
"""

from __future__ import annotations

import datetime as dt
import random
from decimal import Decimal
from typing import Any, Callable, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..domain.partnumbers import (
    BEARING_GEOMETRY,
    BEARING_SUFFIX_BY_BRAND,
    COARSE_PITCH,
    FINISH_DISPLAY,
    THREAD_DIAMETER_MM,
    normalise_number,
)
from ..domain.taxid import generate_unified_business_number
from ..clock import today
from ..models import (
    Approval,
    AuditEntry,
    Case,
    CaseAttachment,
    CaseEvent,
    CaseMessage,
    Clarification,
    Contract,
    ContractLine,
    CrossReference,
    Customer,
    CustomerContact,
    EvaluationRun,
    ExchangeRate,
    FreightRate,
    PriceBreak,
    Product,
    QuoteLine,
    QuoteVersion,
    StockLevel,
    Supplier,
    SupplierRequest,
    TariffLine,
    TariffTable,
    User,
    Warehouse,
)
from ..money import money
from ..security import hash_password

SEED = 20261005
DEMO_PASSWORD = "demo1234"

#: Deliberately a date inside the 2026 duty timeline so every table version matters.
TODAY = today()
#: The calendar year the generated agreements and duty tables sit in, so
#: they stay in force however long after this was written it is run.
YEAR_START = dt.date(TODAY.year, 1, 1)
YEAR_END = dt.date(TODAY.year, 12, 31)


# ---------------------------------------------------------------------------
# People who use the product
# ---------------------------------------------------------------------------
#: Used so a repeated supplier name reads like a real second branch.
CITIES_BY_COUNTRY: dict[str, list[str]] = {
    "TW": ["Taichung", "Tainan", "Kaohsiung", "Changhua", "Taoyuan", "Hsinchu"],
    "CN": ["Ningbo", "Dongguan", "Wenzhou", "Suzhou", "Qingdao"],
    "JP": ["Osaka", "Nagoya", "Yokohama"],
    "DE": ["Solingen", "Hagen", "Schwabach"],
    "US": ["Cleveland", "Rockford", "Houston"],
}

DEMO_USERS: list[dict[str, str]] = [
    {
        "email": "amy.chen@hengtai-industrial.example",
        "full_name": "Amy Chen",
        "role": "sales_engineer",
        "language": "zh",
    },
    {
        "email": "wei.lin@hengtai-industrial.example",
        "full_name": "Wei Lin",
        "role": "sales_engineer",
        "language": "zh",
    },
    {
        "email": "david.hsu@hengtai-industrial.example",
        "full_name": "David Hsu",
        "role": "sales_manager",
        "language": "en",
    },
    {
        "email": "grace.wang@hengtai-industrial.example",
        "full_name": "Grace Wang",
        "role": "director",
        "language": "en",
    },
    {
        "email": "paul.lee@hengtai-industrial.example",
        "full_name": "Paul Lee",
        "role": "pricing_owner",
        "language": "en",
    },
    {
        "email": "admin@hengtai-industrial.example",
        "full_name": "System administrator",
        "role": "administrator",
        "language": "en",
    },
]


# ---------------------------------------------------------------------------
# Catalogue shape
# ---------------------------------------------------------------------------
FASTENER_KINDS: list[dict[str, Any]] = [
    {
        "kind": "socket_head_cap_screw",
        "code": "SHC",
        "standard": "ISO 4762",
        "legacy": "DIN 912",
        "name_en": "Socket head cap screw",
        "name_zh": "內六角圓柱頭螺絲",
        "has_length": True,
        "share": 0.34,
    },
    {
        "kind": "hex_head_bolt",
        "code": "HXB",
        "standard": "ISO 4017",
        "legacy": "DIN 933",
        "name_en": "Hexagon head bolt, fully threaded",
        "name_zh": "六角頭全牙螺栓",
        "has_length": True,
        "share": 0.24,
    },
    {
        "kind": "button_head_screw",
        "code": "BHS",
        "standard": "ISO 7380",
        "legacy": "ISO 7380",
        "name_en": "Button head socket screw",
        "name_zh": "內六角圓頂頭螺絲",
        "has_length": True,
        "share": 0.10,
    },
    {
        "kind": "countersunk_socket_screw",
        "code": "CSK",
        "standard": "ISO 10642",
        "legacy": "DIN 7991",
        "name_en": "Countersunk socket screw",
        "name_zh": "內六角平頭螺絲",
        "has_length": True,
        "share": 0.10,
    },
    {
        "kind": "hex_head_bolt_partial",
        "code": "HXP",
        "standard": "ISO 4014",
        "legacy": "DIN 931",
        "name_en": "Hexagon head bolt, partially threaded",
        "name_zh": "六角頭半牙螺栓",
        "has_length": True,
        "share": 0.18,
    },
    {
        "kind": "socket_set_screw",
        "code": "SSS",
        "standard": "ISO 4026",
        "legacy": "DIN 913",
        "name_en": "Socket set screw, flat point",
        "name_zh": "內六角無頭止付螺絲",
        "has_length": True,
        "share": 0.08,
    },
    {
        "kind": "threaded_stud",
        "code": "STD",
        "standard": "DIN 976",
        "legacy": "DIN 975",
        "name_en": "Threaded stud",
        "name_zh": "全牙柱",
        "has_length": True,
        "share": 0.07,
    },
    {
        "kind": "hex_nut",
        "code": "HXN",
        "standard": "ISO 4032",
        "legacy": "DIN 934",
        "name_en": "Hexagon nut",
        "name_zh": "六角螺帽",
        "has_length": False,
        "share": 0.12,
    },
    {
        "kind": "prevailing_torque_nut",
        "code": "NYL",
        "standard": "ISO 7040",
        "legacy": "DIN 985",
        "name_en": "Prevailing torque nut with a nylon insert",
        "name_zh": "尼龍防鬆螺帽",
        "has_length": False,
        "share": 0.06,
    },
    {
        "kind": "flat_washer",
        "code": "WSH",
        "standard": "ISO 7089",
        "legacy": "DIN 125",
        "name_en": "Flat washer",
        "name_zh": "平墊圈",
        "has_length": False,
        "share": 0.10,
    },
    {
        "kind": "spring_washer",
        "code": "SPW",
        "standard": "DIN 127",
        "legacy": "DIN 127B",
        "name_en": "Spring lock washer, type B",
        "name_zh": "彈簧墊圈",
        "has_length": False,
        "share": 0.05,
    },
]

THREADS = [
    "M3", "M4", "M5", "M6", "M8", "M10", "M12", "M14", "M16", "M18", "M20",
    "M22", "M24", "M27", "M30",
]
LENGTHS_BY_THREAD: dict[str, list[int]] = {
    "M3": [6, 8, 10, 12, 16, 20, 25, 30],
    "M4": [6, 8, 10, 12, 16, 20, 25, 30, 35, 40],
    "M5": [8, 10, 12, 16, 20, 25, 30, 35, 40, 50],
    "M6": [8, 10, 12, 16, 20, 25, 30, 35, 40, 50, 60],
    "M8": [10, 12, 16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80],
    "M10": [16, 20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100],
    "M12": [20, 25, 30, 35, 40, 45, 50, 60, 70, 80, 90, 100, 110],
    "M14": [25, 30, 35, 40, 50, 60, 70, 80, 90, 100],
    "M16": [25, 30, 35, 40, 50, 60, 70, 80, 90, 100, 120],
    "M18": [30, 40, 50, 60, 70, 80, 90, 100],
    "M20": [30, 40, 50, 60, 70, 80, 90, 100, 120, 140],
    "M22": [40, 50, 60, 70, 80, 90, 100],
    "M24": [40, 50, 60, 70, 80, 90, 100, 120, 150],
    "M27": [50, 60, 70, 80, 90, 100, 120, 150],
    "M30": [60, 70, 80, 90, 100, 120, 150, 180],
}

#: The least a volume price may be above standard cost. Hengtai does not sell
#: at a loss just because somebody ordered a lot of them.
MINIMUM_MARKUP = Decimal("1.14")

STEEL_CLASSES = ["8.8", "10.9", "12.9"]      # bolts and screws, ISO 898-1
NUT_CLASSES = ["6", "8", "10", "12"]          # nuts, ISO 898-2
WASHER_CLASSES = ["200HV", "300HV"]           # washers, ISO 7089 hardness
STAINLESS_CLASSES = ["A2-70", "A4-80"]
STEEL_FINISHES = ["plain", "zinc_blue", "zinc_yellow", "hot_dip_galvanised", "black_oxide"]

FINISH_CODE = {
    "plain": "PLN",
    "zinc_blue": "ZNB",
    "zinc_yellow": "ZNY",
    "hot_dip_galvanised": "HDG",
    "black_oxide": "BLK",
    "stainless_plain": "SST",
}

BEARING_SEALS = [
    ("open", "open, no seal", "開放型"),
    ("shielded_both", "shielded both sides", "雙面防塵蓋"),
    ("sealed_both", "sealed both sides", "雙面密封"),
]
BEARING_CLEARANCE = ["CN", "C3"]

PNEUMATIC_BORES = [20, 25, 32, 40, 50, 63, 80, 100]
PNEUMATIC_STROKES = [25, 50, 75, 100, 125, 160, 200, 250, 320, 400]

COMMODITY_CODES = {
    "hex_nut": "7318.16.00",
    "prevailing_torque_nut": "7318.16.00",
    "flat_washer": "7318.22.00",
    "spring_washer": "7318.21.00",
    "bearing": "8482.10.50",
    "iso_15552_cylinder": "8412.31.00",
    "compact_cylinder": "8412.31.00",
    "solenoid_valve": "8481.20.00",
    "push_in_fitting": "8481.80.90",
}


def commodity_code_for_fastener(thread: str) -> str:
    diameter = THREAD_DIAMETER_MM.get(thread, 6)
    return "7318.15.80" if diameter >= 6 else "7318.15.60"


# ---------------------------------------------------------------------------
# Progress reporting, so the loading screen can say what is happening
# ---------------------------------------------------------------------------
ProgressCallback = Callable[[str, int, int], None]


def _noop(_stage: str, _done: int, _total: int) -> None:
    return None


STAGES: list[tuple[str, str]] = [
    ("warehouses", "Opening the two warehouses"),
    ("users", "Creating the sales team"),
    ("suppliers", "Loading 140 suppliers"),
    ("catalogue", "Building the catalogue of 18,000 parts"),
    ("stock", "Counting stock in Taichung and Ontario"),
    ("prices", "Setting list prices and volume breaks"),
    ("cross_references", "Loading competitor and standard part numbers"),
    ("customers", "Loading 1,200 business customers"),
    ("contracts", "Loading customer contracts, including expired ones"),
    ("tariffs", "Loading the dated duty tables for 2026"),
    ("rates", "Loading exchange rates and freight rates"),
    ("samples", "Preparing the sample requests for quotation"),
    ("Filling the inbox with worked cases", "Working two dozen requests through the agent"),
]


# ---------------------------------------------------------------------------
# The generator
# ---------------------------------------------------------------------------
class DemoDataBuilder:
    def __init__(
        self,
        session: Session,
        *,
        product_target: int = 18_000,
        customer_target: int = 1_200,
        supplier_target: int = 140,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.session = session
        self.random = random.Random(SEED)
        self.product_target = product_target
        self.customer_target = customer_target
        self.supplier_target = supplier_target
        self.progress = progress or _noop
        self.counts: dict[str, int] = {}

    # -- helpers ----------------------------------------------------------
    def _bulk(self, model: type, rows: list[dict[str, Any]], chunk: int = 2_000) -> None:
        for start in range(0, len(rows), chunk):
            self.session.bulk_insert_mappings(model, rows[start : start + chunk])
        self.session.flush()

    def _price_from_weight(self, grams: Decimal, premium: Decimal) -> Decimal:
        base = Decimal("1.60") + grams * Decimal("0.085")
        return money(base * premium)

    # -- stages -----------------------------------------------------------
    def build(self) -> dict[str, int]:
        # Deliberate order, and not just a convenient one: on a slow cold
        # start (a function that pays for the Python runtime, the import of
        # SQLAlchemy and Pydantic, and only then this), the sign-in accounts
        # have to exist before anything that can run long or fail. Warehouses
        # and users are cheap and go first; the 18,000 part catalogue, stock,
        # cross-references, customers, contracts and duty tables are the
        # heavier business data and go after. If this build is ever cut short
        # by the caller's own time budget (see system.load_demo_data), sign-in
        # already works even though the rest of the demonstration is thin.
        self.wipe()
        self.build_warehouses()
        self.build_users()
        supplier_ids = self.build_suppliers()
        products = self.build_catalogue(supplier_ids)
        self.build_stock_and_prices(products)
        self.build_cross_references(products)
        customers = self.build_customers()
        self.build_contracts(customers, products)
        self.build_tariff_tables()
        self.build_rates()
        self.session.flush()
        return self.counts

    def wipe(self) -> None:
        """Clear everything the loader owns, in dependency order."""
        for model in (
            EvaluationRun, AuditEntry, Approval, Clarification, SupplierRequest,
            CaseEvent, CaseAttachment, CaseMessage, QuoteLine, QuoteVersion, Case,
            ContractLine, Contract, CrossReference, PriceBreak, StockLevel, Product,
            TariffLine, TariffTable, ExchangeRate, FreightRate,
            CustomerContact, Customer, Supplier, Warehouse, User,
        ):
            self.session.execute(delete(model))
        self.session.flush()

    # -- warehouses and people -------------------------------------------
    def build_warehouses(self) -> None:
        self.progress("warehouses", 0, 2)
        self.session.add_all(
            [
                Warehouse(
                    code="TAICHUNG", name="Taichung head office and main warehouse",
                    country="TW", legal_entity="Hengtai Industrial Supply Co., Ltd.",
                    city="Taichung",
                ),
                Warehouse(
                    code="ONTARIO", name="Ontario, California sales office and warehouse",
                    country="US", legal_entity="Hengtai Industrial Supply USA, Inc.",
                    city="Ontario",
                ),
            ]
        )
        self.session.flush()
        self.counts["warehouses"] = 2
        self.progress("warehouses", 2, 2)

    def build_users(self) -> None:
        self.progress("users", 0, len(DEMO_USERS))
        password = hash_password(DEMO_PASSWORD)
        for index, person in enumerate(DEMO_USERS, start=1):
            self.session.add(User(password_hash=password, **person))
            self.progress("users", index, len(DEMO_USERS))
        self.session.flush()
        self.counts["users"] = len(DEMO_USERS)

    # -- suppliers --------------------------------------------------------
    def build_suppliers(self) -> list[int]:
        names = [
            "Chang Hsing Fastener", "Yung Li Precision", "Ta Chen Metal", "Hong Ji Industrial",
            "Sheng Yu Screw", "Fu Shan Bearing", "Kai Hong Pneumatics", "Ming Tai Steel",
            "Jin Cheng Fastener", "Da Wei Industrial", "Shun Feng Components",
            "Tian Yuan Precision", "Bao Cheng Metal Works", "Hua An Fastener",
            "Zhong Xin Bearing", "Lian Fa Industrial", "Guang Ming Screw",
        ]
        suffixes = ["Co., Ltd.", "Corporation", "Industrial Co.", "Enterprise Co., Ltd."]
        countries = ["TW"] * 90 + ["CN"] * 28 + ["JP"] * 10 + ["DE"] * 8 + ["US"] * 4
        shutdowns = {
            "TW": {"name": "Lunar New Year", "start": "2027-02-05", "end": "2027-02-11",
                   "note": "Taiwan suppliers close about a week."},
            "CN": {"name": "Lunar New Year", "start": "2027-01-30", "end": "2027-02-20",
                   "note": "Mainland suppliers often close two to three weeks."},
            "JP": {"name": "Golden Week", "start": "2027-04-29", "end": "2027-05-05", "note": ""},
            "DE": {"name": "Werksferien", "start": "2027-07-26", "end": "2027-08-09", "note": ""},
            "US": {"name": "Thanksgiving", "start": "2026-11-26", "end": "2026-11-27", "note": ""},
        }

        rows: list[dict[str, Any]] = []
        for index in range(self.supplier_target):
            country = countries[index % len(countries)]
            city = CITIES_BY_COUNTRY[country][index % len(CITIES_BY_COUNTRY[country])]
            stem = names[index % len(names)]
            name = (
                f"{stem} {suffixes[index % len(suffixes)]}"
                if index < len(names)
                else f"{stem} ({city}) {suffixes[index % len(suffixes)]}"
            )
            lead = {"TW": 21, "CN": 35, "JP": 28, "DE": 45, "US": 14}[country]
            rows.append(
                {
                    "code": f"SUP-{index + 1:04d}",
                    "name": name,
                    "country": country,
                    "email": f"sales{index + 1}@supplier-{country.lower()}.example",
                    "currency": {"TW": "TWD", "CN": "USD", "JP": "JPY", "DE": "EUR", "US": "USD"}[country],
                    "lead_time_days": lead + self.random.randint(-5, 14),
                    "lead_time_variance_days": self.random.randint(2, 12),
                    "minimum_order_quantity": self.random.choice([1, 100, 500, 1000, 2000, 5000]),
                    "reliability_percent": Decimal(str(self.random.randint(78, 99))),
                    "annual_shutdown": shutdowns[country],
                }
            )

        # Two duplicate supplier records, because real master data has them.
        rows.append({**rows[0], "code": "SUP-0901", "name": rows[0]["name"].upper()})
        rows.append({**rows[3], "code": "SUP-0902", "name": rows[3]["name"].replace(",", "")})

        self.progress("suppliers", 0, len(rows))
        self._bulk(Supplier, rows)
        self.counts["suppliers"] = len(rows)
        self.progress("suppliers", len(rows), len(rows))
        return list(self.session.scalars(select(Supplier.id)))

    # -- catalogue --------------------------------------------------------
    def build_catalogue(self, supplier_ids: list[int]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        rows.extend(self._bearings(supplier_ids))
        rows.extend(self._pneumatics(supplier_ids))
        remaining = max(self.product_target - len(rows), 0)
        rows.extend(self._fasteners(supplier_ids, remaining))

        self.progress("catalogue", 0, len(rows))
        self._bulk(Product, rows)
        self.counts["products"] = len(rows)
        self.progress("catalogue", len(rows), len(rows))

        stored = self.session.execute(select(Product.id, Product.sku, Product.family)).all()
        by_sku = {sku: (identifier, family) for identifier, sku, family in stored}
        for row in rows:
            row["id"], _ = by_sku[row["sku"]]
        return rows

    def _fasteners(self, supplier_ids: list[int], target: int) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        combinations: list[tuple[dict[str, Any], str, int | None, str, str]] = []

        for definition in FASTENER_KINDS:
            # Nuts are graded 6, 8, 10 or 12 under ISO 898-2 and washers by
            # hardness under ISO 7089. Only bolts and screws carry 8.8 / 10.9 /
            # 12.9, so the catalogue is built that way rather than giving every
            # fastener a bolt class.
            if definition["kind"] in {"hex_nut", "prevailing_torque_nut"}:
                classes = NUT_CLASSES + STAINLESS_CLASSES
            elif definition["kind"] in {"flat_washer", "spring_washer"}:
                classes = WASHER_CLASSES + STAINLESS_CLASSES
            else:
                classes = STEEL_CLASSES + STAINLESS_CLASSES

            for thread in THREADS:
                lengths: Iterable[int | None] = (
                    LENGTHS_BY_THREAD[thread] if definition["has_length"] else [None]
                )
                for length in lengths:
                    for property_class in classes:
                        finishes = (
                            ["stainless_plain"]
                            if property_class in STAINLESS_CLASSES
                            else STEEL_FINISHES
                        )
                        for finish in finishes:
                            combinations.append((definition, thread, length, property_class, finish))

        self.random.shuffle(combinations)
        combinations.sort(key=lambda c: -c[0]["share"])
        combinations = combinations[:target]

        for definition, thread, length, property_class, finish in combinations:
            diameter = THREAD_DIAMETER_MM[thread]
            pitch = COARSE_PITCH[thread]
            if length is not None:
                grams = Decimal(str(round(0.0062 * diameter * diameter * (length + diameter * 0.8), 3)))
            else:
                grams = Decimal(str(round(0.0035 * diameter * diameter * diameter, 3)))

            stainless = property_class in STAINLESS_CLASSES
            premium = Decimal("1.0")
            premium *= {
                "8.8": Decimal("1.00"), "10.9": Decimal("1.22"), "12.9": Decimal("1.45"),
                "6": Decimal("0.92"), "8": Decimal("1.00"), "10": Decimal("1.18"),
                "12": Decimal("1.38"),
                "200HV": Decimal("1.00"), "300HV": Decimal("1.15"),
                "A2-70": Decimal("2.60"), "A4-80": Decimal("3.40"),
            }[property_class]
            premium *= {"plain": Decimal("1.00"), "zinc_blue": Decimal("1.08"),
                        "zinc_yellow": Decimal("1.10"), "hot_dip_galvanised": Decimal("1.30"),
                        "black_oxide": Decimal("1.06"), "stainless_plain": Decimal("1.00")}[finish]

            length_part = f"X{length:03d}" if length is not None else "XXXX"
            sku = f"HT-{definition['code']}-{thread}{length_part}-{property_class.replace('-', '')}-{FINISH_CODE[finish]}"
            size_words = f"{thread}x{length}" if length is not None else thread
            grade_words = (
                f"{property_class[:-2]} HV"
                if property_class.endswith("HV")
                else f"class {property_class}"
            )
            description_en = (
                f"{definition['name_en']} {definition['standard']} {size_words} "
                f"{grade_words}, {FINISH_DISPLAY[finish]}"
            )
            description_zh = f"{definition['name_zh']} {definition['standard']} {size_words} {property_class}"

            pack = 500 if diameter <= 6 else (200 if diameter <= 12 else 100)
            if definition["kind"] == "flat_washer":
                pack = 1000 if diameter <= 8 else 500

            list_price = self._price_from_weight(grams, premium)
            # Standard cost as a share of list price. A distributor runs at
            # roughly 35 to 50 per cent gross margin on list; the thin tail at
            # 0.74 and 0.78 is what the margin floor rule exists to catch once
            # a key account discount and a volume break are both applied.
            cost_share = Decimal(
                str(
                    self.random.choice(
                        [0.44, 0.46, 0.46, 0.48, 0.48, 0.50, 0.50, 0.52, 0.54, 0.58, 0.70, 0.74]
                    )
                )
            )
            cost = money(list_price * cost_share)

            stocked = self.random.random() > 0.18
            rows.append(
                {
                    "sku": sku,
                    "family": "fastener",
                    "description_en": description_en,
                    "description_zh": description_zh,
                    "standard": definition["standard"],
                    "attributes": {
                        "kind": definition["kind"],
                        "thread": thread,
                        "pitch_mm": pitch,
                        "length_mm": str(length) if length is not None else "",
                        "property_class": property_class,
                        "material": "stainless_steel" if stainless else "carbon_steel",
                        "finish": finish,
                        "legacy_standard": definition["legacy"],
                        "metal_content_percent": 100,
                    },
                    "search_text": " ".join(
                        [
                            description_en, description_zh, sku, definition["legacy"],
                            definition["standard"], thread, str(length or ""), property_class,
                            FINISH_DISPLAY[finish],
                        ]
                    ),
                    "selling_unit": "piece",
                    "pack_size": pack,
                    "weight_grams": grams,
                    "harmonised_tariff_code": COMMODITY_CODES.get(
                        definition["kind"], commodity_code_for_fastener(thread)
                    ),
                    "country_of_origin": "TW",
                    "list_price": list_price,
                    "standard_cost": cost,
                    "supplier_id": self.random.choice(supplier_ids),
                    "replenishment_lead_time_days": self.random.choice([21, 28, 35, 42, 56]),
                    "is_stocked": stocked,
                    "is_active": True,
                }
            )
        return rows

    def _bearings(self, supplier_ids: list[int]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for designation, (bore, outside, width) in BEARING_GEOMETRY.items():
            for seal_code, seal_en, seal_zh in BEARING_SEALS:
                for clearance in BEARING_CLEARANCE:
                    suffix = {"open": "", "shielded_both": "-2Z", "sealed_both": "-2RS"}[seal_code]
                    sku = f"HT-BRG-{designation}{suffix}-{clearance}"
                    grams = Decimal(str(round((outside * outside - bore * bore) * width * 0.0000062 * 1000, 2)))
                    premium = Decimal("1.0") + (Decimal("0.18") if seal_code != "open" else Decimal("0"))
                    list_price = money(
                        (Decimal("38") + Decimal(str(bore)) * Decimal("3.4")) * premium
                    )
                    rows.append(
                        {
                            "sku": sku,
                            "family": "bearing",
                            "description_en": (
                                f"Deep groove ball bearing {designation}{suffix} {clearance}, "
                                f"{bore} x {outside} x {width} mm, {seal_en}"
                            ),
                            "description_zh": f"深溝球軸承 {designation}{suffix} {clearance} {seal_zh}",
                            "standard": "ISO 15",
                            "attributes": {
                                "designation": designation,
                                "bore_mm": str(bore),
                                "outside_diameter_mm": str(outside),
                                "width_mm": str(width),
                                "seal": seal_code,
                                "clearance": clearance,
                                "metal_content_percent": 100,
                            },
                            "search_text": (
                                f"deep groove ball bearing {designation}{suffix} {clearance} "
                                f"{bore}x{outside}x{width} {seal_en} {sku} ISO 15"
                            ),
                            "selling_unit": "piece",
                            "pack_size": 1 if bore >= 25 else 10,
                            "weight_grams": grams,
                            "harmonised_tariff_code": COMMODITY_CODES["bearing"],
                            "country_of_origin": self.random.choice(["TW", "TW", "JP", "CN"]),
                            "list_price": list_price,
                            "standard_cost": money(list_price * Decimal("0.68")),
                            "supplier_id": self.random.choice(supplier_ids),
                            "replenishment_lead_time_days": self.random.choice([28, 35, 42]),
                            "is_stocked": self.random.random() > 0.15,
                            "is_active": True,
                        }
                    )
        return rows

    def _pneumatics(self, supplier_ids: list[int]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for bore in PNEUMATIC_BORES:
            for stroke in PNEUMATIC_STROKES:
                sku = f"HT-CYL-{bore:03d}-{stroke:04d}-DA"
                list_price = money(Decimal("820") + Decimal(str(bore)) * Decimal("22") + Decimal(str(stroke)) * Decimal("3.1"))
                rows.append(
                    {
                        "sku": sku,
                        "family": "pneumatic",
                        "description_en": (
                            f"Pneumatic cylinder to ISO 15552, bore {bore} mm, stroke "
                            f"{stroke} mm, double acting"
                        ),
                        "description_zh": f"ISO 15552 氣壓缸 缸徑 {bore} mm 行程 {stroke} mm 雙動",
                        "standard": "ISO 15552",
                        "attributes": {
                            "kind": "iso_15552_cylinder",
                            "bore_mm": str(bore),
                            "stroke_mm": str(stroke),
                            "action": "double_acting",
                            "port": "G1/8" if bore <= 25 else ("G1/4" if bore <= 50 else "G3/8"),
                            "metal_content_percent": 60,
                        },
                        "search_text": (
                            f"pneumatic cylinder iso 15552 bore {bore} stroke {stroke} "
                            f"double acting air cylinder {sku}"
                        ),
                        "selling_unit": "piece",
                        "pack_size": 1,
                        "weight_grams": Decimal(str(round(380 + bore * 24 + stroke * 1.6, 1))),
                        "harmonised_tariff_code": COMMODITY_CODES["iso_15552_cylinder"],
                        "country_of_origin": self.random.choice(["TW", "TW", "JP"]),
                        "list_price": list_price,
                        "standard_cost": money(list_price * Decimal("0.71")),
                        "supplier_id": self.random.choice(supplier_ids),
                        "replenishment_lead_time_days": self.random.choice([35, 42, 56]),
                        "is_stocked": self.random.random() > 0.30,
                        "is_active": True,
                    }
                )
        for bore in [20, 25, 32, 40]:
            sku = f"HT-VLV-5201-{bore:03d}"
            list_price = money(Decimal("1180") + Decimal(str(bore)) * Decimal("14"))
            rows.append(
                {
                    "sku": sku,
                    "family": "pneumatic",
                    "description_en": f"Solenoid valve 5/2 single, port G1/4, 24 V direct current, body {bore} mm",
                    "description_zh": f"電磁閥 5/2 單線圈 G1/4 24V 直流 本體 {bore} mm",
                    "standard": "",
                    "attributes": {
                        "kind": "solenoid_valve",
                        "bore_mm": str(bore),
                        "port": "G1/4",
                        "action": "single_acting",
                        "metal_content_percent": 45,
                    },
                    "search_text": f"solenoid valve 5/2 single G1/4 24V {sku}",
                    "selling_unit": "piece",
                    "pack_size": 1,
                    "weight_grams": Decimal("420"),
                    "harmonised_tariff_code": COMMODITY_CODES["solenoid_valve"],
                    "country_of_origin": "TW",
                    "list_price": list_price,
                    "standard_cost": money(list_price * Decimal("0.73")),
                    "supplier_id": self.random.choice(supplier_ids),
                    "replenishment_lead_time_days": 35,
                    "is_stocked": True,
                    "is_active": True,
                }
            )
        return rows

    # -- stock and prices -------------------------------------------------
    def build_stock_and_prices(self, products: list[dict[str, Any]]) -> None:
        stock_rows: list[dict[str, Any]] = []
        price_rows: list[dict[str, Any]] = []
        total = len(products)

        for index, product in enumerate(products):
            product_id = product["id"]
            if product["is_stocked"]:
                taichung = self.random.choice([0, 0, 120, 450, 900, 1800, 4200, 9000, 16000])
                ontario = self.random.choice([0, 0, 0, 80, 200, 600, 1400])
            else:
                taichung = ontario = 0
            stock_rows.append(
                {
                    "product_id": product_id,
                    "warehouse_code": "TAICHUNG",
                    "quantity_on_hand": taichung,
                    "quantity_allocated": int(taichung * self.random.random() * 0.2),
                }
            )
            stock_rows.append(
                {
                    "product_id": product_id,
                    "warehouse_code": "ONTARIO",
                    "quantity_on_hand": ontario,
                    "quantity_allocated": int(ontario * self.random.random() * 0.2),
                }
            )

            list_price = product["list_price"]
            cost = product["standard_cost"]
            floor_price = money(cost * MINIMUM_MARKUP)
            pack = product["pack_size"]
            for tier, tier_discount in (("standard", Decimal("1.00")),
                                        ("preferred", Decimal("0.94")),
                                        ("key_account", Decimal("0.88"))):
                for minimum, break_discount in (
                    (1, Decimal("1.00")),
                    (max(pack, 100), Decimal("0.93")),
                    (max(pack * 10, 1000), Decimal("0.86")),
                    (max(pack * 50, 5000), Decimal("0.79")),
                ):
                    price_rows.append(
                        {
                            "product_id": product_id,
                            "price_tier": tier,
                            "minimum_quantity": minimum,
                            "unit_price": max(
                                money(list_price * tier_discount * break_discount),
                                floor_price,
                            ),
                        }
                    )
            if index % 500 == 0:
                self.progress("stock", index, total)

        self.progress("stock", total, total)
        self._bulk(StockLevel, stock_rows)
        self.counts["stock_levels"] = len(stock_rows)
        self.progress("prices", 0, len(price_rows))
        self._bulk(PriceBreak, price_rows)
        self.counts["price_breaks"] = len(price_rows)
        self.progress("prices", len(price_rows), len(price_rows))

    # -- cross references -------------------------------------------------
    def build_cross_references(self, products: list[dict[str, Any]]) -> None:
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()

        def add(product_id: int, number: str, brand: str, equivalence: str, note: str) -> None:
            key = (normalise_number(number), brand)
            if not number or key in seen:
                return
            seen.add(key)
            rows.append(
                {
                    "product_id": product_id,
                    "external_number": number,
                    "normalised_number": normalise_number(number),
                    "brand": brand,
                    "equivalence": equivalence,
                    "note": note,
                    "verified_by": "Paul Lee, pricing owner",
                }
            )

        for product in products:
            attributes = product["attributes"]
            product_id = product["id"]

            if product["family"] == "bearing":
                designation = attributes["designation"]
                seal = attributes["seal"]
                clearance = attributes["clearance"]
                for brand, suffixes in BEARING_SUFFIX_BY_BRAND.items():
                    suffix = suffixes.get(seal, "")
                    number = f"{designation}{suffix}" + (f" {clearance}" if clearance != "CN" else "")
                    add(
                        product_id, number, brand, "interchange",
                        (
                            f"ISO 15 fixes {designation} at "
                            f"{attributes['bore_mm']} x {attributes['outside_diameter_mm']} x "
                            f"{attributes['width_mm']} mm, so only the seal suffix differs."
                        ),
                    )

            elif product["family"] == "fastener":
                legacy = attributes.get("legacy_standard", "")
                thread = attributes["thread"]
                length = attributes.get("length_mm", "")
                property_class = attributes["property_class"]
                size = f"{thread}x{length}" if length else thread
                if legacy:
                    add(
                        product_id, f"{legacy} {size} {property_class}", "Published standard",
                        "exact", f"{legacy} is the superseded name for {product['standard']}.",
                    )
                add(
                    product_id, f"{product['standard']} {size} {property_class}",
                    "Published standard", "exact", "",
                )
                # Two competitor numbering schemes, modelled on how distributors
                # build their own numbers from the same attributes.
                digits = abs(hash((product["sku"], "fastbolt"))) % 900000 + 100000
                add(product_id, f"FB-{digits}", "Fastbolt", "interchange",
                    "Competitor number held in the cross-reference table.")
                code = f"NW{thread[1:]}{length or '00'}{property_class.replace('.', '').replace('-', '')}"
                add(product_id, code, "Nordwerk", "interchange",
                    "Competitor number built from thread, length and strength class.")

            elif product["family"] == "pneumatic" and attributes.get("kind") == "iso_15552_cylinder":
                bore, stroke = attributes["bore_mm"], attributes["stroke_mm"]
                add(product_id, f"DSBC-{bore}-{stroke}-PPVA-N3", "Competitor A", "approximate",
                    "Mounting and cushioning differ; always confirm with the customer.")
                add(product_id, f"C96SB{bore}-{stroke}C", "Competitor B", "approximate",
                    "Equivalent bore and stroke to ISO 15552; port thread may differ.")

        self.progress("cross_references", 0, len(rows))
        self._bulk(CrossReference, rows)
        self.counts["cross_references"] = len(rows)
        self.progress("cross_references", len(rows), len(rows))

    # -- customers --------------------------------------------------------
    def build_customers(self) -> list[Customer]:
        first = ["Pacific", "Summit", "Great Lakes", "Cascade", "Atlas", "Northstar", "Redwood",
                 "Granite", "Blue Ridge", "Ironwood", "Harbour", "Meridian"]
        second = ["Motion", "Automation", "Machinery", "Hydraulics", "Industrial", "Assembly",
                  "Fabrication", "Engineering", "Conveyor", "Robotics"]
        third = ["Controls", "Systems", "Works", "Group", "Supply", "Solutions"]
        taiwanese = ["台中精機", "永진工業", "大億機械", "昌益自動化", "泰鋼工業", "宏遠精密",
                     "中興機械", "長榮氣動", "新光扣件", "三洋設備"]

        customers: list[Customer] = []
        contacts: list[CustomerContact] = []

        # The customer the demonstration is built around.
        anchor = Customer(
            code="CUS-00001",
            name="Pacific Motion Controls, Inc.",
            country="US",
            currency="USD",
            language="en",
            default_incoterm="DDP",
            default_named_place="Ontario, California",
            price_tier="key_account",
            margin_floor_percent=Decimal("18"),
            tax_identifier="94-3871205",
            tax_identifier_kind="united_states_employer_identification_number",
            payment_terms_days=45,
            credit_limit=Decimal("450000"),
        )
        customers.append(anchor)
        contacts.append(
            CustomerContact(
                customer=anchor, email="r.mendez@pacificmotion.example",
                full_name="Rosa Mendez", language="en",
            )
        )
        contacts.append(
            CustomerContact(
                customer=anchor, email="purchasing@pacificmotion.example",
                full_name="Pacific Motion purchasing desk", language="en",
            )
        )

        anchor_tw = Customer(
            code="CUS-00002",
            name="台中精機股份有限公司",
            country="TW",
            currency="TWD",
            language="zh",
            default_incoterm="EXW",
            default_named_place="Taichung",
            price_tier="preferred",
            margin_floor_percent=Decimal("16"),
            tax_identifier=generate_unified_business_number(4712033, on_date=TODAY),
            tax_identifier_kind="taiwan_unified_business_number",
            payment_terms_days=60,
            credit_limit=Decimal("8000000"),
        )
        customers.append(anchor_tw)
        contacts.append(
            CustomerContact(
                customer=anchor_tw, email="lin.yc@tcprecision.example",
                full_name="林佑成", language="zh",
            )
        )

        for index in range(3, self.customer_target + 1):
            is_taiwan = index % 5 in (0, 2)
            if is_taiwan:
                name = f"{taiwanese[index % len(taiwanese)]}{index // len(taiwanese) + 1:02d}"
                country, currency, language = "TW", "TWD", "zh"
                incoterm, place = "EXW", "Taichung"
                identifier = generate_unified_business_number(1000000 + index * 37, on_date=TODAY)
                identifier_kind = "taiwan_unified_business_number"
            else:
                name = (
                    f"{first[index % len(first)]} {second[(index // 3) % len(second)]} "
                    f"{third[(index // 7) % len(third)]}"
                )
                country, currency, language = "US", "USD", "en"
                incoterm, place = self.random.choice(
                    [("FOB", "Taichung"), ("DDP", "Ontario, California"), ("CIF", "Long Beach")]
                )
                identifier = f"{self.random.randint(10, 99)}-{self.random.randint(1000000, 9999999)}"
                identifier_kind = "united_states_employer_identification_number"

            customer = Customer(
                code=f"CUS-{index:05d}",
                name=name,
                country=country,
                currency=currency,
                language=language,
                default_incoterm=incoterm,
                default_named_place=place,
                price_tier=self.random.choice(
                    ["standard"] * 6 + ["preferred"] * 3 + ["key_account"]
                ),
                margin_floor_percent=Decimal(str(self.random.choice([15, 16, 18, 18, 20, 22]))),
                tax_identifier=identifier,
                tax_identifier_kind=identifier_kind,
                payment_terms_days=self.random.choice([30, 45, 60, 90]),
                credit_limit=Decimal(str(self.random.choice([200000, 800000, 2000000, 5000000]))),
                on_credit_hold=self.random.random() < 0.03,
            )
            customers.append(customer)
            slug = f"buyer{index}"
            domain = "tw-industrial.example" if is_taiwan else "us-industrial.example"
            contacts.append(
                CustomerContact(
                    customer=customer,
                    email=f"{slug}@{domain}",
                    full_name=("採購 " + str(index)) if is_taiwan else f"Buyer {index}",
                    language=language,
                )
            )
            if index % 250 == 0:
                self.progress("customers", index, self.customer_target)

        self.session.add_all(customers)
        self.session.add_all(contacts)
        self.session.flush()
        self.counts["customers"] = len(customers)
        self.counts["customer_contacts"] = len(contacts)
        self.progress("customers", self.customer_target, self.customer_target)
        return customers

    # -- contracts --------------------------------------------------------
    def build_contracts(self, customers: list[Customer], products: list[dict[str, Any]]) -> None:
        contracts: list[Contract] = []
        lines: list[dict[str, Any]] = []
        stocked = [p for p in products if p["is_stocked"]]

        def contract_lines_for(contract_id: int, chosen: list[dict[str, Any]]) -> None:
            for product in chosen:
                lines.append(
                    {
                        "contract_id": contract_id,
                        "product_id": product["id"],
                        "unit_price": max(
                            money(product["list_price"] * Decimal("0.82")),
                            money(product["standard_cost"] * MINIMUM_MARKUP),
                        ),
                        "minimum_quantity": self.random.choice([1, 100, 500]),
                    }
                )

        anchor = customers[0]
        live = Contract(
            code="C-10422", customer_id=anchor.id,
            valid_from=YEAR_START, valid_to=YEAR_END,
            note="Annual agreement covering 30 regularly ordered parts.",
        )
        expired = Contract(
            code="C-10311", customer_id=anchor.id,
            valid_from=YEAR_START - dt.timedelta(days=365),
            valid_to=TODAY - dt.timedelta(days=97),
            note="Previous agreement. Four parts were never moved onto C-10422.",
        )
        contracts += [live, expired]
        self.session.add_all(contracts)
        self.session.flush()

        anchor_products = self.random.sample(stocked, 34)
        contract_lines_for(live.id, anchor_products[:30])
        contract_lines_for(expired.id, anchor_products[30:34])

        for customer in customers[2:]:
            if self.random.random() > 0.38:
                continue
            start = YEAR_START
            end = (
                YEAR_END
                if self.random.random() > 0.22
                else TODAY - dt.timedelta(days=35)
            )
            contract = Contract(
                code=f"C-{20000 + customer.id}", customer_id=customer.id,
                valid_from=start, valid_to=end,
                note="Generated agreement." + (" Has already run out." if end < TODAY else ""),
            )
            self.session.add(contract)
            self.session.flush()
            contract_lines_for(contract.id, self.random.sample(stocked, self.random.randint(6, 25)))

        self.progress("contracts", 0, len(lines))
        self._bulk(ContractLine, lines)
        self.counts["contract_lines"] = len(lines)
        self.progress("contracts", len(lines), len(lines))

    # -- duty tables ------------------------------------------------------
    def build_tariff_tables(self) -> None:
        """Three dated versions that follow what actually happened in 2026.

        Every rate here is demonstration data. The product's own rule is that
        duty comes from a table a named person owns and a licensed customs
        broker signs off, and that rule is what the screens enforce.
        """
        steel_codes = [
            "7318.15.80", "7318.15.60", "7318.16.00", "7318.21.00", "7318.22.00",
        ]
        other_codes = {"8482.10.50": Decimal("9.0"), "8412.31.00": Decimal("0.0"),
                       "8481.20.00": Decimal("2.0"), "8481.80.90": Decimal("2.0")}
        most_favoured = {
            "7318.15.80": Decimal("8.5"), "7318.15.60": Decimal("6.2"),
            "7318.16.00": Decimal("0.0"), "7318.21.00": Decimal("5.8"),
            "7318.22.00": Decimal("0.0"),
            **other_codes,
        }

        versions = [
            {
                "version": "2026.02-reciprocal",
                "title": "United States and Taiwan reciprocal trade agreement, 15 per cent all in",
                "effective_from": dt.date(2026, 2, 15),
                "effective_to": dt.date(2026, 4, 1),
                "status": "superseded",
                "source_note": (
                    "Reciprocal trade agreement rate applied on top of the normal "
                    "trade relations rate, capped so the combined rate is 15 per cent."
                ),
                "combined_cap": Decimal("15"),
                "section_232": None,
                "section_301_cap": None,
            },
            {
                "version": "2026.04-section232",
                "title": "Section 232 metals duty rebuilt onto full customs value",
                "effective_from": dt.date(2026, 4, 2),
                "effective_to": dt.date(2026, 7, 23),
                "status": "superseded",
                "source_note": (
                    "From April 2026 the Section 232 metals duty on derivative steel "
                    "articles is charged on the full customs value rather than on the "
                    "metal content value."
                ),
                "combined_cap": None,
                "section_232": Decimal("25"),
                "section_301_cap": None,
            },
            {
                "version": "2026.07-section301",
                "title": "Section 301 final action, Taiwan combined rate capped at 10 per cent",
                "effective_from": dt.date(2026, 7, 24),
                "effective_to": None,
                "status": "active",
                "source_note": (
                    "Section 301 duty for Taiwan is set so the normal trade relations "
                    "rate plus the Section 301 rate reaches 10 per cent. Goods already "
                    "carrying a Section 232 metals duty are not stacked with it."
                ),
                "combined_cap": None,
                "section_232": Decimal("25"),
                "section_301_cap": Decimal("10"),
            },
        ]

        broker = "Chen and Partners Customs Brokers, licence 04218"
        for definition in versions:
            table = TariffTable(
                version=definition["version"],
                title=definition["title"],
                effective_from=definition["effective_from"],
                effective_to=definition["effective_to"],
                status=definition["status"],
                owned_by="Paul Lee, pricing owner",
                customs_broker=broker,
                broker_signed_off_at=dt.datetime(
                    definition["effective_from"].year,
                    definition["effective_from"].month,
                    definition["effective_from"].day,
                    9, 0, tzinfo=dt.timezone.utc,
                ),
                source_note=definition["source_note"],
            )
            self.session.add(table)
            self.session.flush()

            rows: list[dict[str, Any]] = []
            for code, rate in most_favoured.items():
                # Taiwan into the United States
                rows.append(
                    {
                        "tariff_table_id": table.id,
                        "harmonised_tariff_code": code,
                        "origin_country": "TW",
                        "destination_country": "US",
                        "component": "most_favoured_nation",
                        "rate_percent": rate,
                        "basis": "customs_value",
                        "authority": "Harmonized Tariff Schedule of the United States",
                        "note": "Normal trade relations rate.",
                    }
                )
                if definition["combined_cap"] is not None:
                    rows.append(
                        {
                            "tariff_table_id": table.id,
                            "harmonised_tariff_code": code,
                            "origin_country": "TW",
                            "destination_country": "US",
                            "component": "reciprocal",
                            "rate_percent": definition["combined_cap"],
                            "basis": "customs_value",
                            "combined_cap_percent": definition["combined_cap"],
                            "excluded_by": "section_232",
                            "authority": "United States and Taiwan Agreement on Reciprocal Trade",
                            "note": "Capped so the combined rate reaches 15 per cent.",
                        }
                    )
                if definition["section_232"] is not None and code in steel_codes:
                    rows.append(
                        {
                            "tariff_table_id": table.id,
                            "harmonised_tariff_code": code,
                            "origin_country": "TW",
                            "destination_country": "US",
                            "component": "section_232",
                            "rate_percent": definition["section_232"],
                            "basis": "customs_value",
                            "authority": "Section 232, derivative steel articles",
                            "note": (
                                "Charged on the full customs value from April 2026, not "
                                "on the metal content value."
                            ),
                        }
                    )
                if definition["section_301_cap"] is not None:
                    rows.append(
                        {
                            "tariff_table_id": table.id,
                            "harmonised_tariff_code": code,
                            "origin_country": "TW",
                            "destination_country": "US",
                            "component": "section_301",
                            "rate_percent": definition["section_301_cap"],
                            "basis": "customs_value",
                            "combined_cap_percent": definition["section_301_cap"],
                            "excluded_by": "section_232" if code in steel_codes else "",
                            "authority": "Section 301 final action, 24 July 2026",
                            "note": (
                                "Set so the normal trade relations rate plus this duty "
                                "reaches 10 per cent. Not stacked on goods already "
                                "carrying a Section 232 metals duty."
                            ),
                        }
                    )

                # Other origins, so a bearing made in Japan or China prices correctly.
                for origin, extra in (
                    ("JP", None), ("DE", None), ("US", None), ("CN", Decimal("25")),
                ):
                    rows.append(
                        {
                            "tariff_table_id": table.id,
                            "harmonised_tariff_code": code,
                            "origin_country": origin,
                            "destination_country": "US",
                            "component": "most_favoured_nation",
                            "rate_percent": rate,
                            "basis": "customs_value",
                            "authority": "Harmonized Tariff Schedule of the United States",
                            "note": "Normal trade relations rate.",
                        }
                    )
                    if extra is not None:
                        rows.append(
                            {
                                "tariff_table_id": table.id,
                                "harmonised_tariff_code": code,
                                "origin_country": origin,
                                "destination_country": "US",
                                "component": "section_301",
                                "rate_percent": extra,
                                "basis": "customs_value",
                                "authority": "Section 301, China",
                                "note": "China list duty.",
                            }
                        )

                # Domestic Taiwan movement: no import duty at all.
                for origin in ("TW", "CN", "JP", "DE", "US"):
                    rows.append(
                        {
                            "tariff_table_id": table.id,
                            "harmonised_tariff_code": code,
                            "origin_country": origin,
                            "destination_country": "TW",
                            "component": "most_favoured_nation",
                            "rate_percent": Decimal("0"),
                            "basis": "customs_value",
                            "authority": "Domestic movement",
                            "note": "Goods already inside Taiwan carry no import duty.",
                        }
                    )

            self._bulk(TariffLine, rows)

        # A fourth version, not yet active, so the demonstration can load it and
        # watch every open quote get flagged for re-pricing.
        draft = TariffTable(
            version="2026.10-revision",
            title="October 2026 revision, awaiting broker sign-off",
            effective_from=TODAY,
            effective_to=None,
            status="draft",
            owned_by="Paul Lee, pricing owner",
            customs_broker="",
            broker_signed_off_at=None,
            source_note=(
                "Draft revision raising the Section 232 metals duty on derivative "
                "steel articles from 25 to 50 per cent of the full customs value. "
                "Not signed off, so it cannot price a quote until the pricing owner "
                "activates it and a customs broker confirms the rates."
            ),
        )
        self.session.add(draft)
        self.session.flush()
        draft_rows: list[dict[str, Any]] = []
        for code, rate in most_favoured.items():
            draft_rows.append(
                {
                    "tariff_table_id": draft.id,
                    "harmonised_tariff_code": code,
                    "origin_country": "TW",
                    "destination_country": "US",
                    "component": "most_favoured_nation",
                    "rate_percent": rate,
                    "basis": "customs_value",
                    "authority": "Harmonized Tariff Schedule of the United States",
                    "note": "Normal trade relations rate.",
                }
            )
            if code in steel_codes:
                draft_rows.append(
                    {
                        "tariff_table_id": draft.id,
                        "harmonised_tariff_code": code,
                        "origin_country": "TW",
                        "destination_country": "US",
                        "component": "section_232",
                        "rate_percent": Decimal("50"),
                        "basis": "customs_value",
                        "authority": "Section 232, derivative steel articles, draft revision",
                        "note": "Draft rate. Confirm with the customs broker before use.",
                    }
                )
            else:
                draft_rows.append(
                    {
                        "tariff_table_id": draft.id,
                        "harmonised_tariff_code": code,
                        "origin_country": "TW",
                        "destination_country": "US",
                        "component": "section_301",
                        "rate_percent": Decimal("10"),
                        "basis": "customs_value",
                        "combined_cap_percent": Decimal("10"),
                        "authority": "Section 301 final action, 24 July 2026",
                        "note": "Unchanged in this draft.",
                    }
                )
            # Bearings and pneumatic parts are made in Japan and mainland China
            # as well as Taiwan, so every origin Hengtai actually buys from has
            # to be in the table. A gap here blocks a quote rather than
            # silently pricing duty at nothing.
            for origin, extra in (("JP", None), ("DE", None), ("CN", Decimal("25")), ("US", None)):
                draft_rows.append(
                    {
                        "tariff_table_id": draft.id,
                        "harmonised_tariff_code": code,
                        "origin_country": origin,
                        "destination_country": "US",
                        "component": "most_favoured_nation",
                        "rate_percent": rate,
                        "basis": "customs_value",
                        "authority": "Harmonized Tariff Schedule of the United States",
                        "note": "Normal trade relations rate.",
                    }
                )
                if extra is not None:
                    draft_rows.append(
                        {
                            "tariff_table_id": draft.id,
                            "harmonised_tariff_code": code,
                            "origin_country": origin,
                            "destination_country": "US",
                            "component": "section_301",
                            "rate_percent": extra,
                            "basis": "customs_value",
                            "authority": "Section 301, China",
                            "note": "China list duty.",
                        }
                    )
            for origin in ("TW", "CN", "JP", "DE", "US"):
                draft_rows.append(
                    {
                        "tariff_table_id": draft.id,
                        "harmonised_tariff_code": code,
                        "origin_country": origin,
                        "destination_country": "TW",
                        "component": "most_favoured_nation",
                        "rate_percent": Decimal("0"),
                        "basis": "customs_value",
                        "authority": "Domestic movement",
                        "note": "Goods already inside Taiwan carry no import duty.",
                    }
                )
        self._bulk(TariffLine, draft_rows)
        self.counts["tariff_tables"] = 4
        self.progress("tariffs", 4, 4)

    # -- currency and freight ---------------------------------------------
    def build_rates(self) -> None:
        rows: list[dict[str, Any]] = []
        base_rate = Decimal("0.031750")  # about 31.5 Taiwan dollars to the US dollar
        for week in range(40):
            as_of = TODAY - dt.timedelta(days=7 * week)
            drift = Decimal(str(round(self.random.uniform(-0.00055, 0.00055), 6)))
            rows.append(
                {
                    "base_currency": "TWD",
                    "quote_currency": "USD",
                    "rate": (base_rate + drift).quantize(Decimal("0.000001")),
                    "as_of_date": as_of,
                    "source": "Demo treasury feed, mid-market close",
                }
            )
            rows.append(
                {
                    "base_currency": "TWD",
                    "quote_currency": "EUR",
                    "rate": (base_rate * Decimal("0.92") + drift).quantize(Decimal("0.000001")),
                    "as_of_date": as_of,
                    "source": "Demo treasury feed, mid-market close",
                }
            )
            rows.append(
                {
                    "base_currency": "USD",
                    "quote_currency": "TWD",
                    "rate": (Decimal("1") / (base_rate + drift)).quantize(Decimal("0.000001")),
                    "as_of_date": as_of,
                    "source": "Demo treasury feed, mid-market close",
                }
            )
        self._bulk(ExchangeRate, rows)
        self.counts["exchange_rates"] = len(rows)

        freight = [
            {
                "origin_country": "TW", "destination_country": "US", "mode": "sea",
                "minimum_charge": Decimal("9800"), "price_per_kilogram": Decimal("42"),
                "handling_per_shipment": Decimal("4200"), "insurance_percent": Decimal("0.35"),
                "transit_days": 21, "currency": "TWD",
            },
            {
                "origin_country": "TW", "destination_country": "US", "mode": "air",
                "minimum_charge": Decimal("18500"), "price_per_kilogram": Decimal("285"),
                "handling_per_shipment": Decimal("5600"), "insurance_percent": Decimal("0.35"),
                "transit_days": 5, "currency": "TWD",
            },
            {
                "origin_country": "TW", "destination_country": "TW", "mode": "courier",
                "minimum_charge": Decimal("350"), "price_per_kilogram": Decimal("18"),
                "handling_per_shipment": Decimal("120"), "insurance_percent": Decimal("0.10"),
                "transit_days": 1, "currency": "TWD",
            },
            {
                "origin_country": "TW", "destination_country": "DE", "mode": "sea",
                "minimum_charge": Decimal("12400"), "price_per_kilogram": Decimal("51"),
                "handling_per_shipment": Decimal("4800"), "insurance_percent": Decimal("0.40"),
                "transit_days": 32, "currency": "TWD",
            },
        ]
        self._bulk(FreightRate, freight)
        self.counts["freight_rates"] = len(freight)
        self.progress("rates", len(rows) + len(freight), len(rows) + len(freight))


def build_demo_data(
    session: Session,
    *,
    product_target: int = 18_000,
    customer_target: int = 1_200,
    progress: ProgressCallback | None = None,
) -> dict[str, int]:
    builder = DemoDataBuilder(
        session,
        product_target=product_target,
        customer_target=customer_target,
        progress=progress,
    )
    return builder.build()
