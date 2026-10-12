"""Today, in one place.

The generated company is laid out relative to the day it is loaded: contracts
running now and contracts that have lapsed, duty tables in force and duty
tables superseded. Pinning that to a date typed into the source means the
demonstration quietly rots — run it a year later and every contract has
expired, so every line falls back to tier pricing for a reason that has
nothing to do with what is being shown.
"""

from __future__ import annotations

import datetime as dt
import os


def today() -> dt.date:
    """The day the generated data is laid out around.

    ``QUOTEAGENT_TODAY`` pins it, so a test or a recorded demonstration can
    ask for a fixed day without the rest of the code knowing.
    """
    pinned = os.getenv("QUOTEAGENT_TODAY", "").strip()
    if pinned:
        try:
            return dt.date.fromisoformat(pinned)
        except ValueError:
            pass
    return dt.date.today()
