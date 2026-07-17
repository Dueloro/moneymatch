"""Health endpoint: public liveness + registered games + flags."""

from __future__ import annotations

from moneymatch_api.constants import REGISTERED_GAMES


async def test_health_ok(client):
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["env"] == "local"
    assert set(body["games"]) == set(REGISTERED_GAMES)


async def test_health_reports_seeded_flags(client):
    body = (await client.get("/api/v1/health")).json()
    flags = body["flags"]
    assert flags["queue_paused"] is False
    assert flags["settlement_paused"] is False
    for game in REGISTERED_GAMES:
        assert flags[f"game:{game}"] is True


async def test_health_is_public(client):
    # No Authorization header required.
    assert (await client.get("/api/v1/health")).status_code == 200
