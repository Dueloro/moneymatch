"""The chess.lichess GameAdapter — the one real adapter in Phase 1."""

from __future__ import annotations

from typing import Optional

from _lib import lichess_service
from _lib.adapters.base import GameAdapter, GameFilters, NormGame
from _lib.schemas import (
    Contract,
    FormatStat,
    SettleResult,
    SkillProfile,
    Speed,
)

_SPEEDS: tuple[Speed, ...] = ("bullet", "blitz", "rapid", "classical")

# Lichess game statuses that mean the game finished with a real result.
_FINISHED = {
    "mate", "resign", "stalemate", "timeout", "draw", "outoftime",
    "cheat", "variantEnd",
}
_DRAW_STATUSES = {"draw", "stalemate"}


def _move_count(moves: Optional[str]) -> int:
    if not moves:
        return 0
    return (len(moves.split()) + 1) // 2


_CLOCK_FOR_SPEED = {"bullet": 60, "blitz": 300, "rapid": 600, "classical": 1800}


class ChessLichessAdapter(GameAdapter):
    id = "chess.lichess"
    brokered = True  # the platform creates the game via a Lichess open challenge

    async def create_match(self, speed: str) -> Optional[dict]:
        """Create an open challenge two players can join (roadmap Phase 1)."""
        return await lichess_service.create_open_challenge(_CLOCK_FOR_SPEED.get(speed, 300))

    async def match_winner(self, game_id: str, players: list[str]) -> Optional[str]:
        """Grade a brokered game once finished, verifying both accounts played it.

        Returns the winner's ``player_id``, ``""`` for a draw, or ``None`` while
        unfinished / if the game wasn't between our two linked accounts.
        """
        g = await lichess_service.get_game(game_id)
        if not g or g.get("status") not in _FINISHED:
            return None
        players_j = g.get("players", {}) or {}
        white = (((players_j.get("white") or {}).get("user")) or {}).get("name")
        black = (((players_j.get("black") or {}).get("user")) or {}).get("name")
        if not white or not black:
            return None  # anonymous player — can't verify
        ids_lower = {p.lower(): p for p in players}
        # Integrity: the game must be between exactly our two matched accounts.
        if white.lower() not in ids_lower or black.lower() not in ids_lower:
            return None
        winner = g.get("winner")  # "white" | "black" | None(draw)
        if winner is None:
            return ""  # draw → refund
        winner_name = white if winner == "white" else black
        return ids_lower.get(winner_name.lower())

    async def link_account(self, method: str, identifier: str) -> SkillProfile:
        # OAuth is the production path; the demo uses the public username path.
        # Both funnel through fetch_profile so the code path is identical.
        profile = await self.fetch_profile(identifier)
        profile.link_method = "oauth" if method == "oauth" else "username"
        return profile

    async def fetch_profile(self, account_id: str) -> SkillProfile:
        raw = await lichess_service.get_user(account_id)
        if raw is None:
            raise ValueError(f"Lichess user '{account_id}' not found")
        return self._to_profile(raw)

    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        perf_types = filters.speeds or ({filters.speed} if filters.speed else None)
        raw_games = await lichess_service.get_user_games(
            account_id, since_ms, perf_types=perf_types
        )
        out: list[NormGame] = []
        for g in raw_games:
            norm = self._normalize(g, account_id)
            if norm is not None:
                out.append(norm)
        # Oldest first so "next game" objectives read naturally.
        out.sort(key=lambda x: x.created_at_ms)
        return out

    def resolve_contract(
        self, contract: Contract, games: list[NormGame], now_ms: int
    ) -> SettleResult:
        """Grade a head-to-head contest against the user's next qualifying game.

        Head-to-head resolves on a single game: if the user wins it they take
        the pot minus rake; a loss or draw goes to the opponent; an expired
        window or no qualifying game refunds both entries (overview §3.3).
        """
        obj = contract.objective
        matched = contract.matched_at or 0
        window_ms = contract.window_hours * 3_600_000
        expired = now_ms > matched + window_ms

        # The user's first qualifying game since the match was made.
        q = [
            g for g in games
            if g.created_at_ms >= matched
            and g.speed == contract.speed
            and g.rated
        ]

        def settled(user_won: bool, ids: list[str]) -> SettleResult:
            return SettleResult(
                id=contract.id, state="SETTLED",
                outcome="won" if user_won else "lost",
                winner="you" if user_won else "opponent",
                qualifying_game_ids=ids, resolved_at=now_ms,
                payout=round(contract.prize if user_won else 0.0, 2),
            )

        def canceled(ids: list[str]) -> SettleResult:
            # Window closed without a qualifying game: refund the user's entry.
            return SettleResult(
                id=contract.id, state="CANCELED", outcome="refunded",
                qualifying_game_ids=ids, resolved_at=now_ms,
                payout=round(contract.entry, 2),
            )

        def active(progress: str) -> SettleResult:
            return SettleResult(
                id=contract.id, state="ACTIVE", progress=progress, payout=0.0,
            )

        if q:
            g = q[0]
            if obj.kind == "win_under_moves":
                user_won = bool(g.won) and g.moves < (obj.moves or 30)
            else:  # win_h2h
                user_won = bool(g.won)
            return settled(user_won, [g.id])

        if expired:
            return canceled([])

        opp = contract.opponent.display_name
        if obj.kind == "win_under_moves":
            return active(f"Beat {opp} in under {obj.moves} moves — awaiting your game")
        return active(f"Awaiting your next {contract.speed} game vs {opp}")

    # ------------------------------------------------------------------
    # Host-specific mapping (kept private to the adapter).
    # ------------------------------------------------------------------

    def _to_profile(self, raw: dict) -> SkillProfile:
        perfs = raw.get("perfs", {}) or {}
        formats: list[FormatStat] = []
        for speed in _SPEEDS:
            p = perfs.get(speed)
            if p and p.get("games", 0) > 0:
                formats.append(
                    FormatStat(
                        speed=speed,
                        rating=int(p.get("rating", 1500)),
                        games=int(p.get("games", 0)),
                        provisional=bool(p.get("prov", False)),
                    )
                )

        count = raw.get("count", {}) or {}
        total = int(count.get("rated", 0)) or int(count.get("all", 0))
        wins = int(count.get("win", 0))
        draws = int(count.get("draw", 0))
        win_rate = (wins + 0.5 * draws) / total if total > 0 else 0.5
        draw_rate = draws / total if total > 0 else 0.12

        primary = max(formats, key=lambda f: f.games).speed if formats else "blitz"

        created = raw.get("createdAt")
        import time as _time
        age_days = (
            int((_time.time() * 1000 - created) / 86_400_000) if created else None
        )

        username = raw.get("username") or raw.get("id", "")
        return SkillProfile(
            username=username,
            display_name=username,
            url=raw.get("url", f"https://lichess.org/@/{username}"),
            link_method="username",
            account_age_days=age_days,
            win_rate=round(win_rate, 4),
            draw_rate=round(draw_rate, 4),
            total_games=total,
            formats=formats,
            primary_speed=primary,
        )

    def _normalize(self, g: dict, account_id: str) -> Optional[NormGame]:
        status = g.get("status")
        if status not in _FINISHED:
            return None
        if g.get("variant", "standard") != "standard":
            return None

        players = g.get("players", {}) or {}
        white_id = (((players.get("white") or {}).get("user") or {}).get("id") or "").lower()
        black_id = (((players.get("black") or {}).get("user") or {}).get("id") or "").lower()
        me = account_id.lower()
        if me == white_id:
            my_color = "white"
        elif me == black_id:
            my_color = "black"
        else:
            return None  # not actually the linked user's game

        winner = g.get("winner")
        drawn = winner is None and status in _DRAW_STATUSES
        won: Optional[bool]
        if winner is None:
            won = False if drawn else None
        else:
            won = winner == my_color

        return NormGame(
            id=g.get("id", ""),
            speed=g.get("speed", "blitz"),
            rated=bool(g.get("rated", False)),
            created_at_ms=int(g.get("createdAt", 0)),
            moves=_move_count(g.get("moves")),
            won=won,
            drawn=drawn,
        )
