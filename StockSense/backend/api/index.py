"""Vercel's entry point.

Vercel looks for an ASGI application called `app` in this file and serves it.
`vercel.json` rewrites every path here, so the routes are exactly the ones in
`app/main.py` and nothing diverges between local and deployed.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The function runs with this directory on the path, not its parent, so the
# package next to it has to be made importable before anything else happens.
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app  # noqa: E402

__all__ = ["app"]
