"""The GameAdapter interface plus the shared, host-agnostic value types.

A normalized :class:`NormGame` is the lowest common denominator every adapter
produces, so the (shared) settlement logic never sees host-specific JSON.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Optional

from _lib.schemas import Contract, Objective, SettleResult, SkillProfile


@dataclass
class NormGame:
    """A finished game, normalized to what settlement needs."""

    id: str
    speed: str
    rated: bool
    created_at_ms: int
    moves: int                      # full moves played
    won: Optional[bool]             # True/False for the linked user; None if unknown
    drawn: bool
    metrics: dict[str, float] = field(default_factory=dict)  # per-game telemetry (CS2, etc.)


@dataclass
class GameFilters:
    speed: Optional[str] = None
    rated_only: bool = True
    speeds: set[str] = field(default_factory=set)


class GameAdapter(abc.ABC):
    """Contract every supported title implements."""

    id: str
    # True ⇒ the platform can create the match itself (e.g. a Lichess open
    # challenge). False ⇒ players coordinate the match on the host and we settle
    # on the shared match found in their histories (roadmap Phase 1).
    brokered: bool = False

    async def create_match(self, speed: str) -> Optional[dict]:
        """Broker a game between two players. Returns
        ``{"game_id", "urls": {side: url}}`` or ``None``. Brokered games only."""
        raise NotImplementedError

    async def match_winner(self, game_id: str, players: list[str]) -> Optional[str]:
        """For a brokered game id, return the winning ``player_id`` once finished,
        ``""`` for a draw, or ``None`` while still in progress / unverifiable."""
        raise NotImplementedError

    @abc.abstractmethod
    async def link_account(self, method: str, identifier: str) -> SkillProfile:
        """Verify an account and return its skill profile."""

    @abc.abstractmethod
    async def fetch_profile(self, account_id: str) -> SkillProfile:
        """Re-fetch the verified skill profile for an already-linked account."""

    @abc.abstractmethod
    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        """Return the user's finished, eligible games since ``since_ms``."""

    @abc.abstractmethod
    def resolve_contract(
        self, contract: Contract, games: list[NormGame], now_ms: int
    ) -> SettleResult:
        """Grade a contract against its qualifying games. Pure (no I/O)."""

    # Shared default the catalog/builder can use to label objectives.
    @staticmethod
    def describe(objective: Objective, speed: str) -> str:  # pragma: no cover - trivial
        return objective.kind
