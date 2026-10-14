"""The day's shipments, with the awkward ones in proportion.

A hundred and eighty a day, of which the great majority are ordinary and a
known minority are not. The proportions are the point: an automation that
is only ever shown clean work looks finished, and the first real morning
it meets a four digit Taiwan postcode and an aerosol it stops dead.
"""

from __future__ import annotations

import datetime as dt
import random
from typing import Any, Callable

from sqlalchemy import delete
from sqlalchemy.orm import Session

from ..clock import today as today_date
from ..models import (
    Challenge,
    EvaluationRun,
    Run,
    ScriptFlag,
    Shipment,
    Step,
    User,
)
from ..security import hash_password
from ..systems.legacy import LegacySystem, Record

DEMO_PASSWORD = "demo1234"

STAFF: list[dict[str, Any]] = [
    {"email": "kai.chen@hengtai-industrial.example", "full_name": "Kai Chen",
     "role": "clerk", "on_duty": True},
    {"email": "mei.lin@hengtai-industrial.example", "full_name": "Mei Lin",
     "role": "clerk", "on_duty": False},
    {"email": "tomas.reyes@hengtai-industrial.example", "full_name": "Tomas Reyes",
     "role": "operations_lead", "on_duty": False},
    {"email": "ana.silva@hengtai-industrial.example", "full_name": "Ana Silva",
     "role": "developer", "on_duty": False},
    {"email": "admin@hengtai-industrial.example", "full_name": "System administrator",
     "role": "administrator", "on_duty": False},
]

CUSTOMERS = [
    ("Chen Precision Co., Ltd.", "TW", "Taichung", "407"),
    ("Yung Li Machinery Co., Ltd.", "TW", "Tainan", "70146"),
    ("Ta Chen Industrial Co.", "TW", "Kaohsiung", "806"),
    ("Hong Ji Automation Co., Ltd.", "TW", "Changhua", "500"),
    ("Northwind Engineering Inc.", "US", "Cleveland", "44113"),
    ("Cascade Tooling Inc.", "US", "Rockford", "61101"),
    ("Ironside Fabrication Inc.", "US", "Houston", "77002"),
    ("Meridian Systems Inc.", "US", "Ontario", "91761"),
    ("Osaka Seiko K.K.", "JP", "Osaka", "530-0001"),
    ("Solingen Werkzeug GmbH", "DE", "Solingen", "42653"),
]

#: Ordinary goods. Nothing in here is dangerous.
PLAIN = [
    ("HT-SHC-M8X030-12.9-ZNB", "Socket head cap screws, zinc plated"),
    ("HT-HXB-M12X060-8.8-HDG", "Hexagon head bolts, galvanised"),
    ("HT-BRG-6204-2RS-C3", "Deep groove ball bearings"),
    ("HT-CYL-032-0100-DA", "Pneumatic cylinders"),
    ("HT-FIT-G14-8MM-PI", "Push-in fittings"),
    ("HT-ORG-0220-NBR70", "O-rings, nitrile"),
]

#: Dangerous goods that ARE in the table, so the bot can declare them.
DECLARABLE = [
    ("HT-AER-PTFE-400", "Dry film lubricant aerosol 400ml"),
    ("HT-AER-ZINC-500", "Cold galvanising spray"),
    ("HT-ADH-THRD-050", "Threadlocking adhesive 50ml"),
    ("HT-SEN-PROX-LI", "Proximity sensor with internal lithium cell"),
]

#: Dangerous goods that are NOT in the table. These must stop the bot.
#: A part that reads as dangerous and has no decision behind it is the
#: case where guessing is an offence rather than a mistake.
UNDECIDED = [
    ("HT-AER-MOULD-300", "Mould release spray, new line"),
    ("HT-SOL-FLUX-001", "Flux remover solvent, new line"),
]

ProgressCallback = Callable[[str, int, int], None]


