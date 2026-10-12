"""QuoteAgent - the application.

Start it with:

    uvicorn app.main:app --reload --app-dir backend

It creates its own database on first run, so there is nothing to install and
nothing to configure before the first request.
"""

from __future__ import annotations

import datetime as dt
import json
from decimal import Decimal
from typing import Any

from collections.abc import AsyncIterator
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from . import __version__
from .config import settings
from .db import create_all
from .routers import auth, cases, catalogue, demo, evaluation, system
from .routers import tariffs as rates_router


def _default(value: Any) -> Any:
    if isinstance(value, Decimal):
        # Money is exact. Sending it as a JSON number would hand it to a
        # JavaScript double and quietly lose cents on a large quote.
        return str(value)
    if isinstance(value, (dt.datetime, dt.date)):
        return value.isoformat()
    if isinstance(value, set):
        return sorted(value)
    return str(value)


class ExactJSONResponse(JSONResponse):
    """JSON that never turns a decimal into a floating point number."""

    def render(self, content: Any) -> bytes:
        return json.dumps(
            content, ensure_ascii=False, allow_nan=False, default=_default
        ).encode("utf-8")


log = logging.getLogger("quoteagent")


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Create the tables on first start, so there is nothing to set up."""
    # A demonstration may run on the published defaults. Anything calling
    # itself something else may not: a known signing secret is a way in.
    problems = settings.insecure_defaults
    if problems and settings.environment != "demo":
        raise RuntimeError(
            "Refusing to start outside a demonstration: "
            + " ".join(problems)
            + " Set it, or set ENVIRONMENT=demo if that is really what this is."
        )
    for problem in problems:
        log.warning("%s Fine for a demonstration, not for anything else.", problem)

    create_all()
    yield


app = FastAPI(
    title="QuoteAgent",
    lifespan=lifespan,
    version=__version__,
    default_response_class=ExactJSONResponse,
    description=(
        "Takes a messy, multi-line request for quotation from the inbox to an "
        "approved quote the same day. Built for Hengtai Industrial Supply, a "
        "fictional Taiwan and United States distributor of industrial parts.\n\n"
        "Two rules hold throughout: the reasoning engine never writes a number, and "
        "every figure on screen can be opened to show the inputs, the formula and "
        "where each input came from."
    ),
)

# Credentials are only allowed when the origins are named. The browser
# refuses the combination of "any origin" and credentials, and this product
# authenticates with a bearer token rather than a cookie, so it does not need
# them.
_origins = settings.cors_origin_list
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials="*" not in _origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(system.router)
app.include_router(catalogue.router)
app.include_router(cases.router)
app.include_router(rates_router.router)
app.include_router(evaluation.router)
app.include_router(demo.router)


@app.get("/api/health", tags=["System"])
def health() -> dict[str, Any]:
    return {
        "status": "ready",
        "version": __version__,
        "reasoning_engine": settings.reasoning_engine,
        "database": "SQLite" if settings.database_url.startswith("sqlite") else "PostgreSQL",
    }


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "application": "QuoteAgent",
        "interface": "http://localhost:3000",
        "api_documentation": "/docs",
    }


@app.exception_handler(ValueError)
def value_error_handler(_request: Request, exc: ValueError) -> JSONResponse:
    return ExactJSONResponse(status_code=400, content={"detail": str(exc)})
