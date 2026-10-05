"""History read from our own `game_matches` table instead of the game's API.

For games in `STORED_HISTORY_GAMES` (PUBG), `registry.get()` wraps the host
adapter in this class. Every consumer that asks for match history (duel
grading, skill-model bootstrap and nightly refresh, the sandbagging detector)
then reads rows the background ingester already stored, and makes **no** host
call. Only the ingester talks to the host, and it does so on a budget.

Identity, profile and brokering calls still go to the real adapter.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select

from ..db.session import get_sessionmaker
from ..models.game_match import GameMatch
from ..schemas.profile import ProfileSnapshot
from .base import GameAdapter, GameFilters, NormGame


def norm_from_row(row: GameMatch) -> NormGame:
    """Rebuild the adapter-level view of a stored match."""
    return NormGame(
        id=row.host_match_id,
        speed=row.mode or "",
        rated=row.rated,
        created_at_ms=int(row.started_at.timestamp() * 1000),
        moves=row.moves,
        won=True if row.result == "win" else (False if row.result else None),
        drawn=row.result == "draw",
        metrics={k: float(v) for k, v in (row.metrics or {}).items()},
        ended_at_ms=int(row.ended_at.timestamp() * 1000) if row.ended_at else None,
        eligible=row.eligible,
        detail=dict(row.detail or {}),
    )


class StoredHistoryAdapter(GameAdapter):
    """Serve `poll_eligible_games` from `game_matches`; delegate the rest."""

    def __init__(self, inner: GameAdapter) -> None:
        self._inner = inner
        self.id = inner.id
        self.brokered = inner.brokered
        self.defer_bootstrap = inner.defer_bootstrap

    @property
    def host(self) -> GameAdapter:
        """The real adapter, for the ingester."""
        return self._inner

    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        since = datetime.fromtimestamp(max(since_ms, 0) / 1000, UTC)
        stmt = (
            select(GameMatch)
            .where(
                GameMatch.game == self.id,
                GameMatch.host_account_id == account_id,
                GameMatch.eligible.is_(True),
                GameMatch.started_at >= since,
            )
            .order_by(GameMatch.started_at.asc())
        )
        if filters.rated_only:
            stmt = stmt.where(GameMatch.rated.is_(True))
        async with get_sessionmaker()() as session:
            rows = list(await session.scalars(stmt))
        games = [norm_from_row(r) for r in rows]
        if filters.speeds:
            games = [g for g in games if g.speed in filters.speeds]
        elif filters.speed:
            games = [g for g in games if g.speed == filters.speed]
        return games

    async def fetch_history(self, account_id, since_ms, *, known_ids, first_poll):
        return await self._inner.fetch_history(
            account_id, since_ms, known_ids=known_ids, first_poll=first_poll
        )

    async def link_account(self, method: str, identifier: str) -> ProfileSnapshot:
        return await self._inner.link_account(method, identifier)

    async def fetch_profile(self, account_id: str) -> ProfileSnapshot:
        return await self._inner.fetch_profile(account_id)

    async def create_match(self, speed: str, users: list[str]) -> dict | None:
        return await self._inner.create_match(speed, users)

    async def match_winner(self, game_id: str, players: list[str]) -> str | None:
        return await self._inner.match_winner(game_id, players)

    async def live_match(self, game_id: str, players: list[str]) -> dict | None:
        return await self._inner.live_match(game_id, players)

    def __getattr__(self, name: str):
        return getattr(self._inner, name)
