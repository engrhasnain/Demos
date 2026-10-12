"""Settings. Everything has a working default so the app starts with no .env file."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

#: True when running on Vercel, where the filesystem is read only apart from
#: /tmp, background threads do not outlive a request, and anything written to
#: disk is gone by the next invocation.
SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

#: Where generated documents and the SQLite file live.
DATA_DIR = Path(
    os.getenv("QUOTEAGENT_DATA_DIR")
    or ("/tmp/quoteagent" if SERVERLESS else str(BACKEND_DIR / "var"))
)
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:  # pragma: no cover - a read-only filesystem with no /tmp
    DATA_DIR = Path("/tmp")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "QuoteAgent"
    environment: str = "demo"

    # SQLite by default so a reviewer needs nothing installed.
    # PostgreSQL 16:  postgresql+psycopg://user:pass@localhost:5432/quoteagent
    database_url: str = f"sqlite:///{(DATA_DIR / 'quoteagent.db').as_posix()}"

    # Fill an empty database with the demonstration data on the first request.
    # Left unset it happens only where storage is temporary (serverless plus
    # SQLite), so a deployment opens with data and nothing to set up. "true"
    # turns it on anywhere, "false" turns it off.
    auto_load_demo_data: str = ""
    auto_load_product_target: int = 1_000
    auto_load_customer_target: int = 80

    # Sign-in. The demo accounts are created by the data loader. Optional for a
    # demonstration; set JWT_SECRET for anything else.
    jwt_secret: str = "demo-only-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 12 * 60

    # Reasoning engine. Leave the key empty and the built-in engine is used.
    # The call is a plain chat-completions request, which every hosted model
    # worth using accepts, so no provider package and no provider is assumed.
    model_api_key: str = ""
    model_base_url: str = ""
    model_name: str = ""
    model_max_tokens: int = 4096
    model_timeout_seconds: float = 45.0
    #: What the operator pays, in dollars per million tokens. Nobody else can
    #: know this, so it is a setting rather than a table that goes stale.
    model_input_cost_per_million: float = 0.0
    model_output_cost_per_million: float = 0.0
    # Hard ceiling per request so a demo can never run up a bill.
    reasoning_budget_usd_per_case: float = 0.50

    # On Vercel the interface is on a domain that is not known at build time,
    # so the default there is "any origin". Sign-in uses a bearer token rather
    # than a cookie, so no credentials ride along with a cross-site request.
    cors_origins: str = (
        "*" if SERVERLESS else "http://localhost:3000,http://127.0.0.1:3000"
    )

    # Company settings a client would own.
    base_currency: str = "TWD"
    quote_validity_days: int = 14
    foreign_exchange_lock_days: int = 14
    director_approval_threshold_twd: float = 1_500_000.0
    default_margin_floor_percent: float = 18.0

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return ["*"] if "*" in origins else origins

    @property
    def reasoning_engine(self) -> str:
        has_endpoint = bool(self.model_api_key.strip() and self.model_base_url.strip())
        return "external" if has_endpoint else "built-in"

    @property
    def insecure_defaults(self) -> list[str]:
        """Settings that are fine for a demonstration and unsafe anywhere else.

        The sign-in token is signed with this secret. Shipping the published
        default means anybody who has read the source can mint a token for
        any account, including the administrator.
        """
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
        """On Vercel a SQLite file lives in /tmp and does not survive.

        The interface says so rather than letting somebody load the data,
        come back after lunch and find an empty database with no explanation.
        """
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
