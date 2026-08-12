"""`/pools` + `/tournaments` HTTP surface: difficulty-bar previews from the
viewer's own baseline, the enqueue flow, the geo-fence blocking a resident
*before* any ledger write, and that no user-supplied number is ever accepted."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from moneymatch_api.constants import POOL_DIFFICULTY_K
from moneymatch_api.models.user import User
from moneymatch_api.models.wallet import LedgerEntry, Wallet
from moneymatch_api.services import fairness

from .conftest import auth_headers, new_sessionmaker
from .factories import create_linked_account, create_metric_model, cs2_profile

pytestmark = pytest.mark.asyncio

V1 = "/api/v1"
CS2 = "cs2.steam"
KD = "cs2_kd_ratio"


class _FakeAdapter:
    id = CS2
    brokered = False

    async def poll_eligible_games(self, host, since_ms, filters):
        return []


@pytest.fixture(autouse=True)
def _stub_host(monkeypatch):
    from moneymatch_api.adapters import registry

    monkeypatch.setattr(registry, "get", lambda game_id: _FakeAdapter())


async def setup_player(client, auth_id, name, *, mu=1.50, n=15, state="MA"):
    r = await client.get(f"{V1}/me", headers=auth_headers(auth_id))
    assert r.status_code == 200
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == auth_id))
        user.username = name
        user.residence_state = state
        await create_linked_account(
            s, user, CS2, host_account_id=f"host_{name}", profile=cs2_profile(name)
        )
        await create_metric_model(s, user, CS2, KD, mu=mu, sigma=0.30, n=n)
        await s.commit()


async def _set_geo(codes):
    import json

    sm = new_sessionmaker()
    async with sm() as s:
        await s.execute(text("DELETE FROM feature_flags WHERE key = 'geo_config'"))
        await s.execute(
            text(
                "INSERT INTO feature_flags (key, enabled, payload) "
                "VALUES ('geo_config', true, cast(:p as jsonb))"
            ),
            {"p": json.dumps({"excluded_states": list(codes)})},
        )
        await s.commit()


def _hdr(auth_id):
    return auth_headers(auth_id)


# --- pool markets --------------------------------------------------------- #


async def test_pool_markets_quote_bars_from_own_baseline(client):
    await setup_player(client, "auth_pm", "pm", mu=1.50)
    r = await client.get(
        f"{V1}/pools/markets", params={"game": CS2}, headers=_hdr("auth_pm")
    )
    assert r.status_code == 200
    body = r.json()
    assert body["linked"] is True
    kd = next(m for m in body["metrics"] if m["metric"] == KD)
    assert kd["provisional"] is False
    by_diff = {c["difficulty"]: c for c in kd["cards"]}
    # μ + k·σ at the medium tier, derived so a retune moves it too.
    assert by_diff["medium"]["bar"] == fairness.personal_bar(
        1.50, 0.30, POOL_DIFFICULTY_K["medium"], 0.05
    )
    # Estimated multiplier is disclosed as an estimate, never an odds line.
    assert by_diff["medium"]["est_multiplier_bps"] > 0


# --- pool enqueue + geo-fence --------------------------------------------- #


async def test_pool_enqueue_searches_then_room_status(client):
    await setup_player(client, "auth_a", "aa")
    r = await client.post(
        f"{V1}/pools/queue",
        json={
            "game": CS2,
            "metric": KD,
            "difficulty": "medium",
            "entry_preset_cents": 1000,
        },
        headers=_hdr("auth_a"),
    )
    assert r.status_code == 200 and r.json()["status"] == "searching"


async def test_activity_shows_pool_wager_and_live_without_any_match(client):
    """Regression: a user whose only in-flight contest is a pool (no H2H match)
    still sees it in Activity as a current wager — and with its live view."""
    from datetime import UTC, datetime, timedelta

    from moneymatch_api.models.linked_account import LinkedAccount
    from moneymatch_api.models.live import LiveSnapshot
    from moneymatch_api.models.pools import SoloEntry, SoloPool

    await setup_player(client, "auth_ponly", "ponly")
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == "auth_ponly"))
        la = await s.scalar(
            select(LinkedAccount).where(LinkedAccount.user_id == user.id)
        )
        now = datetime.now(UTC)
        pool = SoloPool(
            game=CS2,
            metric=KD,
            difficulty="medium",
            room_bar=1.25,
            entry_cents=1000,
            rake_bps=500,
            room_size=1,
            min_entrants=1,
            state="LOCKED",
            window_starts_at=now - timedelta(minutes=5),
            window_ends_at=now + timedelta(hours=1),
        )
        s.add(pool)
        await s.flush()
        s.add(
            SoloEntry(
                pool_id=pool.id,
                user_id=user.id,
                linked_account_id=la.id,
                host_account_id=la.host_account_id,
                personal_bar=1.25,
                status="LOCKED",
            )
        )
        s.add(
            LiveSnapshot(
                ref_type="pool",
                ref_id=pool.id,
                data={
                    "kind": "pool",
                    "label": "K/D ratio",
                    "target": 1.25,
                    "members": {
                        str(user.id): {
                            "status": "cleared",
                            "current": 1.6,
                            "cleared": True,
                            "matches": 1,
                        }
                    },
                },
            )
        )
        await s.commit()

    r = await client.get(f"{V1}/activity", headers=_hdr("auth_ponly"))
    items = r.json()["items"]
    assert len(items) == 1
    it = items[0]
    assert it["type"] == "pool" and it["state"] == "LOCKED"
    assert it["net_cents"] is None  # in flight → shown as "in play"
    assert it["live"]["status"] == "cleared" and it["live"]["current"] == 1.6


async def test_geo_fence_blocks_before_any_ledger_write(client):
    await _set_geo(["FL"])
    await setup_player(client, "auth_fl", "fl", state="FL")
    # Count ledger rows before the blocked entry.
    sm = new_sessionmaker()
    async with sm() as s:
        user = await s.scalar(select(User).where(User.auth_id == "auth_fl"))
        wallet = await s.scalar(select(Wallet).where(Wallet.user_id == user.id))
        before = await s.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.wallet_id == wallet.id)
        )

    r = await client.post(
        f"{V1}/pools/queue",
        json={
            "game": CS2,
            "metric": KD,
            "difficulty": "medium",
            "entry_preset_cents": 1000,
        },
        headers=_hdr("auth_fl"),
    )
    assert r.status_code == 403 and r.json()["code"] == "region_blocked"

    async with sm() as s:
        after = await s.scalar(
            select(func.count())
            .select_from(LedgerEntry)
            .where(LedgerEntry.wallet_id == wallet.id)
        )
    assert after == before  # no ledger row written on a geo-block


async def test_pool_rejects_non_preset_entry(client):
    await setup_player(client, "auth_np", "np")
    r = await client.post(
        f"{V1}/pools/queue",
        json={
            "game": CS2,
            "metric": KD,
            "difficulty": "medium",
            "entry_preset_cents": 1234,
        },
        headers=_hdr("auth_np"),
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_entry"


async def test_no_endpoint_accepts_a_bar_or_room_bar(client):
    await setup_player(client, "auth_b", "bb")
    # A crafted body with bar/room_bar/payout is ignored — the server derives them.
    r = await client.post(
        f"{V1}/pools/queue",
        json={
            "game": CS2,
            "metric": KD,
            "difficulty": "medium",
            "entry_preset_cents": 1000,
            "personal_bar": 0.1,
            "room_bar": 0.1,
            "payout_cents": 999999,
        },
        headers=_hdr("auth_b"),
    )
    assert r.status_code == 200  # extra fields ignored, not honored


# --- tournament markets + enqueue ----------------------------------------- #


async def test_tournament_markets_and_enqueue(client):
    await setup_player(client, "auth_t", "tt")
    m = await client.get(
        f"{V1}/tournaments/markets", params={"game": CS2}, headers=_hdr("auth_t")
    )
    assert m.status_code == 200
    body = m.json()
    assert body["prize_split"] == [50, 30, 20] and body["field_size"] == 10

    r = await client.post(
        f"{V1}/tournaments/queue",
        json={"game": CS2, "metric": KD, "entry_preset_cents": 1000},
        headers=_hdr("auth_t"),
    )
    assert r.status_code == 200 and r.json()["status"] == "searching"
