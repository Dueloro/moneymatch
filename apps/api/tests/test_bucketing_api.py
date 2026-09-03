"""Wiring test gate — the `/bucketing` API surface (ASGI, DB-backed).

Proves the app-facing endpoints work end to end: markets reflect placement + cap,
a wager holds a stake and queues, and everything is dark until the flag is on.
"""

from __future__ import annotations

from sqlalchemy import select

from moneymatch_api.adapters.base import NormGame
from moneymatch_api.constants import FLAG_BUCKETING_ENABLED
from moneymatch_api.models.feature_flag import FeatureFlag
from moneymatch_api.models.user import User
from moneymatch_api.services import wallet_service
from moneymatch_api.services.bucketing import reference as rf
from moneymatch_api.services.bucketing import state as state_svc
from tests.conftest import auth_headers
from tests.factories import create_wallet

BASE = "/api/v1/bucketing"


def _norm(id, moves, created):
    return NormGame(
        id=id, speed="blitz", rated=True, created_at_ms=created,
        moves=int(moves), won=True, drawn=False,
        metrics={"chess_moves": float(moves)},
    )


async def _enable(session):
    row = await session.scalar(
        select(FeatureFlag).where(FeatureFlag.key == FLAG_BUCKETING_ENABLED)
    )
    row.enabled = True
    await session.commit()


async def _place_and_fund(session, user, available=100_000):
    ref = rf.build_reference(
        [float(v) for v in range(20, 60)], 3, lower_is_better=True
    )
    await state_svc.activate_reference(
        session, ref, "chess.lichess", "blitz", "chess_moves", version=1
    )
    w = await wallet_service.get_wallet_or_none(session, user.id)
    if w is None:
        await create_wallet(session, user, available_cents=available)
    else:
        await wallet_service.demo_deposit(session, user.id, available)
    # A few varied games: enough to be placed in a bucket, but under the
    # provisional floor (n < 10), so the stake stays capped at the ladder floor —
    # which is what a real, freshly-placed account looks like.
    for i, moves in enumerate([24, 27, 23, 26, 25, 28]):
        await state_svc.record_and_update(
            session,
            user.id,
            "chess.lichess",
            _norm(f"{user.id}-{i}", moves, 1_760_000_000_000 + i),
        )
    await session.commit()


# --------------------------------------------------------------------------- #
# Flag gating
# --------------------------------------------------------------------------- #


async def test_markets_disabled_returns_empty(client):
    r = await client.get(f"{BASE}/markets", headers=auth_headers("bkt-off"))
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["markets"] == []


async def test_wager_rejected_when_disabled(client):
    r = await client.post(
        f"{BASE}/wagers",
        json={"game": "chess.lichess", "mode": "blitz", "metric": "chess_moves",
              "stake_cents": 500},
        headers=auth_headers("bkt-off2"),
    )
    assert r.status_code == 404
    assert r.json()["code"] == "bucketing_not_enabled"


# --------------------------------------------------------------------------- #
# Happy path
# --------------------------------------------------------------------------- #


async def test_markets_then_wager_flow(client, session):
    h = auth_headers("bkt-player")
    # First call provisions the user.
    await client.get(f"{BASE}/markets", headers=h)
    user = await session.scalar(select(User).where(User.auth_id == "bkt-player"))
    assert user is not None

    await _enable(session)
    await _place_and_fund(session, user)

    # Markets now show the player placed with a bar + a stake cap.
    r = await client.get(f"{BASE}/markets", headers=h)
    body = r.json()
    assert body["enabled"] is True
    card = next(
        c for c in body["markets"]
        if c["metric"] == "chess_moves" and c["mode"] == "blitz"
    )
    assert card["placed"] is True
    assert card["bucket"] is not None
    assert card["bar"] is not None
    assert card["stake_cap_cents"] is not None  # provisional → floor cap

    # Place a wager within the cap.
    r = await client.post(
        f"{BASE}/wagers",
        json={"game": "chess.lichess", "mode": "blitz", "metric": "chess_moves",
              "stake_cents": card["stake_cap_cents"]},
        headers=h,
    )
    assert r.status_code == 200, r.text
    status = r.json()
    assert status["status"] == "queued"
    contest_id = status["contest_id"]

    # The stake is held.
    w = await wallet_service.get_wallet(session, user.id)
    await session.refresh(w)
    assert w.escrow_cents == card["stake_cap_cents"]

    # Status endpoint reflects it.
    r = await client.get(f"{BASE}/contests/{contest_id}", headers=h)
    assert r.status_code == 200
    assert r.json()["status"] == "queued"


async def test_wager_over_cap_is_rejected(client, session):
    h = auth_headers("bkt-overcap")
    await client.get(f"{BASE}/markets", headers=h)
    user = await session.scalar(select(User).where(User.auth_id == "bkt-overcap"))
    await _enable(session)
    await _place_and_fund(session, user)
    r = await client.post(
        f"{BASE}/wagers",
        json={"game": "chess.lichess", "mode": "blitz", "metric": "chess_moves",
              "stake_cents": 50_000},  # way over the provisional floor cap
        headers=h,
    )
    assert r.status_code == 422
    assert r.json()["code"] == "stake_over_cap"


async def test_cannot_wager_a_market_you_are_not_placed_in(client, session):
    h = auth_headers("bkt-unplaced")
    await client.get(f"{BASE}/markets", headers=h)
    user = await session.scalar(select(User).where(User.auth_id == "bkt-unplaced"))
    await _enable(session)
    # Fund but do NOT place (no games played).
    w = await wallet_service.get_wallet_or_none(session, user.id)
    if w is None:
        await create_wallet(session, user, available_cents=100_000)
    await session.commit()
    r = await client.post(
        f"{BASE}/wagers",
        json={"game": "chess.lichess", "mode": "blitz", "metric": "chess_moves",
              "stake_cents": 500},
        headers=h,
    )
    assert r.status_code == 409
    assert r.json()["code"] == "not_placed"
