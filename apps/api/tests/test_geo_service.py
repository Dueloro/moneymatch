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
