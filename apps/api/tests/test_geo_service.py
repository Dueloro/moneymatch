"""Geo-fence: read from `geo_config`, blocks a resident before any escrow, and
responds to an admin flag change without a deploy."""

from __future__ import annotations

import pytest
from sqlalchemy import text

from moneymatch_api.services import geo_service
from moneymatch_api.services.geo_service import RegionBlockedError

pytestmark = pytest.mark.asyncio


async def _set_geo(session, codes):
    await session.execute(text("DELETE FROM feature_flags WHERE key = 'geo_config'"))
    await session.execute(
        text(
            "INSERT INTO feature_flags (key, enabled, payload) "
            "VALUES ('geo_config', true, cast(:p as jsonb))"
        ),
        {"p": f'{{"excluded_states": {list(codes)!r}}}'.replace("'", '"')},
    )
    await session.flush()


async def test_excluded_state_is_blocked(session):
    await _set_geo(session, ["FL", "AZ"])
    with pytest.raises(RegionBlockedError) as exc:
        await geo_service.assert_can_enter(session, "FL")
    assert exc.value.status_code == 403


async def test_allowed_state_passes(session):
    await _set_geo(session, ["FL", "AZ"])
    await geo_service.assert_can_enter(session, "MA")  # no raise


async def test_missing_state_is_blocked(session):
    await _set_geo(session, ["FL"])
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, None)


async def test_flag_change_takes_effect_without_deploy(session):
    await _set_geo(session, ["FL"])
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, "FL")
    # Admin removes FL from the excluded list → allowed on the very next check.
    await _set_geo(session, ["AZ"])
    await geo_service.assert_can_enter(session, "FL")  # no raise


# --------------------------------------------------------------------------- #
# Fail-closed behaviour (Phase 1.1).
#
# The geo-fence used to fail **open**: a missing flag, an empty list, a
# malformed payload or an unreadable database each returned an empty set, and
# an empty set excludes nobody. On a fresh database every state was allowed,
# while the module docstring and an inline comment both claimed it failed
# closed.
#
# "Configuration missing" is not "no exclusions". It is "we do not know whether
# this player is allowed to stake", and the only safe answer to that is no.
# --------------------------------------------------------------------------- #

#: The 14 "Any Chance" states seeded by migration 0001.
SEEDED_EXCLUDED = [
    "AZ", "AR", "CT", "DE", "FL", "IN", "LA",
    "MD", "MN", "MT", "SC", "SD", "TN", "WY",
]


async def _clear_geo(session):
    await session.execute(text("DELETE FROM feature_flags WHERE key = 'geo_config'"))
    await session.flush()


async def _set_raw_payload(session, payload_sql: str):
    await _clear_geo(session)
    await session.execute(
        text(
            "INSERT INTO feature_flags (key, enabled, payload) "
            "VALUES ('geo_config', true, cast(:p as jsonb))"
        ),
        {"p": payload_sql},
    )
    await session.flush()


@pytest.mark.parametrize("state", SEEDED_EXCLUDED)
async def test_each_seeded_state_is_blocked(session, state):
    await _set_geo(session, SEEDED_EXCLUDED)
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, state)


async def test_permitted_state_still_passes_with_full_list(session):
    await _set_geo(session, SEEDED_EXCLUDED)
    await geo_service.assert_can_enter(session, "MA")  # no raise


async def test_missing_flag_blocks_everyone(session):
    """No `geo_config` row at all — configuration is absent, so refuse."""
    await _clear_geo(session)
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, "MA")


async def test_empty_exclusion_list_blocks_everyone(session):
    """An empty list is not 'nowhere is excluded', it is 'unconfigured'."""
    await _set_geo(session, [])
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, "MA")


async def test_payload_without_the_key_blocks_everyone(session):
    await _set_raw_payload(session, '{"something_else": true}')
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, "MA")


async def test_null_payload_blocks_everyone(session):
    await _set_raw_payload(session, "null")
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, "MA")


@pytest.mark.parametrize(
    "payload_sql",
    [
        '{"excluded_states": "FL"}',  # string, not a list
        '{"excluded_states": 42}',  # number
        '{"excluded_states": {"FL": true}}',  # object
        '{"excluded_states": [null]}',  # list of junk
        '{"excluded_states": [""]}',  # list of empty strings
    ],
)
async def test_malformed_payload_blocks_everyone(session, payload_sql):
    await _set_raw_payload(session, payload_sql)
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, "MA")


async def test_unreadable_config_blocks_everyone(session, monkeypatch):
    """A database error must not be silently treated as 'nobody is excluded'."""
    from sqlalchemy.exc import SQLAlchemyError

    async def _boom(*_args, **_kwargs):
        raise SQLAlchemyError("geo_config unreadable")

    monkeypatch.setattr(session, "scalar", _boom)
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, "MA")


async def test_excluded_states_read_view_is_empty_when_unconfigured(session):
    """The admin read view collapses "unconfigured" to an empty set...

    ...which is exactly why it must never be used to gate a stake. This test
    documents that boundary so nobody re-introduces the old bug by reaching for
    the convenient function.
    """
    await _clear_geo(session)
    assert await geo_service.excluded_states(session) == set()
    assert await geo_service.load_excluded_states(session) is None


# --------------------------------------------------------------------------- #
# Production boot check (Phase 1.1).
# --------------------------------------------------------------------------- #


async def test_production_boot_passes_with_the_seeded_fence(session):
    await _set_geo(session, SEEDED_EXCLUDED)
    await geo_service.assert_configured_for_production(session)  # no raise


async def test_production_boot_passes_with_a_wider_fence(session):
    """An admin may widen the fence without a deploy; that must still boot."""
    await _set_geo(session, [*SEEDED_EXCLUDED, "WA", "NV"])
    await geo_service.assert_configured_for_production(session)  # no raise


@pytest.mark.parametrize("dropped", ["FL", "WY", "AZ"])
async def test_production_boot_refuses_a_narrowed_fence(session, dropped):
    remaining = [s for s in SEEDED_EXCLUDED if s != dropped]
    await _set_geo(session, remaining)
    with pytest.raises(geo_service.GeoFenceMisconfigured) as exc:
        await geo_service.assert_configured_for_production(session)
    assert dropped in str(exc.value)


async def test_production_boot_refuses_a_missing_fence(session):
    await _clear_geo(session)
    with pytest.raises(geo_service.GeoFenceMisconfigured):
        await geo_service.assert_configured_for_production(session)


async def test_production_boot_refuses_an_empty_fence(session):
    await _set_geo(session, [])
    with pytest.raises(geo_service.GeoFenceMisconfigured):
        await geo_service.assert_configured_for_production(session)


async def test_the_required_floor_matches_what_migration_0001_seeds(session):
    """The constant and the migration must not drift apart."""
    from moneymatch_api.constants import GEO_REQUIRED_EXCLUDED_STATES

    assert GEO_REQUIRED_EXCLUDED_STATES == set(SEEDED_EXCLUDED)
    assert len(GEO_REQUIRED_EXCLUDED_STATES) == 14
