"""Geo-fence: read from `geo_config`, blocks a resident before any escrow, and
responds to an admin flag change without a deploy.
"""

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
    await geo_service.assert_can_enter(session, "MA")


async def test_missing_state_is_blocked(session):
    await _set_geo(session, ["FL"])
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, None)


async def test_flag_change_takes_effect_without_deploy(session):
    await _set_geo(session, ["FL"])
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, "FL")
    await _set_geo(session, ["AZ"])
    await geo_service.assert_can_enter(session, "FL")


# Fail-closed behaviour.

SEEDED_EXCLUDED = [
    "AZ",
    "AR",
    "CT",
    "DE",
    "FL",
    "IN",
    "LA",
    "MD",
    "MN",
    "MT",
    "SC",
    "SD",
    "TN",
    "WY",
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
    await geo_service.assert_can_enter(session, "MA")


async def test_missing_flag_blocks_everyone(session):
    """No `geo_config` row at all — configuration is absent, so refuse."""
    await _clear_geo(session)
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, "MA")


async def test_empty_exclusion_list_blocks_everyone(session):
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
        '{"excluded_states": "FL"}',
        '{"excluded_states": 42}',
        '{"excluded_states": {"FL": true}}',
        '{"excluded_states": [null]}',
        '{"excluded_states": [""]}',
    ],
)
async def test_malformed_payload_blocks_everyone(session, payload_sql):
    await _set_raw_payload(session, payload_sql)
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, "MA")


async def test_unreadable_config_blocks_everyone(session, monkeypatch):
    from sqlalchemy.exc import SQLAlchemyError

    async def _boom(*_args, **_kwargs):
        raise SQLAlchemyError("geo_config unreadable")

    monkeypatch.setattr(session, "scalar", _boom)
    with pytest.raises(RegionBlockedError):
        await geo_service.assert_can_enter(session, "MA")


async def test_excluded_states_read_view_is_empty_when_unconfigured(session):
    await _clear_geo(session)
    assert await geo_service.excluded_states(session) == set()
    assert await geo_service.load_excluded_states(session) is None


async def test_production_boot_passes_with_the_seeded_fence(session):
    await _set_geo(session, SEEDED_EXCLUDED)
    await geo_service.assert_configured_for_production(session)


async def test_production_boot_passes_with_a_wider_fence(session):
    await _set_geo(session, [*SEEDED_EXCLUDED, "WA", "NV"])
    await geo_service.assert_configured_for_production(session)


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


async def test_floor_check_can_be_disabled_but_defaults_to_strict(session):
    from moneymatch_api.config import Settings

    assert Settings.model_fields["geo_enforce_seeded_floor"].default is True

    await _set_geo(session, ["FL"])
    with pytest.raises(geo_service.GeoFenceMisconfigured):
        await geo_service.assert_configured_for_production(session)
    await geo_service.assert_configured_for_production(session, enforce_floor=False)


async def test_relaxing_the_floor_does_not_permit_an_absent_fence(session):
    await _clear_geo(session)
    with pytest.raises(geo_service.GeoFenceMisconfigured):
        await geo_service.assert_configured_for_production(session, enforce_floor=False)

    await _set_geo(session, [])
    with pytest.raises(geo_service.GeoFenceMisconfigured):
        await geo_service.assert_configured_for_production(session, enforce_floor=False)


async def test_the_required_floor_matches_what_migration_0001_seeds(session):
    from moneymatch_api.constants import GEO_REQUIRED_EXCLUDED_STATES

    assert GEO_REQUIRED_EXCLUDED_STATES == set(SEEDED_EXCLUDED)
    assert len(GEO_REQUIRED_EXCLUDED_STATES) == 14
