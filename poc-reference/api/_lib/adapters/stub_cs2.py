"""Throwaway second adapter (Counter-Strike 2 / Steam).

This exists only to prove the GameAdapter seams are real — a second game
compiles against the same interface without touching the contract, odds, or
settlement layers (roadmap §1.6 success criteria). It is NOT registered for use
and raises if actually called.
"""

from __future__ import annotations

from _lib.adapters.base import GameAdapter, GameFilters, NormGame
from _lib.schemas import Contract, SettleResult, SkillProfile


class CS2SteamAdapter(GameAdapter):
    id = "cs2.steam"

    async def link_account(self, method: str, identifier: str) -> SkillProfile:
        raise NotImplementedError("cs2.steam adapter is a Phase 3+ stub")

    async def fetch_profile(self, account_id: str) -> SkillProfile:
        raise NotImplementedError("cs2.steam adapter is a Phase 3+ stub")

    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        raise NotImplementedError("cs2.steam adapter is a Phase 3+ stub")

    def resolve_contract(
        self, contract: Contract, games: list[NormGame], now_ms: int
    ) -> SettleResult:
        raise NotImplementedError("cs2.steam adapter is a Phase 3+ stub")
