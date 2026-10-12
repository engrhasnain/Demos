"""Settings. Everything has a working default so the app starts with no .env file."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

#: True on serverless hosting, where the filesystem is read only apart from
#: /tmp and background threads do not outlive a request.
SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

DATA_DIR = Path(
    os.getenv("LEDGERFLOW_DATA_DIR")
    or ("/tmp/ledgerflow" if SERVERLESS else str(BACKEND_DIR / "var"))
)
try:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
except OSError:  # pragma: no cover - read-only filesystem with no /tmp
    DATA_DIR = Path("/tmp")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "LedgerFlow"
    environment: str = "demo"

    # SQLite by default so a reviewer needs nothing installed.
    database_url: str = f"sqlite:///{(DATA_DIR / 'ledgerflow.db').as_posix()}"

    jwt_secret: str = "demo-only-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 12 * 60

    # The reading engine. Leave the key empty and the built-in one is used.
    #: The reading step runs on the built-in engine unless a key is set here.
    #: The call is a plain chat-completions request, which every hosted model
    #: worth using accepts, so no provider package and no provider is assumed.
    model_api_key: str = ""
    model_base_url: str = ""
    model_name: str = "built-in"
    model_max_tokens: int = 4096
    model_timeout_seconds: float = 45.0

    cors_origins: str = (
        "*" if SERVERLESS else "http://localhost:3001,http://127.0.0.1:3001"
    )

    # --- finance policy a client would own --------------------------------
    base_currency: str = "TWD"
    business_tax_percent: float = 5.0

    #: An invoice may post untouched only when every check passes and it is
    #: below this value. Above it, somebody signs.
    auto_post_ceiling_twd: float = 200_000.0
    #: Above this, two people sign.
    two_step_approval_twd: float = 1_000_000.0
    #: How far an invoice total may sit above the purchase order before it is
    #: held, as a share of the order and as an absolute floor.
    default_tolerance_percent: float = 2.0
    default_tolerance_absolute_twd: float = 500.0
    #: Charges not on the order, such as freight, accepted without review.
    default_unordered_allowance_twd: float = 1_000.0
    #: An invoice older than this many days is treated as a late arrival.
    late_arrival_days: int = 90

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return ["*"] if "*" in origins else origins

    @property
    def reading_engine(self) -> str:
        has_key = bool(self.model_api_key.strip() and self.model_base_url.strip())
        return "external" if has_key else "built-in"

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
        return SERVERLESS and self.uses_sqlite


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
