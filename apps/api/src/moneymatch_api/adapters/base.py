"""The GameAdapter interface plus the shared, host-agnostic value types.

Ported from `poc-reference/api/_lib/adapters/base.py` (11-migration-map §1), with
`TelemetrySample` moved here (05-phase-2 · deliverable 1). A normalized
`NormGame` is the lowest common denominator every adapter produces, so the
shared metric/settlement logic never sees host-specific JSON.

Phase 2 uses the identity/profile/history surface (`link_account`,
`fetch_profile`, `poll_eligible_games`). Match brokering and result grading are
Phase-3 concerns; the seams are declared here and implemented per-adapter as they
land, so nothing about the Phase-1 PoC `Contract` schema leaks into the port.
"""

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
    moves: int  # full moves played (chess)
    won: bool | None  # True/False for the linked user; None if unknown/draw
    drawn: bool
    metrics: dict[str, float] = field(default_factory=dict)  # rate stats (CS2/Dota)


@dataclass
class GameFilters:
    speed: str | None = None
    rated_only: bool = True
    speeds: set[str] = field(default_factory=set)


@dataclass
class TelemetrySample:
    """Server-fetched per-match telemetry for solo/pool grading (Phase 4).

    Rate metrics only (K/D, ADR, HS%, KDA, GPM); never raw totals or self-report.
    """

    game: str
    metrics: dict[str, float]


class GameAdapter(abc.ABC):
    """Contract every supported title implements."""

    id: str
    # True ⇒ the platform can create the match itself (e.g. a Lichess open
    # challenge). False ⇒ players coordinate on the host and we settle on the
    # shared match found in their histories.
    brokered: bool = False

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

    # --- Phase-3 brokering/settlement seams (implemented per-adapter later) ---

    async def create_match(self, speed: str, users: list[str]) -> dict | None:
        """Broker a game between two players, restricting the seats to ``users``
        (their host handles). Brokered adapters only (Phase 3)."""
        raise NotImplementedError

    async def match_winner(self, game_id: str, players: list[str]) -> str | None:
        """For a brokered game id, return the winning ``player_id`` once finished,
        ``""`` for a draw, or ``None`` while unfinished / unverifiable (Phase 3)."""
        raise NotImplementedError
