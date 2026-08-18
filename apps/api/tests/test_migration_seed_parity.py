"""The migration chain and the code-side flag defaults must not drift apart.

This is the regression guard for `AUDIT_FINDINGS.md` P0-1. The test schema is
now built by running migrations, so seeded rows exist in tests — but that alone
would not stop `DEFAULT_FLAGS` and the migration chain from disagreeing again,
which is how `game:cs2.steam` came to have no row in production while
`game:cs2.faceit` kept one for a game that no longer exists.

Both directions matter and they fail for different reasons:

- **Seeded but not declared** → the code has no default for a row that exists,
  so nothing in the application knows what the flag means.
- **Declared but not seeded** → there is no row to toggle. The flag still reads
  its default, so nothing looks broken until someone needs the kill switch in an
  incident and finds it was never there.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from moneymatch_api.services.feature_flags import DEFAULT_FLAGS

pytestmark = pytest.mark.asyncio

#: Flags seeded by a migration that deliberately have no `DEFAULT_FLAGS` entry.
#: `geo_config` carries a payload rather than a boolean, and `worker_heartbeat`
#: is written by the worker at runtime — neither is a code-side on/off default.
SEEDED_WITHOUT_A_CODE_DEFAULT = {"geo_config", "worker_heartbeat"}


async def _seeded_keys(session) -> set[str]:
    rows = await session.execute(text("SELECT key FROM feature_flags"))
    return {r.key for r in rows}


async def test_every_declared_game_flag_has_a_seeded_row(session):
    """A kill switch with no row is a kill switch you find missing in an incident."""
    seeded = await _seeded_keys(session)
    declared_games = {k for k in DEFAULT_FLAGS if k.startswith("game:")}
    missing = declared_games - seeded
    assert not missing, (
        f"declared in DEFAULT_FLAGS but never seeded: {sorted(missing)}. "
        "Add a migration seeding each, following 0020/0025."
    )


async def test_no_seeded_flag_is_unknown_to_the_code(session):
    seeded = await _seeded_keys(session)
    unknown = seeded - set(DEFAULT_FLAGS) - SEEDED_WITHOUT_A_CODE_DEFAULT
    assert not unknown, (
        f"seeded by a migration but unknown to the code: {sorted(unknown)}. Either "
        "add a DEFAULT_FLAGS entry or remove the row in a migration — a flag "
        "nothing reads is a flag nobody maintains."
    )


async def test_retired_games_have_no_flag_row(session):
    """`cs2.faceit` was retired in 0024; its row went in 0025."""
    seeded = await _seeded_keys(session)
    assert "game:cs2.faceit" not in seeded
    assert "game:cs2.steam" in seeded


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
