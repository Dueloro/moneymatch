"""The dota2.opendota GameAdapter — Dota 2 via the public OpenDota API.

The third real adapter (roadmap §5.2 target #2), and the first against a third
provider (after Lichess + FaceIt) — proof the game-agnostic seams generalize.
Identity + skill come from OpenDota and map into the same :class:`SkillProfile`
the app consumes; head-to-head settlement grades the player's next finished
match (win/loss from ``player_slot`` vs ``radiant_win``), mirroring CS2.
"""

from __future__ import annotations

from typing import Optional

from _lib import opendota_service
from _lib.adapters.base import GameAdapter, GameFilters, NormGame
from _lib.schemas import Contract, SettleResult, SkillProfile

_MODE = "dota2"


class Dota2OpenDotaAdapter(GameAdapter):
    id = "dota2.opendota"

    async def link_account(self, method: str, identifier: str) -> SkillProfile:
        profile = await self.fetch_profile(identifier)
        profile.link_method = "oauth" if method == "oauth" else "username"
        return profile

    async def fetch_profile(self, account_id: str) -> SkillProfile:
        ident = account_id.strip()
        # A numeric Steam32 id is used directly; a name is searched, and we try
        # candidates (most-active first) until one has a public profile.
        candidates = [ident] if ident.isdigit() else await opendota_service.search_players(ident)
        resolved: Optional[str] = None
        player: Optional[dict] = None
        for cid in candidates:
            player = await opendota_service.get_player(cid)
            if player is not None:
                resolved = cid
                break
        if player is None or resolved is None:
            raise ValueError(f"Dota 2 player '{account_id}' not found (or profile is private)")
        wl = await opendota_service.get_player_wl(resolved)
        return self._to_profile(resolved, player, wl)

    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        """The player's finished matches since ``since_ms`` (account_id is numeric)."""
        matches = await opendota_service.get_recent_matches(account_id, limit=20)
        out: list[NormGame] = []
        for m in matches:
            norm = self._normalize(m)
            if norm is not None and norm.created_at_ms >= since_ms - 60_000:
                out.append(norm)
        out.sort(key=lambda x: x.created_at_ms)  # oldest first → "next match" reads naturally
        return out

    def resolve_contract(
        self, contract: Contract, games: list[NormGame], now_ms: int
    ) -> SettleResult:
        """Grade a Dota 2 head-to-head against the player's next finished match.

        Win takes the pot minus rake; loss goes to the opponent; an expired
        window with no qualifying match refunds the entry (mirrors CS2/chess).
        """
        matched = contract.matched_at or 0
        window_ms = contract.window_hours * 3_600_000
        expired = now_ms > matched + window_ms

        q = [g for g in games if g.created_at_ms >= matched and g.won is not None]
        if q:
            g = q[0]
            user_won = bool(g.won)
            return SettleResult(
                id=contract.id, state="SETTLED",
                outcome="won" if user_won else "lost",
                winner="you" if user_won else "opponent",
                qualifying_game_ids=[g.id], resolved_at=now_ms,
                payout=round(contract.prize if user_won else 0.0, 2),
            )
        if expired:
            return SettleResult(
                id=contract.id, state="CANCELED", outcome="refunded",
                qualifying_game_ids=[], resolved_at=now_ms,
                payout=round(contract.entry, 2),
            )
        opp = contract.opponent.display_name
        return SettleResult(
            id=contract.id, state="ACTIVE",
            progress=f"Awaiting your next Dota 2 match vs {opp}", payout=0.0,
        )

    # ------------------------------------------------------------------
    # Host-specific mapping (kept private to the adapter).
    # ------------------------------------------------------------------

    def _to_profile(self, account_id: str, player: dict, wl: dict) -> SkillProfile:
        prof = player.get("profile") or {}
        persona = prof.get("personaname") or f"Player {account_id}"
        wins = int(wl.get("win", 0))
        losses = int(wl.get("lose", 0))
        total = wins + losses
        win_rate = wins / total if total else 0.5

        rank_tier = player.get("rank_tier")
        mmr = (player.get("mmr_estimate") or {}).get("estimate")
        rating = int(mmr) if mmr else opendota_service.mmr_from_rank(rank_tier)

        return SkillProfile(
            username=str(account_id),           # numeric id — the settlement poll key
            display_name=persona,
            url=f"https://www.opendota.com/players/{account_id}",
            link_method="username",
            game=self.id,
            win_rate=round(win_rate, 4),
            draw_rate=0.0,
            total_games=total,
            rating=rating,
            rank_label=opendota_service.rank_label(rank_tier),
            avatar_url=prof.get("avatarfull") or None,
        )

    def _normalize(self, m: dict) -> Optional[NormGame]:
        """Win/loss for the linked player from a recent-match row."""
        radiant_win = m.get("radiant_win")
        slot = m.get("player_slot")
        if radiant_win is None or slot is None:
            return None
        is_radiant = slot < 128
        won = is_radiant == bool(radiant_win)
        return NormGame(
            id=str(m.get("match_id", "")),
            speed=_MODE,
            rated=True,
            created_at_ms=int(m.get("start_time", 0)) * 1000,  # OpenDota uses epoch seconds
            moves=0,
            won=won,
            drawn=False,
        )
