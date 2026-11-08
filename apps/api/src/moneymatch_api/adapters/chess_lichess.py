"""The chess.lichess GameAdapter."""

from __future__ import annotations

import time

from ..constants import CHESS_CLOCKS
from ..schemas.profile import FormatStat, ProfileSnapshot, Speed
from ..services.hosts import lichess
from .base import GameAdapter, GameFilters, MatchResult, NormGame

_SPEEDS: tuple[Speed, ...] = ("bullet", "blitz", "rapid", "classical")

_FINISHED = {
    "mate",
    "resign",
    "stalemate",
    "timeout",
    "draw",
    "outoftime",
    "cheat",
    "variantEnd",
    "insufficientMaterialClaim",
    "unknownFinish",
}
_ABORTED = {"aborted", "noStart"}
_DRAW_STATUSES = {"draw", "stalemate", "insufficientMaterialClaim"}

# Lichess status -> our stable termination enum.
_TERMINATION = {
    "mate": "checkmate",
    "resign": "resignation",
    "outoftime": "time",
    "draw": "draw",
    "insufficientMaterialClaim": "draw",
    "stalemate": "stalemate",
    "timeout": "abandoned",
    "aborted": "aborted",
    "noStart": "aborted",
}


def termination_of(status: str | None) -> str | None:
    if status in _FINISHED or status in _ABORTED:
        return _TERMINATION.get(status or "", "other")
    return None


def _move_count(moves: str | None) -> int:
    if not moves:
        return 0
    return (len(moves.split()) + 1) // 2


def _clocks(g: dict, plies: int) -> dict | None:
    """Remaining time per side in ms. Lichess `clocks` holds the mover's clock (cs)
    after each ply; before any move, both sides sit on `clock.initial` (s).
    """
    clock = g.get("clock") or {}
    initial = clock.get("initial")
    white = black = initial * 1000 if isinstance(initial, int) else None
    series = [c for c in (g.get("clocks") or [])[:plies] if isinstance(c, int)]
    if series[0::2]:
        white = series[0::2][-1] * 10
    if series[1::2]:
        black = series[1::2][-1] * 10
    if white is None or black is None:
        return None
    return {"white_ms": white, "black_ms": black}


class ChessLichessAdapter(GameAdapter):
    id = "chess.lichess"

    async def link_account(self, method: str, identifier: str) -> ProfileSnapshot:
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
            account_id, since_ms, perf_types=perf_types, rated_only=filters.rated_only
        )
        out: list[NormGame] = []
        for g in raw_games:
            norm = self._normalize(g, account_id)
            if norm is None:
                continue
            if filters.rated_only and not norm.rated:
                continue
            out.append(norm)
        out.sort(key=lambda x: x.created_at_ms)
        return out

    async def create_match(self, speed: str, users: list[str]) -> dict | None:
        limit, increment = CHESS_CLOCKS.get(speed, CHESS_CLOCKS["blitz"])
        return await lichess.create_open_challenge(limit, increment, users=users)

    async def match_winner(self, game_id: str, players: list[str]) -> str | None:
        result = await self.match_result(game_id, players)
        return result.winner if result.finished else None

    async def match_result(self, game_id: str, players: list[str]) -> MatchResult:
        """Grade a brokered game, verifying both accounts played it. One export call
        also carries the live board, so grading doubles as the live refresh.
        """
        live = await self.live_match(game_id, players)
        if live is None or not live["finished"]:
            return MatchResult(finished=False, live=live)
        winner = live["winner"]
        handle: str | None
        if winner in ("white", "black"):
            handle = live[winner]
        elif live["termination"] == "aborted":
            handle = None
        else:
            handle = ""  # draw -> refund
        if handle:
            handle = next((p for p in players if p.lower() == handle.lower()), None)
        return MatchResult(
            finished=True,
            winner=handle,
            termination=live["termination"],
            ended_at_ms=live["last_move_at"],
            live=live,
        )

    async def live_match(self, game_id: str, players: list[str]) -> dict | None:
        """Colour-neutral view: the moves (SAN), clocks, whose turn, and the result
        and termination once finished. Lichess delays ongoing games by 3 moves.
        """
        g = await lichess.get_live_game(game_id)
        if not g:
            return None
        players_j = g.get("players", {}) or {}
        white = (((players_j.get("white") or {}).get("user")) or {}).get("name")
        black = (((players_j.get("black") or {}).get("user")) or {}).get("name")
        if not white or not black:
            return None
        want = {p.lower() for p in players}
        if white.lower() not in want or black.lower() not in want:
            return None
        status = g.get("status")
        finished = status in _FINISHED or status in _ABORTED
        san = (g.get("moves") or "").split()
        plies = len(san)
        winner = g.get("winner") if finished else None
        result = winner
        if finished and winner is None:
            result = None if status in _ABORTED else "draw"
        clock = g.get("clock") or {}
        last_move_at = g.get("lastMoveAt")
        return {
            "status": status,
            "finished": finished,
            "termination": termination_of(status),
            "plies": plies,
            "moves": _move_count(g.get("moves")),
            "san": san,
            "clocks": _clocks(g, plies),
            "clock": (
                {"limit": clock["initial"], "increment": clock.get("increment", 0)}
                if isinstance(clock.get("initial"), int)
                else None
            ),
            "last_move_at": last_move_at if isinstance(last_move_at, int) else None,
            "turn": None if finished else ("white" if plies % 2 == 0 else "black"),
            "winner": result,
            "white": white,
            "black": black,
            "speed": g.get("speed"),
        }

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
            return None

        winner = g.get("winner")
        drawn = winner is None and status in _DRAW_STATUSES
        won: bool | None
        if winner is None:
            won = False if drawn else None
        else:
            won = winner == my_color

        moves = _move_count(g.get("moves"))
        return NormGame(
            id=g.get("id", ""),
            speed=g.get("speed", "blitz"),
            rated=bool(g.get("rated", False)),
            created_at_ms=int(g.get("createdAt", 0)),
            moves=moves,
            won=won,
            drawn=drawn,
            metrics=({"chess_moves": float(moves)} if won and moves > 0 else {}),
        )
