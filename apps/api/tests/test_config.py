"""Config fail-fast behaviour (00-README §3.9)."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from moneymatch_api.config import Settings


def _settings(**env: str) -> Settings:
    # `_env_file=None` isolates the test from any local .env.
    return Settings(_env_file=None, **env)  # type: ignore[call-arg]


def test_missing_database_url_fails(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        _settings(supabase_url="https://x.supabase.co", supabase_jwt_secret="s")


def test_missing_supabase_url_fails(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        _settings(database_url="postgresql+asyncpg://u:p@h/db")


def test_auth_requires_secret_or_jwks():
    with pytest.raises(ValidationError, match="Auth misconfigured"):
        _settings(
            database_url="postgresql+asyncpg://u:p@h/db",
            supabase_url="",
            supabase_jwt_secret="",
        )


def test_async_driver_is_coerced():
    s = _settings(
        database_url="postgresql://u:p@h/db",
        supabase_url="https://x.supabase.co",
        supabase_jwt_secret="s",
    )
    assert s.database_url.startswith("postgresql+asyncpg://")


def test_jwks_url_derived_when_no_secret():
    s = _settings(
        database_url="postgresql+asyncpg://u:p@h/db",
        supabase_url="https://x.supabase.co",
        supabase_jwt_secret="",
    )
    assert s.resolved_jwks_url == (
        "https://x.supabase.co/auth/v1/.well-known/jwks.json"
    )


def test_issuer_derived_from_supabase_url():
    s = _settings(
        database_url="postgresql+asyncpg://u:p@h/db",
        supabase_url="https://x.supabase.co/",
        supabase_jwt_secret="s",
    )
    assert s.resolved_issuer == "https://x.supabase.co/auth/v1"


def test_issuer_override_wins():
    s = _settings(
        database_url="postgresql+asyncpg://u:p@h/db",
        supabase_url="https://x.supabase.co",
        supabase_jwt_secret="s",
        supabase_jwt_issuer="https://custom.example/iss",
    )
    assert s.resolved_issuer == "https://custom.example/iss"


@pytest.mark.parametrize("stakes", [{"env": "prod"}, {"payments_live": "true"}])
def test_demo_login_forbidden_with_real_stakes(stakes):
    with pytest.raises(ValidationError, match="demo_login_enabled must be false"):
        _settings(
            database_url="postgresql+asyncpg://u:p@h/db",
            supabase_url="https://x.supabase.co",
            supabase_jwt_secret="s",
            demo_login_enabled="true",
            **stakes,
        )


def test_demo_login_allowed_off_prod():
    # The intended demo posture — non-prod, play-money — still constructs fine.
    s = _settings(
        database_url="postgresql+asyncpg://u:p@h/db",
        supabase_url="https://x.supabase.co",
        supabase_jwt_secret="s",
        demo_login_enabled="true",
    )
    assert s.demo_login_enabled is True


def test_cors_origins_split():
    s = _settings(
        database_url="postgresql+asyncpg://u:p@h/db",
        supabase_url="https://x.supabase.co",
        supabase_jwt_secret="s",
        web_origin="http://a.com, http://b.com",
    )
    assert s.cors_origins == ["http://a.com", "http://b.com"]
