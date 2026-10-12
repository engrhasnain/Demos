"""Settings.

Everything a client would argue about is here and nothing is buried in the
code. The carrying-cost rate in particular is a range a client owns, not the
20 per cent that every inventory tool quietly assumes.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

#: True on serverless hosting, where the filesystem is read only apart from
#: /tmp and nothing survives between requests.
SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

DATA_DIR = Path(
    os.getenv("STOCKSENSE_DATA_DIR")
    or ("/tmp/stocksense" if SERVERLESS else str(BACKEND_DIR / "var"))
)
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "StockSense"
    environment: str = "demo"

    database_url: str = f"sqlite:///{(DATA_DIR / 'stocksense.db').as_posix()}"

    #: Optional for a demonstration. Set it to anything long and random
    #: anywhere else; the app refuses to start outside a demonstration
    #: without one.
    jwt_secret: str = "demo-only-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 12 * 60

    # The reasoning engine writes words, never numbers. Every quantity on
    # screen comes from the forecasting and inventory code.
    model_api_key: str = ""
    model_base_url: str = ""
    model_name: str = ""
    model_max_tokens: int = 2048
    model_timeout_seconds: float = 45.0

    #: On serverless hosting with SQLite (temporary storage), build a compact
    #: demonstration company on the first request after a cold start, so the
    #: deployment works with no database and no setup. Set
    #: AUTO_LOAD_DEMO_DATA=false to start empty instead.
    auto_load_demo_data: bool = True

    cors_origins: str = (
        "*" if SERVERLESS else "http://localhost:3002,http://127.0.0.1:3002"
    )

    # ------------------------------------------------------------------
    # What the business owns
    # ------------------------------------------------------------------
    base_currency: str = "TWD"

    #: Cash the buyers may commit in one weekly ordering round.
    weekly_cash_cap_twd: float = 6_000_000.0

    #: What holding stock costs for a year, as a share of its value. Quoted
    #: as a range because nobody knows it to the percentage point, and a
    #: single number here is how tools end up arguing with the finance team.
    carrying_cost_percent_low: float = 10.0
    carrying_cost_percent_high: float = 25.0

    #: How often the buyers place orders, in days. Demand has to be covered
    #: for the lead time plus the wait until the next chance to order.
    review_period_days: int = 7

    #: The chance of not running out during a replenishment cycle. Set per
    #: class below; this is the fallback.
    default_service_level: float = 0.95

    #: Service by how much the part matters. A fastener that stops a line is
    #: not a fastener that sits in a drawer.
    service_level_a: float = 0.98
    service_level_b: float = 0.95
    service_level_c: float = 0.90

    #: A week selling more than this many times the usual is treated as a
    #: project order and kept out of the baseline.
    project_spike_multiple: float = 6.0

    #: A part with no sales for this long is a candidate for writing down.
    dead_stock_days: int = 180

    #: Weeks of cover to build before a supplier's shutdown, on top of the
    #: ordinary reorder point.
    shutdown_prebuild_weeks: int = 2

    #: How long the generated history runs, in weeks.
    history_weeks: int = 104

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return ["*"] if "*" in origins else origins

    @property
    def forecast_engine(self) -> str:
        """Always "built-in" for the numbers. This names the wording engine."""
        has_endpoint = bool(self.model_api_key.strip() and self.model_base_url.strip())
        return "external" if has_endpoint else "built-in"

    @property
    def insecure_defaults(self) -> list[str]:
        """Settings that are fine for a demonstration and unsafe elsewhere."""
        problems: list[str] = []
        if self.jwt_secret == "demo-only-change-me-in-production":
            problems.append("JWT_SECRET is still the published default.")
        return problems

    @property
    def is_serverless(self) -> bool:
        return SERVERLESS

    @property
    def uses_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")

    @property
    def storage_is_temporary(self) -> bool:
        return SERVERLESS and self.uses_sqlite

    def service_level_for(self, abc_class: str) -> float:
        return {
            "A": self.service_level_a,
            "B": self.service_level_b,
            "C": self.service_level_c,
        }.get(abc_class, self.default_service_level)


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
