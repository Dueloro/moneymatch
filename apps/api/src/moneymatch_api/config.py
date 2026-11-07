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

    # Web Push (VAPID). Without a keypair, push is disabled (no-op) — the app
    # degrades to in-app notifications only.
    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = Field(default="mailto:ops@example.com")

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

    # Transactional email (Resend). With no key the email seam is a no-op — in-app
    # + push notifications still deliver. Synthetic username addresses
    # (@users.moneymatch.app) have no inbox and are never emailed; only real
    # addresses (e.g. Google sign-in) receive mail.
    resend_api_key: str | None = None
    # RFC 5322 From header for outbound mail; the domain must be verified in
    # Resend (SPF/DKIM) or delivery is rejected.
    email_from: str = Field(default="Money Match <noreply@send.dueloro.com>")

    # Payments/KYC readiness (10-phase-7 §1). These are the *only* switches for
    # real rails, and they are guarded in code: turning either on with no live
    # provider compiled in raises at the resolver, so a config flip alone can
    # never move real money or gate on real KYC. Real integration wires a live
    # provider AND flips the flag — never the flag alone.
    payments_live: bool = Field(default=False)
    kyc_live: bool = Field(default=False)

    # Geo-fence boot strictness. With ENV=prod the API refuses to boot unless the
    # `geo_config` flag lists at least the states in
    # `constants.GEO_REQUIRED_EXCLUDED_STATES`.
    #
    # Behind a setting rather than hard-coded because whether the list may ever
    # be narrowed is a product/legal decision that has not been made yet
    # (OPEN_QUESTIONS.md Q7 — DEFERRED pending the state-by-state opinion).
    # Hard-coding it would settle that question by accident, in code.
    #
    # **The default is the strict one.** Turning this off still does not permit
    # an absent or unreadable fence — that check is unconditional and is not the
    # part being deferred. This only governs whether the deploy must carry the
    # full seeded floor.
    geo_enforce_seeded_floor: bool = Field(default=True)

    # Per-request body size cap in bytes (hardening — 10-phase-7 §2 · input caps).
    max_request_bytes: int = Field(default=64 * 1024)

    # Fixed-window rate limit for write / auth-sensitive endpoints
    # (10-phase-7 §2). Requests per minute, per (user-or-ip, method+path).
    rate_limit_writes_per_minute: int = Field(default=60)

    # Dev/e2e sign-in bypass (backlog · "Browser e2e test-auth seam"). When true
    # AND env != prod, a `/dev/e2e/token` route mints a short-lived HS256 JWT for
    # a given auth_id so Playwright can authenticate seeded users headless without
    # a live Supabase project. Never mounted in prod; default off everywhere else.
    e2e_auth_enabled: bool = Field(default=False)

    @field_validator("database_url")
    @classmethod
    def _require_async_driver(cls, v: str) -> str:
        # Hosts (Render) give postgres:// or postgresql://; the engine needs asyncpg.
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
        """Refuse to boot a prod deploy whose web origin is localhost."""
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
    """Cached settings accessor. Raises at first call if config is invalid."""
    return Settings()
