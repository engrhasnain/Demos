"""The application.

Built so the same file runs under `uvicorn` on a laptop and as a serverless
function on Vercel. The only difference is that on Vercel nothing may be
written outside the scratch directory and nothing may outlive a request, so
there are no background threads and no scheduled work anywhere in here.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError

from .config import settings
from .db import create_all
from .routers import auth, demo, evaluation, invoices, system, vendors
from .services.pipeline import PipelineError
from .services.posting import LedgerUnavailable
from .services.workflow import IllegalTransition

log = logging.getLogger("ledgerflow")


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


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    summary="Supplier invoices, read, checked against the order and the delivery, and posted.",
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


# ---------------------------------------------------------------------------
# Errors a person can read
# ---------------------------------------------------------------------------
@app.exception_handler(PipelineError)
async def _pipeline_error(_request: Request, error: PipelineError) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(IllegalTransition)
async def _illegal_transition(_request: Request, error: IllegalTransition) -> JSONResponse:
    return JSONResponse(status_code=409, content={"detail": str(error)})


@app.exception_handler(LedgerUnavailable)
async def _ledger_unavailable(_request: Request, error: LedgerUnavailable) -> JSONResponse:
    # Retry-safe by construction, so say so rather than leaving the caller
    # wondering whether a second attempt would double the bill.
    return JSONResponse(
        status_code=503,
        content={"detail": str(error), "safe_to_try_again": True},
    )


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
    # The handlers above cover everything this application expects to go
    # wrong. Anything else is a bug, and a bug should still hand the caller
    # clean JSON rather than a bare 500 with an HTML stack trace - especially
    # on serverless hosting, where the raw traceback also ends up in a log
    # nobody watching the site in production can see.
    log.exception("unhandled error", exc_info=error)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "message": str(error)},
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(system.router)
app.include_router(invoices.router)
app.include_router(vendors.router)
app.include_router(evaluation.router)
app.include_router(demo.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "api": "/api/docs",
        "health": "/api/health",
    }
