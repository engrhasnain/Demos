"""Settings.

Two of these matter more than the rest.

``verification_attempts`` is how many tries somebody gets before the account
is locked to them. Set it high and the front desk becomes a way to guess at
other people's orders.

``office_*`` is what makes a promised reply time honest. Telling a customer
in California at two in the morning Taipei time that somebody will be with
them shortly is a lie, and they find out it was a lie.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent

SERVERLESS = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))

DATA_DIR = Path(
    os.getenv("FRONTDESK_DATA_DIR")
    or ("/tmp/frontdesk" if SERVERLESS else str(BACKEND_DIR / "var"))
)
DATA_DIR.mkdir(parents=True, exist_ok=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "FrontDesk"
    environment: str = "demo"

    database_url: str = f"sqlite:///{(DATA_DIR / 'frontdesk.db').as_posix()}"

    # Fill an empty database with a small demonstration company on the first
    # request. Left unset it happens only where storage is temporary
    # (serverless plus SQLite), so a deployment opens with data and nothing
    # to set up. "true" turns it on anywhere, "false" turns it off.
    auto_load_demo_data: str = ""
    auto_load_customer_target: int = 20
    auto_load_order_target: int = 60

    jwt_secret: str = "demo-only-change-me-in-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 12 * 60

    # The model chooses words and picks an intent. It never reads a row and
    # never invents a date, a price or an appointment.
    model_api_key: str = ""
    model_base_url: str = ""
    model_name: str = ""
    model_max_tokens: int = 1024
    model_timeout_seconds: float = 30.0

    cors_origins: str = (
        "*" if SERVERLESS else "http://localhost:3003,http://127.0.0.1:3003"
    )

    # ------------------------------------------------------------------
    # Identity
    # ------------------------------------------------------------------
    #: Tries before a visitor is locked out of an account they are guessing at.
    verification_attempts: int = 3
    #: How long that lock lasts.
    lockout_minutes: int = 30
    #: How long a verified conversation stays verified.
    session_minutes: int = 120

    # ------------------------------------------------------------------
    # Office hours, in Taipei, which is where the staff are
    # ------------------------------------------------------------------
    office_timezone_offset_hours: int = 8
    office_opens_hour: int = 9
    office_closes_hour: int = 18
    #: Monday is 0. Saturday and Sunday are not working days.
    office_days: str = "0,1,2,3,4"

    #: What a ticket raised inside hours promises, and outside them.
    reply_minutes_in_hours: int = 45
    reply_minutes_out_of_hours: int = 90

    # ------------------------------------------------------------------
    # Returns
    # ------------------------------------------------------------------
    #: Standard warranty on an industrial part, in months from despatch.
    default_warranty_months: int = 12
    #: A trade customer has this long from delivery to report a shortage or
    #: damage in transit. This is a contract term, not the consumer right.
    transit_damage_days: int = 7
    #: How confident the photograph triage has to be before it is offered as
    #: a suggestion rather than left to a person.
    triage_confidence_floor: float = 0.62

    # ------------------------------------------------------------------
    # Technician visits
    # ------------------------------------------------------------------
    visit_minutes: int = 90
    travel_minutes_same_city: int = 30
    travel_minutes_other_city: int = 120
    #: How far ahead slots are offered.
    booking_horizon_days: int = 14

    # ------------------------------------------------------------------
    # LINE
    # ------------------------------------------------------------------
    line_channel_secret: str = ""
    line_channel_access_token: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        origins = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return ["*"] if "*" in origins else origins

    @property
    def working_days(self) -> set[int]:
        return {int(d) for d in self.office_days.split(",") if d.strip().isdigit()}

    @property
    def reply_engine(self) -> str:
        has_endpoint = bool(self.model_api_key.strip() and self.model_base_url.strip())
        return "external" if has_endpoint else "built-in"

    @property
    def line_configured(self) -> bool:
        return bool(self.line_channel_secret.strip())

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
    def storage_warning(self) -> str:
        return "Demonstration data — resets when the server restarts." if self.storage_is_temporary else ""

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
