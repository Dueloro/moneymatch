"""An adapter that also returns injected matches.

**Scaffolding. Delete with the rest of the demo surface before launch.**

Wraps a real adapter and delegates everything to it, except that
`poll_eligible_games` merges in any simulated matches for the same host account.
Every consumer of match history goes through that one method, so wrapping it
here is what lets a demo settle a wager without a `if simulated` branch in the
settlement worker, the pool engine or the payout path.

`registry.get()` only wraps when `DEMO_SIMULATE_ENABLED` is set. With the flag
off this class is never constructed.
"""

from __future__ import annotations

from ..schemas.profile import ProfileSnapshot
from ..services import demo_simulation
from .base import GameAdapter, GameFilters, NormGame


class SimulatedGamesAdapter(GameAdapter):
    """Delegating wrapper: real host history plus injected matches."""

    def __init__(self, inner: GameAdapter) -> None:
        self._inner = inner
        self.id = inner.id

    # --- the one method that behaves differently ---------------------------- #

    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        real = await self._inner.poll_eligible_games(account_id, since_ms, filters)
        injected = await demo_simulation.games_for(
            self.id, account_id, since_ms, speed=self._speed_hint(real)
        )
        if not injected:
            return real
        # Injected matches are held to the same eligibility rules as real ones,
        # so a simulated result cannot demonstrate a settlement that a real
        # match in the same shape would not have produced.
        keep = [g for g in injected if _passes(g, filters)]
        merged = real + keep
        merged.sort(key=lambda g: g.created_at_ms)
        return merged

    def _speed_hint(self, real: list[NormGame]) -> str:
        """Label injected matches like the host labels real ones.

        Chess filters on speed, so an injected game needs a plausible one; the
        newest real match is the best available guess, and the adapter's own
        default is the fallback.
        """
        if real:
            return real[-1].speed
        return "cs2" if self.id.startswith("cs2") else "blitz"

    # --- everything else is the real adapter -------------------------------- #

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
        """Adapter-specific helpers that are not on the base interface.

        Only reached for names the wrapper and its base class do not define, so
        every interface method above is delegated explicitly rather than by
        accident.
        """
        return getattr(self._inner, name)


def _passes(game: NormGame, filters: GameFilters) -> bool:
    """The same filter checks a real adapter applies to its own history.

    Only the filters this branch's `GameFilters` actually carries. If more are
    added (a minimum-rounds rule for CS2, say), they belong here too, or an
    injected match could demonstrate a settlement a real match of the same shape
    would never have produced.
    """
    if filters.rated_only and not game.rated:
        return False
    if filters.speeds and game.speed not in filters.speeds:
        return False
    return True
