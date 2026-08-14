"""Configuration that used to fail silently now fails loudly, or not at all.

Two settings could be wrong in production with nothing anywhere reporting it.
Steam accepted the sign-in and returned users to localhost; automatic collection
sat switched off and gathered nothing. In both cases every log line was green
and the only symptom was that the product did not work.
"""

from __future__ import annotations

import pytest

from moneymatch_api.config import Settings

pytestmark = pytest.mark.nodb

BASE = {
    "_env_file": None,
    "database_url": "postgresql+asyncpg://u:p@h:5432/x",
    "supabase_url": "https://x.supabase.co",
    "supabase_jwt_secret": "y" * 40,
}


def settings(**overrides) -> Settings:
    return Settings(**{**BASE, **overrides})


# --------------------------------------------------------------------------- #
# The Steam URLs follow the web origin instead of being restated.
# --------------------------------------------------------------------------- #


def test_the_steam_urls_follow_the_web_origin():
    """A deployment states its address once, for CORS, and Steam follows."""
    s = settings(env="prod", web_origin="https://play.example.com")
    assert s.resolved_steam_openid_realm == "https://play.example.com"
    assert (
        s.resolved_steam_openid_return_url
        == "https://play.example.com/auth/steam/callback"
    )


def test_an_explicit_realm_still_wins():
    """Some deployments serve the app and the callback from different hosts."""
    s = settings(
        env="prod",
        web_origin="https://play.example.com",
        steam_openid_realm="https://auth.example.com",
        steam_openid_return_url="https://auth.example.com/steam",
    )
    assert s.resolved_steam_openid_realm == "https://auth.example.com"
    assert s.resolved_steam_openid_return_url == "https://auth.example.com/steam"


def test_the_realm_is_a_prefix_of_the_return_url():
    """Steam refuses the login outright when it is not."""
    s = settings(env="prod", web_origin="https://play.example.com")
    assert s.resolved_steam_openid_return_url.startswith(s.resolved_steam_openid_realm)


def test_local_development_still_points_at_the_dev_server():
    s = settings()
    assert "localhost:5173" in s.resolved_steam_openid_return_url


# --------------------------------------------------------------------------- #
# Production refuses to boot pointing at a developer's laptop.
# --------------------------------------------------------------------------- #


def test_production_refuses_to_start_pointing_at_localhost():
    # A refused boot is a failed deploy: loud, and cheap to fix. Booting
    # happily and returning every user to localhost is neither.
    with pytest.raises(ValueError, match="WEB_ORIGIN"):
        settings(env="prod")


def test_production_refuses_a_loopback_steam_return_url():
    with pytest.raises(ValueError, match="STEAM_OPENID_RETURN_URL"):
        settings(
            env="prod",
            web_origin="https://play.example.com",
            steam_openid_return_url="http://127.0.0.1:5173/auth/steam/callback",
        )


def test_the_other_environments_are_left_alone():
    """The guard is about production, not about forbidding localhost.

    Local development and the dev deployment both legitimately point at a
    laptop, so refusing them would only break the workflow this protects.
    """
    assert settings(env="local").env == "local"
    assert settings(env="dev").env == "dev"


# --------------------------------------------------------------------------- #
# Collection is the only ingest path now, so it is on.
# --------------------------------------------------------------------------- #


def test_automatic_collection_is_on_by_default():
    """The paste box is gone: a deploy that forgets this collects nothing."""
    assert settings().valve_chain_enabled is True


def test_it_can_still_be_switched_off():
    """Worth keeping, to pause collection during a sidecar outage."""
    assert settings(valve_chain_enabled=False).valve_chain_enabled is False
