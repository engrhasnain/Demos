"""The application.

The same file runs under `uvicorn` on a laptop and as a serverless
function. The only difference is that nothing may be written outside the
scratch directory and nothing may outlive a request, so there are no
background threads and no scheduled work anywhere in here.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.types import ASGIApp, Receive, Scope, Send

from . import bootstrap
from .config import settings
from .db import create_all
from .routers import auth, operations

log = logging.getLogger("opsagent")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Importing the catalogue runs its own checks — read-only queries,
    # a declared scope column on anything that touches somebody's data,
    # and a GROUP BY on anything that adds figures up. If one of those
    # fails the process does not start, which is the intention: a
    # capability that can leak is not something to serve and warn about.
    from .domain import capabilities

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
    log.info("%d capabilities loaded and checked.", len(capabilities.CATALOGUE))
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    summary=(
        "Questions about the business, answered from reviewed queries, "
        "scoped to what the asker may see, with the working attached."
    ),
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ReadyBeforeFirstRequest:
    """Hold requests until the database is ready.

    Where storage is temporary that includes loading the demonstration
    data and a handful of example questions, once per process, so the
    first page after a cold start already has data and the demonstration
    accounts can sign in. It runs on the first request rather than at
    start-up so it is bounded by the request time limit on any host.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not bootstrap.is_ready():
            await run_in_threadpool(bootstrap.ensure_ready)
        await self.app(scope, receive, send)


app.add_middleware(ReadyBeforeFirstRequest)


# ---------------------------------------------------------------------------
# Errors a person can read
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def _validation(_request: Request, error: RequestValidationError) -> JSONResponse:
    problems = [
        {
            "field": ".".join(
                str(part) for part in item.get("loc", []) if part != "body"
            ),
            "problem": item.get("msg", ""),
        }
        for item in error.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"detail": "Some of what was sent is not usable.", "problems": problems},
    )


@app.exception_handler(SQLAlchemyError)
async def _database(_request: Request, error: SQLAlchemyError) -> JSONResponse:
    log.exception("database error", exc_info=error)
    return JSONResponse(
        status_code=500,
        content={"detail": "The database refused that. Nothing was changed."},
    )


@app.exception_handler(Exception)
async def _unhandled(_request: Request, error: Exception) -> JSONResponse:
    # The catch-all beneath the two above: anything neither of them is
    # for — a cold-start import error, a bug — still comes back as clean
    # JSON instead of a bare 500 with no body, and is logged server-side
    # so there is something to look at afterwards.
    log.exception("unhandled error", exc_info=error)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "message": str(error)},
    )


app.include_router(auth.router)
app.include_router(operations.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "api": "/api/docs",
        "health": "/api/health",
    }
