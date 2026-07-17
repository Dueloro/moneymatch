"""`/admin/flags` — list, toggle kill switches, edit geo_config, audit.

The load-bearing property: a flip is read per-request, so it takes effect with no
restart (09-phase-6 · "flag flips take effect without restart"). Each write lands
an `admin_audit` row.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from moneymatch_api.constants import FLAG_GEO_CONFIG, FLAG_SETTLEMENT_PAUSED
from moneymatch_api.models.admin_audit import AdminAudit
from moneymatch_api.models.user import User
from moneymatch_api.services import feature_flags, geo_service

from .conftest import auth_headers, new_sessionmaker

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"


async def _admin(client, auth_id="auth_admin", name="admin1"):
    await client.get(f"{V1}/me", headers=auth_headers(auth_id))
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == auth_id))
        user.username = name
        user.role = "admin"
        await s.commit()
        return user.id


async def test_list_flags_returns_seeded(client):
    await _admin(client)
    r = await client.get(f"{V1}/admin/flags", headers=auth_headers("auth_admin"))
    assert r.status_code == 200, r.text
    keys = {f["key"] for f in r.json()["flags"]}
    assert FLAG_SETTLEMENT_PAUSED in keys
    assert any(k.startswith("game:") for k in keys)


async def test_toggle_takes_effect_without_restart(client):
    await _admin(client)
    r = await client.put(
        f"{V1}/admin/flags/{FLAG_SETTLEMENT_PAUSED}",
        headers=auth_headers("auth_admin"),
        json={"enabled": True},
    )
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True

    # A fresh session reads the new value immediately (no process restart).
    sm = new_sessionmaker()
    async with sm() as s:
        flags = await feature_flags.get_boolean_flags(s)
    assert flags[FLAG_SETTLEMENT_PAUSED] is True


async def test_edit_geo_config_payload(client):
    await _admin(client)
    r = await client.put(
        f"{V1}/admin/flags/{FLAG_GEO_CONFIG}",
        headers=auth_headers("auth_admin"),
        json={"payload": {"excluded_states": ["WA", "id"]}},
    )
    assert r.status_code == 200, r.text
    sm = new_sessionmaker()
    async with sm() as s:
        states = await geo_service.excluded_states(s)
    assert states == {"WA", "ID"}


async def test_empty_update_rejected(client):
    await _admin(client)
    r = await client.put(
        f"{V1}/admin/flags/{FLAG_SETTLEMENT_PAUSED}",
        headers=auth_headers("auth_admin"),
        json={},
    )
    assert r.status_code == 422


async def test_flag_write_is_audited(client):
    await _admin(client)
    await client.put(
        f"{V1}/admin/flags/{FLAG_SETTLEMENT_PAUSED}",
        headers=auth_headers("auth_admin"),
        json={"enabled": True},
    )
    sm = new_sessionmaker()
    async with sm() as s:
        count = await s.scalar(
            select(func.count())
            .select_from(AdminAudit)
            .where(AdminAudit.action == "flag.update")
        )
    assert count == 1
