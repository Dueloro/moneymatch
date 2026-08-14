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
    # PUBG — direct to the official PUBG (gamelocker) API. Without it, PUBG
    # lookups fail soft (link "can't right now") rather than crash.
    pubg_api_key: str | None = None
    # PUBG's public limit is ~10 req/min. A process-local token bucket in the PUBG
    # host client throttles to this (keep headroom under 10). Caveat: API and
    # worker are separate processes, each with its own bucket — PUBG traffic is
    # worker-dominated, so a conservative per-process budget stays under the cap.
    pubg_rate_limit_per_min: int = 9

    # Steam Web API (steamcommunity.com/dev/apikey). Used for ban checks at
    # link time and the lifetime-K/D prior. Without it those degrade to a
    # default prior and an unknown ban status rather than failing the link.
    steam_api_key: str | None = None

    # Steam OpenID sign-in. The realm is the site Steam shows the user and must
    # be a prefix of the return URL, or Steam refuses the login outright.
    #
    # Both default to the web origin rather than to localhost. They are not
    # independent facts: the return URL is a page in the web app, so a
    # deployment that sets WEB_ORIGIN (which it must, for CORS) should not also
    # have to restate its own address twice more. Getting that wrong failed
    # silently -- Steam dutifully returned users to localhost and nothing
    # anywhere errored.
    steam_openid_realm: str | None = None
    steam_openid_return_url: str | None = None

    # The Game Coordinator sidecar (phase 2). It can read match data for
    # arbitrary users, so it binds to loopback and is shared-secret protected;
    # it must never face the internet.
    gc_sidecar_url: str = "http://127.0.0.1:8787"
    gc_shared_secret: str | None = None

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
    email_from: str = Field(default="Money Match <noreply@moneymatch.app>")

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

    # Demo escape hatch (IMPLEMENTATION_PROMPT phase 0). Lets an admin inject a
    # finished match and force a contest to settle, so a live demo does not
    # depend on a 40-minute CS2 match completing in front of an audience.
    # Injected results enter at the same seam a real host feed does, so nothing
    # downstream can tell them apart — which is exactly why this must default
    # off and never be set on a real-money deployment.
    demo_simulate_enabled: bool = Field(default=False)
    # Automatic share-code collection (Valve's GetNextMatchSharingCode chain).
    #
    # On by default. It was off while it was new and pasting was the real
    # ingest path; now it is the *only* one, so a flag that has to be switched
    # on for the feature to work at all is not a feature flag, it is a way to
    # ship a deployment that quietly collects nothing. Still switchable, which
    # is worth keeping for pausing collection during a sidecar outage.
    valve_chain_enabled: bool = Field(default=True)

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
    def _production_cannot_point_at_localhost(self) -> Settings:
        """Refuse to boot a production deploy that would send users to localhost.

        This is the failure that taught the lesson: nothing errors. Steam
        accepts the request, returns the user to a host that is not the
        deployment, and the only symptom is that nobody can link an account.
        A refused boot is a failed deploy, which is loud and cheap to fix.
        """
        if self.env != "prod":
            return self
        for name, value in (
            ("WEB_ORIGIN", self.cors_origins[0] if self.cors_origins else ""),
            ("STEAM_OPENID_REALM", self.resolved_steam_openid_realm),
            ("STEAM_OPENID_RETURN_URL", self.resolved_steam_openid_return_url),
        ):
            if "localhost" in value or "127.0.0.1" in value:
                raise ValueError(
                    f"{name} points at {value!r} with ENV=prod. Set WEB_ORIGIN to "
                    "the deployed web address; the Steam OpenID realm and return "
                    "URL follow it unless set explicitly."
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
    def resolved_steam_openid_realm(self) -> str:
        """The realm to send Steam, defaulting to the web origin."""
        return (self.steam_openid_realm or self.cors_origins[0]).rstrip("/")

    @property
    def resolved_steam_openid_return_url(self) -> str:
        """Where Steam returns the user, defaulting to the web app's callback."""
        if self.steam_openid_return_url:
            return self.steam_openid_return_url
        return f"{self.resolved_steam_openid_realm}/auth/steam/callback"

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
