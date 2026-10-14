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

    ``OPSAGENT_TODAY`` pins it, so a test or a recorded demonstration can
    ask for a fixed day without the rest of the code knowing.
    """
    pinned = os.getenv("OPSAGENT_TODAY", "").strip()
    if pinned:
        try:
            return dt.date.fromisoformat(pinned)
        except ValueError:
            pass
    return dt.date.today()
