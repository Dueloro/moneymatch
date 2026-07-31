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
    # Expected `iss` claim. Supabase issues `${SUPABASE_URL}/auth/v1`; override
    # only if your project's issuer differs. Verified on every real token so a
    # validly-signed token from another project/issuer is still rejected.
    supabase_jwt_issuer: str | None = Field(default=None)

    # CORS — comma-separated browser origins.
    web_origin: str = Field(default="http://localhost:5173")

    # Host game APIs (used from Phase 2).
    faceit_api_key: str | None = None
    # PUBG — direct to the official PUBG (gamelocker) API. Without it, PUBG
    # lookups fail soft (link "can't right now") rather than crash.
    pubg_api_key: str | None = None

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

    # Payments/KYC readiness (10-phase-7 §1). These are the *only* switches for
    # real rails, and they are guarded in code: turning either on with no live
    # provider compiled in raises at the resolver, so a config flip alone can
    # never move real money or gate on real KYC. Real integration wires a live
    # provider AND flips the flag — never the flag alone.
    payments_live: bool = Field(default=False)
    kyc_live: bool = Field(default=False)

    # Per-request body size cap in bytes (hardening — 10-phase-7 §2 · input caps).
    max_request_bytes: int = Field(default=64 * 1024)

    # Fixed-window rate limit for write / auth-sensitive endpoints
    # (10-phase-7 §2). Requests per minute, per (user-or-ip, method+path).
    rate_limit_writes_per_minute: int = Field(default=60)

    # Number of trusted reverse-proxy hops in front of the API. When > 0, the
    # rate limiter reads the client IP from `X-Forwarded-For` (the Nth entry from
    # the right, i.e. the address the closest trusted proxy saw) instead of the
    # socket peer — otherwise, behind a load balancer, every client shares the
    # proxy's IP and the "per-client" cap collapses into one global bucket. Only
    # count proxies YOU control; anything beyond is attacker-spoofable. Default 0
    # (direct connections / local). Set to 1 on Render (single edge proxy).
    rate_limit_trusted_proxy_hops: int = Field(default=0, ge=0)

    # Dev/e2e sign-in bypass (backlog · "Browser e2e test-auth seam"). When true
    # AND env != prod, a `/dev/e2e/token` route mints a short-lived HS256 JWT for
    # a given auth_id so Playwright can authenticate seeded users headless without
    # a live Supabase project. Never mounted in prod; default off everywhere else.
    e2e_auth_enabled: bool = Field(default=False)

    # Demo-login bypass. When true, a `/demo/login` route mints a short-lived
    # token for a single shared demo user that `auth.verify_token` accepts
    # alongside real Supabase auth (it uses a separate signing key, so real login
    # keeps working). A complete, email-free sign-in for demos. Play-money only —
    # never enable on a real-money deployment.
    demo_login_enabled: bool = Field(default=False)

    # Run the settlement worker loop *inside* the API process (a background asyncio
    # task started on lifespan startup) instead of as a separate service. This is
    # for hosts with no free/available Background Worker (e.g. Render's free tier):
    # one web service runs both. Safe because the worker claims work with FOR UPDATE
    # SKIP LOCKED and every transition is idempotent, so N in-process copies don't
    # double-settle. Default off — the standalone worker process is the norm.
    run_worker_in_process: bool = Field(default=False)

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

    @model_validator(mode="after")
    def _no_auth_bypass_with_real_stakes(self) -> Settings:
        """Fail fast if a sign-in bypass is armed on a prod / real-money deploy.

        The demo and e2e seams both accept a token signed with a key that is not
        a real secret (demo uses a hardcoded, in-source key; e2e mints with the
        project HS256 secret for arbitrary auth_ids). Either one on a real-money
        deployment is a full authentication bypass, so config alone can never arm
        them there — this refuses to boot rather than half-trusting the flag +
        mount guards in `create_app`.
        """
        real_stakes = self.env == "prod" or self.payments_live
        if real_stakes and self.demo_login_enabled:
            raise ValueError(
                "demo_login_enabled must be false when env=prod or "
                "payments_live=true (it accepts a hardcoded, in-source key)."
            )
        if real_stakes and self.e2e_auth_enabled:
            raise ValueError(
                "e2e_auth_enabled must be false when env=prod or "
                "payments_live=true (it mints tokens for any auth_id)."
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
    def resolved_issuer(self) -> str | None:
        """Expected token issuer: explicit override, else the Supabase default."""
        if self.supabase_jwt_issuer:
            return self.supabase_jwt_issuer
        if self.supabase_url:
            return f"{self.supabase_url.rstrip('/')}/auth/v1"
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
