"""Finding a technician who can actually do the job.

The model never proposes a time. It cannot: times come from here, and here
is a constraint check, not a sentence. Four things have to hold before a
slot is offered:

* the technician is qualified for the work;
* the van has the parts, or the job does not need any;
* they are not already somewhere else, including the travel either side;
* it is inside working hours.

The fourth constraint is the one people forget to model and the one that
ruins a day: a technician in Taichung at eleven cannot be in Kaohsiung at
twelve. Travel time is charged against the diary on both sides of a visit,
so the slot that looks free at noon is not offered if the morning job is
two hours away.

Then there is the race. Two customers press the same slot in the same
second. Checking for a clash and then writing is not enough — both check,
both find it free, both write. The database has a unique constraint on the
technician and the time, so one write wins and the other raises, and the
loser is offered the next slot rather than a failure.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..clock import aware
from ..config import settings
from ..models import Technician, Visit
from .isolation import Scope

TAIPEI = dt.timezone(dt.timedelta(hours=8))


class SlotTaken(Exception):
    """Somebody else booked it between the offer and the acceptance."""


@dataclass(slots=True)
class Slot:
    technician_id: int
    technician_name: str
    starts_at: dt.datetime
    minutes: int
    city: str
    travel_minutes: int

    @property
    def key(self) -> str:
        return f"{self.technician_id}:{self.starts_at.isoformat()}"

    def to_dict(self) -> dict[str, object]:
        local = self.starts_at.astimezone(TAIPEI)
        return {
            "key": self.key,
            "technician_id": self.technician_id,
            "technician": self.technician_name,
            "starts_at": self.starts_at.isoformat(),
            "shown_as": local.strftime("%a %d %b, %H:%M"),
            "minutes": self.minutes,
            "city": self.city,
            "travel_minutes": self.travel_minutes,
        }


@dataclass(slots=True)
class Search:
    """What was looked for, and why most technicians were not offered."""

    slots: list[Slot] = field(default_factory=list)
    considered: int = 0
    ruled_out: dict[str, int] = field(default_factory=dict)

    def rule_out(self, reason: str) -> None:
        self.ruled_out[reason] = self.ruled_out.get(reason, 0) + 1

    def to_dict(self) -> dict[str, object]:
        return {
            "slots": [slot.to_dict() for slot in self.slots],
            "considered": self.considered,
            "ruled_out": self.ruled_out,
        }


def _travel_minutes(base_city: str, to_city: str) -> int:
    if not base_city or not to_city:
        return settings.travel_minutes_other_city
    return (
        settings.travel_minutes_same_city
        if base_city.strip().casefold() == to_city.strip().casefold()
        else settings.travel_minutes_other_city
    )


def _working_slots(from_day: dt.date, days: int) -> list[dt.datetime]:
    """Every start time the diary allows, in Taipei hours."""
    out: list[dt.datetime] = []
    step = settings.visit_minutes
    for offset in range(days):
        day = from_day + dt.timedelta(days=offset)
        if day.weekday() not in settings.working_days:
            continue
        start = dt.datetime.combine(
            day, dt.time(settings.office_opens_hour), tzinfo=TAIPEI
        )
        end = dt.datetime.combine(
            day, dt.time(settings.office_closes_hour), tzinfo=TAIPEI
        )
        moment = start
        while moment + dt.timedelta(minutes=step) <= end:
            out.append(moment.astimezone(dt.timezone.utc))
            moment += dt.timedelta(minutes=step)
    return out


def _clashes(
    starts_at: dt.datetime,
    minutes: int,
    travel: int,
    diary: list[tuple[dt.datetime, int, str]],
    city: str,
) -> bool:
    """Does this slot collide with anything already in the diary?

    Travel is charged on both sides. A visit that ends at noon in one city
    does not free up noon in another.
    """
    wanted_from = starts_at - dt.timedelta(minutes=travel)
    wanted_to = starts_at + dt.timedelta(minutes=minutes + travel)
    for booked_at, booked_minutes, booked_city in diary:
        gap = (
            settings.travel_minutes_same_city
            if booked_city.strip().casefold() == city.strip().casefold()
            else settings.travel_minutes_other_city
        )
        booked_from = booked_at - dt.timedelta(minutes=gap)
        booked_to = booked_at + dt.timedelta(minutes=booked_minutes + gap)
        if wanted_from < booked_to and booked_from < wanted_to:
            return True
    return False


def find_slots(
    session: Session,
    *,
    city: str,
    skill: str,
    parts: list[str] | None = None,
    from_day: dt.date | None = None,
    wanted: int = 3,
) -> Search:
    """The slots that pass every constraint, soonest first."""
    parts = [p for p in (parts or []) if p]
    from_day = from_day or dt.datetime.now(TAIPEI).date()
    search = Search()

    technicians = list(
        session.scalars(select(Technician).where(Technician.is_active.is_(True)))
    )
    search.considered = len(technicians)

    booked: dict[int, list[tuple[dt.datetime, int, str]]] = {}
    for visit in session.scalars(
        select(Visit).where(
            Visit.status == "booked",
            Visit.starts_at >= dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1),
        )
    ):
        booked.setdefault(visit.technician_id, []).append(
            (aware(visit.starts_at), visit.minutes, visit.city)
        )

    candidates: list[Technician] = []
    for technician in technicians:
        if skill and skill not in (technician.skills or []):
            search.rule_out("not qualified")
            continue
        if parts:
            stock = set(technician.van_stock or [])
            if not all(part in stock for part in parts):
                search.rule_out("parts not in the van")
                continue
        candidates.append(technician)

    times = _working_slots(from_day, settings.booking_horizon_days)
    for moment in times:
        for technician in candidates:
            travel = _travel_minutes(technician.base_city, city)
            if _clashes(
                moment,
                settings.visit_minutes,
                travel,
                booked.get(technician.id, []),
                city,
            ):
                continue
            search.slots.append(
                Slot(
                    technician_id=technician.id,
                    technician_name=technician.full_name,
                    starts_at=moment,
                    minutes=settings.visit_minutes,
                    city=city,
                    travel_minutes=travel,
                )
            )
            break
        if len(search.slots) >= wanted:
            break

    if not search.slots:
        search.rule_out("nothing free in the horizon")
    return search


def book(
    session: Session,
    scope: Scope,
    slot: Slot,
    *,
    skill: str = "",
    parts: list[str] | None = None,
    note: str = "",
) -> Visit:
    """Take the slot, or raise because somebody else just did.

    The check-then-write pattern loses this race and the database wins it.
    The caller catches ``SlotTaken`` and offers the next one, which is what
    a person at a desk would do.
    """
    # The savepoint has to be opened *before* the row is added, or the
    # insert belongs to the outer transaction and rolling the savepoint
    # back does not undo it. Getting this the wrong way round means the
    # clash escapes as a database error instead of an offer of another slot.
    savepoint = session.begin_nested()
    try:
        visit = Visit(
            reference=_next_reference(session),
            customer_id=scope.customer_id,
            technician_id=slot.technician_id,
            starts_at=slot.starts_at,
            minutes=slot.minutes,
            city=slot.city,
            skill_needed=skill,
            parts_needed=list(parts or []),
            note=note,
            status="booked",
        )
        session.add(visit)
        session.flush()
        savepoint.commit()
    except IntegrityError as error:
        savepoint.rollback()
        raise SlotTaken(
            f"{slot.technician_name} was booked for that time a moment ago."
        ) from error
    return visit


def _next_reference(session: Session) -> str:
    year = dt.datetime.now(TAIPEI).year
    highest = session.scalar(
        select(Visit.reference)
        .where(Visit.reference.like(f"VIS-{year}-%"))
        .order_by(Visit.reference.desc())
        .limit(1)
    )
    number = int(highest.rsplit("-", 1)[1]) + 1 if highest else 1
    return f"VIS-{year}-{number:05d}"
