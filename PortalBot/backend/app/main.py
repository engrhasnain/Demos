"""The application.

Built so the same file runs under `uvicorn` on a laptop and as a serverless
function on Vercel. The only difference is that on Vercel nothing may be
written outside the scratch directory and nothing may outlive a request, so
there are no background threads and no scheduled work anywhere in here.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.types import ASGIApp, Receive, Scope, Send

from . import bootstrap
from .config import settings
from .db import create_all
from .routers import auth, operations


log = logging.getLogger("portalbot")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Creating the tables is cheap and idempotent. On serverless hosting the
    # scratch disk starts empty on a cold start, so this is what makes the
    # first request work at all.
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


#: Hard wall-clock budget for the one-time readiness/seed work, from this
#: request's point of view. Comfortably inside a Vercel function's own
#: maxDuration (see vercel.json), so a slow cold start times out here and
#: lets the request through instead of being killed by the platform with
#: a bare 500. The seed work keeps running in its background thread (see
#: bootstrap.py); it commits demo sign-in accounts well before this fires,
#: so sign-in still works even when this budget is exceeded.
_READY_TIMEOUT_SECONDS = 25.0


class ReadyBeforeFirstRequest:
    """Hold requests until the database is ready.

    Where storage is temporary that includes loading the demonstration data,
    once per process, so the first page after a cold start already has data
    and the demonstration accounts can sign in. It runs on the first request
    rather than at start-up so it is bounded by the request time limit on
    any host, Vercel included.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and not bootstrap.is_ready():
            try:
                await asyncio.wait_for(
                    run_in_threadpool(bootstrap.ensure_ready),
                    timeout=_READY_TIMEOUT_SECONDS,
                )
            except (TimeoutError, asyncio.TimeoutError):
                # bootstrap.ensure_ready() seeds demo accounts first and
                # commits them on their own before doing anything heavier
                # (see bootstrap._load_if_empty), so even cut short here
                # sign-in already works; only the fuller demo dataset is
                # still catching up in the background.
                log.warning(
                    "Database readiness/seeding exceeded %.0f s; letting the "
                    "request through. Demo sign-in accounts seed first and "
                    "should already be available.",
                    _READY_TIMEOUT_SECONDS,
                )
            except Exception:  # pragma: no cover - ensure_ready already logs internally
                log.exception(
                    "Preparing the database failed; letting the request "
                    "through so any failure surfaces per-request instead of "
                    "here."
                )
        await self.app(scope, receive, send)


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    summary="Two systems with no way in but the screen, driven without duplicates.",
    lifespan=lifespan,
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
    redoc_url=None,
)

app.add_middleware(ReadyBeforeFirstRequest)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# Errors a person can read
# ---------------------------------------------------------------------------
@app.exception_handler(RequestValidationError)
async def _validation(_request: Request, error: RequestValidationError) -> JSONResponse:
    problems = [
        {
            "field": ".".join(str(part) for part in item.get("loc", []) if part != "body"),
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
    """The last resort.

    Anything that reaches here would otherwise be a bare 500 with no body —
    exactly what a cold-start crash on Vercel looks like from the frontend.
    The real exception is logged in full server-side; what goes back to the
    client is a message the existing retry/error UI (see ErrorNote in the
    frontend) can show, not a stack trace.
    """
    log.exception("unhandled exception", exc_info=error)
    message = str(error) or error.__class__.__name__
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "message": message, "detail": message},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(operations.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "api": "/api/docs",
        "health": "/api/health",
    }
