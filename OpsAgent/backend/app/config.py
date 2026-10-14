"""Settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
DATA_DIR = Path(
    os.getenv("OPSAGENT_DATA_DIR")
    or ("/tmp/opsagent" if SERVERLESS else str(BACKEND_DIR / "var"))
)
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "OpsAgent"
    environment: str = "demo"
    database_url: str = f"sqlite:///{(DATA_DIR / 'opsagent.db').as_posix()}"

    jwt_secret: str = "demo-only-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 12 * 60

    # The model, when one is configured, chooses a capability from the
    # catalogue and writes the sentence around the answer. It never writes
    # SQL, never computes a figure and never sees a row it was not handed.
    model_api_key: str = ""
    model_base_url: str = ""
    model_name: str = ""
    model_max_tokens: int = 1024
    model_timeout_seconds: float = 30.0

    cors_origins: str = (
        "*" if SERVERLESS else "http://localhost:3005,http://127.0.0.1:3005"
    )

    # Fill an empty database with the demonstration data on the first
    # request. Left unset it happens only where storage is temporary
    # (serverless plus SQLite), so a deployment opens with data and nothing
    # to set up. "true" turns it on anywhere, "false" turns it off.
    auto_load_demo_data: str = ""
    auto_load_customer_target: int = 60
    auto_load_order_target: int = 280
    #: How long the first-request seed may spend on the heavier business
    #: data (parts, orders, invoices, …) before it stops and lets the
    #: request through with the demo accounts already in place. Keeps a
    #: cold start under a serverless function's own time limit instead of
    #: being killed mid-seed with nothing usable committed.
    seed_time_budget_seconds: float = 20.0

    #: A question that needs more steps than this is a report, not a
    #: question, and running away with it is how a bill arrives.
    max_steps: int = 6
    #: What one question may cost before it is stopped.
    budget_usd_per_question: float = 0.05
    #: And how long it may take.
    seconds_per_question: float = 60.0

    #: A figure older than this is shown with a warning on it.
    stale_after_seconds: int = 300

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return ["*"] if "*" in origins else origins

    @property
    def answer_engine(self) -> str:
        has_endpoint = bool(self.model_api_key.strip() and self.model_base_url.strip())
        return "external" if has_endpoint else "built-in"

    @property
    def insecure_defaults(self) -> list[str]:
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

    @property
    def should_auto_load_demo_data(self) -> bool:
        value = self.auto_load_demo_data.strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
        if value in {"0", "false", "no", "off"}:
            return False
        return self.storage_is_temporary


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
