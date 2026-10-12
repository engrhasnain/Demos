"""The generated company.

Eighteen thousand parts with two years of weekly history each. The history
is the whole product, so it is generated with the awkward properties real
history has, not as smooth noise:

* most parts sell occasionally, not weekly, and the mix follows the
  classification quadrants rather than one distribution;
* some parts die partway through, and their history still shows the sales
  they used to make;
* some parts are born partway through and have almost nothing;
* a few weeks are one-off project orders ten times the usual size;
* the shelf is sometimes empty, and the sales recorded in those weeks are
  not the demand there was;
* suppliers slip against their quoted lead times, by different amounts;
* mainland suppliers stop shipping around the lunar new year.

The buyers' own orders are generated too, from a simple rule of thumb with
human lag in it, because the product is graded against them and grading
against nothing proves nothing.
"""

from __future__ import annotations

import datetime as dt
import math
import random
from decimal import Decimal
from typing import Any, Callable, Iterable

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..clock import today as today_date
from ..config import settings
from ..domain import calendar as shutdowns
from ..models import (
    AuditEntry,
    DemandHistory,
    HistoricOrder,
    Part,
    PlanLine,
    PlanRun,
    ReplayRun,
    Supplier,
    User,
)
from ..numbers import money
from ..security import hash_password

DEMO_PASSWORD = "demo1234"

PEOPLE: list[dict[str, str]] = [
    {"email": "wei.chen@hengtai-industrial.example", "full_name": "Wei Chen", "role": "buyer"},
    {"email": "amara.osei@hengtai-industrial.example", "full_name": "Amara Osei", "role": "buyer"},
    {"email": "lin.hsu@hengtai-industrial.example", "full_name": "Lin Hsu", "role": "senior_buyer"},
    {"email": "tomas.reyes@hengtai-industrial.example", "full_name": "Tomas Reyes", "role": "purchasing_manager"},
    {"email": "clare.whitfield@hengtai-industrial.example", "full_name": "Clare Whitfield", "role": "finance_director"},
    {"email": "admin@hengtai-industrial.example", "full_name": "System administrator", "role": "administrator"},
]

SUPPLIER_NAMES = [
    "Chang Hsing Fastener", "Yung Li Precision", "Ta Chen Metal", "Hong Ji Industrial",
    "Sheng Yu Screw", "Fu Shan Bearing", "Kai Hong Pneumatics", "Ming Tai Steel",
    "Jin Cheng Fastener", "Da Wei Industrial", "Shun Feng Components",
    "Tian Yuan Precision", "Bao Cheng Metal Works", "Hua An Fastener",
    "Zhong Xin Bearing", "Lian Fa Industrial", "Guang Ming Screw",
    "Ningbo Hengli Fastener", "Dongguan Precision Works", "Wenzhou Valve",
    "Midwest Bearing Supply", "Osaka Seiko", "Solingen Werkzeug",
]
SUFFIXES = ["Co., Ltd.", "Corporation", "Industrial Co.", "Enterprise Co., Ltd."]

#: family, prefix, description template, unit cost, pack size, cubic metres
FAMILIES: list[tuple[str, str, str, float, int, float]] = [
    ("socket_cap_screw", "HT-SHC", "Socket head cap screw ISO 4762 {size} class {grade}", 4.0, 500, 0.00002),
    ("hex_bolt", "HT-HXB", "Hexagon head bolt ISO 4017 {size} class {grade}", 7.5, 250, 0.00003),
    ("hex_nut", "HT-HXN", "Hexagon nut ISO 4032 {size} class {grade}", 2.0, 1000, 0.00001),
    ("washer", "HT-WSH", "Flat washer ISO 7089 {size} {grade} HV", 1.0, 2000, 0.000005),
    ("ball_bearing", "HT-BRG", "Deep groove ball bearing {size} {grade}", 110.0, 10, 0.0004),
    ("roller_bearing", "HT-RLR", "Cylindrical roller bearing {size} {grade}", 420.0, 5, 0.0009),
    ("air_cylinder", "HT-CYL", "Pneumatic cylinder {size} {grade}", 1450.0, 1, 0.006),
    ("solenoid_valve", "HT-VLV", "Solenoid valve {size} {grade}", 1280.0, 1, 0.003),
    ("fitting", "HT-FIT", "Push-in fitting {size} {grade}", 38.0, 50, 0.00008),
    ("o_ring", "HT-ORG", "O-ring {size} {grade}", 3.5, 500, 0.000004),
    ("retaining_ring", "HT-RET", "Retaining ring DIN 471 {size} {grade}", 2.8, 500, 0.000004),
    ("dowel_pin", "HT-DWL", "Dowel pin ISO 2338 {size} {grade}", 2.2, 500, 0.000005),
]
SIZES = ["M3x10", "M4x12", "M5x16", "M6x20", "M8x25", "M8x30", "M10x40", "M12x50",
         "M12x60", "M16x70", "M20x80", "6202", "6204", "6206", "6304", "6308",
         "032-0050", "040-0100", "050-0200", "G1/4", "G3/8", "G1/2", "8x1.5",
         "12x2", "16x2", "20x2.5", "25x3"]
