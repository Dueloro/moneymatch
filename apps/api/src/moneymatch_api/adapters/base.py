"""The GameAdapter interface plus the shared, host-agnostic value types."""

from __future__ import annotations

import abc
from dataclasses import dataclass, field

from ..schemas.profile import ProfileSnapshot


@dataclass
class NormGame:
    """A finished game, normalized to what metric-modelling / settlement needs."""

    id: str
    speed: str
    rated: bool
    created_at_ms: int
    moves: int
    won: bool | None
    drawn: bool
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class GameFilters:
    speed: str | None = None
    rated_only: bool = True
    speeds: set[str] = field(default_factory=set)


@dataclass
class TelemetrySample:
    """Server-fetched per-match telemetry for solo/pool grading."""

    game: str
    metrics: dict[str, float]


@dataclass
class MatchResult:
    """A brokered game's state for grading. ``winner`` is the winning handle, ``""``
    for a draw, or ``None``; ``finished`` with no winner and ``termination ==
    "aborted"`` means the game never really happened (refund).
    """

    finished: bool
    winner: str | None = None
    termination: str | None = None
    ended_at_ms: int | None = None
    live: dict | None = None


class GameAdapter(abc.ABC):
    """Contract every supported title implements."""

    id: str

    @abc.abstractmethod
    async def link_account(self, method: str, identifier: str) -> ProfileSnapshot:
        """Verify a host account exists and return its skill profile."""

    @abc.abstractmethod
    async def fetch_profile(self, account_id: str) -> ProfileSnapshot:
        """Re-fetch the verified profile for an already-linked account."""

    @abc.abstractmethod
    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        """Return the user's finished, eligible games since ``since_ms``."""

    async def create_match(self, speed: str, users: list[str]) -> dict | None:
        """Broker a game between two players, restricting the seats to ``users``
        (their host handles).
        """
        raise NotImplementedError

    async def match_winner(self, game_id: str, players: list[str]) -> str | None:
        """For a brokered game id, return the winning ``player_id`` once finished,
        ``""`` for a draw, or ``None`` while unfinished / unverifiable.
        """
        raise NotImplementedError

    async def match_result(self, game_id: str, players: list[str]) -> MatchResult:
        winner = await self.match_winner(game_id, players)
        return MatchResult(finished=winner is not None, winner=winner)

    async def live_match(self, game_id: str, players: list[str]) -> dict | None:
        return None
