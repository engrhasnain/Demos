"""The business system, which has no way in except the screen.

Twenty years old, a green screen behind a web wrapper, no API and no
prospect of one. This is the system the tracking number has to get back
into, and it is the half of the job that people forget: booking the
shipment is useless if customer service still cannot answer "where is my
order".

Its habits are its own:

* it locks a record while somebody has it open, and the lock expires;
* it will not accept a write against a record it thinks is unchanged
  since you read it, so a stale read is rejected rather than silently
  overwriting somebody;
* it is case sensitive about order numbers in one place and not another;
* and it truncates anything over its field width without saying so, which
  is how half a tracking number ends up in the system.

That last one is the nastiest, because it succeeds.
"""

from __future__ import annotations

import datetime as dt
import random
from dataclasses import dataclass, field
from typing import Any


class LegacyError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class RecordLocked(LegacyError):
    def __init__(self, order: str, by: str, until: dt.datetime) -> None:
        super().__init__("locked", f"{order} is open on {by}'s screen.")
        self.until = until


class StaleWrite(LegacyError):
    def __init__(self, order: str) -> None:
        super().__init__(
            "stale",
            f"{order} changed since it was read. Read it again before writing.",
        )


#: The screen truncates at this, silently. A tracking number is twelve
#: characters, so anything that pads it loses the end.
TRACKING_FIELD_WIDTH = 18


@dataclass
class Record:
    order: str
    customer: str
    status: str = "picked"
    tracking_number: str = ""
    carrier: str = ""
    despatched_on: dt.date | None = None
    #: Bumped on every write. A write quoting an old one is refused.
    revision: int = 1
    locked_by: str = ""
    locked_until: dt.datetime | None = None
    history: list[dict[str, Any]] = field(default_factory=list)


class LegacySystem:
    """The screen, driven as a screen."""

    def __init__(self, *, seed: int = 23, lock_rate: float = 0.0) -> None:
        self.random = random.Random(seed)
        self.records: dict[str, Record] = {}
        self.lock_rate = lock_rate
        self.down = False
        self.writes = 0

    def add(self, record: Record) -> Record:
        self.records[record.order.upper()] = record
        return record

    # ------------------------------------------------------------------
    def read(self, order: str) -> Record:
        """Open the record. Case insensitive here, unlike the write."""
        if self.down:
            raise LegacyError("down", "The business system is not responding.")
        record = self.records.get((order or "").upper())
        if record is None:
            raise LegacyError("not_found", f"No order {order}.")

        now = dt.datetime.now(dt.timezone.utc)
        if record.locked_until and record.locked_until <= now:
            record.locked_by = ""
            record.locked_until = None

        if not record.locked_by and self.lock_rate and self.random.random() < self.lock_rate:
            record.locked_by = self.random.choice(["kchen", "mlin", "jwu"])
            record.locked_until = now + dt.timedelta(seconds=2)

        return record

    def write_tracking(
        self,
        order: str,
        *,
        tracking_number: str,
        carrier: str,
        revision: int,
        by: str = "portalbot",
    ) -> Record:
        """Put the tracking number back. Refuses a stale or locked write."""
        if self.down:
            raise LegacyError("down", "The business system is not responding.")

        # Case sensitive on write. A real inconsistency, and a real bug
        # source: it reads fine and then will not save.
        record = self.records.get(order)
        if record is None:
            raise LegacyError(
                "not_found",
                f"No order {order}. (This screen is case sensitive.)",
            )

        now = dt.datetime.now(dt.timezone.utc)
        if record.locked_by and record.locked_until and record.locked_until > now:
            raise RecordLocked(order, record.locked_by, record.locked_until)
        if revision != record.revision:
            raise StaleWrite(order)

        # The silent truncation. It does not error; it just keeps the first
        # eighteen characters of whatever it was given.
        stored = (tracking_number or "")[:TRACKING_FIELD_WIDTH]

        record.tracking_number = stored
        record.carrier = carrier[:24]
        record.status = "despatched"
        record.despatched_on = now.date()
        record.revision += 1
        record.history.append(
            {
                "at": now.isoformat(),
                "by": by,
                "tracking_number": stored,
                "revision": record.revision,
            }
        )
        self.writes += 1
        return record
