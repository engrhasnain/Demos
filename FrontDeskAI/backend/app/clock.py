"""Today, in one place.

Two years of demand history are laid out backwards from the day the data
is loaded, and the next Lunar New Year is found from it. Pinning that to a
date typed into the source means the demonstration quietly rots: run it a
year later and the "upcoming" shutdown is already in the past, which makes
every pre-build recommendation nonsense.
"""

from __future__ import annotations

import datetime as dt
import os


def today() -> dt.date:
    """The day the data is laid out around.

    ``FRONTDESK_TODAY`` pins it, so a test or a recorded demonstration can
    ask for a fixed day without the rest of the code knowing.
    """
    pinned = os.getenv("FRONTDESK_TODAY", "").strip()
    if pinned:
        try:
            return dt.date.fromisoformat(pinned)
        except ValueError:
            pass
    return dt.date.today()


def aware(moment: dt.datetime | None) -> dt.datetime | None:
    """A datetime that is safe to compare.

    SQLite has no timezone type, so a value written as UTC-aware comes back
    naive, and subtracting it from an aware one raises. Everything in this
    product is stored in UTC, so a naive value read from the database is a
    UTC value that has lost its label; this puts the label back.
    """
    if moment is None:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)