class Builder:
    def __init__(
        self,
        session: Session,
        *,
        shipment_target: int = 180,
        seed: int = 20261005,
        progress: ProgressCallback | None = None,
    ) -> None:
        self.session = session
        self.shipment_target = shipment_target
        self.random = random.Random(seed)
        self._progress = progress
        self.counts: dict[str, int] = {}
        self.today = today_date()

    def build(self) -> dict[str, int]:
        self.build_users()
        self.build_shipments()
        return self.counts

    def build_users(self) -> dict[str, int]:
        """Clear the demo tables and seed sign-in accounts only.

        Deliberately small and fast: callers racing a cold-start time
        budget commit this phase on its own, so sign-in works even if
        the heavier :meth:`build_shipments` phase is cut short.
        """
        self._clear()
        self._staff()
        self.session.flush()
        return dict(self.counts)

    def build_shipments(self) -> dict[str, int]:
        """The heavier phase: the day's shipment rows."""
        self._shipments()
        self.session.flush()
        return dict(self.counts)

    def _clear(self) -> None:
        for model in (Step, Challenge, ScriptFlag, Shipment, Run, EvaluationRun, User):
            self.session.execute(delete(model))
        self.session.flush()

    def _staff(self) -> None:
        password = hash_password(DEMO_PASSWORD)
        for person in STAFF:
            self.session.add(User(password_hash=password, **person))
        self.session.flush()
        self.counts["staff"] = len(STAFF)

    def _shipments(self) -> None:
        from ..services.bot import key_for

        rows: list[Shipment] = []
        planted = {
            "bad_postcode": 0,
            "undeclared": 0,
            "declarable": 0,
            "overweight": 0,
            "mixed": 0,
        }

        for index in range(self.shipment_target):
            name, country, city, postcode = CUSTOMERS[index % len(CUSTOMERS)]
            order = f"SO-{40000 + index}"
            roll = self.random.random()

            lines: list[dict[str, str]] = []
            packages = self.random.choice([1, 1, 1, 2, 2, 3, 5])
            weight = round(self.random.uniform(2.0, 40.0) * packages, 1)

            # --- what is in the box ----------------------------------
            if roll < 0.08:
                part, description = DECLARABLE[index % len(DECLARABLE)]
                lines.append({"part_code": part, "description": description})
                planted["declarable"] += 1
            elif roll < 0.11:
                part, description = UNDECIDED[index % len(UNDECIDED)]
                lines.append({"part_code": part, "description": description})
                planted["undeclared"] += 1
            else:
                for _ in range(self.random.randint(1, 3)):
                    part, description = PLAIN[self.random.randrange(len(PLAIN))]
                    lines.append({"part_code": part, "description": description})

            # --- things a clerk gets wrong ---------------------------
            shipment_postcode = postcode
            if self.random.random() < 0.05:
                # A Taiwan postcode with four digits, or a ZIP with a letter.
                shipment_postcode = (
                    postcode + "9" if country == "TW" else postcode[:-1] + "X"
                )
                planted["bad_postcode"] += 1
            if self.random.random() < 0.03:
                weight = round(self.random.uniform(75.0, 140.0) * packages, 1)
                planted["overweight"] += 1

            description = ", ".join(sorted({line["description"] for line in lines}))
            shipment = Shipment(
                reference=f"HT{self.today:%y%m%d}-{index + 1:04d}",
                order_number=order,
                customer_name=name,
                to_name=name,
                to_line1=f"{self.random.randint(1, 400)} Industrial Road",
                to_city=city,
                to_postcode=shipment_postcode,
                to_country=country,
                packages=packages,
                weight_kg=weight,
                goods_description=description[:200],
                service=self.random.choice(["STD", "STD", "EXP"]),
                lines=lines,
                state="pending",
            )
            shipment.idempotency_key = key_for(shipment)
            rows.append(shipment)

        self.session.add_all(rows)
        self.session.flush()
        self.counts["shipments"] = len(rows)
        for key, value in planted.items():
            if value:
                self.counts[f"planted_{key}"] = value

    # ------------------------------------------------------------------
    @staticmethod
    def legacy_for(session: Session, *, lock_rate: float = 0.0) -> LegacySystem:
        """A business system holding a record for every shipment."""
        from sqlalchemy import select

        legacy = LegacySystem(lock_rate=lock_rate)
        for shipment in session.scalars(select(Shipment)):
            legacy.add(
                Record(
                    order=shipment.order_number,
                    customer=shipment.customer_name,
                    status="picked",
                )
            )
        return legacy


def build_demo_data(
    session: Session,
    *,
    shipment_target: int = 180,
    progress: ProgressCallback | None = None,
) -> dict[str, int]:
    return Builder(
        session, shipment_target=shipment_target, progress=progress
    ).build()
