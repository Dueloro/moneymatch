"""Application configuration.

All environment access lives here (00-README §3.9). `Settings` fails fast at
import/startup if a required variable is missing, so a misconfigured deploy
never boots into a half-working state.
"""

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

    # Database — async SQLAlchemy URL (postgresql+asyncpg://...).
    database_url: str = Field(..., description="Async SQLAlchemy database URL")

    # Auth (Supabase). Either a shared HS256 secret or an asymmetric JWKS URL.
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

    # Host game APIs (used from Phase 2).
    faceit_api_key: str | None = None

    # Observability.
    sentry_dsn: str | None = None
    # Release tag applied to Sentry events + PostHog captures (git SHA in deploy).
    release: str | None = None

    # Product analytics (PostHog). With no key the server capture seam is a
    # no-op — tests and local runs never touch the network (09-phase-6 · d.3).
    posthog_api_key: str | None = None
    posthog_host: str = Field(default="https://us.i.posthog.com")

    # Warn when a host-API call exceeds this (ops signal — 09-phase-6 · d.4).
    slow_host_ms: int = Field(default=2_000)

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            # Nudge toward the async driver so the engine actually works.
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        return v

    @model_validator(mode="after")
    def _require_a_verification_method(self) -> Settings:
        if not self.supabase_jwt_secret and not self.resolved_jwks_url:
            raise ValueError(
                "Auth misconfigured: set SUPABASE_JWT_SECRET (HS256) or "
                "SUPABASE_JWKS_URL / SUPABASE_URL (asymmetric)."
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
    """Cached settings accessor. Raises at first call if config is invalid."""
    return Settings()
