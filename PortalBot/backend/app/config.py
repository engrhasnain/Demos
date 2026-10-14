"""Settings."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
DATA_DIR = Path(
    os.getenv("PORTALBOT_DATA_DIR")
    or ("/tmp/portalbot" if SERVERLESS else str(BACKEND_DIR / "var"))
)
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "PortalBot"
    environment: str = "demo"
    database_url: str = f"sqlite:///{(DATA_DIR / 'portalbot.db').as_posix()}"

    jwt_secret: str = "demo-only-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 12 * 60

    cors_origins: str = (
        "*" if SERVERLESS else "http://localhost:3004,http://127.0.0.1:3004"
    )

    carrier_name: str = "Hsinchu Logistics"

    #: How many times a step is retried before it becomes an exception.
    max_attempts: int = 4
    #: The first backoff, doubled each attempt, with jitter.
    backoff_seconds: float = 0.01
    #: How long to poll for a tracking number before giving up on this run.
    #: Giving up is not failing: the booking stands and the next run resumes.
    tracking_timeout_seconds: float = 2.0
    #: How long a clerk has to supply a one-time code.
    challenge_minutes: int = 15

    #: "" (default) follows storage_is_temporary; "true"/"false" overrides it.
    auto_load_demo_data: str = ""
    auto_load_shipment_target: int = 60

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return ["*"] if "*" in origins else origins

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
