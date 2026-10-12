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
from .routers import auth, catalogue, planning, system
from .seed.autoload import ensure_demo_data


log = logging.getLogger("stocksense")


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
    # On Vercel with no database configured, build the demonstration
    # company now so the first screen already has data. Does nothing
    # locally, in tests, on PostgreSQL, or with AUTO_LOAD_DEMO_DATA=false.
    ensure_demo_data()
    yield


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    summary="What to reorder, how much, and what it would cost to be wrong.",
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


@app.middleware("http")
async def _ready(request: Request, call_next):
    # A host that does not run the lifespan still gets its tables and its
    # demonstration data before the first request is answered. After the
    # first call both are a flag check.
    from starlette.concurrency import run_in_threadpool

    await run_in_threadpool(_ensure_ready)
    return await call_next(request)


_tables_ready = False


def _ensure_ready() -> None:
    global _tables_ready
    if not _tables_ready:
        create_all()
        _tables_ready = True
    ensure_demo_data()


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


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------
app.include_router(auth.router)
app.include_router(system.router)
app.include_router(catalogue.router)
app.include_router(planning.router)


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "api": "/api/docs",
        "health": "/api/health",
    }
