"""Worker heartbeat → /health + admin reconciliation (09-phase-6 · deliverable 4)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from moneymatch_api.models.user import User
from moneymatch_api.services import feature_flags
from moneymatch_api.workers import settlement_worker

from .conftest import auth_headers, new_sessionmaker

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"


async def test_health_worker_stale_until_cycle(client):
    body = (await client.get(f"{V1}/health")).json()
    # Never ran → no heartbeat → stale.
    assert body["worker"]["heartbeat_at"] is None
    assert body["worker"]["stale"] is True


async def test_cycle_writes_heartbeat_and_health_clears(client):
    sm = new_sessionmaker()
    await settlement_worker.run_cycle(sm, now=datetime.now(UTC))

    async with sm() as s:
        hb = await feature_flags.get_worker_heartbeat(s)
    assert hb is not None

    body = (await client.get(f"{V1}/health")).json()
    assert body["worker"]["heartbeat_at"] is not None
    assert body["worker"]["stale"] is False


async def test_reconciliation_reports_fresh_worker(client):
    await client.get(f"{V1}/me", headers=auth_headers("auth_admin"))
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == "auth_admin"))
        user.username = "admin1"
        user.role = "admin"
        await s.commit()

    await settlement_worker.run_cycle(sm, now=datetime.now(UTC))
    r = await client.get(
        f"{V1}/admin/reconciliation", headers=auth_headers("auth_admin")
    )
    assert r.status_code == 200, r.text
    assert r.json()["worker"]["stale"] is False
