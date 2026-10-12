"""Shutdowns, and what they do to a lead time.

Lunar New Year is not a public holiday you can add to a calendar and forget.
For an importer buying out of Taiwan and mainland China it is the single
largest planning event of the year, and it behaves differently in each
country:

* **Taiwan** closes for roughly the official week. Factories come back
  close to full strength.
* **Mainland China** officially closes for about eight days, but the real
  shutdown runs far longer. Workers travel home before it and come back
  over several weeks afterwards, so a factory restarts at a fraction of its
  workforce. The practical disruption is four to six weeks, and many plants
  stop taking new orders six to eight weeks ahead of it.

That last point is what the recommendations have to act on. An order placed
in the week before the holiday does not ship late, it does not ship at all.
Cover has to be bought *before* the ordering window closes, which is weeks
earlier than any reorder point would suggest.

Dates are tabulated rather than computed. The lunisolar calendar is not
worth reimplementing to get one date a year, and a wrong date here is worse
than no date at all.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

#: First day of the lunar new year. Published dates, not computed ones.
LUNAR_NEW_YEAR: dict[int, dt.date] = {
    2024: dt.date(2024, 2, 10),
    2025: dt.date(2025, 1, 29),
    2026: dt.date(2026, 2, 17),
    2027: dt.date(2027, 2, 6),
    2028: dt.date(2028, 1, 26),
    2029: dt.date(2029, 2, 13),
    2030: dt.date(2030, 2, 3),
}

#: Per country: days the plants are shut, extra days until output is back to
#: normal, and how far ahead they stop accepting orders for the period.
@dataclass(frozen=True, slots=True)
class ShutdownRule:
    country: str
    label: str
    #: Closed from this many days before the new year.
    closes_days_before: int
    #: Closed until this many days after it.
    reopens_days_after: int
    #: Running below normal output for this many days after reopening.
    recovery_days: int
    #: Stops accepting orders for before the holiday this far ahead of it.
    order_cutoff_days_before: int


RULES: dict[str, ShutdownRule] = {
    "TW": ShutdownRule("TW", "Taiwan", 2, 7, 5, 21),
    "CN": ShutdownRule("CN", "Mainland China", 7, 15, 21, 49),
    "VN": ShutdownRule("VN", "Vietnam", 3, 9, 10, 28),
    # Everywhere else carries on through it.
    "US": ShutdownRule("US", "United States", 0, 0, 0, 0),
    "JP": ShutdownRule("JP", "Japan", 0, 0, 0, 0),
    "DE": ShutdownRule("DE", "Germany", 0, 0, 0, 0),
}


def rule_for(country: str) -> ShutdownRule:
    return RULES.get(country, RULES["US"])


@dataclass(slots=True)
class Shutdown:
    """One supplier's next shutdown, in actual dates."""

    country: str
    label: str
    new_year: dt.date
    closes_on: dt.date
    reopens_on: dt.date
    back_to_normal_on: dt.date
    order_by: dt.date
    affects: bool

    @property
    def closed_days(self) -> int:
        return (self.reopens_on - self.closes_on).days

    @property
    def disrupted_days(self) -> int:
        return (self.back_to_normal_on - self.closes_on).days

    def days_until_order_by(self, today: dt.date) -> int:
        return (self.order_by - today).days

    def extra_lead_time_days(self, order_on: dt.date) -> int:
        """How much longer an order placed on this date will take.

        An order placed before the cut-off is unaffected. One placed after
        it waits for the plant to come back, and then waits again while the
        plant works through the queue that built up.
        """
        if not self.affects or order_on < self.order_by:
            return 0
        if order_on >= self.back_to_normal_on:
            return 0
        wait = (self.reopens_on - order_on).days
        # Coming back at part strength means the queue clears slowly.
        return max(0, wait) + self.recovery_penalty_days

    @property
    def recovery_penalty_days(self) -> int:
        return (self.back_to_normal_on - self.reopens_on).days // 2

    def to_dict(self) -> dict[str, object]:
        return {
            "country": self.country,
            "label": self.label,
            "new_year": self.new_year.isoformat(),
            "closes_on": self.closes_on.isoformat(),
            "reopens_on": self.reopens_on.isoformat(),
            "back_to_normal_on": self.back_to_normal_on.isoformat(),
            "order_by": self.order_by.isoformat(),
            "closed_days": self.closed_days,
            "disrupted_days": self.disrupted_days,
            "affects": self.affects,
        }


def next_new_year(after: dt.date) -> dt.date | None:
    """The next lunar new year on or after a date."""
    upcoming = sorted(d for d in LUNAR_NEW_YEAR.values() if d >= after)
    return upcoming[0] if upcoming else None


def next_shutdown(country: str, today: dt.date) -> Shutdown | None:
    """The next shutdown a supplier in this country will take.

    Looks past a new year that has already finished disrupting things, so
    in March the answer is next year rather than a date in the past.
    """
    rule = rule_for(country)
    candidates = sorted(LUNAR_NEW_YEAR.values())
    for new_year in candidates:
        back_to_normal = new_year + dt.timedelta(
            days=rule.reopens_days_after + rule.recovery_days
        )
        if back_to_normal < today:
            continue
        return Shutdown(
            country=rule.country,
            label=rule.label,
            new_year=new_year,
            closes_on=new_year - dt.timedelta(days=rule.closes_days_before),
            reopens_on=new_year + dt.timedelta(days=rule.reopens_days_after),
            back_to_normal_on=back_to_normal,
            order_by=new_year - dt.timedelta(days=rule.order_cutoff_days_before),
            affects=rule.order_cutoff_days_before > 0,
        )
    return None


def weeks_of_cover_needed(shutdown: Shutdown | None) -> float:
    """How many weeks of demand have to be on the shelf before it starts.

    From the day the plant stops taking orders to the day it is back to
    normal output: that is the whole window during which nothing new can be
    relied on to arrive.
    """
    if shutdown is None or not shutdown.affects:
        return 0.0
    days = (shutdown.back_to_normal_on - shutdown.order_by).days
    return max(0.0, days / 7.0)