GRADES = ["8.8", "10.9", "12.9", "A2-70", "A4-80", "2RS", "ZZ", "C3", "NBR70", "FKM"]

ProgressCallback = Callable[[str, int, int], None]


class Builder:
    """Builds the whole company. Deterministic for a given seed."""

    def __init__(
        self,
        session: Session,
        *,
        part_target: int = 18_000,
        supplier_target: int = 140,
        seed: int = 20261005,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.session = session
        self.part_target = part_target
        self.supplier_target = supplier_target
        self.random = random.Random(seed)
        self._progress = progress
        self.counts: dict[str, int] = {}
        self.today = today_date()
        self.weeks = settings.history_weeks
        # Series start on a Monday, so weeks line up with the ordering round.
        last_monday = self.today - dt.timedelta(days=self.today.weekday())
        self.starts_on = last_monday - dt.timedelta(weeks=self.weeks)

    def progress(self, stage: str, done: int, total: int) -> None:
        if self._progress:
            self._progress(stage, done, total)

    # ------------------------------------------------------------------
    def build(self) -> dict[str, int]:
        self._clear()
        self._people()
        suppliers = self._suppliers()
        parts = self._parts(suppliers)
        self._history(parts)
        self._supersessions(parts)
        self._buyers_orders(parts)
        self.session.flush()
        return self.counts

    def _clear(self) -> None:
        for model in (
            PlanLine, PlanRun, ReplayRun, HistoricOrder, DemandHistory,
            Part, Supplier, AuditEntry, User,
        ):
            self.session.execute(delete(model))
        self.session.flush()

    def _people(self) -> None:
        password = hash_password(DEMO_PASSWORD)
        for person in PEOPLE:
            self.session.add(User(password_hash=password, **person))
        self.session.flush()
        self.counts["people"] = len(PEOPLE)

    # ------------------------------------------------------------------
    def _suppliers(self) -> list[Supplier]:
        # Interleaved rather than grouped, so a small demonstration still
        # gets a mainland supplier and therefore a shutdown to plan around.
        countries = (["TW"] * 9 + ["CN"] * 5 + ["US", "JP", "DE", "VN"]) * 20
        rows: list[Supplier] = []
        for index in range(self.supplier_target):
            country = countries[index]
            name = SUPPLIER_NAMES[index % len(SUPPLIER_NAMES)]
            suffix = SUFFIXES[index % len(SUFFIXES)]
            quoted = {
                "TW": self.random.choice([14, 21, 21, 28]),
                "CN": self.random.choice([28, 35, 42]),
                "VN": self.random.choice([35, 42]),
                "US": self.random.choice([21, 28, 35]),
                "JP": self.random.choice([28, 35]),
                "DE": self.random.choice([42, 49, 56]),
            }[country]

            # Some suppliers keep to their word and some do not. The spread
            # is what safety stock is really paying for.
            reliability = self.random.choice(["good", "good", "fair", "fair", "poor"])
            slip, spread = {
                "good": (0.02, 0.06),
                "fair": (0.12, 0.18),
                "poor": (0.30, 0.35),
            }[reliability]
            samples = []
            for _ in range(self.random.randint(6, 24)):
                factor = self.random.gauss(1 + slip, spread)
                samples.append(max(3, round(quoted * max(0.6, factor))))

            rows.append(
                Supplier(
                    code=f"S-{1000 + index}",
                    name=f"{name} ({country}) {suffix}",
                    country=country,
                    currency={"TW": "TWD", "CN": "CNY", "US": "USD", "JP": "JPY",
                              "DE": "EUR", "VN": "USD"}[country],
                    quoted_lead_time_days=quoted,
                    lead_time_samples=samples,
                    minimum_order_value=money(
                        self.random.choice([0, 0, 20_000, 50_000, 100_000])
                    ),
                    container_cubic_metres=money(
                        0 if country in {"TW"} else self.random.choice([0, 0, 33, 67])
                    ),
                )
            )
        self.session.add_all(rows)
        self.session.flush()
        self.counts["suppliers"] = len(rows)
        return rows

    # ------------------------------------------------------------------
    def _parts(self, suppliers: list[Supplier]) -> list[Part]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        index = 0
        while len(rows) < self.part_target:
            family, prefix, template, base_cost, pack, volume = FAMILIES[
                index % len(FAMILIES)
            ]
            size = SIZES[self.random.randrange(len(SIZES))]
            grade = GRADES[self.random.randrange(len(GRADES))]
            finish = self.random.choice(["ZNB", "PLN", "HDG", "BLK", "NIC"])
            code = f"{prefix}-{size.replace('/', '')}-{grade}-{finish}-{len(rows):05d}"
            if code in seen:
                index += 1
                continue
            seen.add(code)

            cost = base_cost * self.random.uniform(0.7, 1.6)
            supplier = suppliers[self.random.randrange(len(suppliers))]
            rows.append(
                {
                    "code": code,
                    "description": template.format(size=size, grade=grade),
                    "family": family,
                    "supplier_id": supplier.id,
                    "unit_cost": money(cost),
                    "unit": "piece",
                    "pack_size": pack,
                    "minimum_order_quantity": self.random.choice([0, 0, pack, pack * 2]),
                    "cubic_metres_each": money(volume),
                    "abc_class": "C",
                    "on_hand": 0,
                    "on_order": 0,
                }
            )
            index += 1
            if len(rows) % 2000 == 0:
                self.progress("parts", len(rows), self.part_target)

        self.session.bulk_insert_mappings(Part, rows)
        self.session.flush()
        self.counts["parts"] = len(rows)
        self.progress("parts", len(rows), self.part_target)
        return list(self.session.scalars(select(Part).order_by(Part.id)))

    # ------------------------------------------------------------------
    # The history, which is the point of the whole exercise
    # ------------------------------------------------------------------
    #: The mix of demand patterns. Taken from the shape of a real industrial
    #: catalogue rather than spread evenly: most parts are occasional, and
    #: the handful that sell every week are most of the money.
    PATTERN_MIX: list[tuple[str, float]] = [
        ("smooth", 0.08),
        ("erratic", 0.09),
        ("intermittent", 0.38),
        ("lumpy", 0.30),
        ("dying", 0.08),
        ("new", 0.05),
        ("dead", 0.02),
    ]

    def _pick_pattern(self) -> str:
        roll = self.random.random()
        running = 0.0
        for name, share in self.PATTERN_MIX:
            running += share
            if roll <= running:
                return name
        return "lumpy"

    def _history(self, parts: list[Part]) -> None:
        weeks = self.weeks
        histories: list[dict[str, Any]] = []
        part_updates: list[dict[str, Any]] = []

        # Weeks in which mainland suppliers shipped nothing, used to make
        # the generated history agree with the calendar the product reads.
        shutdown_weeks: dict[str, set[int]] = {}
        for country in ("TW", "CN", "VN"):
            marked: set[int] = set()
            for year_start in shutdowns.LUNAR_NEW_YEAR.values():
                rule = shutdowns.rule_for(country)
                closed_from = year_start - dt.timedelta(days=rule.closes_days_before)
                closed_to = year_start + dt.timedelta(days=rule.reopens_days_after)
                for week in range(weeks):
                    monday = self.starts_on + dt.timedelta(weeks=week)
                    if closed_from <= monday <= closed_to:
                        marked.add(week)
            shutdown_weeks[country] = marked

        for position, part in enumerate(parts):
            pattern = self._pick_pattern()
            sold, stocked_out, project, meta = self._one_series(
                pattern,
                weeks,
                shutdown_weeks.get(part.supplier.country, set()),
                float(part.unit_cost),
            )

            histories.append(
                {
                    "part_id": part.id,
                    "starts_on": self.starts_on,
                    "weeks": weeks,
                    "sold": sold,
                    "stocked_out": stocked_out,
                    "was_project": project,
                }
            )

            annual_value = sum(sold[-52:]) * float(part.unit_cost)
            part_updates.append(
                {
                    "id": part.id,
                    "on_hand": meta["on_hand"],
                    "on_order": meta["on_order"],
                    "on_order_due": meta["on_order_due"],
                    "first_sold_on": meta["first_sold_on"],
                    "_annual_value": annual_value,
                }
            )
            if position % 2000 == 0:
                self.progress("history", position, len(parts))

        # A, B and C by what each part is worth in a year. 80/15/5 of value.
        ordered = sorted(part_updates, key=lambda r: -r["_annual_value"])
        total_value = sum(r["_annual_value"] for r in ordered) or 1.0
        running = 0.0
        for row in ordered:
            running += row["_annual_value"]
            share = running / total_value
            row["abc_class"] = "A" if share <= 0.80 else "B" if share <= 0.95 else "C"
            del row["_annual_value"]

        self.session.bulk_insert_mappings(DemandHistory, histories)
        self.session.bulk_update_mappings(Part, part_updates)
        self.session.flush()
        self.counts["weeks_of_history"] = weeks
        self.counts["demand_points"] = len(histories) * weeks
        self.progress("history", len(parts), len(parts))

    #: What one part is worth in a week, in New Taiwan dollars. A long
    #: tail: a handful of parts are most of the revenue and the rest tick
    #: over. Sized so eighteen thousand parts add up to a company of about
    #: the stated size rather than to an implausible one.
    WEEKLY_VALUE: tuple[int, ...] = (
        33, 33, 52, 52, 85, 85, 85, 130, 130, 215, 215, 345, 345,
        540, 540, 845, 1_430, 2_145, 3_445, 8_450,
    )

    def _one_series(
        self, pattern: str, weeks: int, closed_weeks: set[int], unit_cost: float
    ) -> tuple[list[int], list[bool], list[bool], dict[str, Any]]:
        """One part's two years, in the shape its pattern implies."""
        rng = self.random
        # Units a week this part would sell if it sold every week.
        value_a_week = rng.choice(self.WEEKLY_VALUE) * rng.uniform(0.6, 1.6)
        units_a_week = max(1.0, value_a_week / max(1.0, unit_cost))
        sold = [0] * weeks
        stocked_out = [False] * weeks
        project = [False] * weeks

        if pattern == "smooth":
            level = units_a_week
            for week in range(weeks):
                sold[week] = max(0, int(rng.gauss(level, level * 0.18)))
        elif pattern == "erratic":
            level = units_a_week
            for week in range(weeks):
                sold[week] = max(0, int(rng.gauss(level, level * 0.75)))
        elif pattern == "intermittent":
            every = rng.choice([2, 3, 4, 5, 6])
            size = units_a_week * every
            for week in range(weeks):
                if rng.random() < 1 / every:
                    sold[week] = max(1, int(rng.gauss(size, size * 0.22)))
        elif pattern == "lumpy":
            every = rng.choice([3, 4, 6, 8, 10, 13])
            size = units_a_week * every
            for week in range(weeks):
                if rng.random() < 1 / every:
                    sold[week] = max(1, int(size * rng.lognormvariate(0, 0.85)))
        elif pattern == "dying":
            # Sold normally, then stopped. The history still shows it, which
            # is how a reorder engine ends up buying dead stock.
            stopped = rng.randint(int(weeks * 0.35), int(weeks * 0.75))
            every = rng.choice([1, 2, 3])
            size = units_a_week * every
            for week in range(stopped):
                if rng.random() < 1 / every:
                    sold[week] = max(1, int(rng.gauss(size, size * 0.3)))
        elif pattern == "new":
            born = rng.randint(int(weeks * 0.78), weeks - 4)
            every = rng.choice([1, 2, 3, 4])
            size = units_a_week * every
            for week in range(born, weeks):
                if rng.random() < 1 / every:
                    sold[week] = max(1, int(rng.gauss(size, size * 0.3)))
        # "dead" leaves the series at zero throughout.

        # --- one-off project orders ------------------------------------
        if pattern in {"smooth", "erratic", "intermittent", "lumpy"}:
            for _ in range(rng.choice([0, 0, 0, 1, 1, 2])):
                week = rng.randrange(weeks)
                baseline = max(1, int(sum(sold) / max(1, len([s for s in sold if s]))))
                sold[week] += baseline * rng.randint(8, 25)
                project[week] = True

        # --- the shelf was empty ---------------------------------------
        # A week with an empty shelf records less than was wanted, and
        # sometimes nothing at all. Treating that as demand is how a part
        # that keeps running out gets forecast ever lower.
        typical = [s for s in sold if s > 0]
        if typical and pattern != "dead":
            average = sum(typical) / len(typical)
            for _ in range(rng.choice([0, 0, 0, 1, 2, 3, 5])):
                week = rng.randrange(weeks)
                if sold[week] > 0 or rng.random() < 0.4:
                    stocked_out[week] = True
                    sold[week] = int(sold[week] * rng.uniform(0.0, 0.5))

        # --- the supplier was shut -------------------------------------
        for week in closed_weeks:
            if week < weeks and rng.random() < 0.5 and sold[week] > 0:
                stocked_out[week] = True
                sold[week] = int(sold[week] * rng.uniform(0.0, 0.6))

        # --- where the part stands today -------------------------------
        recent = sold[-13:]
        weekly = sum(recent) / max(1, len(recent))
        first_sold = next((w for w, value in enumerate(sold) if value > 0), None)

        on_hand = int(max(0, rng.gauss(weekly * rng.uniform(1, 9), weekly * 1.5)))
        if pattern == "dead":
            # Dead stock: plenty on the shelf and nothing moving. This is
            # the 22 per cent of inventory value nobody wants to talk about.
            on_hand = int(rng.uniform(50, 2500))
        on_order = 0
        on_order_due = None
        if rng.random() < 0.18 and pattern != "dead":
            on_order = int(max(1, weekly * rng.uniform(2, 6)))
            on_order_due = self.today + dt.timedelta(days=rng.randint(3, 50))

        return (
            sold,
            stocked_out,
            project,
            {
                "on_hand": on_hand,
                "on_order": on_order,
                "on_order_due": on_order_due,
                "first_sold_on": (
                    self.starts_on + dt.timedelta(weeks=first_sold)
                    if first_sold is not None
                    else None
                ),
            },
        )

    # ------------------------------------------------------------------
    def _supersessions(self, parts: list[Part]) -> None:
        """Some parts were replaced by a newer number partway through.

        The successor has only the weeks since the change, which on its own
        looks like a brand new part. Carrying the predecessor's history is
        the difference between a usable forecast and a year of guessing.
        """
        rng = self.random
        by_family: dict[str, list[Part]] = {}
        for part in parts:
            by_family.setdefault(part.family, []).append(part)

        pairs = 0
        target = max(1, len(parts) // 60)
        updates: list[dict[str, Any]] = []
        for family_parts in by_family.values():
            rng.shuffle(family_parts)
            for old_part, new_part in zip(family_parts[::2], family_parts[1::2]):
                if pairs >= target:
                    break
                if old_part.id == new_part.id:
                    continue
                updates.append({"id": old_part.id, "replaced_by_part_id": new_part.id,
                                "is_active": False})
                updates.append({"id": new_part.id, "replaces_part_id": old_part.id})
                pairs += 1
            if pairs >= target:
                break

        if updates:
            self.session.bulk_update_mappings(Part, updates)
            self.session.flush()
        self.counts["supersessions"] = pairs

    # ------------------------------------------------------------------
    def _buyers_orders(self, parts: list[Part]) -> None:
        """What the two buyers actually ordered, so there is a bar to clear.

        Their rule is the one a spreadsheet encourages: look at the last
        three months, keep about six weeks of cover, and only notice a part
        when somebody complains. It is not a straw man; it is what works
        well enough to run a business on, and it is what has to be beaten.
        """
        rows: list[dict[str, Any]] = []
        histories = {
            h.part_id: h
            for h in self.session.scalars(select(DemandHistory))
        }
        for part in parts:
            history = histories.get(part.id)
            if history is None:
                continue
            sold = history.sold
            lead_weeks = max(1, round(part.supplier.quoted_lead_time_days / 7))
            position = 0.0
            # They review roughly fortnightly, and miss some reviews.
            for week in range(13, self.weeks, 2):
                recent = sold[max(0, week - 13):week]
                rate = sum(recent) / max(1, len(recent))
                position = max(0.0, position - sum(sold[max(0, week - 2):week]))
                target = rate * (lead_weeks + 6)
                if position < rate * lead_weeks and rate > 0:
                    quantity = int(max(0, target - position))
                    quantity = max(part.pack_size, quantity)
                    if self.random.random() < 0.82 and quantity > 0:
                        ordered_on = self.starts_on + dt.timedelta(weeks=week)
                        samples = part.supplier.lead_time_samples or [
                            part.supplier.quoted_lead_time_days
                        ]
                        actual_days = samples[
                            self.random.randrange(len(samples))
                        ]
                        arrival = ordered_on + dt.timedelta(days=int(actual_days))
                        rows.append(
                            {
                                "part_id": part.id,
                                "ordered_on": ordered_on,
                                "quantity": quantity,
                                "arrived_on": arrival,
                                "unit_cost": part.unit_cost,
                            }
                        )
                        position += quantity
        self.session.bulk_insert_mappings(HistoricOrder, rows)
        self.session.flush()
        self.counts["buyer_orders"] = len(rows)


def build_demo_data(
    session: Session,
    *,
    part_target: int = 18_000,
    supplier_target: int = 140,
    progress: ProgressCallback | None = None,
) -> dict[str, int]:
    return Builder(
        session,
        part_target=part_target,
        supplier_target=supplier_target,
        progress=progress,
    ).build()
