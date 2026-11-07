"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

Env = Literal["local", "dev", "prod"]


class Settings(BaseSettings):
    """Server settings sourced from the environment (and `.env` locally)."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    env: Env = "local"

    database_url: str = Field(..., description="Async SQLAlchemy database URL")

    # Either a shared HS256 secret or an asymmetric JWKS URL.
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_jwt_secret: str | None = Field(
        default=None, description="HS256 JWT secret (Supabase JWT Secret)"
    )
    supabase_jwks_url: str | None = Field(
        default=None, description="JWKS endpoint for RS256/ES256 verification"
    )
    supabase_jwt_audience: str = Field(default="authenticated")

    # CORS — comma-separated browser origins.
    web_origin: str = Field(default="http://localhost:5173")

    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = Field(default="mailto:ops@example.com")

    sentry_dsn: str | None = None
    release: str | None = None

    posthog_api_key: str | None = None
    posthog_host: str = Field(default="https://us.i.posthog.com")

    slow_host_ms: int = Field(default=2_000)

    resend_api_key: str | None = None
    email_from: str = Field(default="Money Match <noreply@send.dueloro.com>")

    payments_live: bool = Field(default=False)
    kyc_live: bool = Field(default=False)

    geo_enforce_seeded_floor: bool = Field(default=True)

    max_request_bytes: int = Field(default=64 * 1024)

    rate_limit_writes_per_minute: int = Field(default=60)

    # When true AND env != prod, a `/dev/e2e/token` route mints a short-lived HS256 JWT
    # for a given auth_id so Playwright can authenticate seeded users headless without a
    # live Supabase project.
    e2e_auth_enabled: bool = Field(default=False)

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, v: str) -> str:
        for scheme in ("postgres://", "postgresql://"):
            if v.startswith(scheme):
                return "postgresql+asyncpg://" + v[len(scheme) :]
        return v

    @model_validator(mode="after")
    def _require_a_verification_method(self) -> Settings:
        if not self.supabase_jwt_secret and not self.resolved_jwks_url:
            raise ValueError(
                "Auth misconfigured: set SUPABASE_JWT_SECRET (HS256) or "
                "SUPABASE_JWKS_URL / SUPABASE_URL (asymmetric)."
            )
        return self

    @model_validator(mode="after")
    def _production_cannot_point_at_localhost(self) -> Settings:
        if self.env != "prod":
            return self
        origin = self.cors_origins[0] if self.cors_origins else ""
        if "localhost" in origin or "127.0.0.1" in origin:
            raise ValueError(
                f"WEB_ORIGIN points at {origin!r} with ENV=prod. Set it to the "
                "deployed web address."
            )
        return self

    @property
    def resolved_jwks_url(self) -> str | None:
        """JWKS URL to use when no HS256 secret is configured."""
        if self.supabase_jwt_secret:
            return None
        if self.supabase_jwks_url:
            return self.supabase_jwks_url
        if self.supabase_url:
            base = self.supabase_url.rstrip("/")
            return f"{base}/auth/v1/.well-known/jwks.json"
        return None

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.web_origin.split(",") if o.strip()]

    @property
    def is_local(self) -> bool:
        return self.env == "local"


@lru_cache
def get_settings() -> Settings:
    return Settings()
