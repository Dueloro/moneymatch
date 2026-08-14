"""Demo reset: refund/clear in-flight contests, restore the starting balance,
and keep the ledger reconciled — the fresh-login "start over" for testers."""

from __future__ import annotations

import pytest

from moneymatch_api.models.user import User
from moneymatch_api.models.wallet import SIGNUP_GRANT_CENTS
from moneymatch_api.routers import demo
from moneymatch_api.services import pool_engine, reconciliation_service, wallet_service

from .conftest import new_sessionmaker
from .factories import (
    create_linked_account,
    create_metric_model,
    create_user,
    create_wallet,
    cs2_profile,
)

pytestmark = pytest.mark.asyncio

CS2 = "cs2.steam"
KD = "cs2_kd_ratio"


async def _noop(*_args, **_kwargs) -> None:  # stub the seed re-application
    return None


async def _fund(session, user, cents: int) -> None:
    await wallet_service.demo_deposit(session, user.id, cents, memo="test fund")


def _stub_seed(monkeypatch) -> None:
    monkeypatch.setattr(demo, "_ensure_demo_fixture", _noop)
    monkeypatch.setattr(demo, "_ensure_demo_history", _noop)
    monkeypatch.setattr(demo, "_ensure_demo_social", _noop)


async def test_reset_restores_balance_up_and_down(monkeypatch):
    """Whether the demo is above or below the baseline, reset lands it exactly on
    the starting funded balance, and the books still reconcile."""
    _stub_seed(monkeypatch)
    sm = new_sessionmaker()

    async with sm() as s:
        rich = await create_user(s, username="rich")
        await create_wallet(s, rich, available_cents=0)
        await _fund(s, rich, SIGNUP_GRANT_CENTS + 5_000)  # drifted above baseline
        rich_id = rich.id
        await s.commit()

    async with sm() as s:
        await demo._reset_demo_state(s, await s.get(User, rich_id))
        await s.commit()

    async with sm() as s:
        w = await wallet_service.get_wallet(s, rich_id)
        assert w.available_cents == SIGNUP_GRANT_CENTS
        assert w.escrow_cents == 0
        assert (await reconciliation_service.check_all(s)).ok


async def test_reset_clears_a_waiting_pool_ticket(monkeypatch):
    """A demo user sitting in the pool queue is unstuck by the reset."""
    _stub_seed(monkeypatch)
    sm = new_sessionmaker()

    async with sm() as s:
        user = await create_user(s, username="waiter")
        await create_linked_account(
            s, user, CS2, host_account_id="h", profile=cs2_profile("waiter")
        )
        await create_metric_model(s, user, CS2, KD, mu=1.50, sigma=0.30, n=15)
        await create_wallet(s, user, available_cents=0)
        await _fund(s, user, SIGNUP_GRANT_CENTS)
        # One entrant can't form a room, so this parks a waiting ticket.
        await pool_engine.enqueue(
            s, user, game=CS2, metric=KD, difficulty="medium", entry_cents=1000
        )
        user_id = user.id
        await s.commit()

    async with sm() as s:
        ticket = await pool_engine.get_waiting_ticket(s, user_id)
        assert ticket is not None  # parked before reset

    async with sm() as s:
        await demo._reset_demo_state(s, await s.get(User, user_id))
        await s.commit()

    async with sm() as s:
        assert await pool_engine.get_waiting_ticket(s, user_id) is None
        w = await wallet_service.get_wallet(s, user_id)
        assert w.available_cents == SIGNUP_GRANT_CENTS
        assert (await reconciliation_service.check_all(s)).ok
