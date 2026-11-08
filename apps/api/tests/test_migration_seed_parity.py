"""The migration chain and the code-side flag defaults must not drift apart."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from moneymatch_api.services.feature_flags import DEFAULT_FLAGS

pytestmark = pytest.mark.asyncio

SEEDED_WITHOUT_A_CODE_DEFAULT = {"geo_config", "worker_heartbeat"}


async def _seeded_keys(session) -> set[str]:
    rows = await session.execute(text("SELECT key FROM feature_flags"))
    return {r.key for r in rows}


async def test_every_declared_game_flag_has_a_seeded_row(session):
    seeded = await _seeded_keys(session)
    declared_games = {k for k in DEFAULT_FLAGS if k.startswith("game:")}
    missing = declared_games - seeded
    assert not missing, (
        f"declared in DEFAULT_FLAGS but never seeded: {sorted(missing)}. "
        "Seed each in a migration."
    )


async def test_no_seeded_flag_is_unknown_to_the_code(session):
    seeded = await _seeded_keys(session)
    unknown = seeded - set(DEFAULT_FLAGS) - SEEDED_WITHOUT_A_CODE_DEFAULT
    assert not unknown, (
        f"seeded by a migration but unknown to the code: {sorted(unknown)}. Either "
        "add a DEFAULT_FLAGS entry or remove the row in a migration — a flag "
        "nothing reads is a flag nobody maintains."
    )


async def test_geo_config_is_seeded_with_its_payload(session):
    """The row whose absence in tests hid the geo-fence bug for the whole suite."""
    row = await session.execute(
        text("SELECT payload FROM feature_flags WHERE key = 'geo_config'")
    )
    payload = row.scalar_one()
    assert payload and payload.get("excluded_states"), (
        "geo_config must be seeded WITH its state list — an empty payload is "
        "exactly the shape that used to read as 'nobody is excluded'"
    )
    assert len(payload["excluded_states"]) == 14
