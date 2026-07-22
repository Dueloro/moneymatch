"""The worker's nightly pass + its self-throttling cadence (backlog · Phase B)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import NormGame
from moneymatch_api.models.risk import RiskFlag
from moneymatch_api.models.skill import MetricModel
from moneymatch_api.workers import settlement_worker
from moneymatch_api.workers.nightly import run_nightly

from .conftest import new_sessionmaker
from .factories import create_linked_account, create_user, cs2_profile

pytestmark = pytest.mark.asyncio

CS2 = "cs2.faceit"
KD = "cs2_kd_ratio"


class _FakeAdapter:
    def __init__(self, values_oldest_first):
        self._games = [
            NormGame(
                id=str(i),
                speed="cs2",
                rated=True,
                created_at_ms=i,
                moves=0,
                won=None,
                drawn=False,
                metrics={KD: v},
            )
            for i, v in enumerate(values_oldest_first)
        ]

    async def poll_eligible_games(self, host, since_ms, filters):
        return self._games


async def test_run_nightly_refreshes_models_and_flags_sandbagger(session, monkeypatch):
    user = await create_user(session, username="tank")
    await create_linked_account(
        session, user, CS2, host_account_id="host_tank", profile=cs2_profile("tank")
    )
    await session.commit()  # visible to run_nightly's own sessions

    baseline = [1.5, 1.4, 1.6, 1.5, 1.5, 1.4, 1.6]
    recent_tanked = [0.6] * 10
    history = baseline + recent_tanked
    monkeypatch.setattr(registry, "get", lambda g: _FakeAdapter(history))

    report = await run_nightly(new_sessionmaker())

    assert report.accounts_refreshed == 1
    assert report.sandbag_flags == 1
    assert report.errors == 0

    model = await session.scalar(
        select(MetricModel).where(
            MetricModel.user_id == user.id, MetricModel.metric == KD
        )
    )
    assert model is not None and model.n == len(baseline) + len(recent_tanked)
    flag = await session.scalar(
        select(RiskFlag).where(
            RiskFlag.user_id == user.id, RiskFlag.kind == "sandbagging"
        )
    )
    assert flag is not None


async def test_maybe_run_nightly_runs_once_then_throttles(monkeypatch):
    calls: list[object] = []

    async def _fake_nightly(sm, *, now=None):
        from moneymatch_api.workers.nightly import NightlyReport

        calls.append(now)
        return NightlyReport()

    monkeypatch.setattr("moneymatch_api.workers.nightly.run_nightly", _fake_nightly)
    sm = new_sessionmaker()

    assert await settlement_worker.maybe_run_nightly(sm) is True  # never run → due
    assert await settlement_worker.maybe_run_nightly(sm) is False  # throttled
    assert len(calls) == 1
