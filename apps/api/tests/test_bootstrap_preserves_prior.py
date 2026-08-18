"""`bootstrap()` must not destroy a model it has no evidence to replace (1.3).

The reported symptom: link Steam, get pool cards, press "Refresh" on the CS2
account, and the cards vanish with "No pools on this game yet".

The cause: only the Steam OpenID callback calls `cs2_prior.seed()`, which writes
a usable prior at `n = PRIOR_N`. Both `linking_service.bind()` and
`linking_service.refresh()` call `metric_models_service.bootstrap()`, which
recomputes from *stored* matches — of which a freshly-linked CS2 account has
none — and unconditionally wrote `(mu=0, sigma=0, n=0)` over the top. `n = 0`
reads as provisional, and a provisional metric is offered no pools at all.

The same overwrite has a second, worse victim that nobody reported: a player
with fifty matches of real history whose host API happens to be down during a
refresh. `poll_eligible_games` returns nothing, and their entire baseline is
replaced with zeros.

So the rule is not "special-case the prior", it is: **an empty result set is not
evidence, and evidence is the only thing allowed to overwrite a model.**
"""

from __future__ import annotations

import pytest

from moneymatch_api.adapters import registry
from moneymatch_api.adapters.base import NormGame
from moneymatch_api.constants import GAME_CS2_STEAM
from moneymatch_api.services import cs2_prior, metric_models_service
from moneymatch_api.services.cs2_prior import PRIOR_N

from .factories import create_linked_account, create_user, cs2_profile

KD = "cs2_kd_ratio"
STEAM_ID = "76561198000000042"


class _FakeAdapter:
    """Returns a fixed list of finished games, oldest-first."""

    def __init__(self, kd_values: list[float]):
        self._games = [
            NormGame(
                id=str(i),
                speed="premier",
                rated=True,
                created_at_ms=1_700_000_000_000 + i * 1000,
                moves=0,
                won=True,
                drawn=False,
                metrics={KD: v, "cs2_headshot_pct": 45.0, "cs2_kills": 17.0},
            )
            for i, v in enumerate(kd_values)
        ]

    async def poll_eligible_games(self, _host_account_id, _since_ms, _filters):
        return list(self._games)


async def _seeded_user(session, monkeypatch, username: str):
    user = await create_user(session, username=username)
    await create_linked_account(
        session,
        user,
        GAME_CS2_STEAM,
        host_account_id=STEAM_ID,
        profile=cs2_profile("seeded"),
    )

    # No Steam lifetime stats → the documented default-prior path.
    #
    # Via monkeypatch, NOT a bare attribute assignment. Assigning
    # `cs2_prior.steam.get_cs2_lifetime_stats = ...` directly mutates the shared
    # `hosts.steam` module for the rest of the session, and `test_steam_host.py`
    # then exercises the stub instead of the real function — two failures that
    # appear only in a full run and pass in isolation.
    async def _no_stats(_steam_id):
        return None

    monkeypatch.setattr(cs2_prior.steam, "get_cs2_lifetime_stats", _no_stats)
    await cs2_prior.seed(session, user.id, STEAM_ID)
    await session.flush()
    return user


async def _model(session, user, metric: str = KD):
    from sqlalchemy import select

    from moneymatch_api.models.skill import MetricModel

    return await session.scalar(
        select(MetricModel).where(
            MetricModel.user_id == user.id,
            MetricModel.game == GAME_CS2_STEAM,
            MetricModel.metric == metric,
        )
    )


async def test_refresh_with_no_stored_matches_keeps_the_prior(session, monkeypatch):
    """The reported bug: link, refresh, cards disappear."""
    user = await _seeded_user(session, monkeypatch, "prior_keeper")
    before = await _model(session, user)
    assert before.n == PRIOR_N and before.mu > 0

    monkeypatch.setattr(registry, "get", lambda _g: _FakeAdapter([]))
    await metric_models_service.bootstrap(session, user.id, GAME_CS2_STEAM, STEAM_ID)

    after = await _model(session, user)
    assert after.n == PRIOR_N, "an empty history must not overwrite the prior"
    assert after.mu == pytest.approx(before.mu)
    assert after.sigma == pytest.approx(before.sigma)


async def test_bar_stays_quotable_after_refresh(session, monkeypatch):
    """The player-visible consequence: pools are still offered."""
    from moneymatch_api.services import pool_engine

    user = await _seeded_user(session, monkeypatch, "bar_keeper")
    monkeypatch.setattr(registry, "get", lambda _g: _FakeAdapter([]))
    await metric_models_service.bootstrap(session, user.id, GAME_CS2_STEAM, STEAM_ID)

    preview = await pool_engine.preview_bars(session, user, GAME_CS2_STEAM, KD)
    assert preview["provisional"] is False
    assert preview["cards"], "a refreshed account must still be offered pools"


async def test_real_history_dominates_the_prior(session, monkeypatch):
    """Evidence must still win — this is not a rule that freezes the model."""
    user = await _seeded_user(session, monkeypatch, "history_wins")
    values = [1.8] * 40
    monkeypatch.setattr(registry, "get", lambda _g: _FakeAdapter(values))
    await metric_models_service.bootstrap(session, user.id, GAME_CS2_STEAM, STEAM_ID)

    after = await _model(session, user)
    assert after.n == 40, "40 real matches must replace a 3-sample prior"
    assert after.mu == pytest.approx(1.8, abs=0.01)


async def test_a_host_outage_does_not_erase_established_history(session, monkeypatch):
    """The unreported victim: 50 games of history vs a down host API."""
    user = await _seeded_user(session, monkeypatch, "outage_victim")
    monkeypatch.setattr(registry, "get", lambda _g: _FakeAdapter([1.6] * 50))
    await metric_models_service.bootstrap(session, user.id, GAME_CS2_STEAM, STEAM_ID)
    established = await _model(session, user)
    assert established.n == 50

    # Host comes back empty (outage, rate limit, revoked key).
    monkeypatch.setattr(registry, "get", lambda _g: _FakeAdapter([]))
    await metric_models_service.bootstrap(session, user.id, GAME_CS2_STEAM, STEAM_ID)

    after = await _model(session, user)
    assert after.n == 50, "an outage must not wipe a real baseline"
    assert after.mu == pytest.approx(established.mu)


async def test_first_bootstrap_with_no_history_still_creates_a_model(
    session, monkeypatch
):
    """A brand-new account with nothing anywhere still gets a (provisional) row.

    Behaviour preserved: the guard is 'do not destroy', not 'do not create'.
    """
    user = await create_user(session, username="brand_new")
    await create_linked_account(
        session,
        user,
        GAME_CS2_STEAM,
        host_account_id="76561198000000099",
        profile=cs2_profile("new"),
    )
    monkeypatch.setattr(registry, "get", lambda _g: _FakeAdapter([]))
    await metric_models_service.bootstrap(
        session, user.id, GAME_CS2_STEAM, "76561198000000099"
    )

    model = await _model(session, user)
    assert model is not None and model.n == 0
