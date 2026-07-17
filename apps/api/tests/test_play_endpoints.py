"""`/play` + `/activity` HTTP surface: markets, the queue → confirm → active
flow, the waiting list, tamper-resistance (no amounts/timestamps, no settle
endpoint), and the queue kill switch.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select, update

from moneymatch_api.constants import FLAG_QUEUE_PAUSED
from moneymatch_api.models.feature_flag import FeatureFlag
from moneymatch_api.models.user import User

from .conftest import auth_headers, new_sessionmaker
from .factories import create_linked_account, create_metric_model, cs2_profile

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"
CS2 = "cs2.faceit"


async def setup_player(client, auth_id, name, *, mu=1.0, n=15, host=None):
    """Provision a user via the auth path, then link CS2 + seed metric models."""
    r = await client.get(f"{V1}/me", headers=auth_headers(auth_id))
    assert r.status_code == 200
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == auth_id))
        user.username = name
        await create_linked_account(
            s, user, CS2, host_account_id=host, profile=cs2_profile(name)
        )
        for metric in ("cs2_kd_ratio", "cs2_adr", "cs2_headshot_pct"):
            await create_metric_model(s, user, CS2, metric, mu=mu, sigma=0.3, n=n)
        await s.commit()


def _hdr(auth_id):
    return auth_headers(auth_id)


# --- markets -------------------------------------------------------------- #


async def test_markets_lists_cs2_with_derived_multiplier(client):
    await setup_player(client, "auth_m1", "m1")
    r = await client.get(
        f"{V1}/play/markets", params={"game": CS2}, headers=_hdr("auth_m1")
    )
    assert r.status_code == 200
    body = r.json()
    assert body["linked"] is True
    assert body["entry_presets_cents"] == [500, 1000, 2500]
    keys = {m["key"] for m in body["markets"]}
    assert keys == {"kd_ratio", "adr", "headshot_pct", "win_next"}
    kd = next(m for m in body["markets"] if m["key"] == "kd_ratio")
    assert kd["multiplier_bps"] == 18000  # derived ×1.80, never an odds line
    assert kd["provisional"] is False  # seeded n=15


async def test_market_provisional_flag_when_metric_thin(client):
    await setup_player(client, "auth_prov", "prov", n=4)  # below the floor
    r = await client.get(
        f"{V1}/play/markets", params={"game": CS2}, headers=_hdr("auth_prov")
    )
    kd = next(m for m in r.json()["markets"] if m["key"] == "kd_ratio")
    assert kd["provisional"] is True


# --- queue → confirm → active -------------------------------------------- #


async def _queue(client, auth_id, market="kd_ratio", entry=1000):
    return await client.post(
        f"{V1}/play/queue",
        json={"game": CS2, "market": market, "entry_preset_cents": entry},
        headers=_hdr(auth_id),
    )


async def test_full_queue_confirm_activate_flow(client):
    await setup_player(client, "auth_a", "alice")
    await setup_player(client, "auth_b", "bob")

    r1 = await _queue(client, "auth_a")
    assert r1.json()["status"] == "searching"

    r2 = await _queue(client, "auth_b")
    body2 = r2.json()
    assert body2["status"] == "matched"
    match_id = body2["match"]["id"]

    # Alice sees "matched" on her status poll.
    rs = await client.get(f"{V1}/play/queue/status", headers=_hdr("auth_a"))
    assert rs.json()["status"] == "matched"

    # Both confirm → ACTIVE, with an honest forecast on the card.
    rc1 = await client.post(
        f"{V1}/play/matches/{match_id}/confirm", headers=_hdr("auth_a")
    )
    assert rc1.json()["state"] == "PENDING"
    rc2 = await client.post(
        f"{V1}/play/matches/{match_id}/confirm", headers=_hdr("auth_b")
    )
    active = rc2.json()
    assert active["state"] == "ACTIVE"
    assert active["forecast"]["you_win_prob"] > 0
    assert "model gives you" in active["forecast"]["label"]

    # Escrow shows on the wallet ("$X in play").
    rw = await client.get(f"{V1}/wallet", headers=_hdr("auth_a"))
    assert rw.json()["escrow_cents"] == 1000


async def test_waiting_list_and_direct_match(client):
    await setup_player(client, "auth_w1", "w1")
    await setup_player(client, "auth_w2", "w2")
    await _queue(client, "auth_w1")  # w1 waits

    rw = await client.get(f"{V1}/play/waiting", headers=_hdr("auth_w2"))
    waiting = rw.json()["waiting"]
    assert len(waiting) == 1 and waiting[0]["username"] == "w1"
    ticket_id = waiting[0]["ticket_id"]

    rm = await client.post(
        f"{V1}/play/waiting/{ticket_id}/match", headers=_hdr("auth_w2")
    )
    assert rm.status_code == 200
    assert rm.json()["state"] == "PENDING"


async def test_activity_lists_the_match(client):
    await setup_player(client, "auth_ac1", "ac1")
    await setup_player(client, "auth_ac2", "ac2")
    await _queue(client, "auth_ac1")
    await _queue(client, "auth_ac2")

    r = await client.get(f"{V1}/activity", headers=_hdr("auth_ac1"))
    items = r.json()["items"]
    assert len(items) == 1
    assert items[0]["type"] == "match"
    assert items[0]["opponent_username"] == "ac2"
    assert items[0]["net_cents"] is None  # still in flight


# --- tamper-resistance ---------------------------------------------------- #


async def test_queue_rejects_non_preset_entry(client):
    await setup_player(client, "auth_t1", "t1")
    r = await _queue(client, "auth_t1", entry=1234)  # not a preset
    assert r.status_code == 422
    assert r.json()["code"] == "invalid_entry"


async def test_there_is_no_settle_endpoint(client):
    await setup_player(client, "auth_ns", "ns")
    # A client can never post a settlement — only the worker settles.
    r = await client.post(
        f"{V1}/play/matches/00000000-0000-0000-0000-000000000000/settle",
        json={"winner": "me", "amount_cents": 99999},
        headers=_hdr("auth_ns"),
    )
    assert r.status_code in (404, 405)


async def test_queue_paused_kill_switch(client):
    await setup_player(client, "auth_kp", "kp")
    sm = new_sessionmaker()
    async with sm() as s:
        await s.execute(
            update(FeatureFlag)
            .where(FeatureFlag.key == FLAG_QUEUE_PAUSED)
            .values(enabled=True)
        )
        await s.commit()
    r = await _queue(client, "auth_kp")
    assert r.status_code == 503
    assert r.json()["code"] == "queue_paused"
