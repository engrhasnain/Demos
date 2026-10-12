"""Today, in one place.

The demonstration data is laid out relative to the day it is loaded: orders a
few weeks back, deliveries after them, invoices a few days old. Pinning that
to a date typed into the source means the demonstration quietly rots — run it
after that date and the invoices are in the future, which the product then
correctly refuses, for a reason that has nothing to do with what is being
shown.
"""

from __future__ import annotations

import datetime as dt
import os


def today() -> dt.date:
    """The day the data is laid out around.

    ``LEDGERFLOW_TODAY`` pins it, so a test or a recorded demonstration can
    ask for a fixed day without the rest of the code knowing.
    """
    pinned = os.getenv("LEDGERFLOW_TODAY", "").strip()
    if pinned:
        try:
            return dt.date.fromisoformat(pinned)
        except ValueError:
            pass
    return dt.date.today()
