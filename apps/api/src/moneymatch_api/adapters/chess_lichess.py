"""The chess.lichess GameAdapter (ported from poc-reference).

Identity + skill from the Lichess public API. Chess is **brokered**: the platform
creates a Lichess open challenge restricted to the two linked accounts, and
Phase-3 settlement grades that specific game id (`match_winner` verifies both of
our accounts actually played it).
"""

from __future__ import annotations

import time

from ..schemas.profile import FormatStat, ProfileSnapshot, Speed
from ..services.hosts import lichess
from .base import GameAdapter, GameFilters, NormGame

_SPEEDS: tuple[Speed, ...] = ("bullet", "blitz", "rapid", "classical")

# Lichess game statuses that mean the game finished with a real result.
_FINISHED = {
    "mate",
    "resign",
    "stalemate",
    "timeout",
    "draw",
    "outoftime",
    "cheat",
    "variantEnd",
}
_DRAW_STATUSES = {"draw", "stalemate"}

_CLOCK_FOR_SPEED = {"bullet": 60, "blitz": 300, "rapid": 600, "classical": 1800}


def _move_count(moves: str | None) -> int:
    if not moves:
        return 0
    return (len(moves.split()) + 1) // 2


class ChessLichessAdapter(GameAdapter):
    id = "chess.lichess"
    brokered = True  # the platform creates the game via a Lichess open challenge

    async def link_account(self, method: str, identifier: str) -> ProfileSnapshot:
        # OAuth is the production path; MVP uses the public username path. Both
        # funnel through fetch_profile so the code path is identical.
        profile = await self.fetch_profile(identifier)
        profile.link_method = "oauth" if method == "oauth" else "username"
        return profile

    async def fetch_profile(self, account_id: str) -> ProfileSnapshot:
        raw = await lichess.get_user(account_id)
        if raw is None:
            raise ValueError(f"Lichess user '{account_id}' not found")
        return self._to_profile(raw)

    async def poll_eligible_games(
        self, account_id: str, since_ms: int, filters: GameFilters
    ) -> list[NormGame]:
        perf_types = filters.speeds or ({filters.speed} if filters.speed else None)
        raw_games = await lichess.get_user_games(
            account_id, since_ms, perf_types=perf_types
        )
        out: list[NormGame] = []
        for g in raw_games:
            norm = self._normalize(g, account_id)
            if norm is not None:
                out.append(norm)
        out.sort(key=lambda x: x.created_at_ms)  # oldest first
        return out

    # --- Phase-3 brokering seams ------------------------------------------- #

    async def create_match(self, speed: str, users: list[str]) -> dict | None:
        # A Lichess **open challenge restricted to the two linked usernames**
        # (users=a,b): both get the same link but only those accounts can occupy
        # the seats, and settlement grades that specific game id (no OAuth needed
        # at MVP — 01-architecture §3.1).
        return await lichess.create_open_challenge(
            _CLOCK_FOR_SPEED.get(speed, 300), users=users
        )

    async def match_winner(self, game_id: str, players: list[str]) -> str | None:
        """Grade a brokered game once finished, verifying both accounts played it.

        Returns the winner's ``player_id``, ``""`` for a draw, or ``None`` while
        unfinished / if the game wasn't between our two linked accounts.
        """
        g = await lichess.get_game(game_id)
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

    # --- Host-specific mapping (private to the adapter) -------------------- #

    def _to_profile(self, raw: dict) -> ProfileSnapshot:
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
        age_days = int((time.time() * 1000 - created) / 86_400_000) if created else None

        username = raw.get("username") or raw.get("id", "")
        return ProfileSnapshot(
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

    def _normalize(self, g: dict, account_id: str) -> NormGame | None:
        status = g.get("status")
        if status not in _FINISHED:
            return None
        if g.get("variant", "standard") != "standard":
            return None

        players = g.get("players", {}) or {}
        white_id = (
            ((players.get("white") or {}).get("user") or {}).get("id") or ""
        ).lower()
        black_id = (
            ((players.get("black") or {}).get("user") or {}).get("id") or ""
        ).lower()
        me = account_id.lower()
        if me == white_id:
            my_color = "white"
        elif me == black_id:
            my_color = "black"
        else:
            return None  # not actually the linked user's game

        winner = g.get("winner")
        drawn = winner is None and status in _DRAW_STATUSES
        won: bool | None
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
