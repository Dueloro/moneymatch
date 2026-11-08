"""Production refuses to boot with a web origin pointing at localhost."""

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


def test_production_refuses_to_start_pointing_at_localhost():
    with pytest.raises(ValueError, match="WEB_ORIGIN"):
        settings(env="prod")


def test_the_other_environments_are_left_alone():
    assert settings(env="local").env == "local"
    assert settings(env="dev").env == "dev"
