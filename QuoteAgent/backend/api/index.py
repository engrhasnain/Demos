"""Vercel entry point.

Vercel serves this file at /api/index and vercel.json rewrites every path to
it, so the FastAPI application sees the original URL and all of its own routes
work unchanged.
"""

from __future__ import annotations

import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.main import app  # noqa: E402

# Vercel's Python runtime looks for an ASGI application called "app".
__all__ = ["app"]
