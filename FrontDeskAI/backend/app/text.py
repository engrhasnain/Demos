"""Wording helpers.

Small, but they stop the interface reading like a log file. ``1 line(s)`` is
the sort of thing that tells a buyer the screen was never looked at.
"""

from __future__ import annotations


def count(many: int, noun: str, plural: str = "") -> str:
    """``1 line`` and ``2 lines``, never ``1 line(s)``."""
    if many == 1:
        return f"{many} {noun}"
    return f"{many} {plural or noun + 's'}"
