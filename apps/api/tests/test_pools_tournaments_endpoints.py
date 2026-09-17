"""`/tournaments` HTTP surface: the market preview, the enqueue flow, the
geo-fence blocking a resident *before* any ledger write, and that no user-supplied
number is ever accepted."""

from __future__ import annotations

import pytest
from sqlalchemy import func, select, text

from moneymatch_api.models.user import User
from moneymatch_api.models.wallet import LedgerEntry, Wallet

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


# --- geo-fence ------------------------------------------------------------- #


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
        f"{V1}/tournaments/queue",
        json={"game": CS2, "metric": KD, "entry_preset_cents": 1000},
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


async def test_tournament_rejects_non_preset_entry(client):
    await setup_player(client, "auth_np", "np")
    r = await client.post(
        f"{V1}/tournaments/queue",
        json={"game": CS2, "metric": KD, "entry_preset_cents": 1234},
        headers=_hdr("auth_np"),
    )
    assert r.status_code == 422 and r.json()["code"] == "invalid_entry"


# --- tournament markets + enqueue ----------------------------------------- #


@pytest.fixture
def simulation_on(monkeypatch):
    from moneymatch_api.config import get_settings

    monkeypatch.setenv("DEMO_SIMULATE_ENABLED", "1")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def test_join_spins_up_a_self_driving_tournament(client, simulation_on):
    """In a sim build, joining a tournament forms a self-driving one right away:
    you plus competitive bots, 60/25/15. Joining again returns the same one
    (idempotent — no second field, no double escrow)."""
    await setup_player(client, "auth_sim", "simmer")

    r = await client.post(
        f"{V1}/tournaments/queue",
        json={"game": CS2, "metric": KD, "entry_preset_cents": 1000},
        headers=_hdr("auth_sim"),
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "formed"
    tour = body["tournament"]
    assert tour["field_size"] == 6  # you + 5 bots
    assert tour["prize_split"] == [60, 25, 15]
    first_id = tour["id"]

    # Joining again while it's live returns the same tournament, not a new field.
    r2 = await client.post(
        f"{V1}/tournaments/queue",
        json={"game": CS2, "metric": KD, "entry_preset_cents": 1000},
        headers=_hdr("auth_sim"),
    )
    assert r2.json()["tournament"]["id"] == first_id


async def test_tournament_markets_and_enqueue(client):
    await setup_player(client, "auth_t", "tt")
    m = await client.get(
        f"{V1}/tournaments/markets", params={"game": CS2}, headers=_hdr("auth_t")
    )
    assert m.status_code == 200
    body = m.json()
    assert body["prize_split"] == [60, 25, 15] and body["field_size"] == 10

    r = await client.post(
        f"{V1}/tournaments/queue",
        json={"game": CS2, "metric": KD, "entry_preset_cents": 1000},
        headers=_hdr("auth_t"),
    )
    assert r.status_code == 200 and r.json()["status"] == "searching"
